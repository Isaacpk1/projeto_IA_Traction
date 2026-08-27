from __future__ import annotations

import os
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]

#: Material fornecido pela TRACTIAN, no repositório vizinho.
MATERIAL = RAIZ.parent / "api_traction" / "inteli-tractian-project" / "agent-input"

#: O contrato fornecido vive no repositório da API industrial, ao lado deste. O caminho
#: é sobrescrevível para que o CI e outra máquina não dependam do layout local.
CONTRACT_PATH = Path(
    os.environ.get(
        "TRACTIAN_CONTRACT_PATH",
        MATERIAL / "api-contract.openapi.yaml",
    )
)

CASES_PATH = Path(
    os.environ.get(
        "TRACTIAN_CASES_PATH",
        MATERIAL / "cases.json",
    )
)


@pytest.fixture(scope="session")
def contract_path() -> Path:
    if not CONTRACT_PATH.exists():
        pytest.skip(f"contrato não encontrado em {CONTRACT_PATH}")
    return CONTRACT_PATH


@pytest.fixture(scope="session")
def cases_path() -> Path:
    if not CASES_PATH.exists():
        pytest.skip(f"cases.json não encontrado em {CASES_PATH}")
    return CASES_PATH


@pytest.fixture(scope="session")
def registry(contract_path: Path):
    from src.tools.provider import build_registry

    reg, _ = build_registry(contract_path)
    return reg


@pytest.fixture(scope="session")
def overlay():
    from src.tools.overlay import load_overlay

    return load_overlay()
