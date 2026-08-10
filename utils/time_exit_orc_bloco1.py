"""PROPOSITO: Gerador de saidas por tempo — unica saida permitida: shift(horizon).

SPEC: S41 — Bloco 1: Torneio do Passado
SAT: time_exit_orc_bloco1

Regra de ouro: saida EXCLUSIVAMENTE por expiracao no tempo.
NUNCA usar SL/TP/Trail. Apenas Close[t+horizon].
ROADMAP: FASE 3 (S41)
"""
from __future__ import annotations

import numpy as np


def generate_exits(
    entry_indices: int | list[int],
    data_length: int,
    horizon: int = 5,
) -> int | list[int]:
    """Gera indices de saida: entry_idx + horizon, clampados ao data_length-1.

    Args:
        entry_indices: indice(s) de entrada (barra do sinal).
        data_length: numero total de barras disponiveis.
        horizon: numero de barras ate a saida (5 = M5, 15 = M15).

    Returns:
        Indice(s) de saida. Sempre clampado a data_length-1.

    Raises:
        ValueError: se horizon <= 0 ou entry_idx < 0.
    """
    if horizon <= 0:
        raise ValueError(f"horizon deve ser > 0, recebido {horizon}")

    max_exit = data_length - 1

    # Normaliza numpy int scalar -> Python int
    if hasattr(entry_indices, "dtype") and hasattr(entry_indices, "item"):
        entry_indices = int(entry_indices.item())

    # Entrada unica (int ou numpy scalar)
    if isinstance(entry_indices, (int, np.integer)):
        eidx = int(entry_indices)
        if eidx < 0:
            raise ValueError(f"entry_idx deve ser >= 0, recebido {eidx}")
        return min(eidx + horizon, max_exit)

    # Lista de entradas
    if not entry_indices:
        return []

    exits = []
    for entry in entry_indices:
        if entry < 0:
            raise ValueError(f"entry_idx deve ser >= 0, recebido {entry}")
        exits.append(min(entry + horizon, max_exit))

    return exits
