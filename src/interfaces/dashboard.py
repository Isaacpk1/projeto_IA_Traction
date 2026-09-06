"""Gera o relatório visual do experimento a partir do quadro de análise.

O front é uma view do que :mod:`src.analysis.report` calcula, nunca uma
segunda implementação. HTML, CSS e JavaScript vivem em ``interfaces.web`` para
serem editáveis, revisáveis e distribuídos junto com o pacote Python.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

__all__ = ["escrever_dashboard", "render_dashboard"]

_WEB_PACKAGE = "src.interfaces.web"

_AVISO = """<div class="note caveat"><p><b>Rodada incompleta.</b> {feitas} de {alvo} execuções
registradas. Os números abaixo são parciais e não constituem o veredito final.</p></div>"""


@lru_cache(maxsize=1)
def _frontend() -> tuple[str, str, str]:
    """Lê a fonte versionada do dashboard empacotada com a aplicação."""
    raiz = files(_WEB_PACKAGE)
    ler = lambda nome: raiz.joinpath(nome).read_text(encoding="utf-8")  # noqa: E731
    return (ler("index.html"), ler("app.css"), ler("app.js"))


def _json_para_script(valor: object) -> str:
    """Serializa os dados sem permitir que conteúdo feche a tag script."""
    return json.dumps(valor, ensure_ascii=False).replace("</", "<\\/")


def render_dashboard(
    relatorio: dict,
    *,
    execucoes: list[dict] | None = None,
    commit: str = "unknown",
    prompt_version: str = "1.1.0",
    gerado: str = "",
    alvo: int | None = None,
) -> str:
    """Devolve o HTML completo com o relatório e as execuções embutidos."""
    template, css, js = _frontend()
    total = relatorio.get("execucoes", 0)
    aviso = ""
    if alvo is not None and total < alvo:
        aviso = _AVISO.format(feitas=total, alvo=alvo)

    substituicoes = {
        "__DASHBOARD_CSS__": css,
        "__DASHBOARD_JS__": js,
        "__REPORT_JSON__": _json_para_script(relatorio),
        "__EXECUTIONS_JSON__": _json_para_script(execucoes or []),
        "__RUN_ID__": str(relatorio.get("run_id") or "—"),
        "__EXECUTION_COUNT__": str(total),
        "__COMMIT__": commit,
        "__PROMPT_VERSION__": prompt_version,
        "__GENERATED_AT__": gerado,
        "__NOTICE__": aviso,
    }
    for marcador, valor in substituicoes.items():
        template = template.replace(marcador, valor)
    return template


def escrever_dashboard(destino: str | Path, html: str) -> Path:
    caminho = Path(destino)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(html, encoding="utf-8")
    return caminho
