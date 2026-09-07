"""Gateway obrigatório para tools de impacto (RF13–RF15)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import ValidationError

from src.core.contracts.resolution import (
    ActionAttempt,
    ActionConfirmation,
    ConfirmationPolicy,
    EvidenceRef,
    PreActionCheck,
)
from src.core.contracts.tool import Tier, ToolDef, ToolResult
from src.core.contracts.trace import ExecutionTrace
from src.core.evidence import evidence_matches, resolve_field
from src.core.ports.tools import ToolProvider

__all__ = ["PreActionGuardProvider", "confirmation_fingerprint"]

_APP_FIELDS = {"evidence_cited"}


def confirmation_fingerprint(tool: str, arguments: dict) -> str:
    """Identifica de forma estável a ação exata que o usuário confirmou."""
    forwarded = {key: value for key, value in arguments.items() if key not in _APP_FIELDS}
    payload = json.dumps(
        {"tool": tool, "arguments": forwarded},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PreActionGuardProvider:
    """Valida política usando o trace corrente e só então delega ao provider real."""

    def __init__(
        self,
        inner: ToolProvider,
        trace: ExecutionTrace,
        *,
        confirmation_policy: ConfirmationPolicy = "auto_refuse",
        confirmation_grants: set[str] | frozenset[str] | None = None,
    ) -> None:
        self.inner = inner
        self.trace = trace
        self.confirmation_policy = confirmation_policy
        self.confirmation_grants = frozenset(confirmation_grants or ())

    @staticmethod
    def _guarded(tool: ToolDef) -> ToolDef:
        if tool.tier != "impact":
            return tool
        parameters = dict(tool.parameters)
        properties = dict(parameters.get("properties", {}))
        properties["evidence_cited"] = {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "properties": {
                    "tool": {"type": "string"},
                    "field": {"type": "string"},
                    "value": {"type": "string"},
                    "step": {"type": "integer", "minimum": 0},
                },
                "required": ["tool", "field", "value", "step"],
                "additionalProperties": False,
            },
        }
        required = list(parameters.get("required", []))
        if "evidence_cited" not in required:
            required.append("evidence_cited")
        parameters.update({"properties": properties, "required": required})
        return tool.model_copy(update={"parameters": parameters})

    def catalog(
        self, tiers: set[Tier] | None = None, only: set[str] | None = None
    ) -> list[ToolDef]:
        return [self._guarded(tool) for tool in self.inner.catalog(tiers=tiers, only=only)]

    def get(self, name: str) -> ToolDef | None:
        tool = self.inner.get(name)
        return self._guarded(tool) if tool is not None else None

    def _permissions(self) -> set[str]:
        for step in reversed(self.trace.steps):
            if step.tool != "getCurrentUser" or step.result is None or step.error is not None:
                continue
            # `getCurrentUser` devolve as permissões na raiz do resultado; as demais
            # tools vêm no envelope `{mode, notes, data}`. Procurar só em
            # `data.permissions` fazia esta checagem falhar **sempre**, e com ela
            # nenhuma ação de impacto podia ser autorizada por agente nenhum.
            value = None
            for caminho in ("permissions", "data.permissions", "data.data.permissions"):
                try:
                    value = resolve_field(step.result, caminho)
                except KeyError:
                    continue
                break
            if value is None:
                return set()
            return {str(item) for item in value} if isinstance(value, list) else set()
        return set()

    def _evidence(self, raw: Any) -> list[EvidenceRef]:
        if not isinstance(raw, list):
            return []
        references = []
        for item in raw:
            try:
                references.append(EvidenceRef.model_validate(item))
            except ValidationError:
                return []
        return references

    async def call(
        self,
        name: str,
        arguments: dict,
        *,
        call_id: str,
        user_id: str | None = None,
        seed: str | None = None,
    ) -> ToolResult:
        tool = self.inner.get(name)
        if tool is None or tool.tier != "impact":
            return await self.inner.call(
                name, arguments, call_id=call_id, user_id=user_id, seed=seed
            )

        failed: list[PreActionCheck] = []
        if not tool.required_permission or tool.required_permission not in self._permissions():
            failed.append("permission")
        digest = confirmation_fingerprint(name, arguments)
        if tool.requires_confirmation:
            confirmed = self.confirmation_policy == "auto_confirm" or (
                self.confirmation_policy == "explicit" and digest in self.confirmation_grants
            )
            source = (
                "policy"
                if self.confirmation_policy == "auto_confirm"
                else "user"
                if confirmed
                else "none"
            )
            self.trace.confirmations.append(
                ActionConfirmation(
                    tool=name,
                    arguments_digest=digest,
                    requested_at_step=len(self.trace.steps),
                    policy=self.confirmation_policy,
                    confirmed=confirmed,
                    source=source,
                    consequence=tool.description,
                )
            )
            if not confirmed:
                failed.append("confirmation")
        references = self._evidence(arguments.get("evidence_cited"))
        justification = arguments.get("justification")
        matching = [
            reference for reference in references if evidence_matches(reference, self.trace)
        ]
        if (
            not references
            or not isinstance(justification, str)
            or not justification.strip()
            or not any(
                reference.value.casefold() in justification.casefold() for reference in matching
            )
        ):
            failed.append("evidence")

        attempt = ActionAttempt(
            tool=name,
            args=dict(arguments),
            requested_at_step=len(self.trace.steps),
            pre_action_verdict="blocked" if failed else "pass",
            failed_preconditions=failed,
            external_call_emitted=False,
        )
        self.trace.action_attempts.append(attempt)
        if failed:
            return ToolResult(
                call_id=call_id,
                name=name,
                error=f"ação bloqueada; pré-condições ausentes: {', '.join(failed)}",
                error_class="behavior",
            )

        forwarded = {key: value for key, value in arguments.items() if key not in _APP_FIELDS}
        result = await self.inner.call(
            name, forwarded, call_id=call_id, user_id=user_id, seed=seed
        )
        attempt.external_call_emitted = result.external_call_emitted
        return result
