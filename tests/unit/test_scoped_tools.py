"""RF12 no ponto de execução, inclusive para chamada não oferecida pelo schema."""

from src.agents.scoped_tools import ScopedToolProvider
from tests.fakes.tools import FakeToolProvider, tool_def


async def test_provider_escopado_nao_delega_tool_fora_da_capacidade():
    inner = FakeToolProvider(
        {"getAsset": {"id": "asset"}, "updateAssetConfig": {"accepted": True}},
        defs=[
            tool_def("getAsset", tier="read"),
            tool_def("updateAssetConfig", tier="impact"),
        ],
    )
    scoped = ScopedToolProvider(inner, [tool_def("getAsset", tier="read")])

    result = await scoped.call("updateAssetConfig", {}, call_id="forbidden")

    assert not result.ok
    assert result.error_class == "contract"
    assert not result.external_call_emitted
    assert inner.calls == []


async def test_provider_escopado_delega_tool_permitida():
    inner = FakeToolProvider(
        {"getAsset": {"id": "asset"}},
        defs=[tool_def("getAsset", tier="read")],
    )
    scoped = ScopedToolProvider(inner, inner.catalog())

    result = await scoped.call("getAsset", {"assetId": "asset"}, call_id="allowed")

    assert result.ok
    assert inner.call_index("getAsset") == 0
