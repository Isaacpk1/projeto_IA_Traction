"""Matriz do experimento — doc 07 §3.1 (E1) e §E2. Planejamento puro, sem I/O.

Separado da CLI de propósito. A matriz é a declaração formal do desenho
experimental e precisa ser verificável por teste sem tocar em fila, API ou
LLM: se `plan_core` devolve 594 tarefas com a distribuição declarada, o
desenho está correto independentemente de o experimento ter rodado.

O `task_id` é determinístico (doc 09 §4.4), então replanejar uma rodada é
idempotente — reenfileirar depois de uma queda não duplica trabalho nem
reexecuta o que já concluiu.
"""

from __future__ import annotations

from src.core.contracts.golden import GoldenCase
from src.core.contracts.task import EXPERIMENT_PRIORITY, Task
from src.core.contracts.trace import Architecture
from src.core.errors import ContractError
from src.core.ids import task_id

__all__ = [
    "E1_SEEDS",
    "E1_REPETITIONS",
    "E1_ARCHITECTURES",
    "E2_POLICIES",
    "E2_REPETITIONS",
    "E2_ARCHITECTURE",
    "ARM_BY_ARCHITECTURE",
    "plan_e1",
    "plan_e2",
    "plan_core",
]

#: Uma âncora sem degradação e sete níveis distintos — doc 07 §3.1. Os seeds são
#: níveis de uma variável de degradação, não repetições disfarçadas.
#:
#: **Estes sete não são arbitrários.** O documento exige, como pré-requisito de
#: validação, medir a intensidade de cada seed candidato sobre o conjunto fixo de
#: recursos do golden e escolher os que **cobrem o espectro**. Uma primeira versão
#: usava `s1..s7` por conveniência; medidos, ficavam todos entre 0,296 e 0,372 —
#: faixa de 0,08, o que colapsaria a dose-resposta num contraste binário entre
#: `complete` e o resto, justamente o que o desenho existe para superar.
#:
#: Os valores abaixo são a intensidade média medida contra a API industrial
#: (`agentes intensity`), e cobrem de 0,13 a 0,52 — cinco vezes mais amplitude:
#:
#:   complete 0,129 · seed1 0,233 · s9 0,270 · s10 0,318
#:   zz 0,388 · x1 0,428 · x2 0,465 · s13 0,522
#:
#: As strings são só entrada de hash da API; o que importa é a intensidade que
#: cada uma produz. Trocar esta tupla obriga a recomputar `degradation_intensity.json`.
E1_SEEDS: tuple[str, ...] = ("complete", "seed1", "s9", "s10", "zz", "x1", "x2", "s13")

E1_REPETITIONS = 2
E1_ARCHITECTURES: tuple[Architecture, ...] = ("mono", "multi")

#: H1 contrasta arquitetura; o rótulo do braço é derivado dela, nunca escolhido à mão.
ARM_BY_ARCHITECTURE: dict[Architecture, str] = {"mono": "A", "multi": "B"}

#: E2 mantém arquitetura, modelo, prompt, tools e casos fixos — só a política muda.
E2_POLICIES: tuple[str, ...] = ("prompt_only", "pre_action_guard")
E2_REPETITIONS = 5
E2_ARCHITECTURE: Architecture = "mono"


def plan_e1(cases: tuple[GoldenCase, ...] | list[GoldenCase], *, run_id: str) -> list[Task]:
    """E1 — H1: mono (braço A) vs multi (braço B).

    `17 casos × 2 arquiteturas × 8 seeds × 2 repetições = 544 execuções`.

    A ordem de emissão agrupa A e B da mesma tupla (caso, seed, repetição). Uma
    rodada interrompida no meio deixa dados **pareados**, não 300 execuções de A
    e nenhuma de B — o que preserva a comparação central mesmo sem a cota inteira.
    """
    if not cases:
        raise ContractError("E1 exige ao menos um caso base")
    tasks: list[Task] = []
    for repetition in range(E1_REPETITIONS):
        for seed in E1_SEEDS:
            for case in cases:
                for architecture in E1_ARCHITECTURES:
                    arm = ARM_BY_ARCHITECTURE[architecture]
                    tasks.append(
                        Task(
                            task_id=task_id(
                                run_id, case.case_id, architecture, seed, repetition, arm=arm
                            ),
                            kind="experiment",
                            case_id=case.case_id,
                            architecture=architecture,
                            priority=EXPERIMENT_PRIORITY,
                            source="cli",
                            run_id=run_id,
                            seed=seed,
                            repetition=repetition,
                            arm=arm,
                        )
                    )
    return tasks


def plan_e2(cases: tuple[GoldenCase, ...] | list[GoldenCase], *, run_id: str) -> list[Task]:
    """E2 — H2: `prompt_only` vs `pre_action_guard` sobre os casos adversariais.

    `5 casos × 2 políticas × 5 repetições = 50 execuções`.

    O seed é fixo em `complete`: E2 isola a política de segurança, e variar
    degradação ao mesmo tempo confundiria as duas causas.
    """
    if not cases:
        raise ContractError("E2 exige ao menos um caso adversarial")
    normais = [case.case_id for case in cases if case.case_type != "adversarial"]
    if normais:
        raise ContractError(f"E2 só aceita casos adversariais; recebeu {normais}")
    tasks: list[Task] = []
    for repetition in range(E2_REPETITIONS):
        for case in cases:
            for policy in E2_POLICIES:
                tasks.append(
                    Task(
                        task_id=task_id(
                            run_id,
                            case.case_id,
                            E2_ARCHITECTURE,
                            "complete",
                            repetition,
                            arm=policy,
                        ),
                        kind="experiment",
                        case_id=case.case_id,
                        architecture=E2_ARCHITECTURE,
                        priority=EXPERIMENT_PRIORITY,
                        source="cli",
                        run_id=run_id,
                        seed="complete",
                        repetition=repetition,
                        arm=policy,
                    )
                )
    return tasks


def plan_core(
    base_cases: tuple[GoldenCase, ...] | list[GoldenCase],
    adversarial_cases: tuple[GoldenCase, ...] | list[GoldenCase],
    *,
    run_id: str,
) -> list[Task]:
    """O núcleo obrigatório do orçamento: E1 + E2 — doc 07 §Orçamento total.

    E2 vem primeiro. São 50 execuções contra 544, e é o experimento que sustenta
    H2; se a cota acabar, o que se perde é resolução de E1, não a hipótese inteira.
    """
    return plan_e2(adversarial_cases, run_id=run_id) + plan_e1(base_cases, run_id=run_id)
