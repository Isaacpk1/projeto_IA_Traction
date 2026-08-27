"""Limitador local por provedor: intervalo fixo e contador diário — ADR-09."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import date

__all__ = ["LocalRateLimiter"]


class LocalRateLimiter:
    """Serializa a reserva de slots; a espera ocorre fora do lock."""

    def __init__(
        self,
        rpm_by_provider: dict[str, int],
        *,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        today: Callable[[], date] = date.today,
    ) -> None:
        if not rpm_by_provider or any(rpm <= 0 for rpm in rpm_by_provider.values()):
            raise ValueError("todo provedor precisa de rpm positivo")
        self._intervals = {provider: 60.0 / rpm for provider, rpm in rpm_by_provider.items()}
        self._next: dict[str, float] = {}
        self._daily: dict[tuple[date, str], int] = {}
        self._monotonic = monotonic
        self._sleep = sleep
        self._today = today
        self._lock = asyncio.Lock()

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
            self._daily[key] = self._daily.get(key, 0) + cost
            return self._daily[key]
