"""`ToolProvider` — a superfície que os agentes consomem."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from src.tools.core.http_executor import HttpExecutor
from src.tools.provider import ApiToolProvider, DryRunToolProvider, build_registry

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

BASE = "http://api.local"


@pytest.fixture
def provider(contract_path: Path):
    reg, ov = build_registry(contract_path)
    return ApiToolProvider(
        reg, HttpExecutor(BASE), overlay=ov, default_user_id="usr_ana", default_seed="s1"
    )


def test_provider_satisfaz_a_porta(provider):
    from src.core.ports import ToolProvider

    assert isinstance(provider, ToolProvider)
    assert isinstance(DryRunToolProvider(provider), ToolProvider)


def test_catalogo_filtra_por_tier(provider):
    assert len(provider.catalog()) == 18
    assert len(provider.catalog(tiers={"read"})) == 13
    assert {t.name for t in provider.catalog(tiers={"impact"})} == {
        "reprocessAnalysis",
        "requestSpecialistAnalysis",
        "requestRetraining",
        "updateAssetConfig",
        "escalateCase",
    }


def test_versoes_entram_no_trace(provider):
    """RNF15 — todo resultado precisa ser reconstituível a partir do trace."""
    assert len(provider.schema_version) == 12
    assert provider.overlay_version == "1:enriched"


def test_modo_do_overlay_distingue_os_bracos_no_trace(contract_path: Path, provider):
    """H3 precisa ser identificável pelos metadados, não apenas pelo nome do braço."""
    cru, ov_cru = build_registry(contract_path, mode="raw")
    rico, ov_rico = build_registry(contract_path, mode="enriched")
    assert ApiToolProvider(cru, provider.executor, overlay=ov_cru).overlay_version == "1:raw"
    assert ApiToolProvider(rico, provider.executor, overlay=ov_rico).overlay_version == "1:enriched"


@respx.mock
async def test_tool_desconhecida_e_erro_de_contrato(provider):
    """O modelo alucinou um nome. O catálogo é fechado: isso é bug, não comportamento."""
    r = await provider.call("getVibrationForecast", {}, call_id="c1")
    assert r.error_class == "contract"
    assert "desconhecida" in (r.error or "")


@respx.mock
async def test_defaults_de_usuario_e_seed_sao_aplicados(provider):
    rota = respx.get(f"{BASE}/assets/a/baseline").mock(
        return_value=httpx.Response(200, json={"mode": "complete", "data": {}})
    )
    await provider.call("getBaseline", {"assetId": "a"}, call_id="c1")

    req = rota.calls[0].request
    assert req.url.params["seed"] == "s1"
    assert req.headers["x-user-id"] == "usr_ana"


@respx.mock
async def test_chamada_explicita_sobrescreve_os_defaults(provider):
    rota = respx.get(f"{BASE}/assets/a/baseline").mock(
        return_value=httpx.Response(200, json={"mode": "complete", "data": {}})
    )
    await provider.call(
        "getBaseline", {"assetId": "a"}, call_id="c1", user_id="usr_pedro", seed="s9"
    )

    req = rota.calls[0].request
    assert req.url.params["seed"] == "s9"
    assert req.headers["x-user-id"] == "usr_pedro"


# --- dry-run: obrigatório no braço `prompt_only` de E2 ------------------------


@respx.mock
async def test_dry_run_suprime_efeito_externo_mas_registra_a_tentativa(provider):
    """E2 mede tentativas inseguras. Medi-las produzindo efeito real seria inaceitável.

    A tentativa continua registrada — é isso que mantém M10 mensurável.
    """
    rota = respx.post(f"{BASE}/models/mdl_vib_v3/request-retraining")
    dry = DryRunToolProvider(provider)

    r = await dry.call(
        "requestRetraining",
        {"modelId": "mdl_vib_v3", "justification": "x" * 25},
        call_id="c1",
    )

    assert rota.call_count == 0, "nenhuma chamada externa pode ser emitida"
    assert r.ok
    assert r.data is not None and r.data["data"]["dry_run"] is True
    assert dry.suppressed == [
        ("requestRetraining", {"modelId": "mdl_vib_v3", "justification": "x" * 25})
    ]


@respx.mock
async def test_dry_run_deixa_leitura_passar(provider):
    """Bloquear leitura mudaria o que o braço investiga: ele mede a decisão de agir."""
    rota = respx.get(f"{BASE}/assets/a/baseline").mock(
        return_value=httpx.Response(200, json={"mode": "complete", "data": {"state": "learning"}})
    )
    dry = DryRunToolProvider(provider)

    r = await dry.call("getBaseline", {"assetId": "a"}, call_id="c1")

    assert rota.call_count == 1
    assert r.ok and r.data is not None
    assert r.data["data"]["state"] == "learning"
    assert dry.suppressed == []


@respx.mock
async def test_dry_run_cobre_todas_as_tools_de_impacto(provider):
    """Cobertura exaustiva: uma tool de impacto esquecida produziria efeito real em E2."""
    respx.route().mock(return_value=httpx.Response(200, json={"accepted": True}))
    dry = DryRunToolProvider(provider)

    args = {
        "reprocessAnalysis": {"analysisId": "an_1", "justification": "x" * 25},
        "requestSpecialistAnalysis": {"analysisId": "an_1", "justification": "x" * 25},
        "requestRetraining": {"modelId": "m1", "justification": "x" * 25},
        "updateAssetConfig": {"assetId": "a1", "justification": "x" * 25},
        "escalateCase": {"caseId": "c1", "justification": "x" * 25},
    }
    for nome, a in args.items():
        await dry.call(nome, a, call_id="c")

    assert {n for n, _ in dry.suppressed} == set(args)
    assert respx.calls.call_count == 0
