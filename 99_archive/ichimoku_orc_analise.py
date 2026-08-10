"""
PROPOSITO: F1 — ICHIMOKU CLOUD
SPEC: S3
ROADMAP: 2.3
"""

from __future__ import annotations

import pandas as pd


def calc_ichimoku(df: pd.DataFrame) -> dict:
    """Retorna as 5 linhas do Ichimoku para o candle atual.

    Requer: colunas high, low, close no df (mín 52 candles).
    """
    if len(df) < 52:
        return {"error": "Precisa de 52+ candles"}

    high = df["high"]
    low = df["low"]
    close = df["close"]

    # Tenkan-sen (Conversion Line): (9-high + 9-low) / 2
    tenkan = (high.rolling(9).max().iloc[-1] + low.rolling(9).min().iloc[-1]) / 2

    # Kijun-sen (Base Line): (26-high + 26-low) / 2
    kijun = (high.rolling(26).max().iloc[-1] + low.rolling(26).min().iloc[-1]) / 2

    # Senkou Span A: (Tenkan + Kijun) / 2, deslocado 26 períodos à frente
    senkou_a = (tenkan + kijun) / 2

    # Senkou Span B: (52-high + 52-low) / 2, deslocado 26 à frente
    senkou_b = (high.rolling(52).max().iloc[-1] + low.rolling(52).min().iloc[-1]) / 2

    # Chikou Span: close deslocado 26 períodos atrás
    chikou = close.iloc[-26] if len(close) >= 26 else close.iloc[-1]

    current = close.iloc[-1]

    # sinais
    cloud_top = max(senkou_a, senkou_b)
    cloud_bottom = min(senkou_a, senkou_b)

    if current > cloud_top:
        signal = "BULLISH (acima da nuvem)"
    elif current < cloud_bottom:
        signal = "BEARISH (abaixo da nuvem)"
    else:
        signal = "NEUTRAL (dentro da nuvem)"

    # TK cross
    if tenkan > kijun:
        tk_cross = "BULLISH (Tenkan > Kijun)"
    elif tenkan < kijun:
        tk_cross = "BEARISH (Tenkan < Kijun)"
    else:
        tk_cross = "FLAT"

    return {
        "tenkan_sen": round(float(tenkan), 5),
        "kijun_sen": round(float(kijun), 5),
        "senkou_span_a": round(float(senkou_a), 5),
        "senkou_span_b": round(float(senkou_b), 5),
        "chikou_span": round(float(chikou), 5),
        "current_price": round(float(current), 5),
        "signal": signal,
        "tk_cross": tk_cross,
    }
