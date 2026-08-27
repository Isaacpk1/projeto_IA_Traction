"""Executor HTTP — transporte mock do httpx, sem rede (doc 14 §6.2)."""

from __future__ import annotations

import httpx
import pytest
import respx

from src.core.contracts.tool import ToolDef
from src.tools.core.http_executor import HttpExecutor, build_request
from src.tools.core.tier_registry import TierRegistry

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")

BASE = "http://api.local"


@pytest.fixture
def executor():
    return HttpExecutor(BASE, max_attempts=3)


def _tool(registry: TierRegistry, nome: str) -> ToolDef:
    tool = registry.get(nome)
    assert tool is not None
    return tool


# --- montagem da requisição ---------------------------------------------------


def test_argumentos_vao_para_path_query_e_corpo(registry: TierRegistry):
    metodo, caminho, query, corpo = build_request(
        _tool(registry, "updateAssetConfig"),
        {
            "assetId": "asset_M101",
            "justification": "baseline invalidado apos manutencao registrada",
            "changes": {"criticality": "high"},
        },
    )
    assert metodo == "patch"
    assert caminho == "/assets/asset_M101"
    assert query == {}
    assert corpo is not None
    assert corpo["justification"].startswith("baseline")
    assert corpo["changes"] == {"criticality": "high"}
    assert "assetId" not in corpo, "parâmetro de path não pode vazar para o corpo"


def test_seed_e_injetado_pelo_executor_nao_pelo_modelo(registry: TierRegistry):
    _, _, query, _ = build_request(
        _tool(registry, "getBaseline"), {"assetId": "asset_M101"}, seed="s3"
    )
    assert query["seed"] == "s3"


def test_seed_e_ignorado_em_operacao_que_nao_o_aceita(registry: TierRegistry):
    _, _, query, _ = build_request(
        _tool(registry, "escalateCase"),
        {"caseId": "c1", "justification": "x" * 25},
        seed="s3",
    )
    assert "seed" not in query


def test_get_nunca_leva_corpo(registry: TierRegistry):
    _, _, _, corpo = build_request(_tool(registry, "getAsset"), {"assetId": "a"})
    assert corpo is None


def test_parametro_de_path_ausente_e_erro_de_contrato(registry: TierRegistry):
    with pytest.raises(ValueError, match="assetId"):
        build_request(_tool(registry, "getAsset"), {})


def test_corpo_obrigatorio_ausente_e_erro_de_contrato(registry: TierRegistry):
    with pytest.raises(ValueError, match="justification"):
        build_request(_tool(registry, "updateAssetConfig"), {"assetId": "a"})


def test_tipo_enum_e_argumento_extra_sao_validados(registry: TierRegistry):
    tool = _tool(registry, "updateAssetConfig")

    with pytest.raises(ValueError, match="is not of type"):
        build_request(
            tool,
            {"assetId": "a", "justification": "x" * 25, "changes": {"criticality": 10}},
        )
    with pytest.raises(ValueError, match="Additional properties"):
        build_request(
            tool,
            {"assetId": "a", "justification": "x" * 25, "changes": {}, "inventado": True},
        )


# --- execução -----------------------------------------------------------------


@respx.mock
async def test_chamada_bem_sucedida_preserva_o_envelope(registry: TierRegistry, executor):
    respx.get(f"{BASE}/assets/asset_S420/baseline").mock(
        return_value=httpx.Response(
            200,
            json={
                "status": "ok",
                "mode": "partial",
                "notes": "features incompletas",
                "data": {"state": "invalidated"},
            },
        )
    )
    r = await executor.execute(
        _tool(registry, "getBaseline"), {"assetId": "asset_S420"}, call_id="c1"
    )

    assert r.ok
    assert r.mode == "partial", "o modo do envelope alimenta a intensidade de degradação"
    assert r.data is not None and r.data["data"]["state"] == "invalidated"
    assert r.latency_ms >= 0


@respx.mock
async def test_user_id_vira_cabecalho(registry: TierRegistry, executor):
    rota = respx.get(f"{BASE}/users/me").mock(return_value=httpx.Response(200, json={"id": "u1"}))
    await executor.execute(_tool(registry, "getCurrentUser"), {}, call_id="c1", user_id="usr_pedro")
    assert rota.calls[0].request.headers["x-user-id"] == "usr_pedro"


@respx.mock
async def test_erro_do_upstream_vira_observacao_e_nao_excecao(registry: TierRegistry, executor):
    """Levantar derrubaria o loop e converteria um 403 legítimo em falha de execução.

    O agente precisa **ver** o 403 para reagir a ele — é assim que "tentei agir sem
    permissão" vira comportamento observável em vez de crash.
    """
    respx.post(f"{BASE}/cases/c1/escalate").mock(
        return_value=httpx.Response(403, json={"code": "UNAUTHORIZED", "message": "sem permissão"})
    )
    r = await executor.execute(
        _tool(registry, "escalateCase"),
        {"caseId": "c1", "justification": "x" * 25},
        call_id="c1",
    )

    assert not r.ok
    assert r.status_code == 403
    assert "sem permissão" in (r.error or "")
    assert r.error_class == "behavior", "4xx é decisão do agente, não falha de infra"


@respx.mock
@pytest.mark.parametrize("status", [429, 503])
async def test_limite_e_indisponibilidade_sao_infra(registry: TierRegistry, executor, status):
    """Separar infra de comportamento é a diferença entre medir o agente e medir a internet."""
    respx.get(f"{BASE}/assets/a/baseline").mock(return_value=httpx.Response(status, json={}))
    r = await executor.execute(_tool(registry, "getBaseline"), {"assetId": "a"}, call_id="c1")
    assert r.error_class == "infra"


@respx.mock
async def test_timeout_recua_e_reencaminha(registry: TierRegistry, executor):
    """RNF04 — recuo exponencial com limite de tentativas."""
    rota = respx.get(f"{BASE}/assets/a/baseline")
    rota.side_effect = [
        httpx.ReadTimeout("t"),
        httpx.ReadTimeout("t"),
        httpx.Response(200, json={"mode": "complete", "data": {}}),
    ]
    r = await executor.execute(_tool(registry, "getBaseline"), {"assetId": "a"}, call_id="c1")

    assert r.ok
    assert rota.call_count == 3


@respx.mock
async def test_falha_persistente_esgota_tentativas_e_classifica_infra(
    registry: TierRegistry, executor
):
    rota = respx.get(f"{BASE}/assets/a/baseline")
    rota.side_effect = httpx.ConnectError("recusada")
    r = await executor.execute(_tool(registry, "getBaseline"), {"assetId": "a"}, call_id="c1")

    assert not r.ok
    assert r.error_class == "infra"
    assert rota.call_count == 3


@respx.mock
async def test_argumento_faltando_nao_chega_a_sair(registry: TierRegistry, executor):
    rota = respx.get(f"{BASE}/assets/a/baseline")
    r = await executor.execute(_tool(registry, "getBaseline"), {}, call_id="c1")

    assert r.error_class == "contract"
    assert rota.call_count == 0, "requisição malformada não deve consumir a API"


@respx.mock
async def test_lista_no_topo_e_embrulhada(registry: TierRegistry, executor):
    """`listAnalyses` devolve array; o trace guarda dicionários."""
    respx.get(f"{BASE}/assets/a/analyses").mock(
        return_value=httpx.Response(200, json=[{"id": "an_1"}, {"id": "an_2"}])
    )
    r = await executor.execute(_tool(registry, "listAnalyses"), {"assetId": "a"}, call_id="c1")

    assert r.ok
    assert r.data is not None and len(r.data["items"]) == 2
