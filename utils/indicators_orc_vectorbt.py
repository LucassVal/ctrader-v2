"""PROPOSITO: indicators_orc_vectorbt.py — Indicadores avancados numpy puro (satelite).
SPEC: S25
ROADMAP: VBT-1, VBT-2 — extraido de orc_vectorbt.py (GOD 456L > 350L, split DDD).

Funcoes puras high/low/close -> float: ADX, Donchian, HMA, Keltner, CCI,
PSAR, Williams %R, Aroon, ZLEMA. Orquestrador: orc_vectorbt.compute_indicators.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> float:
    """ADX via directional movement (vectorbt nao tem ADX nativo na versao instalada)."""
    df = pd.DataFrame({"high": high, "low": low, "close": close})

    df["tr"] = np.maximum(
        df["high"] - df["low"],
        np.maximum(
            abs(df["high"] - df["close"].shift(1)),
            abs(df["low"] - df["close"].shift(1)),
        ),
    )
    df["atr"] = df["tr"].rolling(window).mean()

    df["up"] = df["high"] - df["high"].shift(1)
    df["down"] = df["low"].shift(1) - df["low"]
    df["+dm"] = np.where((df["up"] > df["down"]) & (df["up"] > 0), df["up"], 0)
    df["-dm"] = np.where((df["down"] > df["up"]) & (df["down"] > 0), df["down"], 0)

    df["+di"] = 100 * df["+dm"].rolling(window).mean() / df["atr"]
    df["-di"] = 100 * df["-dm"].rolling(window).mean() / df["atr"]
    df["dx"] = 100 * abs(df["+di"] - df["-di"]) / (df["+di"] + df["-di"])
    df["adx"] = df["dx"].rolling(window).mean()

    return float(df["adx"].iloc[-1]) if not df["adx"].empty and not np.isnan(df["adx"].iloc[-1]) else 0.0


# ═══════════════════════════════════════════════════════════════
# S28 — Indicadores Avancados (numpy puro)
# ═══════════════════════════════════════════════════════════════

def _donchian(high: np.ndarray, low: np.ndarray, window: int = 20) -> tuple[float, float, float]:
    """Donchian Channels: max high, min low, mid dos ultimos N periodos."""
    h = float(np.max(high[-window:])) if len(high) >= window else float(high[-1])
    lo = float(np.min(low[-window:])) if len(low) >= window else float(low[-1])
    m = round((h + lo) / 2, 5)
    return round(h, 5), round(lo, 5), m


def _breakout_pct(close: float, dc_high: float, dc_low: float) -> float:
    """% de penetracao do Donchian: 100=rompeu topo, 0=no fundo."""
    rng = dc_high - dc_low
    if rng <= 0:
        return 50.0
    return round((close - dc_low) / rng * 100, 1)


def _hma(close: np.ndarray, period: int = 14) -> float | None:
    """Hull Moving Average — lag quase zero, resposta rapida."""
    n = len(close)
    if n < period:
        return None
    half = period // 2
    sqrt_n = int(np.sqrt(period))
    wma_half = _wma(close, half)
    wma_full = _wma(close, period)
    if wma_half is None or wma_full is None:
        return None
    raw = 2 * wma_half - wma_full
    result = _wma(np.full(sqrt_n, raw), sqrt_n)
    return round(result, 5) if result is not None else None


def _wma(data: np.ndarray, period: int) -> float | None:
    """Weighted Moving Average."""
    n = len(data)
    if n < period:
        return None
    weights = np.arange(1, period + 1)
    return float(np.sum(data[-period:] * weights) / weights.sum())


def _keltner(close: np.ndarray, high: np.ndarray, low: np.ndarray, window: int = 20, multiplier: float = 2.0) -> tuple[float, float, float]:
    """Keltner Channels: EMA +/- ATR x multiplier. Retorna squeeze %"""
    n = len(close)
    if n < window:
        return 0.0, 0.0, 0.0
    # ATR
    tr = np.maximum(high[-window:] - low[-window:],
                    np.maximum(abs(high[-window:] - np.roll(close[-window:], 1)),
                               abs(low[-window:] - np.roll(close[-window:], 1))))
    tr[0] = high[-window] - low[-window]
    atr_val = float(np.mean(tr))
    # EMA
    ema = float(pd.Series(close).ewm(span=window, adjust=False).mean().iloc[-1])
    upper = round(ema + atr_val * multiplier, 5)
    lower = round(ema - atr_val * multiplier, 5)
    width = upper - lower
    squeeze = round(width / ema * 100, 2) if ema else 0.0
    return upper, lower, squeeze


def _cci(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 20) -> float | None:
    """Commodity Channel Index."""
    n = len(close)
    if n < window:
        return None
    tp = (high[-window:] + low[-window:] + close[-window:]) / 3
    sma_tp = float(np.mean(tp))
    mad = float(np.mean(np.abs(tp - sma_tp)))
    if mad == 0:
        return 0.0
    return round((tp[-1] - sma_tp) / (0.015 * mad), 1)


def _psar(high: np.ndarray, low: np.ndarray, close: np.ndarray, af_start: float = 0.02, af_step: float = 0.02, af_max: float = 0.2) -> float | None:
    """Parabolic SAR — ultimo valor."""
    n = len(close)
    if n < 2:
        return None
    psar = float(low[0])
    ep = float(high[0])  # extreme point
    af = af_start
    uptrend = True
    for i in range(1, n):
        prev_psar = psar
        if uptrend:
            psar = prev_psar + af * (ep - prev_psar)
            psar = min(psar, float(low[i - 1]), float(low[i])) if i >= 2 else min(psar, float(low[i]))
            if close[i] > ep:
                ep = float(high[i])
                af = min(af + af_step, af_max)
            if close[i] < psar:
                uptrend = False
                psar = ep
                ep = float(low[i])
                af = af_start
        else:
            psar = prev_psar - af * (prev_psar - ep)
            psar = max(psar, float(high[i - 1]), float(high[i])) if i >= 2 else max(psar, float(high[i]))
            if close[i] < ep:
                ep = float(low[i])
                af = min(af + af_step, af_max)
            if close[i] > psar:
                uptrend = True
                psar = ep
                ep = float(high[i])
                af = af_start
    return round(psar, 5)


def _williams_r(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int = 14) -> float | None:
    """Williams %R: -100 a 0. -80 = sobrevendido, -20 = sobrecomprado."""
    n = len(close)
    if n < window:
        return None
    hh = float(np.max(high[-window:]))
    ll = float(np.min(low[-window:]))
    rng = hh - ll
    if rng == 0:
        return -50.0
    return round((hh - close[-1]) / rng * -100, 1)


def _aroon(high: np.ndarray, low: np.ndarray, window: int = 14) -> tuple[float | None, float | None]:
    """Aroon Up/Down: 0-100. >70 = tendencia forte."""
    n = len(high)
    if n < window:
        return None, None
    window_high = high[-window:]
    window_low = low[-window:]
    days_since_high = window - 1 - int(np.argmax(window_high))
    days_since_low = window - 1 - int(np.argmin(window_low))
    aroon_up = round((window - days_since_high) / window * 100, 1)
    aroon_down = round((window - days_since_low) / window * 100, 1)
    return aroon_up, aroon_down


def _zlema(close: np.ndarray, period: int = 20) -> float | None:
    """Zero-Lag EMA: close + (close - lag) x alpha."""
    n = len(close)
    if n < period:
        return None
    lag = max(1, period // 2)
    ema_input = 2 * close[-1] - close[-lag]
    alpha = 2 / (period + 1)
    # EMA recursiva
    result = ema_input
    for i in range(min(period, n)):
        idx = n - period + i
        if idx >= 0:
            result = alpha * (2 * close[idx] - (close[idx - lag] if idx >= lag else close[idx])) + (1 - alpha) * result
    return round(result, 5)
