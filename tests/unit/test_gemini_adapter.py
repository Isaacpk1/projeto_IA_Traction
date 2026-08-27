"""Contrato do adaptador Gemini, executado quando o extra ``agent`` está instalado."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.core.contracts.llm import Message
from src.core.contracts.tool import ToolCall, ToolDef
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


async def test_converte_historico_tools_config_e_resposta_sem_chamar_a_rede():
    models = _Models()
    client = SimpleNamespace(aio=SimpleNamespace(models=models))
    adapter = GeminiClient(client=client)
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
