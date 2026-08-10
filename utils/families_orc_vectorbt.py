"""PROPOSITO: families_orc_vectorbt.py — Ultimo valor das 10 familias avancadas (S39).
SPEC: S39 (vista_mercado.md, fix 16/16) + S25/S28
ROADMAP: S39 — split DDD (G12: indicators_orc_vectorbt em 195L).

SAT de orc_vectorbt (R8 naming). Sem IO, sem MCP, sem estado.
R-USE dos helpers escalares de indicators_orc_vectorbt + stoch/sma em pandas.
Uso: consolidated_indicator_points(full_families=True) computa na cauda
(max_points + 250 warmup) e funde no ultimo ponto — o caminho do scan
(full_families=False) NAO chama isto (permanece lean).
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from utils.indicators_orc_vectorbt import (
    _aroon,
    _cci,
    _donchian,
    _hma,
    _keltner,
    _psar,
    _williams_r,
    _zlema,
)

WARMUP_BARS = 250  # cobre sma_slow(50), psar (convergencia) e stoch(14+3)


def _f(v: Any, nd: int = 5) -> float | None:
    try:
        f = float(v)
        return None if np.isnan(f) else round(f, nd)
    except (TypeError, ValueError):
        return None


def latest_families(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
) -> dict[str, Any]:
    """Ultimo valor das 10 familias ausentes do caminho consolidado (S39).

    Entrada: cauda ja fatiada (>= 60 barras idealmente WARMUP_BARS).
    Retorna dict com None honesto onde nao ha dados suficientes (A7).
    """
    out: dict[str, Any] = {
        "stoch_k": None, "stoch_d": None, "sma_fast": None, "sma_slow": None,
        "dc_high": None, "dc_low": None, "dc_mid": None, "hma": None,
        "kc_upper": None, "kc_lower": None, "kc_squeeze": None, "cci": None,
        "psar": None, "wpr": None, "aroon_up": None, "aroon_down": None,
        "zlema": None,
    }
    n = len(close)
    if n < 20:
        return out
    try:
        c = pd.Series(close, dtype="float64")
        h = pd.Series(high, dtype="float64")
        lo = pd.Series(low, dtype="float64")

        # STOCH (14, 3) — mesmo periodo do orc_vectorbt.compute_indicators
        llv = lo.rolling(14).min()
        hhv = h.rolling(14).max()
        rng = (hhv - llv).replace(0, np.nan)
        k = (c - llv) / rng * 100
        out["stoch_k"] = _f(k.iloc[-1], 1)
        out["stoch_d"] = _f(k.rolling(3).mean().iloc[-1], 1)

        # SMA fast/slow (14/50 — periods default do compute_indicators)
        out["sma_fast"] = _f(c.rolling(14).mean().iloc[-1])
        out["sma_slow"] = _f(c.rolling(50).mean().iloc[-1])

        # Familias avancadas — R-USE helpers escalares (S28)
        dc_h, dc_l, dc_m = _donchian(high, low, window=20)
        out["dc_high"], out["dc_low"], out["dc_mid"] = _f(dc_h), _f(dc_l), _f(dc_m)
        out["hma"] = _f(_hma(close, period=14))
        kc_u, kc_l, kc_sq = _keltner(close, high, low, window=20)
        out["kc_upper"], out["kc_lower"] = _f(kc_u), _f(kc_l)
        out["kc_squeeze"] = _f(kc_sq, 2)
        out["cci"] = _f(_cci(high, low, close, window=20), 1)
        out["psar"] = _f(_psar(high, low, close))
        out["wpr"] = _f(_williams_r(high, low, close, window=14), 1)
        a_up, a_dn = _aroon(high, low, window=14)
        out["aroon_up"], out["aroon_down"] = _f(a_up, 1), _f(a_dn, 1)
        out["zlema"] = _f(_zlema(close, period=20))
    except (ValueError, IndexError, TypeError) as e:
        import logging
        logging.getLogger(__name__).error("latest_families falhou parcial: %s", e)
    return out
