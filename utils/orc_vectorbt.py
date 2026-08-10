"""PROPOSITO: Vector BT wrapper — indicadores tecnicos + backtesting (S25 Fase 2).
SPEC: S25 / S39 (MTF resample)
ROADMAP: VBT-1, VBT-2, C4
Motor unico de indicadores: substitui pandas-ta e calculos manuais do F1.
Usa vectorbt (ja instalado) para:
  - Indicadores: RSI, MACD, ATR, BBANDS, ADX, OBV, STOCH
  - Backtesting: Portfolio.from_signals()
  - compute_indicators_mtf: resample M1->M5/M15 + indicadores por timeframe
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

# Split DDD (G12): helpers numpy puros vivem no satelite indicators_orc_vectorbt.
from utils.indicators_orc_vectorbt import (
    _aroon,
    _breakout_pct,
    _cci,
    _compute_adx,
    _donchian,
    _hma,
    _keltner,
    _psar,
    _williams_r,
    _zlema,
)


def compute_indicators(
    ohlcv: dict[str, list[dict[str, float]]],
    periods: tuple[int, ...] = (14, 20, 50),
    timeframe: str | None = None,
) -> dict[str, dict[str, Any]]:
    """Calcula TODOS os indicadores para cada simbolo usando vectorbt.

    Args:
        ohlcv: {symbol: [{open, high, low, close, volume, timestamp}, ...]}
        periods: periodos para medias moveis (default 14, 20, 50)
        timeframe: opcional — rotulo do timeframe (M1, M5, M15, etc.)

    Returns:
        {symbol: {rsi, macd, atr, bb_upper, bb_lower, adx, sma_fast, sma_slow, ...}}
    """
    from vectorbt import ATR, BBANDS, MACD, OBV, RSI, STOCH

    results: dict[str, dict[str, Any]] = {}

    for sym, bars in ohlcv.items():
        if len(bars) < max(periods):
            results[sym] = {"error": f"so {len(bars)} barras, precisa >= {max(periods)}"}
            continue

        df = pd.DataFrame(bars)
        close = df["close"].values.astype(np.float64)
        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        vol = df.get("volume", pd.Series([0] * len(close))).values.astype(np.float64)

        try:
            # RSI
            rsi = RSI.run(close, window=14)
            rsi_val = float(rsi.rsi.iloc[-1]) if len(rsi.rsi) > 0 else None

            # MACD
            macd = MACD.run(close)
            macd_val = float(macd.macd.iloc[-1]) if len(macd.macd) > 0 else None
            macd_signal = float(macd.signal.iloc[-1]) if len(macd.signal) > 0 else None
            macd_hist = float(macd.hist.iloc[-1]) if len(macd.hist) > 0 else None

            # Bollinger Bands
            bb = BBANDS.run(close, window=20)
            bb_upper = float(bb.upper.iloc[-1]) if len(bb.upper) > 0 else None
            bb_middle = float(bb.middle.iloc[-1]) if len(bb.middle) > 0 else None
            bb_lower = float(bb.lower.iloc[-1]) if len(bb.lower) > 0 else None
            bb_width = round((bb_upper - bb_lower) / bb_middle * 100, 2) if bb_middle else None

            # ATR
            atr = ATR.run(high, low, close, window=14)
            atr_val = float(atr.atr.iloc[-1]) if len(atr.atr) > 0 else None

            # ADX (via SMA do directional movement)
            adx_val = _compute_adx(high, low, close, window=14)

            # OBV
            obv = OBV.run(close, vol)
            obv_val = float(obv.obv.iloc[-1]) if len(obv.obv) > 0 else None

            # Stochastic (vbt 1.1.0: percent_k/percent_d)
            stoch = STOCH.run(high, low, close)
            stoch_k = float(stoch.percent_k.iloc[-1]) if len(stoch.percent_k) > 0 else None
            stoch_d = float(stoch.percent_d.iloc[-1]) if len(stoch.percent_d) > 0 else None

            # SMA multiples
            sma_fast = float(pd.Series(close).rolling(periods[0]).mean().iloc[-1])
            sma_slow = float(pd.Series(close).rolling(periods[2]).mean().iloc[-1])

            # -- S28: Indicadores avancados (numpy puro, zero dependencias) --
            # Donchian (breakout)
            dc_high, dc_low, dc_mid = _donchian(high, low, window=20)
            breakout_pct = _breakout_pct(close[-1], dc_high, dc_low)

            # HMA (Hull Moving Average — lag reduzido)
            hma_val = _hma(close, period=14)

            # Keltner (squeeze de volatilidade)
            kc_upper, kc_lower, kc_squeeze = _keltner(close, high, low, window=20)

            # CCI
            cci_val = _cci(high, low, close, window=20)

            # PSAR (stop & reverse)
            psar_val = _psar(high, low, close)

            # Williams %R
            wpr_val = _williams_r(high, low, close, window=14)

            # Aroon
            aroon_up, aroon_down = _aroon(high, low, window=14)

            # ZLEMA (Zero-Lag EMA)
            zlema_val = _zlema(close, period=20)

            results[sym] = {
                # Originais
                "rsi": round(rsi_val, 1) if rsi_val is not None else None,
                "macd": round(macd_val, 5) if macd_val is not None else None,
                "macd_signal": round(macd_signal, 5) if macd_signal is not None else None,
                "macd_hist": round(macd_hist, 5) if macd_hist is not None else None,
                "bb_upper": bb_upper,
                "bb_middle": bb_middle,
                "bb_lower": bb_lower,
                "bb_width_pct": bb_width,
                "atr": round(atr_val, 5) if atr_val is not None else None,
                "adx": round(adx_val, 1) if adx_val is not None else None,
                "obv": obv_val,
                "stoch_k": round(stoch_k, 1) if stoch_k is not None else None,
                "stoch_d": round(stoch_d, 1) if stoch_d is not None else None,
                "sma_fast": round(sma_fast, 5) if sma_fast else None,
                "sma_slow": round(sma_slow, 5) if sma_slow else None,
                # S28 — Avancados
                "dc_high": dc_high,
                "dc_low": dc_low,
                "dc_mid": dc_mid,
                "breakout_pct": breakout_pct,
                "hma": hma_val,
                "kc_upper": kc_upper,
                "kc_lower": kc_lower,
                "kc_squeeze": round(kc_squeeze, 2),
                "cci": round(cci_val, 1) if cci_val is not None else None,
                "psar": round(psar_val, 5) if psar_val is not None else None,
                "wpr": round(wpr_val, 1) if wpr_val is not None else None,
                "aroon_up": round(aroon_up, 1) if aroon_up is not None else None,
                "aroon_down": round(aroon_down, 1) if aroon_down is not None else None,
                "zlema": round(zlema_val, 5) if zlema_val is not None else None,
                "bars": len(bars),
                "last_close": close[-1] if len(close) > 0 else None,
            }

        except Exception as e:
            results[sym] = {"error": str(e)[:100]}

    return results


def compute_indicators_mtf(
    df_m1: pd.DataFrame,
    periods: tuple[int, ...] = (14, 20, 50),
    timeframes: tuple[str, ...] = ("M5", "M15"),
) -> dict[str, dict[str, Any]]:
    """Calcula indicadores para M1, M5 e M15 usando resample do parquet M1.

    S39/C4: substitui get_trendbars MCP — MTF calculado localmente.

    Args:
        df_m1: DataFrame M1 com colunas [timestamp, open, high, low, close,
               tick_volume] (schema do parquet F0)
        periods: periodos para medias moveis
        timeframes: timeframes alvo alem de M1

    Returns:
        {"M1": {indicadores...}, "M5": {...}, "M15": {...}}
        Cada timeframe tem o mesmo schema de compute_indicators().
    """
    from utils.resample import resample_m1_to_mtf

    results: dict[str, dict[str, Any]] = {}

    # -- M1: computa direto (ja e M1) --
    m1_bars = df_m1.to_dict(orient="records")
    # Normaliza volume column name
    vol_col = "tick_volume" if "tick_volume" in df_m1.columns else "volume"
    for bar in m1_bars:
        if vol_col in bar and "volume" not in bar:
            bar["volume"] = bar.get(vol_col, 0)
    m1_indicators = compute_indicators({"M1": m1_bars}, periods=periods, timeframe="M1")
    if "M1" in m1_indicators:
        results["M1"] = m1_indicators["M1"]

    # -- M5/M15: resample + compute --
    try:
        mtf_dfs = resample_m1_to_mtf(df_m1, timeframes=timeframes)
    except ValueError as e:
        for tf in timeframes:
            results[tf] = {"error": f"resample falhou: {e}"}
        return results

    for tf in timeframes:
        if tf not in mtf_dfs or mtf_dfs[tf].empty:
            results[tf] = {"error": f"resample {tf} vazio — dados M1 insuficientes"}
            continue
        df_tf = mtf_dfs[tf].reset_index().rename(columns={"_dt": "timestamp"})
        # Converte timestamp datetime -> ms epoch (compativel com compute_indicators)
        if "timestamp" in df_tf.columns:
            df_tf["timestamp"] = df_tf["timestamp"].astype("int64") // 1_000_000
        bars_tf = df_tf.to_dict(orient="records")
        tf_indicators = compute_indicators({"TF": bars_tf}, periods=periods, timeframe=tf)
        if "TF" in tf_indicators:
            results[tf] = tf_indicators["TF"]

    return results


def compute_portfolio_stats(
    trades: list[dict[str, Any]],
    initial_capital: float = 10_000.0,
) -> dict[str, Any]:
    """Calcula metricas de performance a partir de trades.
    Usa vectorbt apenas se houver trades suficientes (>5).
    Fallback: pandas puro para metricas basicas.

    Args:
        trades: lista de trades [{pnl, volume, symbol, side, open_time, close_time}, ...]
        initial_capital: capital inicial em USD (default 10k)
    """
    if len(trades) < 1:
        return {
            "status": "sem_dados",
            "total_trades": 0,
            "note": "Execute trades para ver metricas de performance.",
        }

    total = len(trades)
    winning = [t for t in trades if t.get("pnl", 0) > 0]
    losing = [t for t in trades if t.get("pnl", 0) < 0]
    total_pnl = sum(t.get("pnl", 0) for t in trades)
    win_rate = len(winning) / total * 100 if total else 0

    gross_profit = sum(t.get("pnl", 0) for t in winning)
    gross_loss = abs(sum(t.get("pnl", 0) for t in losing))
    profit_factor = gross_profit / max(gross_loss, 0.01)

    # Drawdown: equity curve a partir dos PnLs acumulados
    equity = initial_capital
    peak = initial_capital
    max_dd = 0.0
    for t in trades:
        equity += t.get("pnl", 0)
        peak = max(peak, equity)
        dd = (peak - equity) / peak * 100 if peak else 0
        max_dd = max(max_dd, dd)

    # Sharpe (aproximado — precisa de returns diarios)
    import math
    returns = [t.get("pnl", 0) / initial_capital for t in trades]
    avg_ret = sum(returns) / len(returns) if returns else 0
    variance = sum((r - avg_ret) ** 2 for r in returns) / len(returns) if returns else 0
    std_ret = math.sqrt(variance) if variance > 0 else 0.0001
    sharpe = (avg_ret / std_ret) * math.sqrt(252) if std_ret else 0

    # Avg trade duration
    durations = []
    for t in trades:
        ot = t.get("open_time")
        ct = t.get("close_time")
        if ot and ct:
            try:
                from datetime import datetime
                d = (datetime.fromisoformat(str(ct)) - datetime.fromisoformat(str(ot))).total_seconds()
                durations.append(d)
            except Exception:
                pass
    avg_duration = sum(durations) / len(durations) if durations else 0

    # Por simbolo
    by_symbol: dict[str, dict[str, Any]] = {}
    for t in trades:
        sym = t.get("symbol", "?")
        if sym not in by_symbol:
            by_symbol[sym] = {"trades": 0, "pnl": 0.0, "wins": 0}
        by_symbol[sym]["trades"] += 1
        by_symbol[sym]["pnl"] += t.get("pnl", 0)
        if t.get("pnl", 0) > 0:
            by_symbol[sym]["wins"] += 1

    # Vector BT (se >5 trades)
    vectorbt_stats: dict[str, Any] = {}
    if total >= 5:
        try:
            import pandas as pd
            import vectorbt as vbt

            df = pd.DataFrame(trades)
            if "pnl" in df.columns and "close_time" in df.columns:
                df["timestamp"] = pd.to_datetime(df["close_time"], errors="coerce")
                df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
                if len(df) >= 5:
                    # Criar serie de retornos
                    returns_series = df.set_index("timestamp")["pnl"] / initial_capital
                    # Portfolio stats via vectorbt
                    pf = vbt.Portfolio.from_orders(
                        close=returns_series.cumsum() + initial_capital,
                        size=pd.Series(1, index=returns_series.index),
                        price=returns_series.cumsum() + initial_capital,
                        init_cash=initial_capital,
                    )
                    vectorbt_stats = {
                        "sharpe_ratio": round(float(pf.sharpe_ratio()), 3) if pf.sharpe_ratio() is not None else None,
                        "max_drawdown": round(float(pf.max_drawdown() * 100), 2),
                        "calmar_ratio": round(float(pf.calmar_ratio()), 3) if pf.calmar_ratio() is not None else None,
                        "total_return": round(float(pf.total_return() * 100), 2),
                    }
        except Exception:
            vectorbt_stats = {}

    return {
        "status": "ativo",
        "total_trades": total,
        "winning": len(winning),
        "losing": len(losing),
        "win_rate": round(win_rate, 1),
        "profit_factor": round(profit_factor, 2),
        "total_pnl": round(total_pnl, 2),
        "avg_pnl": round(total_pnl / total, 2) if total else 0,
        "max_drawdown_pct": round(max_dd, 2),
        "sharpe_ratio": round(sharpe, 3),
        "avg_trade_duration_s": round(avg_duration, 1),
        "by_symbol": by_symbol,
        "vectorbt": vectorbt_stats,
        "capital": initial_capital,
        "equity": round(equity, 2),
        "filters_disponiveis": ["7d", "30d", "60d", "90d", "all"],
    }
