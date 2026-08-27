"""Execução HTTP das tools. **Zero conhecimento de domínio (RNF06).**

O executor monta a requisição a partir da proveniência que o parser extraiu — quais
argumentos vão no path, quais na query, quais no corpo — e nunca a partir de uma tabela
de endpoints escrita à mão.

Duas decisões que valem registro:

- **Erro do upstream não levanta.** Devolve `ToolResult` com `error` preenchido, para que
  a falha vire observação no trace e o agente possa reagir a ela. Levantar derrubaria o
  loop e converteria um 404 legítimo em falha de execução.
- **O `seed` é injetado aqui**, não exposto ao modelo. É parâmetro de determinismo do
  experimento; deixá-lo no schema convidaria o agente a inventar valores e contaminaria a
  variável independente.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from jsonschema import Draft202012Validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from src.core.contracts.tool import ToolDef, ToolResult
from src.core.errors import classify

__all__ = ["HttpExecutor", "build_request"]

#: Erros de transporte que justificam nova tentativa. 4xx nunca entra aqui: repetir uma
#: requisição malformada só gasta tempo e cota.
_RETRIABLE = (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError)


def build_request(
    tool: ToolDef, arguments: dict[str, Any], *, seed: str | None = None
) -> tuple[str, str, dict[str, Any], dict[str, Any] | None]:
    """Monta `(método, caminho, query, corpo)` a partir dos argumentos do modelo."""
    erros = sorted(
        Draft202012Validator(tool.parameters).iter_errors(arguments),
        key=lambda erro: list(erro.absolute_path),
    )
    if erros:
        erro = erros[0]
        local = ".".join(str(parte) for parte in erro.absolute_path) or "<raiz>"
        raise ValueError(f"{tool.name}: argumentos inválidos em {local}: {erro.message}")

    caminho = tool.path
    query: dict[str, Any] = {}
    corpo: dict[str, Any] = {}

    for nome in tool.path_params:
        valor = arguments.get(nome)
        if valor is None:
            raise ValueError(f"{tool.name}: parâmetro de path ausente: {nome}")
        caminho = caminho.replace("{" + nome + "}", str(valor))

    for nome in tool.query_params:
        if nome in arguments and arguments[nome] is not None:
            query[nome] = arguments[nome]

    for nome in tool.body_params:
        if nome in arguments and arguments[nome] is not None:
            corpo[nome] = arguments[nome]

    if tool.accepts_seed and seed:
        query["seed"] = seed

    tem_corpo = tool.method in ("post", "put", "patch")
    return tool.method, caminho, query, (corpo if tem_corpo else None)


class HttpExecutor:
    """Cliente assíncrono da API. Assíncrono porque o runner é concorrente."""

    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 30.0,
        max_attempts: int = 3,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_attempts = max_attempts
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url, timeout=httpx.Timeout(timeout)
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> HttpExecutor:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def execute(
        self,
        tool: ToolDef,
        arguments: dict[str, Any],
        *,
        call_id: str,
        user_id: str | None = None,
        seed: str | None = None,
    ) -> ToolResult:
        inicio = time.perf_counter()
        try:
            metodo, caminho, query, corpo = build_request(tool, arguments, seed=seed)
        except ValueError as exc:
            # argumento faltando é erro de contrato: o modelo não preencheu o schema
            return ToolResult(
                call_id=call_id,
                name=tool.name,
                error=str(exc),
                error_class="contract",
                latency_ms=(time.perf_counter() - inicio) * 1000,
            )

        headers = {"x-user-id": user_id} if user_id else {}

        try:
            resposta = await self._send(metodo, caminho, query, corpo, headers)
        except Exception as exc:
            return ToolResult(
                call_id=call_id,
                name=tool.name,
                error=f"{type(exc).__name__}: {exc}",
                error_class=classify(exc),
                latency_ms=(time.perf_counter() - inicio) * 1000,
            )

        latencia = (time.perf_counter() - inicio) * 1000
        dados = _parse_body(resposta)

        if resposta.status_code >= 400:
            return ToolResult(
                call_id=call_id,
                name=tool.name,
                data=dados,
                error=_error_message(resposta, dados),
                # 429 é do ambiente; 4xx é decisão do agente (permissão, argumento) e
                # portanto comportamento observado, não falha de infraestrutura.
                error_class="infra" if resposta.status_code in (429, 502, 503, 504) else "behavior",
                status_code=resposta.status_code,
                latency_ms=latencia,
            )

        return ToolResult(
            call_id=call_id,
            name=tool.name,
            data=dados,
            status_code=resposta.status_code,
            latency_ms=latencia,
        )

    async def _send(
        self,
        metodo: str,
        caminho: str,
        query: dict[str, Any],
        corpo: dict[str, Any] | None,
        headers: dict[str, str],
    ) -> httpx.Response:
        @retry(
            retry=retry_if_exception_type(_RETRIABLE),
            stop=stop_after_attempt(self.max_attempts),
            wait=wait_exponential_jitter(initial=0.5, max=8.0),
            reraise=True,
        )
        async def _tentar() -> httpx.Response:
            return await self._client.request(
                metodo.upper(),
                caminho,
                params=query or None,
                json=corpo,
                headers=headers or None,
            )

        return await _tentar()


def _parse_body(resposta: httpx.Response) -> dict[str, Any] | None:
    try:
        corpo = resposta.json()
    except Exception:
        texto = resposta.text
        return {"raw": texto} if texto else None
    # Alguns endpoints devolvem lista no topo; o trace guarda dicionários, então a
    # lista é embrulhada em vez de descartada.
    return corpo if isinstance(corpo, dict) else {"items": corpo}


def _error_message(resposta: httpx.Response, dados: dict[str, Any] | None) -> str:
    if isinstance(dados, dict):
        for chave in ("message", "detail", "error"):
            valor = dados.get(chave)
            if isinstance(valor, str):
                return f"HTTP {resposta.status_code}: {valor}"
    return f"HTTP {resposta.status_code}"
