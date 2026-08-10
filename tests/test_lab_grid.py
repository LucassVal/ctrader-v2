"""PROPOSITO: test_lab_grid.py — Harness S43 (parameter_grid, window_runner, stability_analyzer, lab_orc_grid).
SPEC: S43 (orc_grid.md)
G19: tmp_path para dados temporarios.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# -- SAT 1: parameter_grid ----------------------------------------------

def test_build_parameter_grid_returns_list_of_dicts():
    """build_parameter_grid retorna list[dict] com keys de parametros."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("buy")
    assert isinstance(result, list)
    assert len(result) > 0
    assert all(isinstance(combo, dict) for combo in result)


def test_build_parameter_grid_buy_has_correct_keys():
    """BUY_GRID contem rsi_period, rsi_threshold, macd_fast, adx_period, adx_threshold (v2.1)."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("buy")
    for combo in result:
        assert "rsi_period" in combo
        assert "rsi_threshold" in combo
        assert "macd_fast" in combo
        assert "adx_period" in combo
        assert "adx_threshold" in combo


def test_build_parameter_grid_sell_has_correct_keys():
    """SELL_GRID contem rsi_period, rsi_threshold, adx_period, adx_threshold (v2.1 RSI overbought)."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("sell")
    for combo in result:
        assert "rsi_period" in combo
        assert "rsi_threshold" in combo
        assert "adx_period" in combo
        assert "adx_threshold" in combo


def test_build_parameter_grid_force_has_correct_keys():
    """FORCE_GRID contem tick_vol_percentile, roc_period, roc_threshold."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("force")
    for combo in result:
        assert "tick_vol_percentile" in combo
        assert "roc_period" in combo
        assert "roc_threshold" in combo


def test_build_parameter_grid_buy_max_200():
    """BUY_GRID: 1080 combos reduzidos para no maximo 200 (Pareto 80/20)."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("buy")
    assert len(result) <= 200
    # Deve ter pelo menos alguns combos
    assert len(result) >= 10


def test_build_parameter_grid_sell_exact_count():
    """SELL_GRID: 4x2x2x2x2 = 64 combos exatos."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("sell")
    assert len(result) == 36  # 3x3x2x2 = 36 (v2.1)


def test_build_parameter_grid_force_exact_count():
    """FORCE_GRID: 3x3x4 = 36 combos exatos."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("force")
    assert len(result) == 36


def test_build_parameter_grid_cartesian_product():
    """Combos sao produto cartesiano (via itertools.product)."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("force")
    # Verificar que todos os combos sao unicos
    unique = {tuple(sorted(c.items())) for c in result}
    assert len(unique) == len(result)


def test_build_parameter_grid_invalid_type_raises():
    """Tipo invalido lanca ValueError."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    with pytest.raises(ValueError, match="invalido"):
        build_parameter_grid("invalid")


def test_build_parameter_grid_all_grids():
    """Testa 'all' combina todos os grids (buy + sell + force)."""
    from utils.parameter_grid_orc_bloco1 import build_parameter_grid

    result = build_parameter_grid("all")
    assert len(result) > 0
    # Deve ter keys de todos os grids
    all_keys = set()
    for combo in result:
        all_keys.update(combo.keys())
    assert "rsi_period" in all_keys or "atr_period" in all_keys
    assert "tick_vol_percentile" in all_keys or "roc_period" in all_keys


# -- SAT 2: window_runner -----------------------------------------------

def _make_synthetic_ohlcv(n_bars: int = 200, seed: int = 42) -> pd.DataFrame:
    """Cria OHLCV sintetico com tendencia conhecida."""
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n_bars))
    high = close + np.abs(rng.normal(0, 0.5, n_bars))
    low = close - np.abs(rng.normal(0, 0.5, n_bars))
    open_ = close - rng.normal(0, 0.2, n_bars)
    volume = rng.integers(100, 1000, n_bars).astype(float)
    dates = pd.date_range("2024-01-01", periods=n_bars, freq="5min")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume, "timestamp": dates,
    }).set_index("timestamp")


def test_run_single_window_returns_dict():
    """run_single_window retorna dict com train_mae, test_mae, etc."""
    from utils.window_runner_orc_grid import run_single_window

    train = _make_synthetic_ohlcv(100, seed=1)
    test = _make_synthetic_ohlcv(50, seed=2)
    params = {"rsi_period": 14, "macd_fast": 12, "adx_period": 20}

    result = run_single_window(train, test, params)
    assert isinstance(result, dict)
    assert "train_mae" in result
    assert "test_mae" in result
    assert "test_sharpe" in result or "test_win_rate" in result
    assert "params" in result


def test_run_single_window_test_independent():
    """run_single_window NAO re-otimiza no test — os params sao fixos."""
    from utils.window_runner_orc_grid import run_single_window

    train = _make_synthetic_ohlcv(100, seed=1)
    test = _make_synthetic_ohlcv(50, seed=2)
    params = {"rsi_period": 14, "macd_fast": 12, "adx_period": 20}

    result = run_single_window(train, test, params)
    # O params na saida deve ser IGUAL ao params de entrada
    assert result["params"] == params


def test_run_single_window_mae_is_float():
    """train_mae e test_mae sao floats nao-negativos."""
    from utils.window_runner_orc_grid import run_single_window

    train = _make_synthetic_ohlcv(100, seed=5)
    test = _make_synthetic_ohlcv(50, seed=6)
    # Usar threshold mais alto para gerar sinais com dados sinteticos
    params = {"rsi_period": 5, "rsi_threshold": 99, "adx_period": 20}

    result = run_single_window(train, test, params)
    assert isinstance(result["train_mae"], (float, type(None)))
    # test_mae pode ser None se nao houver sinais — ambos aceitaveis
    assert isinstance(result["test_mae"], (float, type(None)))
    if result["train_mae"] is not None:
        assert result["train_mae"] >= 0
    if result["test_mae"] is not None:
        assert result["test_mae"] >= 0


def test_run_single_window_empty_data():
    """Dados vazios retornam dict com erro."""
    from utils.window_runner_orc_grid import run_single_window

    empty = pd.DataFrame()
    params = {"rsi_period": 14}
    result = run_single_window(empty, empty, params)
    assert "error" in result or result.get("train_mae") is None


# -- SAT 3: stability_analyzer ------------------------------------------

def _make_window_results(n_windows: int = 12,
                         rsi_values: list | None = None) -> list[dict]:
    """Cria resultados sinteticos de janelas para teste."""
    if rsi_values is None:
        rsi_values = [14] * 10 + [21, 21]  # mode = 14 (83% stability)
    results = []
    for i in range(n_windows):
        results.append({
            "best_params": {
                "rsi_period": rsi_values[i % len(rsi_values)],
                "macd_fast": 12,
                "adx_period": 20,
            },
            "train_mae": 0.10 + (i * 0.01),
            "test_mae": 0.15 + (i * 0.02),
            "test_sharpe": 0.45,
        })
    return results


def test_analyze_stability_returns_dict():
    """analyze_stability retorna dict com parametro_mode, parametro_stability, overfit_flag."""
    from utils.stability_analyzer_orc_grid import analyze_stability

    windows = _make_window_results()
    result = analyze_stability(windows)
    assert isinstance(result, dict)
    assert "rsi_period_mode" in result
    assert "rsi_period_stability" in result
    assert "overfit_flag" in result


def test_analyze_stability_mode_correct():
    """Moda do rsi_period = valor mais frequente entre janelas."""
    from utils.stability_analyzer_orc_grid import analyze_stability

    # 10 janelas com rsi=14, 2 com rsi=21
    windows = _make_window_results(12, [14] * 10 + [21, 21])
    result = analyze_stability(windows)
    assert result["rsi_period_mode"] == 14


def test_analyze_stability_stability_pct():
    """rsi_period_stability = % de janelas com o valor modal."""
    from utils.stability_analyzer_orc_grid import analyze_stability

    windows = _make_window_results(12, [14] * 10 + [21, 21])
    result = analyze_stability(windows)
    assert result["rsi_period_stability"] == pytest.approx(10 / 12, rel=1e-2)


def test_analyze_stability_overfit_true():
    """Flag overfitting: train_mae < test_mae * 0.5 por >50% das janelas."""
    from utils.stability_analyzer_orc_grid import analyze_stability

    windows = []
    for _i in range(12):
        windows.append({
            "best_params": {"rsi_period": 14},
            "train_mae": 0.05,  # muito menor que test_mae
            "test_mae": 0.20,   # 0.05 < 0.20 * 0.5 = 0.10 -> overfit
        })
    result = analyze_stability(windows)
    assert result["overfit_flag"] is True


def test_analyze_stability_overfit_false():
    """Sem overfitting quando train_mae NAO e consistentemente muito menor."""
    from utils.stability_analyzer_orc_grid import analyze_stability

    windows = []
    for _i in range(12):
        windows.append({
            "best_params": {"rsi_period": 14},
            "train_mae": 0.12,
            "test_mae": 0.15,  # 0.12 > 0.15 * 0.5 -> no overfit
        })
    result = analyze_stability(windows)
    assert result["overfit_flag"] is False


def test_analyze_stability_mode_all_params():
    """Moda calculada para TODOS os parametros, nao so rsi."""
    from utils.stability_analyzer_orc_grid import analyze_stability

    windows = []
    for i in range(8):
        windows.append({
            "best_params": {
                "rsi_period": 14 if i < 6 else 21,
                "macd_fast": 12 if i < 5 else 16,
                "adx_period": 20,
            },
            "train_mae": 0.10,
            "test_mae": 0.12,
        })
    result = analyze_stability(windows)
    assert result["rsi_period_mode"] == 14
    assert result["macd_fast_mode"] == 12  # 5/8 = 62.5%
    assert result["adx_period_mode"] == 20  # 100%


def test_analyze_stability_empty_windows():
    """Lista vazia retorna dict com defaults."""
    from utils.stability_analyzer_orc_grid import analyze_stability

    result = analyze_stability([])
    assert isinstance(result, dict)
    assert result.get("overfit_flag") is False


# -- SAT 4: lab_orc_grid (orquestrador) ---------------------------------

def test_run_walkforward_grid_returns_dict():
    """run_walkforward_grid retorna dict com windows e stability."""
    from utils.orc_grid import run_walkforward_grid

    result = run_walkforward_grid("XAUUSD", tf="M5", window_len=60, test_len=15, n_windows=2)
    assert isinstance(result, dict)
    assert "windows" in result
    assert "stability" in result
    assert isinstance(result["windows"], list)


def test_run_walkforward_grid_windows_have_keys():
    """Cada janela tem train, test, best_params, train_mae, test_mae."""
    from utils.orc_grid import run_walkforward_grid

    result = run_walkforward_grid("XAUUSD", tf="M5", window_len=60, test_len=15, n_windows=2)
    for w in result["windows"]:
        assert "train" in w
        assert "test" in w
        assert "best_params" in w
        assert "train_mae" in w
        assert "test_mae" in w


def test_run_walkforward_grid_n_windows_respected():
    """n_windows limita o numero de janelas."""
    from utils.orc_grid import run_walkforward_grid

    result = run_walkforward_grid("XAUUSD", tf="M5", window_len=60, test_len=15, n_windows=3)
    assert len(result["windows"]) <= 3
    # Pelo menos 1 janela se houver dados suficientes
    assert len(result["windows"]) >= 1


def test_run_walkforward_grid_symbol_unknown():
    """Simbolo desconhecido retorna windows vazio + erro."""
    from utils.orc_grid import run_walkforward_grid

    result = run_walkforward_grid("ZZZUSD", tf="M5", window_len=60, test_len=15, n_windows=2)
    assert "error" in result or len(result["windows"]) == 0
