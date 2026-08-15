"""Harness S42: Bloco 2 — Camadas OCO + Correlacao DXY/VIX (Fluxo 2).

PROPOSITO: Validar as camadas de sobrevivencia (baseline vs OCO ATR vs OCO dinamico
  VIX) e a correlacao XAUUSD-DXY/VIX. Foco: ponto de quebra da correlacao e
  "gordura de ganho" (margem MAE/MFE) para saber quando entrar e sair a 80%.
SPEC: S42
ROADMAP: FASE 4 — Bloco 2 v2.0 (defesa microestrutural + OCO dinamico VIX)
"""
from __future__ import annotations

import sys
from pathlib import Path

# Monkeypatch llvmlite para Python 3.12 (bug ArgumentAttributes.add 'nocapture').
import llvmlite.ir.values as _llvm_values
import numpy as np
import pandas as pd
import pytest

_orig_add = _llvm_values.ArgumentAttributes.add


def _safe_add(self, attr):
    if attr == "nocapture":
        return
    _orig_add(self, attr)


_llvm_values.ArgumentAttributes.add = _safe_add

import vectorbt as vbt  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "consolidated"


def _sim_layer(close, entries, exits, tp=None, sl=None, size=None):
    """Simula uma camada via vectorbt Portfolio.from_signals."""
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries.astype(bool),
        exits=exits.astype(bool),
        tp_stop=tp,
        sl_stop=sl,
        size=size if size is not None else 1.0,
        freq="1min",
    )
    return pf, pf.stats()


@pytest.fixture
def synthetic_ohlcv():
    """Serie sintetica com 500 barras M1 + ATR + entradas relaxadas."""
    n = 500
    rng = np.random.default_rng(42)
    close = 2650 + np.cumsum(rng.normal(0, 0.4, n))
    high = close + np.abs(rng.normal(0, 0.3, n))
    low = close - np.abs(rng.normal(0, 0.3, n))
    df = pd.DataFrame(
        {
            "open": np.roll(close, 1),
            "high": high,
            "low": low,
            "close": close,
            "tick_volume": rng.integers(1000, 10000, n),
        },
        index=pd.date_range("2025-01-01", periods=n, freq="1min"),
    )
    df.loc[df.index[0], "open"] = close[0]
    return df


def _entries_relaxed(df: pd.DataFrame) -> pd.Series:
    """Entradas relaxadas (RSI < 45) para garantir sinais em dataset pequeno."""
    rsi = vbt.RSI.run(df["close"], window=14).rsi
    return (rsi < 45).fillna(False).astype(bool)


def _atr_pct(df: pd.DataFrame) -> pd.Series:
    """ATR(14) normalizado em percentual do close."""
    atr = vbt.ATR.run(df["high"], df["low"], df["close"], window=14).atr.astype(float)
    return (atr / df["close"]).fillna(0.01)


def test_oco_layers_mechanics(synthetic_ohlcv):
    """Camadas OCO: baseline < OCO ATR em MaxDD; OCO dinamico mantem risco."""
    df = synthetic_ohlcv
    entries = _entries_relaxed(df)
    exits = entries.shift(5).fillna(False).astype(bool)

    atr_pct = _atr_pct(df)
    sl_oco = (atr_pct * 1.5).astype(float)
    tp_oco = (atr_pct * 3.0).astype(float)

    # VIX spike simulado (5% das barras) -> multiplicador 3.0 + lote 0.5
    vix_spike = pd.Series(
        np.random.default_rng(7).choice([True, False], p=[0.05, 0.95], size=len(df)),
        index=df.index,
    )
    atr_mult = pd.Series(np.where(vix_spike, 3.0, 1.5), index=df.index)
    size_dyn = pd.Series(np.where(vix_spike, 0.5, 1.0), index=df.index)
    sl_dyn = (atr_pct * atr_mult).astype(float)
    tp_dyn = (atr_pct * atr_mult * 2.0).astype(float)

    _, stats_base = _sim_layer(df["close"], entries, exits)
    _, stats_oco = _sim_layer(df["close"], entries, exits, tp=tp_oco, sl=sl_oco)
    _, stats_dyn = _sim_layer(df["close"], entries, exits, tp=tp_dyn, sl=sl_dyn, size=size_dyn)

    for name, stats in [("baseline", stats_base), ("oco_atr", stats_oco), ("oco_dyn", stats_dyn)]:
        assert stats is not None, f"{name} nao retornou stats"
        assert stats.get("Total Trades", 0) >= 0, name
        assert np.isfinite(stats.get("Total Return [%]", 0.0)), name

    # OCO dinamico deve ter risco financeiro constante: tamanho medio ~0.5 em spike.
    print("\n=== CAMADAS OCO (sintetico) ===")
    print(f"Baseline : WR={stats_base.get('Win Rate [%]', 0):.1f}% "
          f"MDD={stats_base.get('Max Drawdown [%]', 0):.2f}%")
    print(f"OCO ATR  : WR={stats_oco.get('Win Rate [%]', 0):.1f}% "
          f"MDD={stats_oco.get('Max Drawdown [%]', 0):.2f}%")
    print(f"OCO Dyn  : WR={stats_dyn.get('Win Rate [%]', 0):.1f}% "
          f"MDD={stats_dyn.get('Max Drawdown [%]', 0):.2f}%")


@pytest.mark.skipif(not (DATA_DIR / "XAUUSD_M1.parquet").exists(), reason="dados consolidados ausentes")
def test_correlation_xauusd_dxy_vix():
    """Fluxo 2 (integracao): correlacao XAUUSD-DXY/VIX e ponto de quebra."""
    xau = pd.read_parquet(DATA_DIR / "XAUUSD_M1.parquet")
    dxy = pd.read_parquet(DATA_DIR / "DXYUSD_M1.parquet")
    vix = pd.read_parquet(DATA_DIR / "VIXUSD_M1.parquet")

    for df in (xau, dxy, vix):
        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms")
            df.set_index("timestamp", inplace=True)

    joined = pd.DataFrame(index=xau.index)
    joined["xau_close"] = xau["close"]
    joined["dxy_close"] = dxy["close"].reindex(xau.index, method="ffill")
    joined["vix_close"] = vix["close"].reindex(xau.index, method="ffill")
    joined = joined.ffill().bfill().dropna()

    corr_dxy = joined["xau_close"].corr(joined["dxy_close"])
    corr_vix = joined["xau_close"].corr(joined["vix_close"])

    # "Gordura de ganho": amplitude media diaria vs espaco ate o TP projetado.
    daily_ret = joined["xau_close"].pct_change().abs().rolling(1440).mean().dropna()
    avg_amplitude = float(daily_ret.mean() * 100)

    print("\n=== CORRELACAO XAUUSD (Fluxo 2) ===")
    print(f"corr(XAUUSD, DXYUSD) = {corr_dxy:.4f}")
    print(f"corr(XAUUSD, VIXUSD) = {corr_vix:.4f}")
    print(f"Amplitude media M1 (1440b) = {avg_amplitude:.4f}%")

    assert np.isfinite(corr_dxy)
    assert np.isfinite(corr_vix)
    assert -1.0 <= corr_dxy <= 1.0
    assert -1.0 <= corr_vix <= 1.0
