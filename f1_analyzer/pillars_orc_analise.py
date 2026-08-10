"""PROPOSITO: PILARES F1 — macro, vol, tec scores
SPEC: S3
ROADMAP: 2.2
FLOW:   df_master -> calculate_macro_score / _vol_score / _tec_score
        _indicators.py -> atr(), rsi(), bbands() | _dxy.py -> calculate_multi_dxy_score() — Indicadores via _indicators.py (modulo compartilhado vivo+replay)
"""
from __future__ import annotations

import logging

import pandas as pd

from f1_analyzer.indicators_orc_analise import atr, bbands, rsi

logger = logging.getLogger(__name__)


def calculate_macro_score(df: pd.DataFrame) -> float:
    """Pilar 1 — Macro/Contexto. DXY, sentimento, volume."""
    try:
        dxy = df["dxy_close"].dropna()
        if len(dxy) >= 20:
            sma20 = dxy.rolling(20).mean().iloc[-1]
            std20 = dxy.rolling(20).std().iloc[-1]
            if std20 and std20 > 0:
                dxy_z = abs((dxy.iloc[-1] - sma20) / std20)
                dxy_score = min(dxy_z * 40, 40)
            else:
                dxy_score = 20
        else:
            dxy_score = 20

        sent = df["sentiment_ratio"].dropna()
        if len(sent) > 0:
            long_ratio = sent.iloc[-1]
            sent_score = (1.0 - long_ratio) * 35
        else:
            sent_score = 17.5

        vol = df["tick_volume"].dropna()
        if len(vol) >= 10:
            last_vol = vol.iloc[-1]
            pct = (vol < last_vol).sum() / len(vol)
            vol_score = pct * 25
        else:
            vol_score = 12.5

        return min(max(dxy_score + sent_score + vol_score, 0), 100)
    except Exception as e:
        logger.error("Erro macro score: %s", e)
        return 50.0


def calculate_vol_score(df: pd.DataFrame) -> float:
    """Pilar 2 — Volatilidade. ATR via _indicators (ROADMAP 2.2)."""
    try:
        if all(c in df.columns for c in ("high", "low", "close")) and len(df) >= 15:
            atr_series = atr(df["high"], df["low"], df["close"], 14)
            atr_val = atr_series.iloc[-1]
            atr_pct = (atr_series.dropna() < atr_val).sum() / len(atr_series.dropna())
            atr_score = atr_pct * 50 if not pd.isna(atr_val) else 25
        else:
            atr_score = 25

        contango_score = 15  # neutro

        spread = df["spread"].dropna()
        if len(spread) > 0:
            spread_pct = (spread < spread.iloc[-1]).sum() / len(spread)
            spread_score = (1 - spread_pct) * 20
        else:
            spread_score = 10

        return min(max(atr_score + contango_score + spread_score, 0), 100)
    except Exception as e:
        logger.error("Erro vol score: %s", e)
        return 50.0


def calculate_tec_score(df: pd.DataFrame) -> float:
    """Pilar 3 — Tecnico. RSI + Bollinger via _indicators (ROADMAP 2.2)."""
    try:
        close = df["close"].dropna()

        # Momentum (RCA) — simples, nao precisa de modulo compartilhado
        if len(close) >= 14:
            momentum = close.iloc[-1] - close.iloc[-14]
            rca_score = min(abs(momentum) / close.iloc[-1] * 1000 * 0.40, 40)
        else:
            rca_score = 20

        # RSI via _indicators (ROADMAP 2.2)
        if len(close) >= 15:
            rsi_series = rsi(close, 14)
            rsi_val = rsi_series.iloc[-1]
            if not pd.isna(rsi_val):
                rsi_extreme = abs(rsi_val - 50) * 2
                rsi_score = min(rsi_extreme * 0.20, 20)
            else:
                rsi_score = 10
        else:
            rsi_score = 10

        # Bollinger %B via _indicators (ROADMAP 2.2)
        if len(close) >= 21:
            bb = bbands(close, 20)
            boll_pct_b = bb["pct_b"].iloc[-1]
            _bw = bb["bandwidth"].iloc[-1]  # reservado para filtro de squeeze (ROADMAP 4.5.2)
            if not pd.isna(boll_pct_b):
                if boll_pct_b > 0.8:
                    boll_score = (1 - boll_pct_b) * 50
                elif boll_pct_b < 0.2:
                    boll_score = boll_pct_b * 50
                else:
                    boll_score = abs(boll_pct_b - 0.5) * 40
            else:
                boll_score = 15
        else:
            boll_score = 15

        delta_score = 17.5  # neutro (sem DOM)

        return min(max(rca_score + rsi_score + boll_score + delta_score, 0), 100)
    except Exception as e:
        logger.error("Erro tec score: %s", e)
        return 50.0
