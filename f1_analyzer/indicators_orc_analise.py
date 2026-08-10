"""PROPOSITO: Indicadores compartilhados — mesmo codigo para vivo e replay
SPEC: S3
ROADMAP: 2.2b — 1 fonte de verdade para indicadores.
R-AI-REUSE: usa pandas (ja instalado). vectorbt opcional para TA-Lib.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def sma(series: pd.Series, window: int) -> pd.Series:
    """Simple Moving Average."""
    return series.rolling(window).mean()


def bbands(close: pd.Series, window: int = 20, num_std: float = 2.0) -> dict[str, pd.Series]:
    """Bollinger Bands: middle, upper, lower, %B, bandwidth."""
    middle = sma(close, window)
    std = close.rolling(window).std()
    upper = middle + num_std * std
    lower = middle - num_std * std
    pct_b = (close - lower) / (upper - lower)
    bandwidth = (upper - lower) / middle
    return {"middle": middle, "upper": upper, "lower": lower, "pct_b": pct_b, "bandwidth": bandwidth}


def atr(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average True Range."""
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window).mean()


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Relative Strength Index."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window).mean()
    avg_loss = loss.rolling(window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict[str, pd.Series]:
    """MACD: line, signal, histogram."""
    ema_fast = close.ewm(span=fast).mean()
    ema_slow = close.ewm(span=slow).mean()
    line = ema_fast - ema_slow
    signal_line = line.ewm(span=signal).mean()
    histogram = line - signal_line
    return {"line": line, "signal": signal_line, "histogram": histogram}


def stoch(high: pd.Series, low: pd.Series, close: pd.Series,
           k_window: int = 14, d_window: int = 3) -> dict[str, pd.Series]:
    """Stochastic Oscillator: %K, %D."""
    low_min = low.rolling(k_window).min()
    high_max = high.rolling(k_window).max()
    k = 100 * (close - low_min) / (high_max - low_min)
    d = k.rolling(d_window).mean()
    return {"k": k, "d": d}


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume."""
    direction = np.where(close.diff() > 0, 1, np.where(close.diff() < 0, -1, 0))
    return (volume * direction).cumsum()


def adx(high: pd.Series, low: pd.Series, close: pd.Series, window: int = 14) -> pd.Series:
    """Average Directional Index (simplificado).

    S39: DX=0 quando nao ha movimento direcional (plus_di+minus_di==0) —
    antes 0/0=NaN envenenava a media movel e a ultima barra saia None
    (health 15/16). Convencao padrao de mercado: sem DM, DX=0.
    """
    atr_val = atr(high, low, close, window)
    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
    plus_di = 100 * pd.Series(plus_dm).rolling(window).mean() / atr_val
    minus_di = 100 * pd.Series(minus_dm).rolling(window).mean() / atr_val
    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di)).fillna(0)
    return dx.rolling(window).mean()
