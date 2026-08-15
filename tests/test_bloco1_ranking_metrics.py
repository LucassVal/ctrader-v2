"""Harness S41: Bloco 1 — Ranking de Metricas Buy/Sell (Adaptativo).

PROPOSITO: Validar o ranking das metricas do Torneio do Passado (Fluxo 1).
  - 2 anos de dados, 5 ativos (forex).
  - Ranking BUY/SELL por MAE (melhor metrica para o presente).
  - Calcula win rate / profit factor / sharpe / max drawdown a partir dos trades.
SPEC: S41
ROADMAP: FASE 3 — Bloco 1 v3.0 (validacao empirica do ranking)
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "consolidated"
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def _load_m5(symbol: str) -> pd.DataFrame:
    """Carrega parquet M1 consolidado e resample para M5."""
    path = DATA_DIR / f"{symbol}_M1.parquet"
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms")
        df.set_index("timestamp", inplace=True)
    for col in ["open", "high", "low", "close"]:
        if col in df.columns:
            df[col] = df[col].astype(float) / 100000.0
    if "tick_volume" in df.columns:
        df["tick_volume"] = df["tick_volume"].astype(float)
    ohlcv = df.resample("5min").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "tick_volume": "sum",
        }
    ).dropna()
    return ohlcv


def _ranking_metrics(trades: list[dict]) -> dict[str, float]:
    """Deriva metricas de ranking a partir da lista de trades do Bloco 1."""
    if not trades:
        return {
            "total_trades": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
        }
    pnl = pd.Series([float(t.get("pnl_pct", 0.0)) for t in trades])
    wins = pnl[pnl > 0].sum()
    losses = -pnl[pnl < 0].sum()
    profit_factor = wins / losses if losses > 0 else float("inf")
    sharpe = pnl.mean() / pnl.std() if pnl.std() > 0 else 0.0
    equity = (1.0 + pnl).cumprod()
    max_drawdown = float(((equity.cummax() - equity) / equity.cummax()).max() * 100)
    return {
        "total_trades": float(len(trades)),
        "win_rate": float((pnl > 0).mean() * 100),
        "profit_factor": float(profit_factor),
        "sharpe": float(sharpe),
        "max_drawdown": max_drawdown,
    }


def test_ranking_contract_synthetic():
    """Mecanica do ranking: run_bloco1 retorna contrato valido com dados sinteticos."""
    from utils.orc_bloco1 import run_bloco1

    df = pd.DataFrame(
        {
            "open": np.linspace(100, 110, 120),
            "high": np.linspace(101, 112, 120),
            "low": np.linspace(99, 108, 120),
            "close": np.linspace(100.5, 110.5, 120),
            "tick_volume": np.full(120, 5000),
        }
    )
    result = run_bloco1(ohlc_df=df, symbol="XAUUSD", tf="M5", horizon=5)

    assert "best_buy_trigger" in result
    assert "best_sell_trigger" in result
    assert "signals_validated" in result
    buy_mae = result["best_buy_trigger"].get("mae_pct")
    sell_mae = result["best_sell_trigger"].get("mae_pct")
    assert buy_mae is not None and np.isfinite(buy_mae)
    assert sell_mae is not None and np.isfinite(sell_mae)


def test_ranking_metrics_derived():
    """Metricas derivadas dos trades devem ser finitas e consistentes."""
    trades = [
        {"pnl_pct": 0.5, "direction": "BUY"},
        {"pnl_pct": -0.3, "direction": "BUY"},
        {"pnl_pct": 0.2, "direction": "SELL"},
        {"pnl_pct": -0.1, "direction": "SELL"},
    ]
    metrics = _ranking_metrics(trades)
    assert metrics["total_trades"] == 4
    assert metrics["win_rate"] == 50.0
    assert np.isfinite(metrics["profit_factor"])
    assert np.isfinite(metrics["sharpe"])
    assert metrics["max_drawdown"] >= 0.0


@pytest.mark.skipif(not (DATA_DIR / "XAUUSD_M1.parquet").exists(), reason="dados consolidados ausentes")
def test_ranking_real_xauusd():
    """Fluxo 1 (integracao): ranking real XAUUSD M5 — imprime metricas para documentacao."""
    from utils.orc_bloco1 import run_bloco1

    ohlcv = _load_m5("XAUUSD")
    result = run_bloco1(ohlcv, "XAUUSD", "M5", horizon=5)
    metrics = _ranking_metrics(result["trades"])

    print("\n=== RANKING BUY/SELL XAUUSD M5 (S41) ===")
    print(f"BUY  best: {result['best_buy_trigger']}")
    print(f"SELL best: {result['best_sell_trigger']}")
    print(f"Sinais validados: {result['signals_validated']}")
    print(f"Metricas derivadas: {metrics}")

    assert result["signals_validated"]["total"] >= 0
    assert np.isfinite(metrics["max_drawdown"])


@pytest.mark.skipif(not (DATA_DIR / "XAUUSD_M1.parquet").exists(), reason="dados consolidados ausentes")
def test_ranking_real_five_symbols():
    """Fluxo 1 (integracao): ranking para os 5 ativos forex (2 anos)."""
    from utils.orc_bloco1 import run_bloco1

    ranking = {}
    for sym in SYMBOLS:
        ohlcv = _load_m5(sym)
        result = run_bloco1(ohlcv, sym, "M5", horizon=5)
        metrics = _ranking_metrics(result["trades"])
        ranking[sym] = {
            "buy_mae_pct": result["best_buy_trigger"].get("mae_pct"),
            "sell_mae_pct": result["best_sell_trigger"].get("mae_pct"),
            "signals": result["signals_validated"]["total"],
            "win_rate": metrics["win_rate"],
            "sharpe": metrics["sharpe"],
        }
        print(f"\n[{sym}] BUY MAE={ranking[sym]['buy_mae_pct']} | "
              f"SELL MAE={ranking[sym]['sell_mae_pct']} | "
              f"sinais={ranking[sym]['signals']} | "
              f"WR={ranking[sym]['win_rate']:.1f}% | "
              f"Sharpe={ranking[sym]['sharpe']:.2f}")

    assert set(ranking.keys()) == set(SYMBOLS)
    for sym, r in ranking.items():
        assert r["buy_mae_pct"] is not None and np.isfinite(r["buy_mae_pct"]), sym
        assert r["sell_mae_pct"] is not None and np.isfinite(r["sell_mae_pct"]), sym
