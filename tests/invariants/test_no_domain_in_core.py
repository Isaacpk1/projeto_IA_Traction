"""RNF06 — o núcleo genérico não conhece o domínio.

Invariante arquitetural do princípio P1. É o que sustenta a promessa de portabilidade:
integrar outra API exige um novo contrato e um novo overlay, e `tools/core/` não muda.

A varredura é sobre o **código**, não sobre a intenção. Um identificador de domínio que
apareça em `tools/core/` quebra o build — que é o comportamento correto, porque nesse
momento a promessa do RNF06 já deixou de ser verdadeira.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[2]
NUCLEO = RAIZ / "src" / "tools" / "core"

#: Vocabulário do domínio industrial. Se qualquer um destes aparecer no núcleo, a
#: separação núcleo/overlay foi violada.
TERMOS_DE_DOMINIO = (
    "baseline",
    "rms",
    "spectrum",
    "espectro",
    "asset",
    "ativo",
    "analysis",
    "analise",
    "vibra",
    "tractian",
    "bearing",
    "rotation",
    "criticality",
    "criticidade",
    "machine_type",
    "snr",
    "insight",
    "manuten",
    "escalate",
    "escalar",
    "retraining",
    "reprocess",
)

#: `getCompany`, `getAsset` e afins são dados do contrato, não do código — mas se um
#: `operationId` for escrito literalmente no núcleo, ele deixou de ser genérico.
OPERATION_IDS = (
    "getCompany",
    "listAssetsByCompany",
    "getCurrentUser",
    "getAsset",
    "updateAssetConfig",
    "listAnalyses",
    "getAnalysis",
    "reprocessAnalysis",
    "requestSpecialistAnalysis",
    "getBaseline",
    "getRmsSeries",
    "getSpectrum",
    "getDataQuality",
    "getModel",
    "requestRetraining",
    "searchKnowledge",
    "getKnowledgeDoc",
    "escalateCase",
)


def _arquivos_do_nucleo() -> list[Path]:
    return sorted(p for p in NUCLEO.rglob("*.py") if p.name != "__init__.py")


def _codigo_sem_comentarios(arquivo: Path) -> str:
    """Remove docstrings e comentários.

    Um comentário explicando *por que* o núcleo não conhece domínio precisa poder citar
    o domínio — senão a regra impediria de documentar a própria regra. O que a varredura
    persegue é **código** acoplado, não prosa.
    """
    fonte = arquivo.read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    docstrings: set[int] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            corpo = getattr(no, "body", [])
            if (
                corpo
                and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)
            ):
                doc = corpo[0]
                docstrings.update(range(doc.lineno, (doc.end_lineno or doc.lineno) + 1))

    linhas = []
    for i, linha in enumerate(fonte.splitlines(), start=1):
        if i in docstrings:
            continue
        linhas.append(re.sub(r"#.*$", "", linha))
    return "\n".join(linhas)


def test_nucleo_de_ferramentas_existe():
    assert _arquivos_do_nucleo(), "tools/core/ vazio — a varredura passaria por vacuidade"


@pytest.mark.parametrize("arquivo", _arquivos_do_nucleo(), ids=lambda p: p.name)
def test_nucleo_nao_menciona_o_dominio(arquivo: Path):
    codigo = _codigo_sem_comentarios(arquivo).lower()
    encontrados = [t for t in TERMOS_DE_DOMINIO if t in codigo]
    assert not encontrados, (
        f"{arquivo.relative_to(RAIZ)} contém domínio: {encontrados}. "
        "Semântica de domínio pertence ao overlay (ADR-02)."
    )


@pytest.mark.parametrize("arquivo", _arquivos_do_nucleo(), ids=lambda p: p.name)
def test_nucleo_nao_cita_operation_id(arquivo: Path):
    codigo = _codigo_sem_comentarios(arquivo)
    encontrados = [op for op in OPERATION_IDS if op in codigo]
    assert not encontrados, f"{arquivo.relative_to(RAIZ)} referencia operações: {encontrados}"


def test_nucleo_nao_importa_o_overlay():
    """A dependência aponta para fora: `provider.py` conhece os dois, o núcleo conhece um."""
    for arquivo in _arquivos_do_nucleo():
        codigo = arquivo.read_text(encoding="utf-8")
        assert "from src.tools.overlay" not in codigo, arquivo.name
        assert "from src.tools.provider" not in codigo, arquivo.name


def test_varredura_pega_uma_violacao_plantada(tmp_path: Path):
    """O teste do teste.

    Uma varredura que nunca acusa nada é indistinguível de uma varredura quebrada. Este
    caso planta a violação de propósito e exige que ela seja detectada.
    """
    plantado = tmp_path / "violacao.py"
    plantado.write_text(
        "def limiar(asset_id: str) -> float:\n    return baseline_reference(asset_id)\n",
        encoding="utf-8",
    )
    codigo = _codigo_sem_comentarios(plantado).lower()
    assert [t for t in TERMOS_DE_DOMINIO if t in codigo]
