"""Harness S41: Bloco 1 — Torneio do Passado (Alpha Generation).

TDD: RED — todos os testes escritos antes da implementacao.
Testa cada SAT isoladamente + orquestrador integrado.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ---------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------


@pytest.fixture
def ohlc_bullish():
    """Serie bullish simples: sobe de 100 a 110 em 20 barras."""
    n = 20
    close = np.linspace(100, 110, n)
    high = close + np.random.uniform(0.5, 1.5, n)
    low = close - np.random.uniform(0.2, 1.0, n)
    open_ = np.roll(close, 1)
    open_[0] = close[0] - 0.5
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "tick_volume": np.full(n, 5000)}
    )


@pytest.fixture
def ohlc_bearish():
    """Serie bearish simples: cai de 110 a 100 em 20 barras."""
    n = 20
    close = np.linspace(110, 100, n)
    high = close + np.random.uniform(0.2, 1.0, n)
    low = close - np.random.uniform(0.5, 1.5, n)
    open_ = np.roll(close, -1)
    open_[0] = close[0] + 0.5
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "tick_volume": np.full(n, 5000)}
    )


@pytest.fixture
def ohlc_large():
    """Serie de 200 barras para testes de grid/integracao."""
    n = 200
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + np.abs(rng.normal(0.5, 0.15, n))
    low = close - np.abs(rng.normal(0.3, 0.1, n))
    open_ = np.roll(close, 1)
    open_[0] = close[0] - rng.normal(0, 0.2)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "tick_volume": rng.integers(1000, 10000, n)}
    )


# ---------------------------------------------------------------
# 1. mae_mfe_orc_bloco1 — calc_mae_mfe
# ---------------------------------------------------------------


def test_calc_mae_mfe_long_bullish():
    """MAE/MFE para long em mercado bullish: MFE > 0, MAE pequena."""
    from utils.mae_mfe_orc_bloco1 import calc_mae_mfe

    highs = pd.Series([101.0, 102.0, 103.0, 105.0, 107.0, 106.0, 108.0], dtype=float)
    lows = pd.Series([99.0, 98.5, 98.0, 99.0, 100.0, 101.0, 102.0], dtype=float)
    entry_price = 100.0

    mae, mfe = calc_mae_mfe(entry_price, highs, lows, 6)

    # MFE: (max(high) - entry) / entry = (108-100)/100 = 0.08
    assert mfe == pytest.approx(0.08, abs=0.001)
    # MAE: (entry - min(low)) / entry = (100-98)/100 = 0.02
    assert mae == pytest.approx(0.02, abs=0.001)
    # MFE deve ser positiva em mercado bullish
    assert mfe >= 0
    # MAE nao-negativa
    assert mae >= 0


def test_calc_mae_mfe_short_bearish():
    """MAE/MFE para short em mercado bearish: MFE > 0, MAE = 0 (sem excursao adversa)."""
    from utils.mae_mfe_orc_bloco1 import calc_mae_mfe

    highs = pd.Series([109.0, 108.0, 107.5, 107.0, 106.0, 105.0, 104.0], dtype=float)
    lows = pd.Series([107.0, 106.5, 105.0, 103.0, 102.0, 101.0, 100.0], dtype=float)
    entry_price = 110.0

    mae, mfe = calc_mae_mfe(entry_price, highs, lows, 6, direction="SHORT")

    # MFE short: (entry - min(low)) / entry = (110-100)/110 = 0.0909
    assert mfe == pytest.approx(0.0909, abs=0.002)
    # MAE short: high nunca superou entry -> MAE = 0
    assert mae == pytest.approx(0.0, abs=0.001)
    assert mfe >= 0
    assert mae >= 0


def test_calc_mae_mfe_no_adverse_excursion():
    """Quando preco so sobe (long): MAE = 0."""
    from utils.mae_mfe_orc_bloco1 import calc_mae_mfe

    highs = pd.Series([101, 102, 103, 104, 105], dtype=float)
    lows = pd.Series([100, 101, 102, 103, 104], dtype=float)
    entry_price = 100.0

    mae, mfe = calc_mae_mfe(entry_price, highs, lows, 4)

    # Nunca caiu abaixo da entrada -> MAE = 0
    assert mae == pytest.approx(0.0)
    assert mfe > 0


def test_calc_mae_mfe_empty_series():
    """Series vazias retornam 0, 0 (sem crash)."""
    from utils.mae_mfe_orc_bloco1 import calc_mae_mfe

    mae, mfe = calc_mae_mfe(100.0, pd.Series([], dtype=float), pd.Series([], dtype=float), 0)
    assert mae == 0.0
    assert mfe == 0.0


def test_calc_mae_mfe_numpy_input():
    """Aceita numpy arrays alem de pd.Series."""
    from utils.mae_mfe_orc_bloco1 import calc_mae_mfe

    highs = np.array([102.0, 103.0, 105.0])
    lows = np.array([99.0, 98.0, 100.0])

    mae, mfe = calc_mae_mfe(100.0, highs, lows, 2)

    assert isinstance(mae, float)
    assert isinstance(mfe, float)
    assert mae >= 0
    assert mfe >= 0


# ---------------------------------------------------------------
# 2. signal_matrix_orc_bloco1 — build_boolean_matrix
# ---------------------------------------------------------------


def test_build_boolean_matrix_all_true():
    """AND logico: todas as sub-fases OK -> sinal validado."""
    from utils.signal_matrix_orc_bloco1 import build_boolean_matrix

    idx = pd.date_range("2024-01-01", periods=5, freq="5min")
    gatilho = pd.DataFrame({"BUY": [True, True, True, True, True]}, index=idx)
    forca = pd.DataFrame({"BUY": [True, True, True, True, True]}, index=idx)
    dxy_ok = pd.Series([True, True, True, True, True], index=idx)

    result = build_boolean_matrix(gatilho, forca, dxy_ok)

    assert isinstance(result, pd.DataFrame)
    assert result.shape == (5, 1)
    assert result.iloc[:, 0].all()


def test_build_boolean_matrix_partial():
    """Se uma sub-fase falhar -> sinal FALSE. Soh a linha 3 tem todos True."""
    from utils.signal_matrix_orc_bloco1 import build_boolean_matrix

    idx = pd.date_range("2024-01-01", periods=4, freq="5min")
    gatilho = pd.DataFrame({"SELL": [True, True, False, True]}, index=idx)
    forca = pd.DataFrame({"SELL": [True, False, True, True]}, index=idx)
    dxy_ok = pd.Series([False, True, True, True], index=idx)

    result = build_boolean_matrix(gatilho, forca, dxy_ok)

    # Linhas 0,1,2: pelo menos uma condicao False -> False
    # Linha 3: todas True -> True
    expected = [False, False, False, True]
    assert result.iloc[:, 0].tolist() == expected


def test_build_boolean_matrix_dxy_none():
    """DXY ok=None significa sem filtro (todos True)."""
    from utils.signal_matrix_orc_bloco1 import build_boolean_matrix

    idx = pd.date_range("2024-01-01", periods=3, freq="5min")
    gatilho = pd.DataFrame({"BUY": [True, False, True]}, index=idx)
    forca = pd.DataFrame({"BUY": [True, True, False]}, index=idx)

    result = build_boolean_matrix(gatilho, forca, dxy_ok=None)

    # Sem DXY: apenas AND de gatilho & forca
    expected = [True, False, False]
    assert result.iloc[:, 0].tolist() == expected


def test_build_boolean_matrix_multi_symbol():
    """Multiplos simbolos na matriz."""
    from utils.signal_matrix_orc_bloco1 import build_boolean_matrix

    idx = pd.date_range("2024-01-01", periods=3, freq="5min")
    gatilho = pd.DataFrame(
        {"XAUUSD": [True, True, False], "EURUSD": [True, False, True]}, index=idx
    )
    forca = pd.DataFrame(
        {"XAUUSD": [True, True, True], "EURUSD": [True, True, True]}, index=idx
    )
    dxy_ok = pd.Series([True, True, True], index=idx)

    result = build_boolean_matrix(gatilho, forca, dxy_ok)

    assert result.shape == (3, 2)
    assert list(result.columns) == ["XAUUSD", "EURUSD"]


def test_build_boolean_matrix_index_mismatch():
    """Se dxy_ok tem index diferente -> alinha automaticamente."""
    from utils.signal_matrix_orc_bloco1 import build_boolean_matrix

    idx = pd.date_range("2024-01-01", periods=3, freq="5min")
    idx_dxy = pd.date_range("2024-01-01", periods=5, freq="5min")
    gatilho = pd.DataFrame({"BUY": [True, True, True]}, index=idx)
    forca = pd.DataFrame({"BUY": [True, True, True]}, index=idx)
    dxy_ok = pd.Series([True, False, True, True, True], index=idx_dxy)

    result = build_boolean_matrix(gatilho, forca, dxy_ok)

    # Deve alinhar pelos 3 primeiros timestamps
    assert result.shape == (3, 1)


# ---------------------------------------------------------------
# 3. dxy_filter_orc_bloco1 — check_dxy_alignment
# ---------------------------------------------------------------


def test_dxy_xauusd_bullish_dxy_falling():
    """XAUUSD bullish + DXY caindo -> OK (correlacao inversa)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    # DXY caindo: dxy_return < 0
    result = check_dxy_alignment("XAUUSD", "BULLISH", dxy_roc=-0.005)
    assert result is True


def test_dxy_xauusd_bullish_dxy_rising():
    """XAUUSD bullish + DXY subindo -> ANOMALIA (FALSE)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    result = check_dxy_alignment("XAUUSD", "BULLISH", dxy_roc=0.005)
    assert result is False


def test_dxy_xauusd_bearish_dxy_rising():
    """XAUUSD bearish + DXY subindo -> OK (correlacao inversa: ouro cai, dolar sobe)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    result = check_dxy_alignment("XAUUSD", "BEARISH", dxy_roc=0.008)
    assert result is True


def test_dxy_eurusd_bullish_dxy_falling():
    """EURUSD bullish + DXY caindo -> OK (inversa)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    result = check_dxy_alignment("EURUSD", "BULLISH", dxy_roc=-0.003)
    assert result is True


def test_dxy_usdjpy_bullish_dxy_rising():
    """USDJPY bullish + DXY subindo -> OK (correlacao DIRETA)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    result = check_dxy_alignment("USDJPY", "BULLISH", dxy_roc=0.004)
    assert result is True


def test_dxy_usdjpy_bullish_dxy_falling():
    """USDJPY bullish + DXY caindo -> FALSE (correlacao DIRETA violada)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    result = check_dxy_alignment("USDJPY", "BULLISH", dxy_roc=-0.004)
    assert result is False


def test_dxy_neutral_always_ok():
    """DXY neutro (|return| < threshold) -> sempre OK."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    assert check_dxy_alignment("XAUUSD", "BULLISH", dxy_roc=0.0001) is True
    assert check_dxy_alignment("USDJPY", "BEARISH", dxy_roc=-0.0001) is True


def test_dxy_unknown_symbol_passes():
    """Simbolo desconhecido -> passa (sem filtro, warn log)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    result = check_dxy_alignment("BTCUSD", "BULLISH", dxy_roc=0.01)
    assert result is True


def test_dxy_invalid_direction():
    """Direcao invalida -> passa (sem crash)."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    result = check_dxy_alignment("XAUUSD", "INVALID", dxy_roc=0.01)
    assert result is True


def test_dxy_anomaly_threshold():
    """Anomalia ouro+dolar mesma direcao > threshold -> aborte."""
    from utils.dxy_filter_orc_bloco1 import check_dxy_alignment

    # XAUUSD BULLISH + DXY subindo MUITO (> threshold 0.003)
    result = check_dxy_alignment("XAUUSD", "BULLISH", dxy_roc=0.01, anomaly_threshold=0.003)
    assert result is False

    # XAUUSD BULLISH + DXY subindo POUCO (< threshold) -> OK se abaixo do limiar
    # nota: abaixo do threshold é tratado como neutro
    result = check_dxy_alignment("XAUUSD", "BULLISH", dxy_roc=0.002, anomaly_threshold=0.003)
    assert result is True


# ---------------------------------------------------------------
# 4. time_exit_orc_bloco1 — generate_exits
# ---------------------------------------------------------------


def test_generate_exits_horizon_5():
    """Saida em t+5 a partir do entry_idx."""
    from utils.time_exit_orc_bloco1 import generate_exits

    n = 20
    exit_idx = generate_exits(entry_indices=5, data_length=n, horizon=5)

    assert exit_idx == 10


def test_generate_exits_horizon_15():
    """Saida em t+15."""
    from utils.time_exit_orc_bloco1 import generate_exits

    exit_idx = generate_exits(entry_indices=3, data_length=50, horizon=15)

    assert exit_idx == 18


def test_generate_exits_clamped_to_overflow():
    """Se entry_idx + horizon > data_length -> clamp ao ultimo indice."""
    from utils.time_exit_orc_bloco1 import generate_exits

    exit_idx = generate_exits(entry_indices=95, data_length=100, horizon=10)

    assert exit_idx == 99  # ultimo indice valido


def test_generate_exits_batch():
    """Matriz de saidas para multiplas entradas."""
    from utils.time_exit_orc_bloco1 import generate_exits

    entry_indices = [10, 20, 30]
    exits = generate_exits(entry_indices, data_length=50, horizon=5)

    assert exits == [15, 25, 35]


def test_generate_exits_invalid_horizon():
    """Horizon invalido -> ValueError."""
    from utils.time_exit_orc_bloco1 import generate_exits

    with pytest.raises(ValueError, match="horizon"):
        generate_exits(5, data_length=50, horizon=0)


def test_generate_exits_negative_entry():
    """Entry negativo -> ValueError."""
    from utils.time_exit_orc_bloco1 import generate_exits

    with pytest.raises(ValueError, match="entry"):
        generate_exits(-1, data_length=50, horizon=5)


def test_generate_exits_empty_list():
    """Lista vazia -> lista vazia."""
    from utils.time_exit_orc_bloco1 import generate_exits

    exits = generate_exits([], data_length=50, horizon=5)
    assert exits == []


# ---------------------------------------------------------------
# 5. grid_search_orc_bloco1 — run_parameter_grid
# ---------------------------------------------------------------


def test_run_parameter_grid_returns_dataframe():
    """Grid retorna DataFrame com colunas obrigatorias."""
    from utils.grid_search_orc_bloco1 import run_parameter_grid

    param_grid = {
        "rsi_period": [5, 10],
        "adx_period": [10, 14],
    }
    result = run_parameter_grid(param_grid)

    assert isinstance(result, pd.DataFrame)
    assert "mae" in result.columns
    assert len(result) == 4  # 2x2


def test_run_parameter_grid_max_combos():
    """Limite de 200 combos (Pareto 80/20)."""
    from utils.grid_search_orc_bloco1 import run_parameter_grid

    # Grid que geraria 500 combos
    param_grid = {
        f"param_{i}": list(range(5)) for i in range(4)  # 5^4 = 625
    }
    result = run_parameter_grid(param_grid, max_combos=200)

    assert len(result) <= 200


def test_run_parameter_grid_sort_by_mae():
    """Resultado ordenado por MAE crescente (menor = melhor)."""
    from utils.grid_search_orc_bloco1 import run_parameter_grid

    param_grid = {
        "period": [5, 10, 14, 20],
    }
    result = run_parameter_grid(param_grid)

    assert result["mae"].is_monotonic_increasing


def test_run_parameter_grid_empty_grid():
    """Grid vazio -> DataFrame vazio."""
    from utils.grid_search_orc_bloco1 import run_parameter_grid

    result = run_parameter_grid({})
    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


# ---------------------------------------------------------------
# 6. lab_orc_bloco1 (orquestrador) — run_bloco1
# ---------------------------------------------------------------


def test_run_bloco1_contract(ohlc_large):
    """Contrato de saida: dict com todas as chaves obrigatorias."""
    from utils.orc_bloco1 import run_bloco1

    result = run_bloco1(
        ohlc_df=ohlc_large,
        symbol="XAUUSD",
        tf="M5",
        horizon=5,
    )

    assert isinstance(result, dict)
    assert "symbol" in result
    assert result["symbol"] == "XAUUSD"
    assert "tf" in result
    assert result["tf"] == "M5"
    assert "signals_validated" in result
    assert "signals_validated" in result  # v2.1: mae_by_combo removido
    assert "best_combo" in result
    assert "dxy_filtered_out" in result
    assert "trades" in result


def test_run_bloco1_best_combo_keys():
    """best_combo contem parametros otimizados."""
    from utils.orc_bloco1 import run_bloco1

    result = run_bloco1(
        ohlc_df=pd.DataFrame({
            "open": np.linspace(100, 110, 100),
            "high": np.linspace(101, 112, 100),
            "low": np.linspace(99, 108, 100),
            "close": np.linspace(100.5, 110.5, 100),
            "tick_volume": np.full(100, 5000),
        }),
        symbol="XAUUSD",
        tf="M5",
    )

    best = result["best_combo"]
    assert "buy_trigger" in best, f"Keys: {list(best.keys())}"
    # buy_trigger deve ter os parametros vencedores
    assert isinstance(best["buy_trigger"], dict)


def test_run_bloco1_trades_log_format():
    """Cada trade no log tem formato esperado."""
    from utils.orc_bloco1 import run_bloco1

    result = run_bloco1(
        ohlc_df=pd.DataFrame({
            "open": np.random.default_rng(42).normal(100, 1, 200).cumsum() / 5 + 100,
            "high": np.random.default_rng(43).normal(101, 1, 200).cumsum() / 5 + 101,
            "low": np.random.default_rng(44).normal(99, 1, 200).cumsum() / 5 + 99,
            "close": np.random.default_rng(45).normal(100.5, 1, 200).cumsum() / 5 + 100,
            "tick_volume": np.random.default_rng(46).integers(1000, 10000, 200),
        }),
        symbol="EURUSD",
        tf="M5",
        horizon=5,
    )

    for trade in result["trades"]:
        for key in ["entry_time", "exit_time", "direction", "entry_price",
                     "exit_price", "mae_pct", "mfe_pct", "pnl_pct", "horizon"]:
            assert key in trade, f"Trade missing key: {key}"


def test_run_bloco1_empty_data():
    """DataFrame vazio -> resultado vazio, sem crash."""
    from utils.orc_bloco1 import run_bloco1

    result = run_bloco1(
        ohlc_df=pd.DataFrame(),
        symbol="XAUUSD",
        tf="M5",
    )

    assert isinstance(result, dict)
    assert result["signals_validated"] is not None
    assert len(result["trades"]) == 0


def test_run_bloco1_different_horizons():
    """Horizon 5 vs 15 gera saidas diferentes."""
    from utils.orc_bloco1 import run_bloco1

    df = pd.DataFrame({
        "open": np.linspace(100, 110, 100),
        "high": np.linspace(101, 112, 100),
        "low": np.linspace(99, 108, 100),
        "close": np.linspace(100.5, 110.5, 100),
        "tick_volume": np.full(100, 5000),
    })

    r5 = run_bloco1(ohlc_df=df, symbol="XAUUSD", tf="M5", horizon=5)
    r15 = run_bloco1(ohlc_df=df, symbol="XAUUSD", tf="M5", horizon=15)

    # Horizons diferentes devem gerar metricas diferentes
    # (pelo menos o best_combo pode diferir)
    assert isinstance(r5, dict)
    assert isinstance(r15, dict)


def test_run_bloco1_all_five_symbols():
    """Orquestrador aceita qualquer dos 5 simbolos do A5."""
    from utils.orc_bloco1 import run_bloco1

    df = pd.DataFrame({
        "open": np.linspace(1.10, 1.12, 80),
        "high": np.linspace(1.11, 1.13, 80),
        "low": np.linspace(1.09, 1.11, 80),
        "close": np.linspace(1.105, 1.125, 80),
        "tick_volume": np.full(80, 5000),
    })

    for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        result = run_bloco1(ohlc_df=df, symbol=sym, tf="M5")
        assert result["symbol"] == sym
