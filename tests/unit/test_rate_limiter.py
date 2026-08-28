"""Token bucket local independente da concorrência dos workers."""

from __future__ import annotations

import asyncio
from datetime import date

import pytest

from src.core.errors import QuotaExhausted
from src.evaluation.runner.rate_limiter import LocalRateLimiter


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.waits: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)


async def test_concorrencia_nao_ultrapassa_rpm_configurado():
    clock = _Clock()
    limiter = LocalRateLimiter({"gemini": 15}, monotonic=clock.monotonic, sleep=clock.sleep)

    await asyncio.gather(*(limiter.acquire("gemini") for _ in range(3)))

    assert clock.waits == [4.0, 8.0]


async def test_consumo_diario_e_separado_por_provedor_e_dia():
    day = date(2026, 8, 27)
    limiter = LocalRateLimiter({"gemini": 15, "judge": 30}, today=lambda: day)

    assert await limiter.consume_daily("gemini", 2) == 2
    assert await limiter.consume_daily("gemini") == 3
    assert await limiter.consume_daily("judge") == 1


async def test_rejeita_provedor_desconhecido_e_custo_invalido():
    limiter = LocalRateLimiter({"gemini": 15})

    with pytest.raises(KeyError):
        await limiter.acquire("unknown")
    with pytest.raises(ValueError):
        await limiter.consume_daily("gemini", 0)


async def test_cota_diaria_bloqueia_antes_de_ultrapassar_e_reinicia_no_dia_seguinte(tmp_path):
    current = [date(2026, 8, 27)]
    limiter = LocalRateLimiter(
        {"gemini": 15},
        daily_limit_by_provider={"gemini": 2},
        daily_state_path=tmp_path / "quota.db",
        today=lambda: current[0],
    )

    assert await limiter.consume_daily("gemini", 2) == 2
    with pytest.raises(QuotaExhausted):
        await limiter.consume_daily("gemini")

    current[0] = date(2026, 8, 28)
    assert await limiter.consume_daily("gemini") == 1
    limiter.close()


async def test_cota_diaria_e_compartilhada_entre_processos_logicos(tmp_path):
    path = tmp_path / "quota.db"
    first = LocalRateLimiter(
        {"gemini": 15},
        daily_limit_by_provider={"gemini": 2},
        daily_state_path=path,
    )
    second = LocalRateLimiter(
        {"gemini": 15},
        daily_limit_by_provider={"gemini": 2},
        daily_state_path=path,
    )

    assert await first.consume_daily("gemini") == 1
    assert await second.consume_daily("gemini") == 2
    with pytest.raises(QuotaExhausted):
        await first.consume_daily("gemini")
    first.close()
    second.close()


def test_rejeita_limite_diario_invalido_ou_sem_provedor():
    with pytest.raises(ValueError):
        LocalRateLimiter({"gemini": 15}, daily_limit_by_provider={"judge": 10})
    with pytest.raises(ValueError):
        LocalRateLimiter({"gemini": 15}, daily_limit_by_provider={"gemini": 0})
    with pytest.raises(ValueError, match="daily_state_path"):
        LocalRateLimiter({"gemini": 15}, daily_limit_by_provider={"gemini": 10})
