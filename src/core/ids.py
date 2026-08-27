"""Hierarquia de identificadores — doc 09 §5.

| ID             | Escopo                  | Geração                        |
| :------------- | :---------------------- | :----------------------------- |
| `run_id`       | uma varredura           | ULID                           |
| `task_id`      | uma unidade de trabalho | determinístico (hash da tupla) |
| `execution_id` | uma tentativa da task   | ULID por tentativa             |
| `step_id`      | um passo do loop ReAct  | `{execution_id}.{n}`           |
| `call_id`      | uma chamada de tool     | `{step_id}.{k}`                |

`task_id` e `execution_id` são separados de propósito: a task é *o que precisa ser
feito*, a execução é *uma tentativa de fazer*. Colapsar os dois inflaria a taxa de erro
do agente com instabilidade de rede (doc 09 §5.1).
"""

from __future__ import annotations

import hashlib
import os
import time

__all__ = ["new_ulid", "task_id", "step_id", "call_id"]

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _encode(value: int, length: int) -> str:
    out = [""] * length
    for i in range(length - 1, -1, -1):
        out[i] = _CROCKFORD[value & 0x1F]
        value >>= 5
    return "".join(out)


def new_ulid() -> str:
    """ULID: 48 bits de timestamp + 80 bits aleatórios, ordenável por tempo.

    Ordenação lexicográfica == ordenação temporal, o que torna `run_id` e
    `execution_id` diretamente ordenáveis em listagens e nomes de arquivo.
    """
    ms = int(time.time() * 1000)
    randomness = int.from_bytes(os.urandom(10), "big")
    return _encode(ms, 10) + _encode(randomness, 16)


def task_id(
    run_id: str | None,
    case_id: str,
    architecture: str,
    seed: str | None,
    repetition: int,
) -> str:
    """Hash determinístico da tupla de trabalho — doc 09 §4.4.

    É o que torna reenfileirar idempotente: retomar uma rodada é
    `INSERT OR IGNORE` de todas as tasks, e as concluídas colidem.
    """
    chave = f"{run_id or 'notrun'}|{case_id}|{architecture}|{seed or 'noseed'}|{repetition}"
    return hashlib.sha256(chave.encode()).hexdigest()[:16]


def step_id(execution_id: str, step: int) -> str:
    return f"{execution_id}.{step}"


def call_id(execution_id: str, step: int, k: int) -> str:
    return f"{execution_id}.{step}.{k}"
