"""backtest_simulator.py — Gera backtest_trades.db a partir do Parquet VBT consolidado.

PROPOSITO: Simular trades no historico
SPEC: S29
ROADMAP: 6.1

R-USE: consolidated/ Parquet (2 anos) + VBT indicators.
Pipeline: Parquet M_1 -> VBT indicators -> sinais (regras S29) -> trades simulados -> backtest_trades.db.
Executar: python backtest_simulator.py [--fast]  (--fast = amostra 5% para teste rapido)
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent  # f0_collector/ -> ctrader/
CONSOLIDATED_DIR = ROOT / "data" / "consolidated"
DB_OUT = ROOT / "status" / "backtest_trades.db"
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
TP_PIPS = 20.0           # take profit em pips
SL_PIPS = 10.0           # stop loss em pips
PIP_VALUES = {"XAUUSD": 0.1, "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "AUDUSD": 0.0001}


def compute_vbt_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computa indicadores VBT inline (R-USE: orc_vectorbt nao importado — evitamos numba JIT)."""
    import numpy as np

    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    n = len(close)

    # RSI (14)
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).ewm(span=14, adjust=False).mean().values
    avg_loss = pd.Series(loss).ewm(span=14, adjust=False).mean().values
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR (14)
    tr_raw = np.maximum(high - low, np.abs(high - np.roll(close, 1)))
    tr_raw[0] = high[0] - low[0]
    tr = tr_raw
    atr = pd.Series(tr).ewm(span=14, adjust=False).mean().values
    df["adx"] = 20.0  # simplified — full ADX needs +DM/-DM

    # MACD (12, 26, 9)
    ema12 = pd.Series(close).ewm(span=12, adjust=False).mean().values
    ema26 = pd.Series(close).ewm(span=26, adjust=False).mean().values
    macd_line = ema12 - ema26
    signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values
    df["macd"] = macd_line - signal_line  # histogram

    # Bollinger Bands position (20, 2)
    sma20 = pd.Series(close).rolling(20).mean().values
    std20 = pd.Series(close).rolling(20).std().values
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20
    df["bb_position"] = np.divide(close - bb_lower, bb_upper - bb_lower,
                                   out=np.full(n, 0.5), where=(bb_upper - bb_lower) != 0)

    # ATR %
    df["atr_pct"] = atr / close * 100

    return df


def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    """Regras S29 simplificadas: RSI < 35 -> BUY; RSI > 65 -> SELL (ADX simplificado)."""
    import numpy as np
    signals = np.zeros(len(df), dtype=int)
    rsi = df["rsi"].values
    signals[rsi < 35] = 1
    signals[rsi > 65] = -1
    df["signal"] = signals
    df["confidence"] = np.where(
        signals != 0,
        np.abs(rsi - 50) / 50,
        0.0,
    )
    return df


def simulate_trades(df: pd.DataFrame, symbol: str, pip_val: float, lookahead_bars: int, tf_label: str) -> list[dict]:
    """Simula trades: entrada na vela seguinte ao sinal, saida apos LOOKAHEAD ou TP/SL."""
    trades = []
    close = df["close"].values
    high = df["high"].values
    low = df["low"].values
    timestamps = df["timestamp"].values  # ms
    signals = df["signal"].values
    confidences = df["confidence"].values

    tp_price = TP_PIPS * pip_val
    sl_price = SL_PIPS * pip_val

    i = 0
    while i < len(df) - lookahead_bars - 1:
        sig = signals[i]
        if sig == 0:
            i += 1
            continue

        entry_price = close[i + 1]
        entry_ts = timestamps[i + 1]
        exit_price = entry_price
        pnl = 0.0

        # Check TP/SL within lookahead
        for j in range(1, lookahead_bars + 1):
            idx = i + 1 + j
            if idx >= len(df):
                break
            if sig == 1:  # BUY -> lucro se sobe
                if high[idx] >= entry_price + tp_price:
                    exit_price = entry_price + tp_price
                    pnl = TP_PIPS
                    break
                if low[idx] <= entry_price - sl_price:
                    exit_price = entry_price - sl_price
                    pnl = -SL_PIPS
                    break
            else:  # SELL -> lucro se desce
                if low[idx] <= entry_price - tp_price:
                    exit_price = entry_price - tp_price
                    pnl = TP_PIPS
                    break
                if high[idx] >= entry_price + sl_price:
                    exit_price = entry_price + sl_price
                    pnl = -SL_PIPS
                    break

        # Time exit: último bar do lookahead
        if pnl == 0.0:
            exit_idx = min(i + 1 + lookahead_bars, len(df) - 1)
            exit_price = close[exit_idx]
            pnl_pips = (exit_price - entry_price) / pip_val
            pnl = pnl_pips if sig == 1 else -pnl_pips

        side = "BUY" if sig == 1 else "SELL"
        ts_entry_str = datetime.fromtimestamp(entry_ts / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        scores_json = json.dumps({"scores": {"final_adjusted": round(float(confidences[i]) * 100, 1)}})

        trades.append({
            "symbol": symbol,
            "timeframe": tf_label,
            "side": side,
            "timestamp_utc": ts_entry_str,
            "pnl_net": round(pnl, 2),
            "scores_json": scores_json,
            "exit_price": round(float(exit_price), 5),
        })

        # Pular LOOKAHEAD barras apos entrada (evitar overlapping)
        i += lookahead_bars + 1

    return trades


def main():
    fast = "--fast" in sys.argv
    print(f"[START] Backtest Simulator {'(FAST 5%)' if fast else '(FULL 2 anos)'}")

    DB_OUT.parent.mkdir(parents=True, exist_ok=True)

    # Criar DB
    if DB_OUT.exists():
        DB_OUT.unlink()
    conn = sqlite3.connect(str(DB_OUT))
    conn.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT, timeframe TEXT, side TEXT,
        timestamp_utc TEXT, pnl_net REAL,
        scores_json TEXT, exit_price REAL
    )""")
    conn.commit()

    total_trades = 0
    for sym in SYMBOLS:
        parquet_path = CONSOLIDATED_DIR / f"{sym}_M1.parquet"
        if not parquet_path.exists():
            print(f"  [SKIP] {sym} — {parquet_path} nao encontrado")
            continue

        print(f"  [{sym}] Lendo Parquet...")
        df = pd.read_parquet(parquet_path)
        if fast:
            df = df.iloc[::20].reset_index(drop=True)  # 5% amostra

        # Timestamps em ms -> garantir sort
        df = df.sort_values("timestamp").reset_index(drop=True)
        print(f"  [{sym}] {len(df)} barras — computando VBT...")
        df = compute_vbt_indicators(df)
        df = generate_signals(df)

        n_signals = int((df["signal"] != 0).sum())
        print(f"  [{sym}] {n_signals} sinais — simulando trades M5 e M15...")

        # Simula M5 (5 barras de M1)
        trades_m5 = simulate_trades(df, sym, PIP_VALUES[sym], lookahead_bars=5, tf_label="M5")
        # Simula M15 (15 barras de M1)
        trades_m15 = simulate_trades(df, sym, PIP_VALUES[sym], lookahead_bars=15, tf_label="M15")

        trades = trades_m5 + trades_m15

        if trades:
            conn.executemany(
                "INSERT INTO trades (symbol, timeframe, side, timestamp_utc, pnl_net, scores_json, exit_price) "
                "VALUES (:symbol, :timeframe, :side, :timestamp_utc, :pnl_net, :scores_json, :exit_price)",
                trades,
            )
            conn.commit()
        print(f"  [{sym}] {len(trades)} trades escritos")
        total_trades += len(trades)

    conn.close()
    print(f"[OK] {total_trades} trades totais em {DB_OUT}")
    print("     Verifique: curl http://127.0.0.1:7744/api/ctrader/performance?mode=backtest")


if __name__ == "__main__":
    main()
