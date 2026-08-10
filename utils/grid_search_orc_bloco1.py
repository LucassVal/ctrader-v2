"""PROPOSITO: Grid search de parametros — busca combinatoria via itertools.product.

SPEC: S41 — Bloco 1: Torneio do Passado / S43 — Grid de Parametros
SAT: grid_search_orc_bloco1

R-USE: itertools.product para grid cartesiano.
Controle: max 200 combos (Pareto 80/20).
Cada combo -> placeholder MAE. O orquestrador injeta avaliacao real.
ROADMAP: FASE 3 (S41)
"""
from __future__ import annotations

import itertools
from typing import Any

import pandas as pd


def run_parameter_grid(
    param_grid: dict[str, list[Any]],
    max_combos: int = 200,
) -> pd.DataFrame:
    """Gera grid cartesiano de parametros com placeholder MAE.

    Args:
        param_grid: {param_name: [values]} — grid de busca.
        max_combos: limite maximo de combinacoes (default 200).

    Returns:
        DataFrame com colunas = param_names + "mae", ordenado por MAE crescente.
        MAE = 999.0 placeholder (orquestrador preenche com valor real).
    """
    if not param_grid:
        return pd.DataFrame(columns=["mae"])

    # Produto cartesiano
    keys = list(param_grid.keys())
    values = list(param_grid.values())

    # Se exceder max_combos, faz amostragem para limitar
    total_combos = 1
    for v in values:
        total_combos *= len(v)

    if total_combos > max_combos:
        # Pareto 80/20: pega os primeiros valores de cada parametro
        # que cobrem aproximadamente 80% do espaco
        sampled_values = []
        for v_list in values:
            n_take = max(1, int(len(v_list) * 0.6))  # 60% dos valores = ~80% cobertura
            sampled_values.append(v_list[:n_take])
        values = sampled_values

    # Gera todas as combinacoes
    combos = list(itertools.product(*values))

    # Limita a max_combos
    if len(combos) > max_combos:
        combos = combos[:max_combos]

    # Monta DataFrame
    rows = []
    for combo in combos:
        row = dict(zip(keys, combo, strict=False))
        row["mae"] = 999.0  # placeholder
        rows.append(row)

    df = pd.DataFrame(rows)

    # Ordena por MAE (placeholder, mas orquestrador vai preencher)
    if not df.empty:
        df = df.sort_values("mae").reset_index(drop=True)

    return df
