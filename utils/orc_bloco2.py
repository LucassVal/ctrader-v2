"""orc_bloco2.py — S42: Orquestrador do Bloco 2 (Sobrevivencia).

PROPOSITO: Wirear todos os SATs de gestao de ordens e comparar camadas.
SPEC: S42
R-USE: vectorbt.Portfolio.from_signals() com stops nativos.

Fluxo:
  baseline (sem stops) -> TP80 (partial exit 80%) -> BE (breakeven) -> Trail -> OCO ATR

Regras:
  - NUNCA recalcular indicadores — sinais vem prontos do Bloco 1
  - NUNCA alterar a matriz de sinais — apenas simular execucao
  - Ordem de aplicacao: baseline -> TP80 -> BE -> Trail -> OCO (sequencial)
ROADMAP: FASE 3 (S42)
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def run_bloco2(
    signals_validated: pd.DataFrame,
    ohlcv: pd.DataFrame,
    tf: str = "M5",
) -> dict[str, Any]:
    """Executa o Bloco 2: simula 5 camadas de gestao de ordens.

    Args:
        signals_validated: DataFrame com colunas 'entries' e 'exits' (booleanas).
                           Vem do Bloco 1 (S41).
        ohlcv: DataFrame com colunas 'open', 'high', 'low', 'close', 'volume'.
               Index deve ser datetime.
        tf: Timeframe ('M5' ou 'M15').

    Returns:
        {
            "comparison": pd.DataFrame,       # Camada x metricas
            "best_layer": str,               # Nome da melhor camada por Sharpe
            "equity_curves": dict,           # {camada: [equity values]}
            "trades_per_layer": dict,        # {camada: [trade dicts]}
        }
    """
    import vectorbt as vbt

    from utils.breakeven_orc_bloco2 import build_be_callback
    from utils.layer_comparator_orc_bloco2 import compare_layers
    from utils.montecarlo_orc_bloco2 import monte_carlo_shuffle
    from utils.oco_atr_orc_bloco2 import calc_sl_tp_pcts
    from utils.partial_exit_orc_bloco2 import build_tp_callback

    # -- Validate inputs ----------------------------------------
    _validate_inputs(signals_validated, ohlcv)

    # Extrair arrays
    close = _get_close_array(ohlcv)
    entries = _get_bool_array(signals_validated, "entries")
    exits = _get_bool_array(signals_validated, "exits")

    # Configuracao padrao
    init_cash = 10_000.0
    slippage = 0.001
    fees = 0.0001
    freq = _freq_map(tf)

    # Calcular ATR para OCO
    atr_value = _compute_atr(ohlcv)

    results: dict[str, Any] = {}
    equity_curves: dict[str, list[dict[str, Any]]] = {}
    trades_per_layer: dict[str, list[dict[str, Any]]] = {}

    # -- Camada 0: BASELINE (sem stops) -------------------------
    pf_base = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=np.inf,
        size_type="percent",
        init_cash=init_cash,
        slippage=slippage,
        fees=fees,
        freq=freq,
        use_stops=False,
    )
    results["baseline"] = _extract_metrics(pf_base)
    equity_curves["baseline"] = _extract_equity(pf_base, ohlcv)
    trades_per_layer["baseline"] = _extract_trades(pf_base)

    # -- Camada 1: TP80 (partial exit 80%) ----------------------
    tp_callback = build_tp_callback(tp1_pct=0.8, tp1_target=0.02)
    pf_tp80 = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=np.inf,
        size_type="percent",
        init_cash=init_cash,
        slippage=slippage,
        fees=fees,
        freq=freq,
        tp_stop=0.02,               # TP fixo 2%
        adjust_tp_func_nb=tp_callback,
        allow_partial=True,         # Habilita saida parcial
        use_stops=True,
    )
    results["tp_80"] = _extract_metrics(pf_tp80)
    equity_curves["tp_80"] = _extract_equity(pf_tp80, ohlcv)
    trades_per_layer["tp_80"] = _extract_trades(pf_tp80)

    # -- Camada 2: BREAKEVEN ------------------------------------
    be_callback = build_be_callback(trigger_pct=0.006, spread_pips=1.0)
    pf_be = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=np.inf,
        size_type="percent",
        init_cash=init_cash,
        slippage=slippage,
        fees=fees,
        freq=freq,
        sl_stop=0.01,               # SL inicial 1%
        adjust_sl_func_nb=be_callback,
        use_stops=True,
    )
    results["be"] = _extract_metrics(pf_be)
    equity_curves["be"] = _extract_equity(pf_be, ohlcv)
    trades_per_layer["be"] = _extract_trades(pf_be)

    # -- Camada 3: TRAILING STOP --------------------------------
    pf_trail = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=np.inf,
        size_type="percent",
        init_cash=init_cash,
        slippage=slippage,
        fees=fees,
        freq=freq,
        sl_stop=0.01,
        sl_trail=True,
        use_stops=True,
    )
    results["trail"] = _extract_metrics(pf_trail)
    equity_curves["trail"] = _extract_equity(pf_trail, ohlcv)
    trades_per_layer["trail"] = _extract_trades(pf_trail)

    # -- Camada 4: OCO ADAPTATIVO ATR ---------------------------
    if atr_value > 0 and close[entries].size > 0:
        entry_price = float(np.mean(close[entries])) if np.any(entries) else float(close[0])
        sl_pct, tp_pct = calc_sl_tp_pcts(atr_value, entry_price, multiplier=1.5)
        # Clamp para evitar stops absurdos
        sl_pct = min(max(sl_pct, 0.002), 0.10)
        tp_pct = min(max(tp_pct, 0.004), 0.20)
    else:
        sl_pct = 0.01
        tp_pct = 0.02

    pf_oco = vbt.Portfolio.from_signals(
        close=close,
        entries=entries,
        exits=exits,
        size=np.inf,
        size_type="percent",
        init_cash=init_cash,
        slippage=slippage,
        fees=fees,
        freq=freq,
        sl_stop=sl_pct,
        tp_stop=tp_pct,
        use_stops=True,
    )
    results["oco_atr"] = _extract_metrics(pf_oco)
    equity_curves["oco_atr"] = _extract_equity(pf_oco, ohlcv)
    trades_per_layer["oco_atr"] = _extract_trades(pf_oco)

    # -- Comparar camadas ---------------------------------------
    comparison = compare_layers(results)

    # Melhor camada por Sharpe
    best_layer = "baseline"
    if not comparison.empty:
        best_layer = str(comparison.iloc[0]["Camada"])

    # Monte Carlo shuffle na melhor camada (S42 §Pre-requisito: Sharpe nao eh sorte)
    best_trades = trades_per_layer.get(best_layer, [])
    mc_trades = [
        {"pnl_pct": float(t.get("Return", t.get("PnL", 0.0)) or 0.0)}
        for t in best_trades
    ]
    monte_carlo = monte_carlo_shuffle(mc_trades, n_simulations=200, seed=42)

    return {
        "comparison": comparison,
        "best_layer": best_layer,
        "equity_curves": equity_curves,
        "trades_per_layer": trades_per_layer,
        "monte_carlo": monte_carlo,
    }


# -- Helpers ------------------------------------------------------


def _validate_inputs(signals: pd.DataFrame, ohlcv: pd.DataFrame) -> None:
    """Valida se os inputs tem o formato esperado."""
    required_signal_cols = {"entries", "exits"}
    required_ohlcv_cols = {"open", "high", "low", "close"}

    if not required_signal_cols.issubset(signals.columns):
        missing = required_signal_cols - set(signals.columns)
        raise ValueError(f"signals_validated missing columns: {missing}")

    if not required_ohlcv_cols.issubset(ohlcv.columns):
        missing = required_ohlcv_cols - set(ohlcv.columns)
        raise ValueError(f"ohlcv missing columns: {missing}")

    if len(signals) == 0:
        raise ValueError("signals_validated is empty")

    if len(ohlcv) == 0:
        raise ValueError("ohlcv is empty")


def _get_close_array(ohlcv: pd.DataFrame) -> np.ndarray:
    """Extrai close como float64 array."""
    return ohlcv["close"].values.astype(np.float64)


def _get_bool_array(df: pd.DataFrame, col: str) -> np.ndarray:
    """Extrai coluna como bool array."""
    return df[col].values.astype(bool)


def _freq_map(tf: str) -> str:
    """Mapeia timeframe para frequencia vectorbt."""
    mapping = {
        "M1": "1min",
        "M5": "5min",
        "M15": "15min",
        "H1": "1h",
        "D": "1d",
    }
    return mapping.get(tf, "5min")


def _compute_atr(ohlcv: pd.DataFrame, period: int = 14) -> float:
    """Calcula ATR simples usando numpy (sem vectorbt overhead)."""
    high = ohlcv["high"].values.astype(np.float64)
    low = ohlcv["low"].values.astype(np.float64)
    close = ohlcv["close"].values.astype(np.float64)

    prev_close = np.roll(close, 1)
    prev_close[0] = close[0]

    tr1 = high - low
    tr2 = np.abs(high - prev_close)
    tr3 = np.abs(low - prev_close)
    true_range = np.maximum(np.maximum(tr1, tr2), tr3)

    # Média móvel simples do true_range
    atr_array = np.full_like(true_range, np.nan)
    for i in range(period - 1, len(true_range)):
        atr_array[i] = np.mean(true_range[i - period + 1 : i + 1])

    # Último valor de ATR válido
    valid = atr_array[~np.isnan(atr_array)]
    if len(valid) == 0:
        return 0.0
    return float(valid[-1])


def _extract_metrics(pf: Any) -> dict[str, float]:
    """Extrai metricas de um Portfolio vectorbt."""
    try:
        stats = pf.stats()
        return {
            "sharpe": round(float(stats.get("Sharpe Ratio", 0.0)), 2),
            "max_dd": round(float(stats.get("Max Drawdown [%]", 0.0)), 2),
            "win_rate": round(float(stats.get("Win Rate [%]", 0.0)), 2),
            "profit_factor": round(float(stats.get("Profit Factor", 0.0)), 2),
            "expectancy": round(float(stats.get("Expectancy", 0.0)), 2),
            "total_return": round(float(stats.get("Total Return [%]", 0.0)), 2),
        }
    except Exception:
        return {
            "sharpe": 0.0,
            "max_dd": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "expectancy": 0.0,
            "total_return": 0.0,
        }


def _extract_equity(pf: Any, ohlcv: pd.DataFrame) -> list[dict[str, Any]]:
    """Extrai equity curve de um Portfolio."""
    try:
        equity = pf.value()
        if isinstance(equity, pd.Series):
            return [
                {"index": int(i), "equity": round(float(v), 2)}
                for i, v in enumerate(equity.values)
            ]
        return []
    except Exception:
        return []


def _extract_trades(pf: Any) -> list[dict[str, Any]]:
    """Extrai trades de um Portfolio."""
    try:
        trades = pf.trades.records_readable
        if isinstance(trades, pd.DataFrame) and not trades.empty:
            return trades.head(50).to_dict(orient="records")  # type: ignore[no-any-return]
        return []
    except Exception:
        return []
