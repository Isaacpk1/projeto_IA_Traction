"""Resolução determinística de referências de evidência no trace."""

from __future__ import annotations

import json
import re
from typing import Any

from src.core.contracts.resolution import EvidenceRef
from src.core.contracts.trace import ExecutionTrace

__all__ = ["evidence_matches", "normalizar_tool", "observation_view", "resolve_field"]


#: `a[0].b` e `a.0.b` designam a mesma coisa. O prompt nunca fixou a sintaxe, e
#: recusar a forma com colchetes mediria a notação escolhida pelo modelo, não se a
#: evidência existe.
_INDICE = re.compile(r"\[(\d+)\]")


def resolve_field(value: Any, path: str) -> Any:
    """Percorre objetos JSON por caminho pontuado; índices de lista são numéricos."""
    current = value
    for part in _INDICE.sub(r".\1", path).split("."):
        if not part:
            continue
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            raise KeyError(path)
    return current


def observation_view(result: Any) -> dict:
    """A forma em que o passo chega ao modelo — doc 09, loop ReAct.

    O trace guarda `ToolResult.data`; o agente recebe esse valor **embrulhado**
    junto de erro e status. Uma citação como `data.data.state` está correta do
    ponto de vista de quem a escreveu, e resolvê-la só contra a forma do trace
    reprovaria a referência por diferença de camada, não por evidência ausente.
    """
    return {"data": result, "error": None, "error_class": None, "status_code": None}


def _text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _mesmo_valor(observado: Any, citado: str) -> bool:
    """Compara o fato, não a formatação com que foi escrito.

    `["read", "action_low"]` e `["read","action_low"]` são o mesmo dado; `12` e
    `12.0` também. Reprovar por espaço depois da vírgula mediria a serialização
    do modelo, não se a evidência existe — e o custo desse rigor é bloquear uma
    entrega cuja conclusão está correta.
    """
    if _text(observado) == citado:
        return True
    alvo = citado.strip()
    try:
        return json.loads(json.dumps(observado)) == json.loads(alvo)
    except (ValueError, TypeError):
        pass
    if isinstance(observado, bool):
        return alvo.lower() == str(observado).lower()
    if isinstance(observado, int | float):
        try:
            return float(alvo) == float(observado)
        except ValueError:
            return False
    return False


#: O Gemini expõe as tools sob um namespace e nomeia o retorno com sufixo. O modelo
#: cita no dialeto que vê — `default_api.getBaseline`, `getBaseline_response` — e
#: recusar isso mediria a convenção do SDK, não se a evidência existe. A identidade
#: da ferramenta continua inequívoca depois de tirar o enfeite.
_PREFIXO_SDK = re.compile(r"^(?:default_api|functions|tool_code)\.")
_SUFIXO_SDK = re.compile(r"_(?:response|result|output)$")


def normalizar_tool(nome: str) -> str:
    """Reduz o nome citado ao identificador da ferramenta."""
    return _SUFIXO_SDK.sub("", _PREFIXO_SDK.sub("", nome or "")).strip()


def _caminhos(field: str, tool: str) -> list[str]:
    """Variações do caminho que designam o mesmo campo.

    O modelo às vezes prefixa o caminho com o nome da variável de resposta —
    `getAsset_response.data.state`. Isso é endereço do SDK, não do dado.
    """
    caminhos = [field]
    for prefixo in (f"{tool}_response.", f"{tool}.", "default_api."):
        if field.startswith(prefixo):
            caminhos.append(field[len(prefixo):])
    return caminhos


def evidence_matches(reference: EvidenceRef, trace: ExecutionTrace) -> bool:
    """Confirma passo, tool, caminho e valor — não apenas a existência da tool."""
    alvo = normalizar_tool(reference.tool)
    step = next((item for item in trace.steps if item.step == reference.step), None)
    if step is None or normalizar_tool(step.tool or "") != alvo or step.result is None:
        return False
    # As duas formas da mesma observação: a que o trace grava e a que o agente viu.
    # O passo e a tool continuam exigidos — afrouxá-los mudaria a métrica, não a
    # corrigiria.
    for shape in (step.result, observation_view(step.result)):
        for caminho in _caminhos(reference.field, alvo):
            try:
                actual = resolve_field(shape, caminho)
            except (KeyError, TypeError):
                continue
            if _mesmo_valor(actual, reference.value):
                return True
    return False
