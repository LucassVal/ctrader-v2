"""PROPOSITO: test_orc_scan.py — Harness S34 (engine numpy do scan).
SPEC: S34 (orc_pattern_engine.md)
G19: NAO escreve em producao — scan_symbol testado com dados sinteticos
(monkeypatch no loader do consolidado), sem escrita em disco.
"""
from __future__ import annotations

import numpy as np
import pytest

from utils import matrix_orc_quality as mq, matrix_orc_scan as matrix, orc_scan as scan


def _synthetic_points(n: int = 800) -> list[dict]:
    """Serie sintetica deterministica (seno + tendencia) com indicadores fake."""
    pts = []
    for i in range(n):
        close = 100 + np.sin(i / 50) * 2 + i * 0.001
        pts.append({
            "timestamp": 1_700_000_000 + i * 60,
            "close": float(close),
            "rsi": 50 + 20 * np.sin(i / 30),
            "macd_hist": 0.01 * np.sin(i / 20),
            "adx": 20 + 10 * np.cos(i / 40),
            "bb_upper": close * 1.001,
            "bb_lower": close * 0.999,
            "atr": close * 0.001,
        })
    return pts


def test_feature_matrix_defaults():
    """rsi/adx None caem nos defaults do codigo original (50/20)."""
    feats, ts, closes, rsi, adx = matrix.feature_matrix([
        {"timestamp": 1000, "close": 10.0, "rsi": None, "adx": None},
        {"timestamp": 1060, "close": 11.0, "rsi": 80.0, "adx": 40.0},
    ])
    assert feats.shape == (2, 5)
    assert feats[0, 0] == pytest.approx(0.5)   # rsi default 50/100
    assert feats[0, 2] == pytest.approx(0.2)   # adx default 20/100
    assert feats[1, 0] == pytest.approx(0.8)
    assert closes[1] == pytest.approx(11.0)
    assert ts[0] == 1000
    # v1.2: rsi/adx crus saem para o trailing_quality_f1
    assert rsi[0] == pytest.approx(50.0) and rsi[1] == pytest.approx(80.0)
    assert adx[1] == pytest.approx(40.0)


def test_cosine_batch_identico():
    v = np.array([[1.0, 0.0, 0.0], [0.5, 0.5, 0.0], [1.0, 0.0, 0.0]])
    q = np.array([1.0, 0.0, 0.0])
    sims = matrix.cosine_batch(q, v)
    assert sims[0] == pytest.approx(1.0)
    assert sims[1] == pytest.approx(2**0.5 / 2, abs=1e-3)
    assert sims[2] == pytest.approx(1.0)


def test_session_of_map():
    ts = np.array([0, 3 * 3600, 8 * 3600, 15 * 3600, 22 * 3600], dtype=np.int64)
    sess = matrix.session_of(ts)
    assert list(sess) == [0, 0, 1, 2, 3]  # tokyo, tokyo, london, ny, rollover


def test_outcome_stats_ponderado():
    pips = np.array([10.0, -10.0, 10.0])
    w = np.array([2.0, 1.0, 2.0])  # 4/5 bullish ponderado
    s = matrix.outcome_stats(pips, w, min_pips=2.0)
    assert s["n"] == 3
    assert s["bullish_pct"] == pytest.approx(80.0)
    assert s["bearish_pct"] == pytest.approx(20.0)


def test_scan_symbol_sintetico(monkeypatch):
    """scan_symbol end-to-end com loader mockado (sem disco, sem MCP)."""
    import utils.storage_orc_consolidated as store

    monkeypatch.setattr(store, "consolidated_indicator_points",
                        lambda *a, **k: {"points": _synthetic_points(),
                                         "history_days": 1.0, "source": "test"})
    r = scan.scan_symbol("EURUSD", days=1, stride=50, min_sim=0.99)
    assert r["status"] == "ok"
    assert r["windows"] == 800
    assert r["prototypes"] > 5
    for pat in r["patterns"]:
        assert pat["occurrences"] >= scan.MIN_OCCURRENCES
        assert {"outcome_5m", "outcome_15m", "outcome_60m"} <= set(pat)
    for row in r["replay_rows"]:
        assert row["origem"] == "replay"
        assert row["symbol"] == "EURUSD"
        assert isinstance(row["acerto_15m"], bool)
        # v1.2: rastreabilidade da composicao (quality pode ser NaN -> None)
        assert "quality_f1" in row
        assert 0 <= row["score"] <= 100


def test_trailing_quality_f1_todos_ganhos():
    """BUYs em serie monotonica crescente: f1 == 1.0 na janela (S34 v1.2)."""
    n = 200
    closes = 100 + np.arange(n) * 0.1  # +0,1%/barra > limiar 0,05%
    rsi = np.full(n, 50.0)
    rsi[::10] = 30.0   # BUY a cada 10 barras (RSI<35)
    adx = np.full(n, 30.0)  # ADX>20
    f1 = mq.trailing_quality_f1(rsi, adx, closes, window_bars=1000, min_signals=3)
    assert not np.isnan(f1[-1])
    assert f1[-1] == pytest.approx(1.0)


def test_trailing_quality_f1_todos_perdidos():
    """BUYs em serie monotonica decrescente: f1 == 0.0."""
    n = 200
    closes = 200 - np.arange(n) * 0.1
    rsi = np.full(n, 50.0)
    rsi[::10] = 30.0
    adx = np.full(n, 30.0)
    f1 = mq.trailing_quality_f1(rsi, adx, closes, window_bars=1000, min_signals=3)
    assert f1[-1] == pytest.approx(0.0)


def test_trailing_quality_f1_zero_lookahead():
    """f1[t] NAO muda quando barras FUTURAS mudam (prova de zero lookahead)."""
    n = 300
    rng = np.random.default_rng(7)
    closes = 100 + np.cumsum(rng.normal(0, 0.2, n))
    rsi = np.clip(50 + rng.normal(0, 15, n), 5, 95)
    adx = np.full(n, 30.0)
    f1_a = mq.trailing_quality_f1(rsi, adx, closes, window_bars=500, min_signals=3)
    closes_b = closes.copy()
    closes_b[250:] *= 1.5  # futuro brutalmente diferente
    f1_b = mq.trailing_quality_f1(rsi, adx, closes_b, window_bars=500, min_signals=3)
    corte = 240  # barras cujo lookahead 5 nao toca a zona alterada
    np.testing.assert_allclose(f1_a[:corte], f1_b[:corte], equal_nan=True)


def test_trailing_quality_f1_amostra_minima():
    """Menos de min_signals na janela: NaN -> fallback 'apenas patterns' (A7)."""
    n = 100
    closes = 100 + np.arange(n) * 0.1
    rsi = np.full(n, 50.0)
    rsi[10] = 30.0  # 1 sinal apenas
    adx = np.full(n, 30.0)
    f1 = mq.trailing_quality_f1(rsi, adx, closes, window_bars=1000, min_signals=30)
    assert np.isnan(f1).all()
