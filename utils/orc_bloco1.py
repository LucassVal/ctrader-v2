"""PROPOSITO: Orquestrador do Bloco 1 - Torneio do Passado (Alpha Generation).

SPEC: S41 - Bloco 1: Torneio do Passado (v2.1)
ORQ: orc_bloco1

Wireia todos os SATs do Bloco 1:
  1. mae_mfe_orc_bloco1 - calculo de MAE/MFE
  2. signal_matrix_orc_bloco1 - matriz booleana de sinais
  3. dxy_filter_orc_bloco1 - filtro DXY+VIX (correlacao DURA por ROC)
  4. time_exit_orc_bloco1 - saidas por tempo (sem SL/TP)
  5. grid_search_orc_bloco1 - busca de parametros otimos

R-USE: compute_indicators() de utils/orc_vectorbt.py.
Contrato de saida conforme SPEC S41 v2.1.

Changelog v2.1:
  - preflight_check(): DXYUSD + VIXUSD reais (FAIL FAST)
  - SELL: RSI sobrecomprado (substitui BB/Keltner)
  - BUY_GRID: remove RSI(5), adiciona adx_threshold
  - Transparencia: [TORNEIO] + [RANKING] no console
  - Wire: status/bloco1_best.json -> orc_score
ROADMAP: FASE 3 (S41)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from utils.date_utils import backtest_end
from utils.grid_search_orc_bloco1 import run_parameter_grid
from utils.mae_mfe_orc_bloco1 import calc_mae_mfe
from utils.preflight_orc_bloco1 import preflight_check
from utils.signal_detector_orc_bloco1 import detect_buy_signals, detect_sell_signals
from utils.signal_matrix_orc_bloco1 import build_boolean_matrix
from utils.time_exit_orc_bloco1 import generate_exits

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# GRIDS DE PARAMETROS (v2.1)
# ═══════════════════════════════════════════════════════════════

BUY_GRID: dict[str, list[int]] = {
    "rsi_period": [8, 14, 21],
    "rsi_threshold": [25, 30],
    "macd_fast": [10, 14, 18],
    "adx_period": [14, 20],
    "adx_threshold": [20, 25],
}

SELL_GRID: dict[str, list[float]] = {
    "rsi_period": [8, 14, 21],
    "rsi_threshold": [65, 70, 75],
    "adx_period": [14, 20],
    "adx_threshold": [20, 25],
}

# ═══════════════════════════════════════════════════════════════
# AVALIADOR DE COMBO
# ═══════════════════════════════════════════════════════════════

def _evaluate_combo(
    df: pd.DataFrame,
    buy_params: dict[str, int],
    sell_params: dict[str, float],
    dxy_close: pd.Series,
    vix_close: pd.Series,
    symbol: str,
    horizon: int,
    apply_macro: bool = False,
    start_idx: int = 0,
) -> dict[str, Any]:
    """Avalia um combo de parametros no DataFrame. Suporta validacao dupla S41."""
    if start_idx > 0:
        df = df.iloc[start_idx:]
        dxy_close = dxy_close.iloc[start_idx:]
        vix_close = vix_close.iloc[start_idx:]

    buy_signals = detect_buy_signals(
        df,
        rsi_period=buy_params.get("rsi_period", 14),
        rsi_threshold=buy_params.get("rsi_threshold", 30),
        macd_fast=buy_params.get("macd_fast", 12),
        adx_period=buy_params.get("adx_period", 14),
        adx_threshold=buy_params.get("adx_threshold", 20),
    )
    sell_signals = detect_sell_signals(
        df,
        rsi_period=int(sell_params.get("rsi_period", 14)),
        rsi_threshold=int(sell_params.get("rsi_threshold", 70)),
        adx_period=int(sell_params.get("adx_period", 14)),
        adx_threshold=int(sell_params.get("adx_threshold", 20)),
    )

    if apply_macro:
        from utils.dxy_filter_orc_bloco1 import _DIRECT_SYMBOLS, _INVERSE_SYMBOLS

        roc = dxy_close.diff(5) / dxy_close.shift(5)
        roc = roc.fillna(0.0)
        vix_ok = vix_close <= 35.0

        dxy_up = roc > 0
        is_inverse = symbol in _INVERSE_SYMBOLS
        is_direct = symbol in _DIRECT_SYMBOLS

        neutral_mask = roc.abs() < 0.0005
        anomaly_threshold = 0.003

        buy_macro_ok = pd.Series(True, index=df.index)
        sell_macro_ok = pd.Series(True, index=df.index)

        if is_inverse:
            buy_macro_ok = neutral_mask | (~dxy_up | (roc.abs() <= anomaly_threshold))
            sell_macro_ok = neutral_mask | (dxy_up | (roc.abs() <= anomaly_threshold))
        elif is_direct:
            buy_macro_ok = neutral_mask | (dxy_up | (roc.abs() <= anomaly_threshold))
            sell_macro_ok = neutral_mask | (~dxy_up | (roc.abs() <= anomaly_threshold))

        dxy_ok_buy = buy_macro_ok & vix_ok
        dxy_ok_sell = sell_macro_ok & vix_ok
    else:
        dxy_ok_buy = pd.Series(True, index=df.index)
        dxy_ok_sell = pd.Series(True, index=df.index)

    _trigger = pd.DataFrame({"BUY": buy_signals, "SELL": sell_signals})
    _force = pd.DataFrame(True, index=df.index, columns=["BUY", "SELL"])
    _validated = build_boolean_matrix(_trigger, _force, dxy_ok_buy=dxy_ok_buy, dxy_ok_sell=dxy_ok_sell)
    buy_signals = _validated["BUY"]
    sell_signals = _validated["SELL"]

    n_buy = int(buy_signals.sum())
    n_sell = int(sell_signals.sum())

    # Simula trades e calcula MAE
    trades = []
    total_mae = 0.0
    n_trades = 0

    # Cria iteradores de sinais
    for direction in ["BUY", "SELL"]:
        sig_series = buy_signals if direction == "BUY" else sell_signals
        entries_idx = sig_series[sig_series].index

        for entry_ts in entries_idx:
            try:
                pos = df.index.get_loc(entry_ts)
            except KeyError:
                continue

            if pos + horizon >= len(df):
                continue

            entry_price = float(df["open"].iloc[pos + 1]) if pos + 1 < len(df) else float(df["close"].iloc[pos])
            exit_idx = generate_exits(pos, len(df), horizon)
            exit_price = float(df["close"].iloc[exit_idx])
            high_slice = df["high"].iloc[pos + 1 : exit_idx + 1]
            low_slice = df["low"].iloc[pos + 1 : exit_idx + 1]

            mae, mfe = calc_mae_mfe(
                entry_price=entry_price,
                highs=high_slice,
                lows=low_slice,
                exit_idx=horizon - 1,
                direction="LONG" if direction == "BUY" else "SHORT",
            )

            if direction == "BUY":
                pnl = (exit_price - entry_price) / entry_price
            else:
                pnl = (entry_price - exit_price) / entry_price

            total_mae += mae
            n_trades += 1

            trades.append({
                "entry_time": str(entry_ts),
                "exit_time": str(df.index[pos + horizon]) if pos + horizon < len(df.index) else None,
                "direction": direction,
                "entry_price": entry_price,
                "exit_price": exit_price,
                "mae_pct": round(mae, 6),
                "mfe_pct": round(mfe, 6),
                "pnl_pct": round(pnl, 6),
                "horizon": horizon,
            })

    avg_mae = total_mae / n_trades if n_trades > 0 else float("inf")
    n_dxy_filtered = int((~dxy_ok_buy).sum() + (~dxy_ok_sell).sum()) if apply_macro else 0

    return {
        "avg_mae": avg_mae,
        "n_trades": n_trades,
        "n_buy": n_buy,
        "n_sell": n_sell,
        "trades": trades,
        "dxy_filtered": n_dxy_filtered,
    }


# ═══════════════════════════════════════════════════════════════
# ORQUESTRADOR PRINCIPAL
# ═══════════════════════════════════════════════════════════════

def run_bloco1(
    ohlc_df: pd.DataFrame,
    symbol: str = "XAUUSD",
    tf: str = "M5",
    horizon: int = 5,
    use_macro: bool = True,
) -> dict[str, Any]:
    """Orquestrador do Bloco 1: Torneio do Passado (v2.1)."""
    if ohlc_df.empty:
        return {
            "symbol": symbol, "tf": tf,
            "window": {"train_start": None, "train_end": None},
            "best_buy_trigger": {}, "best_sell_trigger": {},
            "force_threshold": {},
            "signals_validated": {"total": 0, "buy": 0, "sell": 0},
            "dxy_filtered_out": 0, "trades": [],
        }

    if not isinstance(ohlc_df.index, pd.DatetimeIndex):
        if "timestamp" in ohlc_df.columns:
            ohlc_df = ohlc_df.copy()
            ohlc_df.index = pd.to_datetime(ohlc_df["timestamp"])
        else:
            ohlc_df = ohlc_df.copy()
            ohlc_df.index = pd.RangeIndex(len(ohlc_df))

    ohlc_df, dxy_close, vix_close = preflight_check(ohlc_df, symbol)
    n_bars = len(ohlc_df)

    buy_grid_df = run_parameter_grid(BUY_GRID, max_combos=50)
    sell_grid_df = run_parameter_grid(SELL_GRID, max_combos=32)

    # -- Avalia combos (Fluxo 1: Otimizacao 2 Anos sem Macro) --
    best_buy = {"avg_mae": float("inf")}
    best_buy_params: dict[str, int] = {}
    best_sell = {"avg_mae": float("inf")}
    best_sell_params: dict[str, float] = {}

    buy_results: list[dict[str, Any]] = []
    sell_results: list[dict[str, Any]] = []

    buy_default_sell = {"rsi_period": 14.0, "rsi_threshold": 70.0, "adx_period": 14.0, "adx_threshold": 20.0}
    sell_default_buy = {"rsi_period": 14, "rsi_threshold": 30, "macd_fast": 12, "adx_period": 14, "adx_threshold": 20}

    for _, row in buy_grid_df.iterrows():
        params = {k: int(v) for k, v in row.items() if k != "mae" and k in BUY_GRID}
        if not params:
            continue
        result = _evaluate_combo(ohlc_df, params, buy_default_sell, dxy_close, vix_close, symbol, horizon, apply_macro=use_macro)
        result["params"] = params
        buy_results.append(result)
        if result["avg_mae"] < best_buy["avg_mae"] and result["n_trades"] > 0:
            best_buy = result
            best_buy_params = params

    for _, row in sell_grid_df.iterrows():
        params = {k: float(v) for k, v in row.items() if k != "mae" and k in SELL_GRID}
        if not params:
            continue
        result = _evaluate_combo(ohlc_df, sell_default_buy, params, dxy_close, vix_close, symbol, horizon, apply_macro=use_macro)
        result["params"] = params
        sell_results.append(result)
        if result["avg_mae"] < best_sell["avg_mae"] and result["n_trades"] > 0:
            best_sell = result
            best_sell_params = params

    # -- RANKING INTERMEDIARIO --
    buy_ranking = sorted(buy_results, key=lambda x: x["avg_mae"])[:3]
    sell_ranking = sorted(sell_results, key=lambda x: x["avg_mae"])[:3]
    if buy_ranking:
        print("[RANKING BUY] Top 3 menor MAE:")
        for i, r in enumerate(buy_ranking, 1):
            print(f"  {i}. MAE={r['avg_mae']*100:.3f}% trades={r['n_trades']} params={r.get('params',{})}")
    if sell_ranking:
        print("[RANKING SELL] Top 3 menor MAE:")
        for i, r in enumerate(sell_ranking, 1):
            print(f"  {i}. MAE={r['avg_mae']*100:.3f}% trades={r['n_trades']} params={r.get('params',{})}")
    print()

    # -- Melhor combo final --
    best_buy_final = best_buy_params if best_buy_params else {"rsi_period": 14, "rsi_threshold": 30, "macd_fast": 12, "adx_period": 14, "adx_threshold": 20}
    best_sell_final = best_sell_params if best_sell_params else {"rsi_period": 14.0, "rsi_threshold": 70.0, "adx_period": 14.0, "adx_threshold": 20.0}

    final_result = _evaluate_combo(ohlc_df, best_buy_final, best_sell_final, dxy_close, vix_close, symbol, horizon, apply_macro=use_macro)

    # -- Monta contrato de saida --
    start_ts = str(ohlc_df.index[0]) if n_bars > 0 else None
    end_ts = str(ohlc_df.index[-1]) if n_bars > 0 else None

    result = {
        "symbol": symbol,
        "tf": tf,
        "window": {
            "train_start": start_ts,
            "train_end": end_ts,
            "backtest_end_utc": backtest_end().isoformat(),
        },
        "best_buy_trigger": {
            **{k: int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for k, v in best_buy_final.items()},
            "mae_pct": round(best_buy.get("avg_mae", 0.0), 4),
        },
        "best_sell_trigger": {
            **{k: float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v for k, v in best_sell_final.items()},
            "mae_pct": round(best_sell.get("avg_mae", 0.0), 4),
        },
        "force_threshold": {"tick_vol_pct": 80, "roc_pct": 0.5, "vix_max": 35.0},
        "signals_validated": {
            "total": final_result["n_buy"] + final_result["n_sell"],
            "buy": final_result["n_buy"],
            "sell": final_result["n_sell"],
        },
        "dxy_filtered_out": final_result.get("dxy_filtered", 0),
        "trades": final_result["trades"],
        "best_combo": {
            "buy_trigger": best_buy_final,
            "sell_trigger": best_sell_final,
        },
    }

    # -- WIRE Lab -> Analise --
    import json as _json
    _wire_path = Path(__file__).resolve().parent.parent / "status" / "bloco1_best.json"
    _wire_path.parent.mkdir(parents=True, exist_ok=True)
    _wire_data = {
        "symbol": symbol, "tf": tf,
        "best_buy_trigger": result["best_buy_trigger"],
        "best_sell_trigger": result["best_sell_trigger"],
        "signals_validated": result["signals_validated"],
        "best_combo": result["best_combo"],
    }
    _wire_path.write_text(_json.dumps(_wire_data, indent=2, default=str))

    return result
