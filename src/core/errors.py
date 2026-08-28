"""Taxonomia de falhas — doc 09 §6.

A separação entre `infra` e `behavior` é a diferença entre medir o agente e medir a
internet. Só `behavior` conta como resultado experimental.

| Classe      | Destino da task                       | Conta como resultado? |
| :---------- | :------------------------------------ | :-------------------- |
| `infra`     | volta a `pending`, novo execution_id  | não — descartada      |
| `behavior`  | `done` — execução registrada          | **sim**               |
| `contract`  | `failed` + alerta                     | não — bug a investigar|
| `budget`    | volta a `pending`, sem incrementar    | não — retoma no dia+1 |
"""

from __future__ import annotations

from typing import Literal

ErrorClass = Literal["infra", "behavior", "contract", "budget"]

__all__ = [
    "ErrorClass",
    "AgentError",
    "InfraError",
    "RateLimitError",
    "UpstreamTimeout",
    "UpstreamUnavailable",
    "ContractError",
    "UnknownToolError",
    "ToolValidationError",
    "BudgetError",
    "QuotaExhausted",
    "BehaviorError",
    "GuardBlocked",
    "IsolationViolation",
    "CompositionViolation",
    "InvalidArmError",
    "classify",
]


class AgentError(Exception):
    """Raiz da taxonomia. Toda exceção do sistema herda daqui."""

    error_class: ErrorClass = "behavior"


# --- infra: falha do ambiente, nunca resultado experimental ------------------


class InfraError(AgentError):
    error_class: ErrorClass = "infra"


class RateLimitError(InfraError):
    """429 do provedor — a task volta para a fila com backoff."""


class UpstreamTimeout(InfraError):
    """Timeout na API industrial ou no provedor de LLM."""


class UpstreamUnavailable(InfraError):
    """5xx ou conexão perdida."""


# --- contract: bug nosso, não do agente e não do ambiente --------------------


class ContractError(AgentError):
    error_class: ErrorClass = "contract"


class UnknownToolError(ContractError):
    """O modelo chamou uma tool que não existe no catálogo composto."""


class ToolValidationError(ContractError):
    """Argumentos ou retorno fora do schema declarado (RNF13)."""


# --- budget: ausência de recurso, não falha da task --------------------------


class BudgetError(AgentError):
    error_class: ErrorClass = "budget"


class QuotaExhausted(BudgetError):
    """Cota diária do provedor esgotada — não incrementa `attempts`."""


# --- behavior: o resultado experimental --------------------------------------


class BehaviorError(AgentError):
    error_class: ErrorClass = "behavior"


class GuardBlocked(BehaviorError):
    """Guard determinístico barrou a ação ou a entrega. É comportamento medido."""

    def __init__(self, message: str, failed_checks: list[str] | None = None) -> None:
        super().__init__(message)
        self.failed_checks = failed_checks or []


# --- invariantes: abortam o processo, não são resultado ----------------------


class IsolationViolation(AgentError):
    """RNF02 — gabarito acessível ao agente. Aborta a suíte inteira (P5)."""

    error_class: ErrorClass = "contract"


class CompositionViolation(AgentError):
    """RNF05 / RF12 — papel de investigação com tool de `tier: impact`."""

    error_class: ErrorClass = "contract"


class InvalidArmError(AgentError):
    """RF33 — combinação (arquitetura, atribuição de modelo) fora dos braços previstos."""

    error_class: ErrorClass = "contract"


def classify(exc: BaseException) -> ErrorClass:
    """Classifica uma exceção qualquer na taxonomia — doc 09 §6.

    Exceções nossas declaram a própria classe. Exceções de terceiros (httpx,
    asyncio, SDKs) são mapeadas pelo tipo. O default é `behavior`, porque uma
    falha não reconhecida vinda do loop do agente é comportamento até prova
    em contrário — o inverso descartaria resultado legítimo da análise.
    """
    if isinstance(exc, AgentError):
        return exc.error_class
    if isinstance(exc, TimeoutError | ConnectionError | OSError):
        return "infra"
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status == 429 or isinstance(status, int) and status >= 500:
        return "infra"
    # httpx e SDKs de provedor não são importáveis aqui (core/ não importa nada):
    # a identificação é pelo nome do tipo.
    name = type(exc).__name__
    if name in {
        "ReadTimeout",
        "ConnectTimeout",
        "PoolTimeout",
        "ConnectError",
        "RemoteProtocolError",
        "APIConnectionError",
        "InternalServerError",
        "ServiceUnavailableError",
    }:
        return "infra"
    if name in {"RateLimitError", "TooManyRequests"}:
        return "infra"
    if name in {"ValidationError", "ResponseValidationError"}:
        return "contract"
    return "behavior"
