"""Porta das arquiteturas de agente — doc 13 §5.1. **Strategy.**

É o padrão mais *load-bearing* do projeto. H1 compara duas arquiteturas: se cada uma
tivesse seu próprio runner, sua própria instrumentação e seu próprio caminho de
persistência, a diferença medida incluiria a diferença entre os runners. Strategy é o
que garante que tudo fora da variável manipulada seja literalmente o mesmo código.

> Sem Strategy, H1 não é testável.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.core.contracts.golden import CaseInput
from src.core.contracts.trace import Architecture as ArchName
from src.core.contracts.trace import ExecutionTrace

__all__ = ["RunContext", "Architecture"]


class RunContext:
    """Tudo que a execução precisa e que não vem do caso.

    Deliberadamente uma classe simples, não um contêiner de injeção: Python resolve
    composição com argumentos e `interfaces/`; um container acrescentaria mágica e um
    arquivo de configuração para resolver nada (doc 13 §5.3).
    """

    def __init__(
        self,
        *,
        execution_id: str,
        task_id: str,
        run_id: str | None = None,
        arm: str = "A",
        seed: str | None = None,
        repetition: int = 0,
        experiment_id: str | None = None,
        max_steps: int = 8,
        dry_run: bool = False,
        confirmation_policy: str = "auto_confirm",
        metadata: dict | None = None,
    ) -> None:
        self.execution_id = execution_id
        self.task_id = task_id
        self.run_id = run_id
        self.arm = arm
        self.seed = seed
        self.repetition = repetition
        self.experiment_id = experiment_id
        self.max_steps = max_steps
        self.dry_run = dry_run
        self.confirmation_policy = confirmation_policy
        self.metadata = metadata or {}


@runtime_checkable
class Architecture(Protocol):
    name: ArchName

    async def run(self, case: CaseInput, ctx: RunContext) -> ExecutionTrace:
        """Atende um caso e devolve o trace.

        Recebe `CaseInput`, nunca `GoldenCase`: o gabarito não atravessa esta fronteira
        (RNF02), e a assinatura é o primeiro lugar onde isso é garantido.
        """
        ...
