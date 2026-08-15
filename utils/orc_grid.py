"""PROPOSITO: orc_grid.py — ORQUESTRADOR S43: run_walkforward_grid().
SPEC: S43 (orc_grid.md)
ROADMAP: S43 Grid/Walk-Forward

Orquestrador principal de walk-forward validation:
1. Carrega dados M1 parquet
2. Cria janelas RollingSplitter
3. Para cada janela: grid search no train -> aplicar melhor no test
4. Consolida metricas + analise de estabilidade
"""
from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd

from utils.parameter_grid_orc_grid import build_parameter_grid
from utils.stability_analyzer_orc_grid import analyze_stability
from utils.window_runner_orc_grid import run_single_window

logger = logging.getLogger(__name__)

# -- Constantes --
CTRADER_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(CTRADER_DIR, "data")


def _load_parquet(symbol: str) -> pd.DataFrame | None:
    """Carrega M1 parquet do simbolo.

    Tenta primeiro data/m1_SYMBOL_2026.parquet, depois consolidated/SYMBOL_M1.parquet.
    Normaliza colunas: timestamp -> index, tick_volume -> volume, OHLCV apenas.
    """
    candidates = [
        os.path.join(DATA_DIR, f"m1_{symbol}_2026.parquet"),
        os.path.join(DATA_DIR, "consolidated", f"{symbol}_M1.parquet"),
    ]

    for path in candidates:
        if os.path.exists(path):
            df = pd.read_parquet(path)

            # Normalizar timestamp -> index
            if "timestamp" in df.columns:
                ts_col = df["timestamp"]
                # Pode ser epoch ms ou datetime string
                if ts_col.dtype.kind in ("i", "f"):
                    df["timestamp"] = pd.to_datetime(ts_col, unit="ms", utc=True)
                else:
                    df["timestamp"] = pd.to_datetime(ts_col, utc=True)
                df = df.set_index("timestamp")

            # Normalizar volume: tick_volume -> volume
            if "volume" not in df.columns and "tick_volume" in df.columns:
                df["volume"] = df["tick_volume"].astype(float)

            # Selecionar apenas colunas OHLCV para o pipeline
            ohlcv_cols = ["open", "high", "low", "close", "volume"]
            available = [c for c in ohlcv_cols if c in df.columns]
            df = df[available].copy()

            return df

    logger.error("[ERRO] _load_parquet: nenhum parquet encontrado para %s", symbol)
    return None


def _resample_to_tf(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Resample M1 para M5 ou M15."""
    if tf == "M1":
        return df.copy()

    rule_map = {"M5": "5min", "M15": "15min", "H1": "1h", "D": "1d"}
    rule = rule_map.get(tf, "5min")

    resampled: pd.DataFrame = df.resample(rule).agg({  # type: ignore[assignment]
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum" if "volume" in df.columns else "count",
    }).dropna()

    return resampled


def _create_windows(
    df: pd.DataFrame, window_len: int, test_len: int, n_windows: int
) -> list[tuple[pd.DataFrame, pd.DataFrame, int, int]]:
    """Cria janelas walk-forward via RollingSplitter manual.

    Returns:
        list of (train_df, test_df, train_start_idx, test_start_idx)
    """
    n = len(df)
    windows: list[tuple[pd.DataFrame, pd.DataFrame, int, int]] = []

    # Rolling windows: avanca test_len barras por janela
    test_end = n
    for _w in range(n_windows):
        test_start = test_end - test_len
        train_start = max(0, test_start - window_len)

        if test_start <= 0 or train_start >= test_start:
            break

        train_df = df.iloc[train_start:test_start].copy()
        test_df = df.iloc[test_start:test_end].copy()

        if len(train_df) < 50 or len(test_df) < 5:
            break

        windows.append((train_df, test_df, train_start, test_start))
        test_end = test_start  # avanca para tras (walk-forward no tempo)

    # Reverte para ordem cronologica
    windows.reverse()
    return windows


def run_walkforward_grid(
    symbol: str,
    tf: str = "M5",
    window_len: int = 365,
    test_len: int = 90,
    n_windows: int = 12,
    grid_type: str = "buy",
) -> dict[str, Any]:
    """Executa walk-forward validation com grid search de parametros.

    Args:
        symbol: par forex (XAUUSD, EURUSD, etc.)
        tf: timeframe (M1, M5, M15)
        window_len: barras de treino por janela
        test_len: barras de teste por janela
        n_windows: numero maximo de janelas
        grid_type: tipo de grid ("buy", "sell", "force")

    Returns:
        dict com windows (lista de resultados por janela) e stability (analise)
    """
    result: dict[str, Any] = {
        "windows": [],
        "stability": {},
    }

    # Carregar dados
    df = _load_parquet(symbol)
    if df is None:
        result["error"] = f"dados nao encontrados para {symbol}"
        return result

    # Resample para o timeframe desejado
    df = _resample_to_tf(df, tf)

    # Criar janelas
    windows = _create_windows(df, window_len, test_len, n_windows)
    if not windows:
        result["error"] = "dados insuficientes para criar janelas"
        return result

    # Construir grid de parametros
    param_grid = build_parameter_grid(grid_type)

    # Para cada janela: grid search no train -> aplicar melhor no test
    window_results: list[dict[str, Any]] = []
    for train_df, test_df, train_start, test_start in windows:
        best_train_mae = float("inf")
        best_combo: dict[str, Any] = {}
        best_test_result: dict[str, Any] = {}

        # Grid search no TRAIN
        for params in param_grid:
            single_result = run_single_window(train_df, test_df, params)
            if single_result.get("error"):
                continue
            train_mae = single_result.get("train_mae")
            if train_mae is not None and train_mae < best_train_mae:
                best_train_mae = train_mae
                best_combo = dict(params)
                best_test_result = single_result

        # Resultado da janela com o melhor combo
        window_result: dict[str, Any] = {
            "train": (
                str(df.index[train_start]) if train_start < len(df.index) else "?",
                str(df.index[test_start - 1]) if test_start > 0 else "?",
            ),
            "test": (
                str(df.index[test_start]) if test_start < len(df.index) else "?",
                str(df.index[min(test_start + test_len - 1, len(df.index) - 1)]),
            ),
            "best_params": best_combo,
            "train_mae": best_test_result.get("train_mae"),
            "test_mae": best_test_result.get("test_mae"),
            "test_win_rate": best_test_result.get("test_win_rate"),
        }
        window_results.append(window_result)
        result["windows"].append(window_result)

    # Analisar estabilidade
    result["stability"] = analyze_stability(window_results)

    return result
