"""PROPOSITO: test_orc_calibracao.py — Harness S36 (append/reconcile/summary).
SPEC: S36 (orc_calibracao.md)
G19: SIGNALS_LOG / CONSOLIDATED_DIR / CALIBRATION_JSON monkeypatchados p/ tmp_path.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from utils import orc_calibracao as cal


def _row(ts: datetime, score: float = 60.0, sinal: str = "BULLISH",
         origem: str = "replay", outcome: float | None = None) -> dict:
    return {
        "ts": ts.isoformat(), "symbol": "EURUSD", "origem": origem,
        "strategy_id": None, "sinal": sinal, "score": score,
        "coverage_pct": 98.5, "close_entrada": 1.1000,
        "outcome_5m_pips": outcome, "outcome_15m_pips": outcome,
        "outcome_60m_pips": outcome,
        "acerto_5m": None if outcome is None else outcome > 0,
        "acerto_15m": None if outcome is None else outcome > 0,
        "acerto_60m": None if outcome is None else outcome > 0,
    }


def test_append_dedup(monkeypatch, tmp_path):
    log = tmp_path / "signals_log.parquet"
    monkeypatch.setattr(cal, "SIGNALS_LOG", log)
    ts = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    cal.append_signals([_row(ts), _row(ts)])  # duplicado na mesma chamada
    assert len(pd.read_parquet(log)) == 1
    cal.append_signals([_row(ts), _row(ts + timedelta(minutes=1))])
    assert len(pd.read_parquet(log)) == 2


def test_summary_amostra_insuficiente():
    ts = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    df = pd.DataFrame([_row(ts + timedelta(minutes=i), outcome=1.0) for i in range(5)])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    out = cal.calibration_summary(df)
    assert out["total_signals"] == 5
    assert out["hit_rate_por_faixa"]["50-70"]["status"] == "amostra_insuficiente"


def test_summary_hit_rate_e_brier():
    ts = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
    rows = []
    for i in range(40):
        rows.append(_row(ts + timedelta(minutes=i), score=60.0, outcome=1.0 if i % 2 else -1.0))
    df = pd.DataFrame(rows)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    out = cal.calibration_summary(df)
    faixa = out["hit_rate_por_faixa"]["50-70"]
    assert faixa["n"] == 40
    assert faixa["hit_15m"] == pytest.approx(50.0)
    assert "15m" in out["brier"]


def test_reconcile_fecha_outcomes(monkeypatch, tmp_path):
    """Sinal live de 2h atras reconcilia contra consolidado sintetico."""
    log = tmp_path / "signals_log.parquet"
    cons_dir = tmp_path / "consolidated"
    cons_dir.mkdir()
    monkeypatch.setattr(cal, "SIGNALS_LOG", log)
    monkeypatch.setattr(cal, "CONSOLIDATED_DIR", cons_dir)
    monkeypatch.setattr(cal, "CALIBRATION_JSON", tmp_path / "calibration.json")

    base_ts = 1_785_400_000_000  # ms
    # closes em UNIDADES BRUTAS cTrader (x price_divisor) — formato real do
    # consolidado G23 (S34 v1.2 fix: pip_raw = pip_size x divisor)
    closes = (1.10 + np.linspace(0, 0.004, 200)) * 100000
    pd.DataFrame({
        "timestamp": [base_ts + i * 60_000 for i in range(200)],
        "close": closes,
    }).to_parquet(cons_dir / "EURUSD_M1.parquet", index=False)

    ts_signal = datetime.fromtimestamp(base_ts / 1000 + 60, UTC)  # barra idx 1
    cal.append_signals([_row(ts_signal, origem="live")])
    r = cal.reconcile()
    assert r["reconciled"] == 1
    df = pd.read_parquet(log)
    row = df.iloc[0]
    assert not pd.isna(row["outcome_60m_pips"])
    # alta real no consolidado -> BULLISH acertou nos 3 horizontes
    assert bool(row["acerto_15m"]) is True
    # liquido de spread: 60 barras * 0.000002 real/bar = 12 pips - 1.0 spread
    assert row["outcome_60m_pips"] == pytest.approx(
        (closes[61] - closes[1]) / 10 - 1.0, abs=0.01)  # 10 = pip_raw EURUSD


def test_purge_signals_so_replay(monkeypatch, tmp_path):
    """Purge remove so a origem/simbolos pedidos — live intocado (S34 v1.2)."""
    log = tmp_path / "signals_log.parquet"
    monkeypatch.setattr(cal, "SIGNALS_LOG", log)
    ts = datetime(2026, 7, 30, 12, 0, tzinfo=UTC)
    cal.append_signals([
        _row(ts, origem="replay"),
        _row(ts + timedelta(minutes=1), origem="replay"),
        _row(ts + timedelta(minutes=2), origem="live"),
    ])
    removed = cal.purge_signals(origem="replay", symbols=["EURUSD"])
    assert removed == 2
    df = pd.read_parquet(log)
    assert len(df) == 1
    assert df.iloc[0]["origem"] == "live"
    # simbolo fora da lista: nada e removido
    assert cal.purge_signals(origem="replay", symbols=["XAUUSD"]) == 0
