"""PROPOSITO: matrix_orc_vista.py — Engine numpy/pandas da vista MTF (S39).
SPEC: S39 (vista_mercado.md)
ROADMAP: S39 — split DDD (G12: vista_orc_mercado estourou 200L).

SAT de vista_orc_mercado (R8 naming). Sem IO, sem MCP, sem estado:
- regime_tf: RSI/ADX/ATR%/slope EMA20 + rotulo de regime por timeframe
- sessao_atual: sessao UTC corrente (tokyo/london/new_york/rollover)
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pandas as pd


def regime_tf(df: pd.DataFrame, rule: str | None) -> dict[str, Any] | None:
    """Regime de 1 TF: resample (ou M1 puro) + RSI/ADX/ATR%/slope EMA20.

    R-USE f1_analyzer.indicators_orc_analise (mesmas funcoes do consolidado).
    So barras FECHADAS: descarta a barra parcial corrente (zero lookahead).
    RangeIndex obrigatorio apos resample: indicators_orc_analise mistura
    np.where (RangeIndex) com rolling do input — DatetimeIndex desalinhava
    e o ADX saia 0.0 em todo TF resampleado (bug medido 2026-07-30).
    """
    from f1_analyzer import indicators_orc_analise as ind

    d = df.iloc[:-1] if len(df) > 60 else df  # barra corrente fora
    if rule:
        g = d.set_index(pd.to_datetime(d["timestamp"], unit="ms", utc=True))
        ohlc = g.resample(rule).agg(
            {"open": "first", "high": "max", "low": "min", "close": "last"}
        ).dropna().reset_index(drop=True)
    else:
        ohlc = d[["open", "high", "low", "close"]].dropna()
    if len(ohlc) < 60:
        import sys
        print("[ERRO] matrix_orc_vista.py: dados insuficientes (min 60) para calcular regime MTF", file=sys.stderr)
        return None
    c = pd.to_numeric(ohlc["close"], errors="coerce").ffill()
    h = pd.to_numeric(ohlc["high"], errors="coerce").ffill()
    lo = pd.to_numeric(ohlc["low"], errors="coerce").ffill()
    rsi_v = float(ind.rsi(c).iloc[-1])
    adx_v = float(ind.adx(h, lo, c).iloc[-1])
    atr_v = float(ind.atr(h, lo, c).iloc[-1])
    ema = c.ewm(span=20, adjust=False).mean()
    slope = float((ema.iloc[-1] / ema.iloc[-6] - 1) * 100) if len(ema) > 6 else 0.0
    if adx_v >= 25:
        regime = "TREND_UP" if slope > 0 else "TREND_DOWN"
    elif adx_v < 20:
        regime = "RANGE"
    else:
        regime = "TRANSICAO"
    return {
        "rsi": round(rsi_v, 1), "adx": round(adx_v, 1),
        "atr_pct": round(atr_v / float(c.iloc[-1]) * 100, 3) if c.iloc[-1] else None,
        "ema_slope_pct": round(slope, 3), "regime": regime, "barras": len(ohlc),
    }


def sessao_atual() -> str:
    h = datetime.now(UTC).hour
    if 0 <= h < 7:
        return "tokyo"
    if 7 <= h < 12:
        return "london"
    if 12 <= h < 21:
        return "new_york"
    return "rollover"
