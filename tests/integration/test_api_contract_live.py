"""Camada de ferramentas contra a API industrial real.

Pulado quando a API não está no ar — a suíte precisa rodar em máquina limpa. Estes testes
não consomem cota de LLM: exercitam apenas o caminho tool → HTTP → envelope.

O teste central aqui é o de determinismo por `seed`. O desenho de E1 trata os seeds como
**níveis de uma variável contínua** em vez de um fator binário, o que multiplica o poder
estatístico sem custo adicional. Isso só é legítimo se a API for de fato determinística —
e essa premissa merece verificação executável, não apenas leitura do código-fonte.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest

from src.core.contracts.trace import ExecutionTrace, TraceStep
from src.tools.core.http_executor import HttpExecutor
from src.tools.provider import ApiToolProvider, build_registry

API_URL = os.environ.get("TRACTIAN_API_URL", "http://127.0.0.1:8000")
ASSET = "asset_S420"


def _api_no_ar() -> bool:
    try:
        return httpx.get(f"{API_URL}/docs", timeout=2.0).status_code == 200
    except Exception:
        return False


pytestmark = [
    pytest.mark.filterwarnings("ignore::UserWarning"),
    pytest.mark.skipif(not _api_no_ar(), reason=f"API industrial fora do ar em {API_URL}"),
]


@pytest.fixture
async def provider(contract_path: Path):
    reg, ov = build_registry(contract_path)
    async with HttpExecutor(API_URL) as ex:
        yield ApiToolProvider(reg, ex, overlay=ov, default_user_id="usr_pedro")


async def test_toda_tool_de_leitura_responde(provider):
    """Se uma tool gerada não conversa com a API real, o schema está errado."""
    args = {
        "getCompany": {"companyId": "comp_forja_br"},
        "listAssetsByCompany": {"companyId": "comp_forja_br"},
        "getCurrentUser": {},
        "getAsset": {"assetId": ASSET},
        "listAnalyses": {"assetId": ASSET},
        "getBaseline": {"assetId": ASSET},
        "getRmsSeries": {"assetId": ASSET},
        "getSpectrum": {"assetId": ASSET},
        "getDataQuality": {"assetId": ASSET},
        "searchKnowledge": {"q": "baseline"},
    }
    falhas = []
    for nome, a in args.items():
        r = await provider.call(nome, a, call_id=nome, seed="s1")
        if not r.ok or r.data is None:
            falhas.append((nome, r.error))
    assert not falhas, falhas


async def test_mesmo_seed_produz_a_mesma_resposta(provider):
    """Premissa de RNF01 e do desenho dose-resposta."""
    a = await provider.call("getBaseline", {"assetId": ASSET}, call_id="a", seed="s1")
    b = await provider.call("getBaseline", {"assetId": ASSET}, call_id="b", seed="s1")
    assert a.data == b.data


async def test_seeds_distintos_produzem_regimes_distintos(provider):
    """Sem variação entre seeds, o eixo de degradação de H1 seria constante — e a
    análise dose-resposta não teria variável independente."""
    modos = set()
    for s in [f"s{i}" for i in range(8)]:
        r = await provider.call("getBaseline", {"assetId": ASSET}, call_id=s, seed=s)
        modos.add(r.mode)
    assert len(modos) >= 2, f"todos os seeds produziram o mesmo modo: {modos}"


async def test_intensidade_de_degradacao_sai_do_trace(provider):
    """A variável independente de H1 é computada do trace, nunca do gabarito."""
    passos = []
    trajetoria = ["getAsset", "listAnalyses", "getBaseline", "getRmsSeries", "getDataQuality"]
    for i, nome in enumerate(trajetoria):
        r = await provider.call(nome, {"assetId": ASSET}, call_id=str(i), seed="s0")
        passos.append(TraceStep(step=i, agent="agent", tool=nome, result=r.data))

    trace = ExecutionTrace(
        task_id="t", execution_id="e", case_id="c", architecture="mono", arm="A", steps=passos
    )

    assert len(trace.api_modes_seen()) == len(trajetoria), "todo GET traz envelope com modo"
    intensidade = trace.observed_degradation_intensity()
    assert intensidade is not None and 0.0 <= intensidade <= 1.0


async def test_acao_sem_justificativa_e_recusada_pela_api(provider):
    """L13: a API valida a justificativa apenas por comprimento (≥20 chars).

    Fixar o comportamento aqui é o que sustenta a limitação declarada — e deixa
    explícito que a rede real contra justificativa vazia é nossa, não da API.
    """
    r = await provider.call(
        "escalateCase", {"caseId": "case_tkt_inv_06", "justification": "curta"}, call_id="c"
    )
    assert not r.ok
    assert r.status_code in (400, 422)
