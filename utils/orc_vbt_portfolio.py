"""orc_vbt_portfolio.py — S30-VBT: Backtest via vectorbt.Portfolio.from_signals().

PROPOSITO: Realizar backtest usando vectorbt
SPEC: S30
ROADMAP: 6.1

R-USE: orc_vectorbt.py (indicators), consolidated/ Parquet (2 anos).
Substitui o loop manual do backtest_simulator.py quando modo --vbt.

vectorbt.Portfolio.from_signals() oferece:
  - Slippage + comissoes configuraveis
  - Sharpe ratio, drawdown, profit factor, expectancy
  - Trade records completos (entries, exits, PnL, duration)
  - Benchmarking vs buy-and-hold
"""
from __future__ import annotations

import json
import time
from datetime import UTC
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONSOLIDATED = ROOT / "data" / "consolidated"
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def _compute_signals(close: np.ndarray, rsi_period: int = 14) -> tuple[np.ndarray, np.ndarray]:
    """Gera entries/exits a partir do RSI (regras S29) — LONG only.

    Returns (entries, exits) — arrays booleanos.
    RSI < 35 -> BUY entry; RSI > 65 -> close position.
    Sem short selling (evita 'infinite short direction' do VBT).
    """
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).ewm(span=rsi_period, adjust=False).mean().values
    avg_loss = pd.Series(loss).ewm(span=rsi_period, adjust=False).mean().values
    rs = np.divide(avg_gain, avg_loss, out=np.ones_like(avg_gain), where=avg_loss != 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    entries = rsi < 35
    exits = rsi > 65

    return entries.astype(bool), exits.astype(bool)


def run_vbt_portfolio(
    symbol: str,
    initial_capital: float = 10_000.0,
    slippage: float = 0.001,   # 0.1%
    commission: float = 0.0001, # 0.01%
) -> dict[str, Any]:
    """Executa backtest completo via vectorbt.Portfolio.from_signals().

    Retorna dict com metricas VBT + equity curve.
    """
    import vectorbt as vbt

    parquet_path = CONSOLIDATED / f"{symbol}_M1.parquet"
    if not parquet_path.exists():
        return {"symbol": symbol, "status": "error", "error": f"Parquet ausente: {parquet_path}"}

    t0 = time.time()

    # 1. Carregar OHLCV
    df = pd.read_parquet(parquet_path)
    df = df.sort_values("timestamp").reset_index(drop=True)
    close = df["close"].values.astype(np.float64)

    # 2. Gerar sinais (RSI) — LONG only
    entries, exits = _compute_signals(close)

    # 3. VectorBT Portfolio — com stops OCO nativos (S27 v3.0)
    pf = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=np.inf,          # all-in
        size_type="percent",
        init_cash=initial_capital,
        slippage=slippage,
        fees=commission,
        freq="1min",
        sl_stop=0.01,         # Stop-loss 1% (OCO implícito)
        tp_stop=0.02,         # Take-profit 2% (OCO implícito)
        sl_trail=True,        # Trailing stop ativo
        use_stops=True,
    )

    # 4. Extrair metricas
    stats = pf.stats()
    metrics = {
        "symbol": symbol,
        "status": "ok",
        "total_return_pct": round(float(stats.get("Total Return [%]", 0)), 2),
        "sharpe_ratio": round(float(stats.get("Sharpe Ratio", 0)), 2),
        "max_drawdown_pct": round(float(stats.get("Max Drawdown [%]", 0)), 2),
        "profit_factor": round(float(stats.get("Profit Factor", 0)), 2),
        "expectancy": round(float(stats.get("Expectancy", 0)), 2),
        "win_rate_pct": round(float(stats.get("Win Rate [%]", 0)), 2),
        "total_trades": int(stats.get("Total Trades", 0)),
        "avg_trade_duration": str(stats.get("Avg Trade Duration", "N/A")),
        "best_trade_pct": round(float(stats.get("Best Trade [%]", 0)), 2),
        "worst_trade_pct": round(float(stats.get("Worst Trade [%]", 0)), 2),
    }

    # 5. Equity curve diaria
    equity = pf.value()
    if isinstance(equity, pd.Series):
        from datetime import datetime

        # Reamostrar para diario (pegar ultimo valor de cada dia)
        # Converter timestamp ms -> datetime
        if "timestamp" in df.columns:
            ts_sec = df["timestamp"].values / 1000
            dates = [datetime.fromtimestamp(t, tz=UTC).strftime("%Y-%m-%d") for t in ts_sec]
            equity.index = dates

        # Agrupar por data (ultimo valor do dia)
        daily_equity = equity.groupby(equity.index).last()
        metrics["equity_curve"] = [
            {"date": str(d), "equity": round(float(v), 2)}
            for d, v in daily_equity.items()
        ]
    else:
        metrics["equity_curve"] = []

    metrics["elapsed_s"] = round(time.time() - t0, 1)
    return metrics


def run_all_vbt(
    initial_capital: float = 10_000.0,
    slippage: float = 0.001,
    commission: float = 0.0001,
) -> dict[str, Any]:
    """Executa VBT Portfolio em todos os 5 simbolos e consolida.

    Returns dict com per-symbol metrics + equity curve combinada.
    """
    results = {}
    combined_equity: dict[str, float] = {}
    total_start = time.time()

    for sym in SYMBOLS:
        print(f"  [{sym}] VBT Portfolio...")
        r = run_vbt_portfolio(sym, initial_capital, slippage, commission)
        results[sym] = r

        # Acumular equity curve
        for pt in r.get("equity_curve", []):
            d = pt["date"]
            combined_equity[d] = combined_equity.get(d, 0.0) + pt["equity"]

    # Equity combinada (soma dos 5 portfolios)
    combined = [
        {"date": d, "Total": round(v, 2)}
        for d, v in sorted(combined_equity.items())
    ]

    # Tabela resumo
    summary = []
    for sym, r in results.items():
        if r["status"] == "ok":
            summary.append({
                "symbol": sym,
                "total_return_pct": r["total_return_pct"],
                "sharpe_ratio": r["sharpe_ratio"],
                "max_drawdown_pct": r["max_drawdown_pct"],
                "win_rate_pct": r["win_rate_pct"],
                "total_trades": r["total_trades"],
            })

    return {
        "status": "ok",
        "initial_capital": initial_capital,
        "slippage_pct": slippage * 100,
        "commission_pct": commission * 100,
        "per_symbol": results,
        "combined_equity": combined,
        "summary": summary,
        "total_elapsed_s": round(time.time() - total_start, 1),
    }


if __name__ == "__main__":
    import sys

    sym = sys.argv[1] if len(sys.argv) > 1 else "XAUUSD"
    result = run_vbt_portfolio(sym)
    print(json.dumps(result, indent=2, default=str))
