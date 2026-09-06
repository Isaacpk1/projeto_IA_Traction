"""Composition root — doc 14 Fase 6. O que se testa aqui é a fiação, não o agente.

O LLM real é substituído por um duplo que responde em texto: nenhuma tool é
chamada, então nenhum HTTP sai. O que sobra sob teste é exatamente o que a CLI
existe para fazer — ligar fila, arquitetura, sink e scoring numa coisa só.
"""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from src.agents.architectures import MonoArchitecture, MultiArchitecture
from src.core.contracts.task import Task
from src.evaluation.runner.queue_sqlite import SQLiteWorkQueue
from src.interfaces import cli
from src.storage.jsonl_traces import JsonlTraceSink
from src.tools.core.http_executor import HttpExecutor
from src.tools.provider import ApiToolProvider, build_registry
from tests.conftest import CONTRACT_PATH
from tests.fakes.llm import FakeLLMClient, say

runner = CliRunner()


def _provider_qualquer():
    """A fábrica só encaminha o provider; o que ele fala não importa aqui."""
    registry, overlay = build_registry(CONTRACT_PATH)
    return ApiToolProvider(registry, HttpExecutor("http://127.0.0.1:1"), overlay=overlay)


class _FakeGemini(FakeLLMClient):
    """Mesma porta do GeminiClient, incluindo o `provider` que o rate limiter usa."""

    provider = "google-ai-studio"

    def __init__(self, model: str = "fake", rate_limiter: object = None, **kwargs: object) -> None:
        super().__init__(script=[], provider=self.provider, on_exhausted=lambda: say("sem tools"))
        self.model = model
        self.rate_limiter = rate_limiter

    async def aclose(self) -> None:
        return None


@pytest.fixture
def chave(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "chave-de-teste")
    monkeypatch.setattr(cli, "GeminiClient", _FakeGemini)


def test_plan_materializa_o_nucleo_e_e_idempotente(tmp_path):
    db = tmp_path / "q.db"

    primeiro = runner.invoke(cli.app, ["plan", "--run-id", "r", "--db", str(db)])
    segundo = runner.invoke(cli.app, ["plan", "--run-id", "r", "--db", str(db)])

    assert primeiro.exit_code == 0, primeiro.output
    assert "planejadas 594 · novas 594" in primeiro.output
    assert "novas 0 · já existentes 594" in segundo.output


def test_plan_recusa_experimento_desconhecido(tmp_path):
    resultado = runner.invoke(
        cli.app,
        ["plan", "--run-id", "r", "--experiment", "e9", "--db", str(tmp_path / "q.db")],
    )

    assert resultado.exit_code != 0
    assert "e9" in resultado.output


def test_status_sem_fila_falha_com_instrucao(tmp_path):
    resultado = runner.invoke(cli.app, ["status", "--db", str(tmp_path / "vazio.db")])

    assert resultado.exit_code == 1
    assert "plan" in resultado.output


def test_run_recusa_a_chave_placeholder(tmp_path, monkeypatch):
    """O erro tem que aparecer antes das 594 tarefas, não durante."""
    monkeypatch.setenv("GEMINI_API_KEY", cli._PLACEHOLDER)
    db = tmp_path / "q.db"
    runner.invoke(cli.app, ["plan", "--run-id", "r", "--db", str(db)])

    resultado = runner.invoke(cli.app, ["run", "--run-id", "r", "--db", str(db)])

    assert resultado.exit_code != 0
    assert "GEMINI_API_KEY" in resultado.output


def test_run_drena_a_fila_e_persiste_trace_e_metricas(tmp_path, chave):
    db, traces, metrics = tmp_path / "q.db", tmp_path / "traces", tmp_path / "m.db"
    runner.invoke(cli.app, ["plan", "--run-id", "r", "--experiment", "e2", "--db", str(db)])

    resultado = runner.invoke(
        cli.app,
        [
            "run", "--run-id", "r", "--db", str(db),
            "--traces", str(traces), "--metrics", str(metrics),
            "--quota", str(tmp_path / "quota.db"),
            "--max-tasks", "2",
        ],
    )

    assert resultado.exit_code == 0, resultado.output
    assert "processadas 2" in resultado.output

    with SQLiteWorkQueue(db) as queue:
        counts = queue.counts("r")
    assert counts["pending"] == 48
    assert sum(counts.values()) == 50

    escritos = list(traces.rglob("*.jsonl"))
    assert escritos, "o trace canônico é a fonte de verdade — sem ele não há dado"
    linhas = [json.loads(linha) for linha in escritos[0].read_text().splitlines() if linha]
    assert linhas
    assert metrics.exists(), "o scoring roda depois de fechar a task, não durante"


@pytest.mark.parametrize(
    ("arm", "architecture", "esperado", "guard"),
    [
        ("A", "mono", MonoArchitecture, True),
        ("B", "multi", MultiArchitecture, True),
        ("pre_action_guard", "mono", MonoArchitecture, True),
        ("prompt_only", "mono", MonoArchitecture, False),
    ],
)
def test_braco_declarado_na_matriz_vira_a_arquitetura_que_o_realiza(
    arm, architecture, esperado, guard, tmp_path
):
    """Se este mapeamento errar, H1 e H2 medem outra coisa sem avisar."""
    task = Task(
        task_id="t",
        kind="experiment",
        case_id="c",
        architecture=architecture,
        arm=arm,
    )
    provider = _provider_qualquer()

    construida = cli.build_architecture(
        task, llm=_FakeGemini(), provider=provider, sink=JsonlTraceSink(tmp_path)
    )

    assert isinstance(construida, esperado)
    assert construida.name == architecture
    if esperado is MonoArchitecture:
        assert construida.enforce_pre_action_guard is guard


def test_braco_inseguro_recebe_provider_dry_run(tmp_path):
    """`prompt_only` sem provider dry-run é o cenário que a doc 07 §E2 proíbe."""
    task = Task(
        task_id="t", kind="experiment", case_id="c", architecture="mono", arm="prompt_only"
    )

    construida = cli.build_architecture(
        task, llm=_FakeGemini(), provider=_provider_qualquer(), sink=JsonlTraceSink(tmp_path)
    )

    assert getattr(construida.tools, "is_dry_run", False) is True


def test_multi_recebe_o_mesmo_modelo_em_todos_os_papeis(tmp_path):
    """RF33: heterogeneidade de modelo entre papéis é vedada em E1."""
    task = Task(task_id="t", kind="experiment", case_id="c", architecture="multi", arm="B")
    llm = _FakeGemini()

    construida = cli.build_architecture(
        task, llm=llm, provider=_provider_qualquer(), sink=JsonlTraceSink(tmp_path)
    )

    assert set(construida.llms) == set(cli.MULTI_ROLES)
    assert {id(cliente) for cliente in construida.llms.values()} == {id(llm)}
