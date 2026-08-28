"""Limitador por provedor: intervalo local e cota diária SQLite compartilhada — ADR-09."""

from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Awaitable, Callable
from datetime import date
from pathlib import Path

from src.core.errors import QuotaExhausted

__all__ = ["LocalRateLimiter"]


class LocalRateLimiter:
    """Serializa slots no processo e reserva a cota diária entre processos.

    O espaçamento por minuto continua local ao processo. A garantia que não admite
    ultrapassagem — o teto diário — usa SQLite e transação imediata quando configurada.
    """

    def __init__(
        self,
        rpm_by_provider: dict[str, int],
        *,
        daily_limit_by_provider: dict[str, int] | None = None,
        daily_state_path: str | Path | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        today: Callable[[], date] = date.today,
    ) -> None:
        if not rpm_by_provider or any(rpm <= 0 for rpm in rpm_by_provider.values()):
            raise ValueError("todo provedor precisa de rpm positivo")
        self._intervals = {provider: 60.0 / rpm for provider, rpm in rpm_by_provider.items()}
        limits = daily_limit_by_provider or {}
        unknown = set(limits) - set(rpm_by_provider)
        if unknown:
            raise ValueError(f"limite diário para provedor sem RPM: {sorted(unknown)}")
        if any(limit <= 0 for limit in limits.values()):
            raise ValueError("todo limite diário precisa ser positivo")
        if limits and daily_state_path is None:
            raise ValueError("limite diário exige daily_state_path compartilhado e durável")
        self._daily_limits = dict(limits)
        self._daily_db: sqlite3.Connection | None = None
        if daily_state_path is not None:
            self._daily_db = sqlite3.connect(
                str(daily_state_path), timeout=30, isolation_level=None
            )
            self._daily_db.execute("PRAGMA journal_mode=WAL")
            self._daily_db.execute(
                """
                CREATE TABLE IF NOT EXISTS daily_quota (
                    day TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    consumed INTEGER NOT NULL,
                    PRIMARY KEY (day, provider)
                )
                """
            )
        self._next: dict[str, float] = {}
        self._daily: dict[tuple[date, str], int] = {}
        self._monotonic = monotonic
        self._sleep = sleep
        self._today = today
        self._lock = asyncio.Lock()

    def close(self) -> None:
        if self._daily_db is not None:
            self._daily_db.close()
            self._daily_db = None

    @staticmethod
    def _cost(cost: int) -> None:
        if cost <= 0:
            raise ValueError("cost deve ser positivo")

    async def acquire(self, provider: str, cost: int = 1) -> None:
        self._cost(cost)
        try:
            interval = self._intervals[provider]
        except KeyError as exc:
            raise KeyError(f"provedor sem limite configurado: {provider}") from exc

        async with self._lock:
            now = self._monotonic()
            reserved = max(now, self._next.get(provider, now))
            wait = max(0.0, reserved - now)
            self._next[provider] = reserved + interval * cost
        if wait:
            await self._sleep(wait)

    async def consume_daily(self, provider: str, cost: int = 1) -> int:
        self._cost(cost)
        if provider not in self._intervals:
            raise KeyError(f"provedor sem limite configurado: {provider}")
        async with self._lock:
            key = (self._today(), provider)
            if self._daily_db is not None:
                return self._consume_persistent(key[0], provider, cost)
            consumed = self._daily.get(key, 0)
            limit = self._daily_limits.get(provider)
            if limit is not None and consumed + cost > limit:
                raise QuotaExhausted(
                    f"cota diária de {provider} esgotada: {consumed}/{limit}"
                )
            self._daily[key] = consumed + cost
            return self._daily[key]

    def _consume_persistent(self, day: date, provider: str, cost: int) -> int:
        db = self._daily_db
        if db is None:  # pragma: no cover - chamado somente pelo ramo persistente
            raise RuntimeError("estado diário não inicializado")
        db.execute("BEGIN IMMEDIATE")
        try:
            row = db.execute(
                "SELECT consumed FROM daily_quota WHERE day = ? AND provider = ?",
                (day.isoformat(), provider),
            ).fetchone()
            consumed = int(row[0]) if row else 0
            limit = self._daily_limits.get(provider)
            if limit is not None and consumed + cost > limit:
                raise QuotaExhausted(
                    f"cota diária de {provider} esgotada: {consumed}/{limit}"
                )
            updated = consumed + cost
            db.execute(
                """
                INSERT INTO daily_quota(day, provider, consumed) VALUES (?, ?, ?)
                ON CONFLICT(day, provider) DO UPDATE SET consumed = excluded.consumed
                """,
                (day.isoformat(), provider, updated),
            )
            db.commit()
            return updated
        except BaseException:
            db.rollback()
            raise
