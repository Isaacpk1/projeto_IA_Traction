"""Guardrail determinístico aplicado entre ``Resolution`` e ``Delivered`` (RF44)."""

from __future__ import annotations

import re

from src.core.contracts.resolution import Delivered, GuardCheck, Resolution
from src.core.contracts.trace import ExecutionTrace
from src.core.evidence import evidence_matches, resolve_field

__all__ = ["PreDeliveryGuard"]

_FORBIDDEN = re.compile(r"\bISO\s*10816\b|tabela\s+por\s+classe", re.IGNORECASE)
_NUMERIC_THRESHOLD = re.compile(
    r"\b(?:limiar|threshold)\b[^.\n]{0,40}\b\d+(?:[.,]\d+)?", re.IGNORECASE
)


class PreDeliveryGuard:
    @staticmethod
    def _has_baseline(trace: ExecutionTrace) -> bool:
        for step in trace.steps:
            if step.result is None or step.error is not None or step.mode != "complete":
                continue
            if step.tool == "getBaseline":
                return True
            if step.tool == "getRmsSeries":
                try:
                    if resolve_field(step.result, "data.alarm_threshold") is not None:
                        return True
                except KeyError:
                    pass
        return False

    @staticmethod
    def _fundamentada(resolution: Resolution, trace: ExecutionTrace) -> bool:
        """V1 — a conclusão se apoia em evidência verificável?

        A pergunta é sobre a **conclusão**, não sobre cada citação isolada. Uma
        resolução com cinco de seis referências conferindo está fundamentada; a
        sexta mal escrita não a torna infundada, e recusá-la por isso descarta
        trabalho correto — foi o que fez o sistema escalar quase tudo.

        `agir` é a exceção e continua exigindo todas. Ação sobre o ativo é
        irreversível na prática, e ali o custo de aceitar uma referência frouxa
        é maior que o de escalar à toa.
        """
        referencias = resolution.evidence_cited
        if not referencias:
            # Sem citação nenhuma não há o que verificar; V2 e V3 seguem valendo.
            return True
        conferem = sum(evidence_matches(r, trace) for r in referencias)
        if resolution.decision == "agir":
            return conferem == len(referencias)
        return conferem * 2 > len(referencias)

    def check(self, trace: ExecutionTrace) -> Delivered:
        resolution = trace.resolution
        if resolution is None:
            return Delivered(
                decision="escalar",
                guardrail_verdict="blocked",
                guardrail_failed_checks=["V1"],
                guardrail_reason="execução sem resolução",
            )

        failed: list[GuardCheck] = []
        if not self._fundamentada(resolution, trace):
            failed.append("V1")

        text = "\n".join(
            filter(
                None,
                [
                    resolution.justification,
                    resolution.action_taken,
                    *resolution.unverified,
                    *resolution.conflicts,
                ],
            )
        )
        if _FORBIDDEN.search(text):
            failed.append("V2")

        if _NUMERIC_THRESHOLD.search(text) and not self._has_baseline(trace):
            failed.append("V3")

        if failed:
            return Delivered(
                decision="escalar",
                guardrail_verdict="blocked",
                guardrail_failed_checks=failed,
                guardrail_reason="resolução bloqueada pelo guardrail determinístico",
            )
        return Delivered(decision=resolution.decision, guardrail_verdict="pass")

    def apply(self, trace: ExecutionTrace) -> Delivered:
        delivered = self.check(trace)
        trace.delivered = delivered
        return delivered
