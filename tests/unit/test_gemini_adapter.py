"""Contrato do adaptador Gemini, executado quando o extra ``agent`` está instalado."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.contracts.llm import Message
from src.core.contracts.tool import ToolCall, ToolDef
from src.core.errors import ContractError, UpstreamUnavailable
from src.llm.gemini import GeminiClient

genai = pytest.importorskip("google.genai")
types = genai.types


class _Models:
    kwargs: dict

    async def generate_content(self, **kwargs):
        self.kwargs = kwargs
        part = types.Part.from_function_call(name="getAsset", args={"assetId": "a1"})
        candidate = SimpleNamespace(
            content=types.Content(role="model", parts=[part]),
            finish_reason="STOP",
        )
        usage = SimpleNamespace(prompt_token_count=7, candidates_token_count=3)
        return SimpleNamespace(
            candidates=[candidate],
            usage_metadata=usage,
            model_version="test-version",
        )


class _Limiter:
    def __init__(self) -> None:
        self.acquired: list[str] = []
        self.consumed: list[str] = []

    async def acquire(self, provider: str, cost: int = 1) -> None:
        self.acquired.extend([provider] * cost)

    async def consume_daily(self, provider: str, cost: int = 1) -> int:
        self.consumed.extend([provider] * cost)
        return len(self.consumed)


async def test_converte_historico_tools_config_e_resposta_sem_chamar_a_rede():
    models = _Models()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    limiter = _Limiter()
    adapter = GeminiClient(client=client, rate_limiter=limiter)
    messages = [
        Message(role="user", content="investigue"),
        Message(
            role="assistant",
            tool_calls=[ToolCall(call_id="c1", name="getBaseline", arguments={"assetId": "a1"})],
        ),
        Message(
            role="tool",
            name="getBaseline",
            tool_call_id="c1",
            content='{"data": {"state": "invalidated"}}',
        ),
    ]
    tools = [ToolDef(name="getAsset", description="consulta", parameters={"type": "object"})]

    response = await adapter.chat(messages, tools)

    assert [content.role for content in models.kwargs["contents"]] == ["user", "model", "user"]
    config = models.kwargs["config"]
    assert config.automatic_function_calling.disable is True
    assert config.tools[0].function_declarations[0].name == "getAsset"
    assert response.message.tool_calls[0].name == "getAsset"
    assert response.usage.tokens_in == 7 and response.usage.tokens_out == 3
    assert response.model_version == "test-version"
    assert limiter.acquired == ["google-ai-studio"]
    assert limiter.consumed == ["google-ai-studio"]


async def _responde(monkeypatch, resposta):
    client = GeminiClient(client=_Client(resposta))
    return await client.chat([Message(role="user", content="oi")])


class _Client:
    def __init__(self, resposta):
        self.aio = SimpleNamespace(models=_ModelsFixos(resposta))


class _ModelsFixos:
    def __init__(self, resposta):
        self.resposta = resposta

    async def generate_content(self, **kwargs):
        return self.resposta


async def test_candidato_sem_conteudo_e_falha_de_infra_nao_de_comportamento():
    """Filtro de segurança do provedor não pode virar erro de raciocínio do agente.

    Classificar como `behavior` poluiria M1–M16 com execuções em que o modelo
    sequer respondeu — o roadmap proíbe isso explicitamente.
    """
    resposta = SimpleNamespace(
        candidates=[SimpleNamespace(content=None, finish_reason="SAFETY")],
        usage_metadata=None,
        model_version="x",
    )

    with pytest.raises(UpstreamUnavailable, match="SAFETY"):
        await _responde(None, resposta)

    assert UpstreamUnavailable.error_class == "infra"


async def test_resposta_sem_candidato_algum_e_infra():
    resposta = SimpleNamespace(
        candidates=[],
        prompt_feedback=SimpleNamespace(block_reason="PROHIBITED_CONTENT"),
        usage_metadata=None,
    )

    with pytest.raises(UpstreamUnavailable, match="PROHIBITED_CONTENT"):
        await _responde(None, resposta)


async def test_candidato_com_parts_nulo_nao_estoura():
    """`parts=None` com conteúdo presente é resposta vazia legítima, não crash."""
    resposta = SimpleNamespace(
        candidates=[SimpleNamespace(content=SimpleNamespace(parts=None), finish_reason="STOP")],
        usage_metadata=None,
        model_version="x",
    )

    r = await _responde(None, resposta)

    assert r.message.content is None
    assert r.message.tool_calls == []
    assert r.finish_reason == "STOP"


async def test_chamada_de_ferramenta_malformada_e_erro_de_contrato():
    """RS-02 do doc 12 vigia a taxa de `contract` para instabilidade de tool calling.

    Classificar isso como `infra` devolveria a task para a fila e o risco ficaria
    invisível justamente na métrica criada para detectá-lo.
    """
    resposta = SimpleNamespace(
        candidates=[SimpleNamespace(content=None, finish_reason="MALFORMED_FUNCTION_CALL")],
        usage_metadata=None,
        model_version="x",
    )

    with pytest.raises(ContractError, match="MALFORMED_FUNCTION_CALL"):
        await _responde(None, resposta)

    assert ContractError.error_class == "contract"
