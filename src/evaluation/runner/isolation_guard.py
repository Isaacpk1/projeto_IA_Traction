"""Guarda bloqueante contra vazamento do gabarito para a execução (RNF02)."""

from __future__ import annotations

import contextvars
import os
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from src.core.contracts.golden import GOLDEN_ONLY_FIELDS
from src.core.errors import IsolationViolation

__all__ = ["IsolationGuard"]

_ACTIVE_FORBIDDEN: contextvars.ContextVar[tuple[Path, ...]] = contextvars.ContextVar(
    "agent_forbidden_paths", default=()
)
_AUDIT_HOOK_INSTALLED = False


def _is_forbidden(candidate: Path, forbidden: tuple[Path, ...]) -> bool:
    return any(candidate == target or target in candidate.parents for target in forbidden)


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event != "open" or not (forbidden := _ACTIVE_FORBIDDEN.get()) or not args:
        return
    raw = args[0]
    if isinstance(raw, int):
        return
    try:
        candidate = Path(os.fsdecode(os.fspath(raw))).resolve(strict=False)
    except (TypeError, ValueError, OSError):
        return
    if _is_forbidden(candidate, forbidden):
        raise IsolationViolation(f"acesso do agente ao gabarito bloqueado: {candidate}")


def _install_audit_hook() -> None:
    global _AUDIT_HOOK_INSTALLED
    if not _AUDIT_HOOK_INSTALLED:
        sys.addaudithook(_audit)
        _AUDIT_HOOK_INSTALLED = True


class IsolationGuard:
    def __init__(self, forbidden_paths: list[str | Path] | None = None) -> None:
        root = Path(__file__).resolve().parents[3]
        defaults = [
            root / "eval",
            root / "inteli-tractian-project" / "eval",
            root / "docs" / "test-scenarios.md",
            root / "data" / "cases.parquet",
            root / "artifacts" / "golden",
        ]
        self.forbidden_paths = tuple(
            Path(path).resolve(strict=False) for path in (forbidden_paths or defaults)
        )
        _install_audit_hook()

    def check(self, value: Any) -> None:
        leaked = self._find(value)
        if leaked:
            raise IsolationViolation(f"gabarito exposto à execução: {', '.join(sorted(leaked))}")

    def _find(self, value: Any) -> set[str]:
        if isinstance(value, BaseModel):
            return self._find(value.model_dump())
        if isinstance(value, dict):
            keys = {str(key) for key in value}.intersection(GOLDEN_ONLY_FIELDS)
            for child in value.values():
                keys.update(self._find(child))
            return keys
        if isinstance(value, list | tuple | set):
            leaked: set[str] = set()
            for child in value:
                leaked.update(self._find(child))
            return leaked
        return set()

    @contextmanager
    def protect_filesystem(self) -> Iterator[None]:
        """Bloqueia aberturas de arquivos de gabarito durante o turno do agente.

        O audit hook cobre ``open``, ``pathlib.Path.open`` e ``os.open``. O estado é um
        ``ContextVar`` para que workers assíncronos concorrentes não desativem a guarda
        uns dos outros nem bloqueiem o carregamento legítimo feito antes do turno.
        """
        token = _ACTIVE_FORBIDDEN.set(self.forbidden_paths)
        try:
            yield
        finally:
            _ACTIVE_FORBIDDEN.reset(token)
