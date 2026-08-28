"""Classificação de falhas externas não pode contaminar métricas de comportamento."""

from src.core.errors import classify


class ClientError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def test_client_error_de_rate_limit_e_5xx_e_infra():
    assert classify(ClientError(429)) == "infra"
    assert classify(ClientError(503)) == "infra"


def test_client_error_4xx_sem_mapeamento_permanece_comportamento():
    assert classify(ClientError(400)) == "behavior"
