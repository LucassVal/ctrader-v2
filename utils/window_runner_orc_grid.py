"""PROPOSITO: window_runner_orc_grid.py — SAT S43.2: run_single_window().
SPEC: S43 (orc_grid.md)
ROADMAP: S43 Grid/Walk-Forward

Executa uma unica janela de walk-forward: treina no train, testa no test.
NUNCA re-otimiza no test — os params sao fixos.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _generate_signals(df: pd.DataFrame, params: dict[str, Any]) -> np.ndarray:
    """Gera sinais booleanos de entrada baseados nos parametros.

    Usa RSI simplificado + MACD-like para gerar sinais de compra.
    Para SELL grid, inverte a logica.

    Returns:
        np.ndarray booleano com entradas (True = entra na barra seguinte)
    """
    close = df["close"].values.astype(np.float64)
    n = len(close)

    if n < 30:
        return np.zeros(n, dtype=bool)

    signals = np.zeros(n, dtype=bool)

    # Determinar se e buy ou sell pelo tipo de parametros
    is_sell = "atr_period" in params

    if "rsi_period" in params:
        # Buy signal: RSI abaixo do threshold
        rsi_period = int(params["rsi_period"])
        rsi_threshold = float(params.get("rsi_threshold", 30))

        if n > rsi_period:
            # RSI simplificado
            delta = np.diff(close, prepend=close[0])
            gain = np.where(delta > 0, delta, 0.0)
            loss = np.where(delta < 0, -delta, 0.0)

            # SMA of gains/losses
            avg_gain = pd.Series(gain).rolling(rsi_period).mean().values
            avg_loss = pd.Series(loss).rolling(rsi_period).mean().values

            with np.errstate(divide="ignore", invalid="ignore"):
                rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100.0)
                rsi_vals = 100.0 - (100.0 / (1.0 + rs))

            rsi_vals[np.isnan(rsi_vals)] = 50.0

            if is_sell:
                # Sell: RSI acima de (100 - threshold)
                signals[rsi_vals > (100 - rsi_threshold)] = True
            else:
                # Buy: RSI abaixo do threshold
                signals[rsi_vals < rsi_threshold] = True

    elif "atr_period" in params:
        # Sell signal baseado em volatilidade
        atr_period = int(params["atr_period"])
        if n > atr_period:
            high = df["high"].values.astype(np.float64)
            low = df["low"].values.astype(np.float64)

            # ATR simplificado
            tr = np.maximum(
                high - low,
                np.maximum(
                    np.abs(high - np.roll(close, 1)),
                    np.abs(low - np.roll(close, 1)),
                ),
            )
            tr[0] = high[0] - low[0]
            atr = pd.Series(tr).rolling(atr_period).mean().values
            atr[np.isnan(atr)] = 0.0

            # Volatility spike = sell signal
            atr_median = np.median(atr[atr > 0]) if np.any(atr > 0) else 1.0
            if atr_median > 0:
                signals[atr > atr_median * 1.5] = True

    return signals


def _compute_mae(
    df: pd.DataFrame, entries: np.ndarray, horizon: int = 5
) -> float | None:
    """Calcula MAE (Maximum Adverse Excursion) medio para sinais de entrada.

    Entrada: Open da barra seguinte ao sinal (shift(1) para evitar look-ahead).
    Saida: Close[t + horizon].
    MAE: (entry_price - low.min()) / entry_price para long.

    Returns:
        float: MAE medio em percentual, ou None se sem sinais
    """
    n = len(df)
    if n < horizon + 2 or not np.any(entries):
        return None

    open_prices = df["open"].values.astype(np.float64)
    low_prices = df["low"].values.astype(np.float64)

    entry_indices = np.where(entries)[0]

    mae_values: list[float] = []
    for idx in entry_indices:
        entry_idx = idx + 1  # entra na barra seguinte (shift(1))
        exit_idx = entry_idx + horizon

        if exit_idx >= n:
            continue

        entry_price = open_prices[entry_idx]
        low_slice = low_prices[entry_idx : exit_idx + 1]

        if entry_price <= 0 or low_slice.size == 0:
            continue

        # MAE = quanto o preco andou CONTRA a entrada
        min_low = low_slice.min()
        mae = (entry_price - min_low) / entry_price
        mae_values.append(float(mae))

    if not mae_values:
        return None

    return float(np.mean(mae_values))


def run_single_window(
    train_df: pd.DataFrame,
    test_df: pd.DataFrame,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Executa uma unica janela de walk-forward com parametros fixos.

    Treina no train_df (calcula MAE), testa no test_df (calcula MAE out-of-sample).
    NUNCA re-otimiza os parametros no test.

    Args:
        train_df: OHLCV DataFrame de treino
        test_df: OHLCV DataFrame de teste
        params: dicionario de parametros (do grid)

    Returns:
        dict com train_mae, test_mae, test_win_rate, params, error (se falhou)
    """
    result: dict[str, Any] = {
        "params": dict(params),
        "train_mae": None,
        "test_mae": None,
        "test_win_rate": None,
    }

    # Validar dados
    if train_df.empty and test_df.empty:
        result["error"] = "dados vazios"
        return result

    if train_df.empty:
        result["error"] = "train_df vazio"
        return result

    # Gerar sinais no train
    train_signals = _generate_signals(train_df, params)
    train_mae = _compute_mae(train_df, train_signals, horizon=5)
    result["train_mae"] = train_mae

    # Testar no test (NUNCA re-otimizar)
    if not test_df.empty:
        test_signals = _generate_signals(test_df, params)
        test_mae = _compute_mae(test_df, test_signals, horizon=5)
        result["test_mae"] = test_mae

        # Win rate: % de trades com PnL positivo
        if test_signals.any():
            close = test_df["close"].values.astype(np.float64)
            n = len(close)
            entry_indices = np.where(test_signals)[0]
            wins = 0
            total = 0
            for idx in entry_indices:
                entry_idx = idx + 1
                exit_idx = entry_idx + 5
                if exit_idx >= n:
                    continue
                if close[exit_idx] > close[entry_idx]:
                    wins += 1
                total += 1
            if total > 0:
                result["test_win_rate"] = round(wins / total, 4)

    return result
