"""PROPOSITO: Orquestrador do Bloco 1 — Torneio do Passado (Alpha Generation).

SPEC: S41 — Bloco 1: Torneio do Passado (v2.1)
ORQ: orc_bloco1

Wireia todos os SATs do Bloco 1:
  1. mae_mfe_orc_bloco1 — calculo de MAE/MFE
  2. signal_matrix_orc_bloco1 — matriz booleana de sinais
  3. dxy_filter_orc_bloco1 — filtro DXY+VIX (correlacao DURA por ROC)
  4. time_exit_orc_bloco1 — saidas por tempo (sem SL/TP)
  5. grid_search_orc_bloco1 — busca de parametros otimos

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

import numpy as np
import pandas as pd

from utils.dxy_filter_orc_bloco1 import (
    check_dxy_alignment,
    check_vix_filter,
    get_dxy_roc,
)
from utils.grid_search_orc_bloco1 import run_parameter_grid
from utils.signal_matrix_orc_bloco1 import build_boolean_matrix

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
# PREFLIGHT — DXYUSD + VIXUSD (FAIL FAST)
# ═══════════════════════════════════════════════════════════════

def preflight_check(
    ohlc_df: pd.DataFrame,
    symbol: str,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Baixa e alinha DXYUSD + VIXUSD do parquet. FAIL FAST se ausentes.

    Universo Macro (S41.4 v2.0):
      DXYUSD — Filtro Direcional (ROC 5 periodos)
      VIXUSD — Filtro de Volatilidade/Panico (>35 = aborta)

    Returns:
        (ohlc_df, dxy_close, vix_close): Series alinhadas por timestamp.
    """
    import sys as _sys

    data_dir = Path(__file__).resolve().parent.parent / "data"
    consolidated_dir = data_dir / "consolidated"

    dxy_path = consolidated_dir / "DXYUSD_M1.parquet"
    vix_path = consolidated_dir / "VIXUSD_M1.parquet"

    if not dxy_path.exists():
        logger.error("PREFLIGHT: %s nao encontrado. Execute backfill. ABORTANDO %s.", dxy_path, symbol)
        print("[PREFLIGHT] ERRO: DXYUSD_M1.parquet ausente. Execute backfill primeiro.")
        _sys.exit(1)
    if not vix_path.exists():
        logger.error("PREFLIGHT: %s nao encontrado. Execute backfill. ABORTANDO %s.", vix_path, symbol)
        print("[PREFLIGHT] ERRO: VIXUSD_M1.parquet ausente. Execute backfill primeiro.")
        _sys.exit(1)

    try:
        dxy_df = pd.read_parquet(dxy_path)
        vix_df = pd.read_parquet(vix_path)
    except Exception as e:
        logger.error("PREFLIGHT: erro ao ler parquet — %s. ABORTANDO.", e)
        _sys.exit(1)

    # Alinha ao index do ativo (forward fill)
    # Se o index do ativo for datetime, alinha por timestamp.
    # Se for int64 (testes/dados sinteticos), alinha por posicao.
    ohlc_idx = ohlc_df.index
    if isinstance(ohlc_idx, pd.DatetimeIndex):
        idx_naive = ohlc_idx.tz_localize(None) if hasattr(ohlc_idx, 'tz') and ohlc_idx.tz is not None else ohlc_idx
        dxy_aligned = dxy_df["close"].reindex(idx_naive, method="ffill")
        vix_aligned = vix_df["close"].reindex(idx_naive, method="ffill")
    else:
        # Index nao-datetime (testes): trunca ou estica para o tamanho do ativo
        dxy_vals = dxy_df["close"].values
        vix_vals = vix_df["close"].values
        n = len(ohlc_df)
        dxy_aligned = pd.Series(
            np.resize(dxy_vals, n) if len(dxy_vals) > 0 else np.zeros(n),
            index=ohlc_df.index,
        )
        vix_aligned = pd.Series(
            np.resize(vix_vals, n) if len(vix_vals) > 0 else np.zeros(n),
            index=ohlc_df.index,
        )

    n_dxy_miss = dxy_aligned.isna().sum()
    n_vix_miss = vix_aligned.isna().sum()
    n_bars = len(ohlc_df)  # usa ohlc_df original (pode ter tz)

    if n_dxy_miss > n_bars * 0.5:
        logger.error("PREFLIGHT: DXYUSD >50%% missing (%d/%d). ABORTANDO.", n_dxy_miss, n_bars)
        _sys.exit(1)
    if n_vix_miss > n_bars * 0.5:
        logger.error("PREFLIGHT: VIXUSD >50%% missing (%d/%d). ABORTANDO.", n_vix_miss, n_bars)
        _sys.exit(1)

    dxy_aligned = dxy_aligned.ffill().bfill().fillna(0.0)
    vix_aligned = vix_aligned.ffill().bfill().fillna(0.0)

    # Normaliza VIX: cTrader retorna em escala bruta (~100,000x)
    # Valor real do VIX fica entre 10-40. Divisao por 100,000.
    vix_aligned = vix_aligned / 100_000.0

    cov_dxy = (1 - n_dxy_miss / n_bars) * 100 if n_bars > 0 else 0
    cov_vix = (1 - n_vix_miss / n_bars) * 100 if n_bars > 0 else 0

    logger.info("PREFLIGHT: DXY=%db(%.0f%%) VIX=%db(%.0f%%) alinhados com %s",
                n_bars, cov_dxy, n_bars, cov_vix, symbol)
    print(f"[PREFLIGHT] DXYUSD+VIXUSD: {n_bars} barras, cobertura DXY={cov_dxy:.0f}% VIX={cov_vix:.0f}%, alinhado com {symbol}")
    return ohlc_df, dxy_aligned, vix_aligned


# ═══════════════════════════════════════════════════════════════
# DETECTORES DE SINAL
# ═══════════════════════════════════════════════════════════════

def _detect_buy_signals(
    df: pd.DataFrame,
    rsi_period: int = 14,
    rsi_threshold: int = 30,
    macd_fast: int = 12,
    adx_period: int = 14,
    adx_threshold: int = 25,
) -> pd.Series:
    """Detecta sinais de compra: RSI oversold (dip) + MACD + ADX."""
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    n = len(close)

    if n < max(rsi_period, macd_fast, adx_period) + 2:
        return pd.Series([False] * n, index=df.index)

    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).rolling(rsi_period, min_periods=1).mean().values
    avg_loss = pd.Series(loss).rolling(rsi_period, min_periods=1).mean().values
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi_oversold = rsi < rsi_threshold

    ema_fast = pd.Series(close).ewm(span=macd_fast, adjust=False).mean().values
    ema_slow = pd.Series(close).ewm(span=macd_fast * 2, adjust=False).mean().values
    macd_line = ema_fast - ema_slow
    macd_signal_line = pd.Series(macd_line).ewm(span=9, adjust=False).mean().values
    macd_bullish = macd_line > macd_signal_line

    tr = np.maximum.reduce([
        high - low,
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1)),
    ])
    tr[0] = high[0] - low[0]
    atr_adx = pd.Series(tr).rolling(adx_period, min_periods=1).mean().values
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    up_move[0] = 0
    down_move[0] = 0
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = pd.Series(plus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx * 100
    minus_di = pd.Series(minus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx * 100
    adx_val = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx_strong = adx_val > adx_threshold

    buy_signal = rsi_oversold & macd_bullish & adx_strong
    return pd.Series(buy_signal, index=df.index)


def _detect_sell_signals(
    df: pd.DataFrame,
    rsi_period: int = 14,
    rsi_threshold: int = 70,
    adx_period: int = 14,
    adx_threshold: int = 20,
) -> pd.Series:
    """Detecta sinais de venda: RSI sobrecomprado + ADX confirma tendencia de baixa."""
    close = df["close"].values.astype(np.float64)
    high = df["high"].values.astype(np.float64)
    low = df["low"].values.astype(np.float64)
    n = len(close)

    if n < max(rsi_period, adx_period) + 2:
        return pd.Series([False] * n, index=df.index)

    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    avg_gain = pd.Series(gain).rolling(rsi_period, min_periods=1).mean().values
    avg_loss = pd.Series(loss).rolling(rsi_period, min_periods=1).mean().values
    rs = np.divide(avg_gain, avg_loss, out=np.zeros_like(avg_gain), where=avg_loss != 0)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    rsi_overbought = rsi > rsi_threshold

    tr = np.maximum.reduce([
        high - low,
        np.abs(high - np.roll(close, 1)),
        np.abs(low - np.roll(close, 1)),
    ])
    tr[0] = high[0] - low[0]
    atr_adx = pd.Series(tr).rolling(adx_period, min_periods=1).mean().values
    up_move = high - np.roll(high, 1)
    down_move = np.roll(low, 1) - low
    up_move[0] = 0
    down_move[0] = 0
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_di = 100 * pd.Series(plus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx
    minus_di = 100 * pd.Series(minus_dm).rolling(adx_period, min_periods=1).mean().values / atr_adx
    adx_val = np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10) * 100
    adx_strong = adx_val > adx_threshold
    bearish_trend = minus_di > plus_di

    sell_signal = rsi_overbought & bearish_trend & adx_strong
    return pd.Series(sell_signal, index=df.index)


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
) -> dict[str, Any]:
    """Avalia um combo de parametros no DataFrame completo."""
    buy_signals = _detect_buy_signals(
        df,
        rsi_period=buy_params.get("rsi_period", 14),
        rsi_threshold=buy_params.get("rsi_threshold", 30),
        macd_fast=buy_params.get("macd_fast", 12),
        adx_period=buy_params.get("adx_period", 14),
        adx_threshold=buy_params.get("adx_threshold", 20),
    )
    sell_signals = _detect_sell_signals(
        df,
        rsi_period=int(sell_params.get("rsi_period", 14)),
        rsi_threshold=int(sell_params.get("rsi_threshold", 70)),
        adx_period=int(sell_params.get("adx_period", 14)),
        adx_threshold=int(sell_params.get("adx_threshold", 20)),
    )

    # Filtro DXY + VIX
    dxy_roc = get_dxy_roc(dxy_close.values, lookback=5)
    dxy_buy_ok = check_dxy_alignment(symbol, "BULLISH", dxy_roc)
    dxy_sell_ok = check_dxy_alignment(symbol, "BEARISH", dxy_roc)

    vix_val = float(vix_close.iloc[-1]) if len(vix_close) > 0 else 0.0
    vix_ok = check_vix_filter(vix_val, max_vix=35.0)

    dxy_ok_series = pd.Series([(dxy_buy_ok or dxy_sell_ok) and vix_ok] * len(df), index=df.index)

    # Matriz booleana
    trigger = pd.DataFrame({"BUY": buy_signals, "SELL": sell_signals})
    force = pd.DataFrame({"BUY": [True] * len(df), "SELL": [True] * len(df)}, index=df.index)
    validated = build_boolean_matrix(trigger, force, dxy_ok_series)

    n_buy = int(validated["BUY"].sum())
    n_sell = int(validated["SELL"].sum())

    # Simula trades e calcula MAE
    trades = []
    total_mae = 0.0
    n_trades = 0

    for direction in ["BUY", "SELL"]:
        sig_series = validated[direction]
        entries_idx = sig_series[sig_series].index

        for entry_ts in entries_idx:
            try:
                pos = df.index.get_loc(entry_ts)
            except KeyError:
                continue

            if pos + horizon >= len(df):
                continue

            entry_price = float(df["open"].iloc[pos + 1]) if pos + 1 < len(df) else float(df["close"].iloc[pos])
            exit_price = float(df["close"].iloc[pos + horizon])
            high_slice = df["high"].iloc[pos + 1 : pos + horizon + 1]
            low_slice = df["low"].iloc[pos + 1 : pos + horizon + 1]

            if direction == "BUY":
                mae = (entry_price - low_slice.min()) / entry_price
                mfe = (high_slice.max() - entry_price) / entry_price
                pnl = (exit_price - entry_price) / entry_price
            else:
                mae = (high_slice.max() - entry_price) / entry_price
                mfe = (entry_price - low_slice.min()) / entry_price
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
    n_dxy_filtered = int((~dxy_ok_series).sum())

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

    # -- PREFLIGHT: DXYUSD + VIXUSD --
    print(f"\n[TORNEIO] {symbol} {tf} — iniciando Bloco 1 com {len(ohlc_df)} barras")
    ohlc_df, dxy_close, vix_close = preflight_check(ohlc_df, symbol)

    n_bars = len(ohlc_df)

    # -- Grid search --
    buy_grid_df = run_parameter_grid(BUY_GRID, max_combos=50)
    sell_grid_df = run_parameter_grid(SELL_GRID, max_combos=32)

    # -- TRANSPARENCIA --
    buy_candidates = list(BUY_GRID.keys())
    sell_candidates = list(SELL_GRID.keys())
    force_candidates = ["ADX", "ROC(DXY)", "VIX", "tick_volume"]
    print(f"[TORNEIO] COMPRA ({len(buy_grid_df)} combos): {', '.join(buy_candidates)}")
    print(f"[TORNEIO] VENDA ({len(sell_grid_df)} combos): {', '.join(sell_candidates)}")
    print(f"[TORNEIO] FORCA/FILTRO: {', '.join(force_candidates)}")

    # -- Avalia combos --
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
        result = _evaluate_combo(ohlc_df, params, buy_default_sell, dxy_close, vix_close, symbol, horizon)
        result["params"] = params
        buy_results.append(result)
        if result["avg_mae"] < best_buy["avg_mae"] and result["n_trades"] > 0:
            best_buy = result
            best_buy_params = params

    for _, row in sell_grid_df.iterrows():
        params = {k: float(v) for k, v in row.items() if k != "mae" and k in SELL_GRID}
        if not params:
            continue
        result = _evaluate_combo(ohlc_df, sell_default_buy, params, dxy_close, vix_close, symbol, horizon)
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

    final_result = _evaluate_combo(ohlc_df, best_buy_final, best_sell_final, dxy_close, vix_close, symbol, horizon)

    # -- Monta contrato de saida --
    start_ts = str(ohlc_df.index[0]) if n_bars > 0 else None
    end_ts = str(ohlc_df.index[-1]) if n_bars > 0 else None

    result = {
        "symbol": symbol,
        "tf": tf,
        "window": {"train_start": start_ts, "train_end": end_ts},
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
