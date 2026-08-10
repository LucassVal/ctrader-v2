"""PROPOSITO: Calculo de MAE (Maximum Adverse Excursion) e MFE (Maximum Favorable Excursion).

SPEC: S41 — Bloco 1: Torneio do Passado
SAT: mae_mfe_orc_bloco1

Regra de ouro: entrada no Open da barra seguinte ao sinal (.shift(1)).
MAE long: (entry_price - low.min()) / entry_price
MFE long: (high.max() - entry_price) / entry_price
Saida: exclusivamente Close[t+horizon] (time-only exit).
ROADMAP: FASE 3 (S41)
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def calc_mae_mfe(
    entry_price: float,
    highs: np.ndarray | pd.Series,
    lows: np.ndarray | pd.Series,
    exit_idx: int,
    direction: str = "LONG",
) -> tuple[float, float]:
    """Calcula MAE e MFE para uma entrada ate o indice de saida.

    Args:
        entry_price: preco de entrada (Open da barra seguinte ao sinal).
        highs: serie de precos maximos desde a entrada ate a saida.
        lows: serie de precos minimos desde a entrada ate a saida.
        exit_idx: indice da barra de saida (exclusivo, slice [0:exit_idx+1]).
        direction: "LONG" ou "SHORT".

    Returns:
        (mae, mfe) — ambos >= 0, expressos como fracao do entry_price.

    MAE = perda maxima durante o trade (mais profundo que o preco chegou contra voce).
    MFE = ganho maximo durante o trade (mais longe que o preco chegou a seu favor).
    """
    # Valida entrada
    if entry_price <= 0:
        return (0.0, 0.0)

    # Converte para arrays float64 e fatia ate exit_idx+1
    if isinstance(highs, pd.Series):
        highs_arr = highs.values[: exit_idx + 1]
    else:
        highs_arr = np.asarray(highs, dtype=np.float64)[: exit_idx + 1]

    if isinstance(lows, pd.Series):
        lows_arr = lows.values[: exit_idx + 1]
    else:
        lows_arr = np.asarray(lows, dtype=np.float64)[: exit_idx + 1]

    # Garante arrays float64 para numpy
    highs_arr = np.asarray(highs_arr, dtype=np.float64)
    lows_arr = np.asarray(lows_arr, dtype=np.float64)

    if len(highs_arr) == 0 or len(lows_arr) == 0:
        return (0.0, 0.0)

    if direction.upper() == "SHORT":
        # Short: MAE = (high.max() - entry) / entry; MFE = (entry - low.min()) / entry
        mae_val = (np.nanmax(highs_arr) - entry_price) / entry_price
        mfe_val = (entry_price - np.nanmin(lows_arr)) / entry_price
    else:
        # Long: MAE = (entry - low.min()) / entry; MFE = (high.max() - entry) / entry
        mae_val = (entry_price - np.nanmin(lows_arr)) / entry_price
        mfe_val = (np.nanmax(highs_arr) - entry_price) / entry_price

    # Garante >= 0
    mae_val = max(0.0, mae_val)
    mfe_val = max(0.0, mfe_val)

    return (round(float(mae_val), 6), round(float(mfe_val), 6))
