"""Regra de dependência — doc 13 §2.

Delegado ao `import-linter`, e não a um verificador de AST próprio, por um motivo
concreto: um checker caseiro pega **import direto**. O `import-linter` pega **import
indireto** — cadeias através de módulos intermediários. Se `analysis/` importasse
`utils/` e `utils/` importasse `agents/`, o checker caseiro passaria, e a promessa de que
a análise roda sem SDK de LLM seria falsa sem ninguém notar.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]


def _executavel() -> str | None:
    """Localiza o console script `lint-imports`.

    ⚠️ **Não use `python -m importlinter.cli`.** O pacote não tem `__main__`, e invocar o
    submódulo assim executa o corpo do arquivo sem acionar o comando do Click: o processo
    **sai com 0 sem verificar contrato nenhum**. Este teste passou verde por vacuidade até
    a descoberta — que é exatamente o modo de falha mais perigoso num teste de invariante.
    """
    if achado := shutil.which("lint-imports"):
        return achado
    candidato = Path(sys.executable).parent / "lint-imports"
    return str(candidato) if candidato.exists() else None


def test_regra_de_dependencia():
    """`core/` não importa nada; módulos não se importam lateralmente; só `interfaces/` compõe."""
    exe = _executavel()
    if exe is None:
        pytest.skip("import-linter não instalado (extra dev)")

    r = subprocess.run([exe], cwd=RAIZ, capture_output=True, text=True)
    assert r.returncode == 0, f"contratos violados:\n{r.stdout}\n{r.stderr}"
    assert "Contracts: " in r.stdout, f"nenhum contrato foi avaliado:\n{r.stdout}"
    assert " broken" not in r.stdout.split("Contracts: ")[1].split("\n")[0].replace(
        "0 broken", ""
    ), r.stdout


def test_o_verificador_de_imports_realmente_verifica(tmp_path: Path):
    """O teste do teste — um verificador que nunca acusa nada é indistinguível de um quebrado.

    Planta uma violação da regra de dependência (`core/` importando um módulo) e exige que
    o `import-linter` a detecte.
    """
    exe = _executavel()
    if exe is None:
        pytest.skip("import-linter não instalado (extra dev)")

    plantado = RAIZ / "src" / "core" / "_violacao_temporaria.py"
    plantado.write_text("from src.agents.roles import MONO  # noqa: F401\n", encoding="utf-8")
    try:
        r = subprocess.run([exe], cwd=RAIZ, capture_output=True, text=True)
    finally:
        plantado.unlink()

    assert r.returncode != 0, f"violação plantada não foi detectada:\n{r.stdout}"


def test_core_nao_importa_o_projeto():
    """Verificação direta, redundante de propósito.

    O `import-linter` cobre isto e mais, mas ele depende de uma dependência de dev
    instalada. Esta asserção roda sempre — e `core/` é o contrato que, se quebrar,
    quebra todo o resto.
    """
    proibidos = ("src.agents", "src.tools", "src.evaluation", "src.analysis", "src.storage")
    for arquivo in (RAIZ / "src" / "core").rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for proibido in proibidos:
            assert proibido not in texto, f"{arquivo.relative_to(RAIZ)} importa {proibido}"
