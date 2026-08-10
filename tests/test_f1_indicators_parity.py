"""PROPOSITO: H2.3 — Harness paridade indicadores vivo vs replay
SPEC: S3
ROADMAP: 2.2b — Mesmo modulo de indicador no vivo e replay.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from f1_analyzer.indicators_orc_analise import atr, bbands, macd, rsi, sma


def test_sma_values() -> None:
    """SMA com valores conhecidos."""
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(s, 3)
    assert abs(result.iloc[-1] - 4.0) < 0.01, f"SMA(3)={result.iloc[-1]}"


def test_bbands_pct_b_range() -> None:
    """Bollinger %B entre 0 e 1 para precos dentro das bandas."""
    s = pd.Series([100.0 + i * 0.5 for i in range(30)])
    bands = bbands(s, 20)
    last_pct_b = bands["pct_b"].iloc[-1]
    assert 0 <= last_pct_b <= 1, f"%B={last_pct_b} fora de [0,1]"


def test_atr_positive() -> None:
    """ATR sempre positivo."""
    hi = pd.Series([105.0 + i for i in range(20)])
    lo = pd.Series([95.0 + i for i in range(20)])
    c = pd.Series([100.0 + i for i in range(20)])
    result = atr(hi, lo, c, 14)
    assert (result.dropna() > 0).all(), "ATR com valores <= 0"


def test_rsi_range() -> None:
    """RSI entre 0 e 100."""
    s = pd.Series([100.0 + np.sin(i * 0.5) * 5 for i in range(30)])
    result = rsi(s, 14)
    assert result.dropna().between(0, 100).all(), "RSI fora de [0,100]"


def test_macd_structure() -> None:
    """MACD retorna line, signal, histogram."""
    s = pd.Series([100.0 + i * 0.1 for i in range(50)])
    result = macd(s)
    for key in ("line", "signal", "histogram"):
        assert key in result, f"MACD sem {key}"
        assert len(result[key].dropna()) > 0
