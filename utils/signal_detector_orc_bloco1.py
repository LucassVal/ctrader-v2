"""PROPOSITO: Detectores de sinal do Bloco 1 (RSI/MACD/ADX).

SPEC: S41 — Bloco 1: Torneio do Passado
SAT: signal_detector_orc_bloco1
ROADMAP: FASE 3 (S41)

Extrai do ORQ orc_bloco1.py (split DDD G12 — GOD object).
Detecta sinais de compra (dip buy) e venda (short top) via indicadores puros.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def detect_buy_signals(
    df: pd.DataFrame,
    rsi_period: int = 14,
    rsi_threshold: int = 30,
    macd_fast: int = 12,
    adx_period: int = 14,
    adx_threshold: int = 25,
) -> pd.Series:
    """Detecta sinais de compra: RSI oversold (dip) + MACD + ADX."""
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    n = len(close)

    if n < max(rsi_period, macd_fast, adx_period) + 2:
        return pd.Series([False] * n, index=df.index)

    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).rolling(rsi_period, min_periods=1).mean().values
    avg_loss = pd.Series(loss).rolling(rsi_period, min_periods=1).mean().values
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi_oversold = rsi < rsi_threshold

    ema_fast = pd.Series(close).ewm(span=macd_fast, adjust=False).mean().values
    ema_slow = pd.Series(close).ewm(span=macd_fast * 2, adjust=False).mean().values
    macd_line = ema_fast - ema_slow
    macd_signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values
    macd_bullish = macd_line > macd_signal_line

    tr = np.maximum.reduce([
        high - low,
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1)),
    ])
    tr[0] = high[0] - low[0]
    atr_adx = pd.Series(tr).rolling(adx_period, min_periods=1).mean().values
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    up_move[0] = 0
    down_move[0] = 0
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = pd.Series(plus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx * 100
    minus_di = pd.Series(minus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx * 100
    adx_val = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx_strong = adx_val > adx_threshold

    buy_signal = rsi_oversold & macd_bullish & adx_strong
    return pd.Series(buy_signal, index=df.index)


def detect_sell_signals(
    df: pd.DataFrame,
    rsi_period: int = 14,
    rsi_threshold: int = 70,
    adx_period: int = 14,
    adx_threshold: int = 20,
) -> pd.Series:
    """Detecta sinais de venda: RSI sobrecomprado + ADX confirma tendencia de baixa."""
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    n = len(close)

    if n < max(rsi_period, adx_period) + 2:
        return pd.Series([False] * n, index=df.index)

    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).rolling(rsi_period, min_periods=1).mean().values
    avg_loss = pd.Series(loss).rolling(rsi_period, min_periods=1).mean().values
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi_overbought = rsi > rsi_threshold

    tr = np.maximum.reduce([
        high - low,
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1)),
    ])
    tr[0] = high[0] - low[0]
    atr_adx = pd.Series(tr).rolling(adx_period, min_periods=1).mean().values
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    up_move[0] = 0
    down_move[0] = 0
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100 * pd.Series(plus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx
    minus_di = 100 * pd.Series(minus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx
    adx_val = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx_strong = adx_val > adx_threshold
    bearish_trend = minus_di > plus_di

    sell_signal = rsi_overbought & bearish_trend & adx_strong
    return pd.Series(sell_signal, index=df.index)
