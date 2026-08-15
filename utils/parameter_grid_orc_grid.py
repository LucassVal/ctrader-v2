"""PROPOSITO: parameter_grid_orc_grid.py — SAT S43.1: build_parameter_grid().
SPEC: S43 (orc_grid.md)
ROADMAP: S43 Grid/Walk-Forward

Produto cartesiano de parametros com controle de explosao combinatória.
Max 200 combos por grid (Pareto 80/20).
"""
from __future__ import annotations

import itertools
from typing import Any

# -- Grid definitions (SPEC S43) --

BUY_GRID: dict[str, list[Any]] = {
    "rsi_period": [8, 14, 21],
    "rsi_threshold": [25, 30],
    "macd_fast": [10, 14, 18],
    "adx_period": [14, 20],
    "adx_threshold": [20, 25],
}
# Total: 3x2x3x2x2 = 72 combos

SELL_GRID: dict[str, list[Any]] = {
    "rsi_period": [8, 14, 21],
    "rsi_threshold": [65, 70, 75],
    "adx_period": [14, 20],
    "adx_threshold": [20, 25],
}
# Total: 4x2x2x2x2 = 64 combos

FORCE_GRID: dict[str, list[Any]] = {
    "tick_vol_percentile": [70, 80, 90],
    "roc_period": [5, 10, 14],
    "roc_threshold": [0.3, 0.5, 0.8, 1.0],
}
# Total: 3x3x4 = 36 combos

MAX_COMBOS = 200


def _cartesian(grid: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """Produto cartesiano de todos os parametros via itertools.product."""
    keys = list(grid.keys())
    values = list(grid.values())
    combos: list[dict[str, Any]] = []
    for combo in itertools.product(*values):
        combos.append(dict(zip(keys, combo, strict=False)))
    return combos


def _pareto_reduce(combos: list[dict[str, Any]], max_n: int = MAX_COMBOS) -> list[dict[str, Any]]:
    """Reduz grid para max_n combos usando diversidade de parametros (Pareto 80/20).

    Prioriza combos que cobrem mais valores unicos de cada parametro.
    Usa spaced sampling: divide o espaco igualmente entre os parametros.
    """
    if len(combos) <= max_n:
        return combos

    # Estrategia: samplear uniformemente do espaco ordenado
    # Ordena por "distancia do centro" para garantir cobertura do espaco
    keys = list(combos[0].keys())
    # Constroi score de diversidade: valores nos extremos pontuam mais
    scored = []
    for combo in combos:
        score = 0.0
        for k in keys:
            vals = sorted({c[k] for c in combos})
            if len(vals) <= 1:
                continue
            idx = vals.index(combo[k])
            # Valores nos extremos (0 e len-1) = score alto, centro = score baixo
            score += abs(idx - (len(vals) - 1) / 2) / max(len(vals) - 1, 1)
        scored.append((score, combo))

    # Ordena por score decrescente (mais diverso primeiro)
    scored.sort(key=lambda x: -x[0])

    # Sampleia uniformemente do espaco ordenado
    step = len(scored) / max_n
    selected: list[dict[str, Any]] = []
    for i in range(max_n):
        idx = min(int(i * step), len(scored) - 1)
        selected.append(scored[idx][1])

    return selected


def build_parameter_grid(grid_type: str = "buy") -> list[dict[str, Any]]:
    """Constroi grid de parametros para walk-forward validation.

    Args:
        grid_type: "buy", "sell", "force", or "all"

    Returns:
        list[dict]: Lista de combinacoes de parametros (max 200 por tipo)

    Raises:
        ValueError: se grid_type invalido
    """
    valid_types = {"buy", "sell", "force", "all"}

    if grid_type not in valid_types:
        raise ValueError(
            f"Tipo de grid invalido: '{grid_type}'. Validos: {sorted(valid_types)}"
        )

    if grid_type == "buy":
        combos = _cartesian(BUY_GRID)
        return _pareto_reduce(combos, MAX_COMBOS)

    if grid_type == "sell":
        return _cartesian(SELL_GRID)  # 64 combos, no reduction needed

    if grid_type == "force":
        return _cartesian(FORCE_GRID)  # 36 combos, no reduction needed

    # "all": combina buy (reduzido) + sell + force
    buy_combos = _pareto_reduce(_cartesian(BUY_GRID), 100)
    sell_combos = _cartesian(SELL_GRID)
    force_combos = _cartesian(FORCE_GRID)
    # Merge: adiciona prefixo de categoria para evitar conflito de keys
    merged: list[dict[str, Any]] = []
    for c in buy_combos:
        merged.append({"category": "buy", **c})
    for c in sell_combos:
        merged.append({"category": "sell", **c})
    for c in force_combos:
        merged.append({"category": "force", **c})
    return merged
