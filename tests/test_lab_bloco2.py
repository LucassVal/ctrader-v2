"""Harness S42: Bloco 2 — Sobrevivencia (partial exit, breakeven, OCO ATR, layer comparator, orquestrador).

TDD: testes escritos ANTES da implementacao.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# --------------------------------------------------------------
# PARTIAL EXIT (TP 80%)
# --------------------------------------------------------------


def test_build_tp_callback_returns_callable():
    """build_tp_callback deve retornar um callable (numba dispatcher)."""
    from utils.partial_exit_orc_bloco2 import build_tp_callback

    cb = build_tp_callback(tp1_pct=0.8, tp1_target=0.02)
    assert callable(cb), "Callback must be callable"


def test_build_tp_callback_is_numba_dispatcher():
    """O callback deve ser um numba CPUDispatcher."""
    from utils.partial_exit_orc_bloco2 import build_tp_callback

    cb = build_tp_callback(tp1_pct=0.8, tp1_target=0.02)
    assert hasattr(cb, "py_func") or hasattr(cb, "_dispatcher"), (
        "Callback should be a numba-dispatched function"
    )


def test_build_tp_callback_returns_float_not_tuple():
    """adjust_tp_func_nb deve retornar float (nao tuple)."""
    from vectorbt.portfolio.enums import AdjustTPContext

    from utils.partial_exit_orc_bloco2 import build_tp_callback

    cb = build_tp_callback(tp1_pct=0.8, tp1_target=0.02)
    fn = cb.py_func

    # AdjustTPContext fields: i, col, position_now, val_price_now, init_i, init_price, curr_stop
    ctx = AdjustTPContext(
        i=5, col=0, position_now=1.0, val_price_now=100.0,
        init_i=2, init_price=100.0, curr_stop=np.nan,
    )
    result = fn(ctx)
    assert isinstance(result, float), f"Expected float, got {type(result)}"


def test_build_tp_callback_no_position_no_change():
    """Quando position_now=0 (flat), callback nao deve alterar nada."""
    from vectorbt.portfolio.enums import AdjustTPContext

    from utils.partial_exit_orc_bloco2 import build_tp_callback

    cb = build_tp_callback(tp1_pct=0.8, tp1_target=0.02)
    fn = cb.py_func

    ctx = AdjustTPContext(
        i=5, col=0, position_now=0.0, val_price_now=102.5,
        init_i=2, init_price=100.0, curr_stop=np.nan,
    )
    result = fn(ctx)
    assert np.isnan(result), (
        f"Stop should not change when flat, got {result}"
    )


def test_build_tp_callback_triggers_exit_at_tp1():
    """Quando preco atinge TP1 (+2%), callback retorna 0 (saida imediata)."""
    from vectorbt.portfolio.enums import AdjustTPContext

    from utils.partial_exit_orc_bloco2 import build_tp_callback

    cb = build_tp_callback(tp1_pct=0.8, tp1_target=0.02)
    fn = cb.py_func

    ctx = AdjustTPContext(
        i=5, col=0, position_now=1.0, val_price_now=102.5,
        init_i=2, init_price=100.0, curr_stop=np.nan,
    )
    result = fn(ctx)
    assert result == 0.0, (
        f"Should return 0 (exit) when price > target. Got {result}"
    )


def test_build_tp_callback_below_target_no_exit():
    """Preco abaixo do TP1: manter stop atual."""
    from vectorbt.portfolio.enums import AdjustTPContext

    from utils.partial_exit_orc_bloco2 import build_tp_callback

    cb = build_tp_callback(tp1_pct=0.8, tp1_target=0.02)
    fn = cb.py_func

    ctx = AdjustTPContext(
        i=5, col=0, position_now=1.0, val_price_now=101.5,
        init_i=2, init_price=100.0, curr_stop=1.02,
    )
    result = fn(ctx)
    assert result == 1.02, (
        f"Should keep current stop when below target. Got {result}"
    )


# --------------------------------------------------------------
# BREAKEVEN (BE)
# --------------------------------------------------------------


def test_build_be_callback_returns_callable():
    """build_be_callback deve retornar um callable."""
    from utils.breakeven_orc_bloco2 import build_be_callback

    cb = build_be_callback(trigger_pct=0.6)
    assert callable(cb), "Callback must be callable"


def test_build_be_callback_is_numba_dispatcher():
    """O callback BE deve ser um numba CPUDispatcher."""
    from utils.breakeven_orc_bloco2 import build_be_callback

    cb = build_be_callback(trigger_pct=0.6)
    assert hasattr(cb, "py_func") or hasattr(cb, "_dispatcher"), (
        "Breakeven callback should be numba-dispatched"
    )


def test_build_be_callback_returns_tuple():
    """adjust_sl_func_nb deve retornar Tuple[float, bool]."""
    from vectorbt.portfolio.enums import AdjustSLContext

    from utils.breakeven_orc_bloco2 import build_be_callback

    cb = build_be_callback(trigger_pct=0.006, spread_pips=1.0)
    fn = cb.py_func

    # AdjustSLContext fields: i, col, position_now, val_price_now, init_i, init_price,
    #                         curr_i, curr_price, curr_stop, curr_trail
    ctx = AdjustSLContext(
        i=10, col=0, position_now=1.0, val_price_now=101.0,
        init_i=5, init_price=100.0,
        curr_i=10, curr_price=101.0, curr_stop=98.0, curr_trail=False,
    )
    new_stop, trail = fn(ctx)
    assert isinstance(new_stop, float), f"Expected float new_stop, got {type(new_stop)}"
    assert isinstance(trail, bool), f"Expected bool trail, got {type(trail)}"


def test_build_be_callback_no_position_no_change():
    """Quando flat, breakeven callback nao altera SL."""
    from vectorbt.portfolio.enums import AdjustSLContext

    from utils.breakeven_orc_bloco2 import build_be_callback

    cb = build_be_callback(trigger_pct=0.006, spread_pips=1.0)
    fn = cb.py_func

    ctx = AdjustSLContext(
        i=10, col=0, position_now=0.0, val_price_now=101.5,
        init_i=5, init_price=100.0,
        curr_i=10, curr_price=101.5, curr_stop=98.0, curr_trail=False,
    )
    new_stop, trail = fn(ctx)
    assert new_stop == 98.0, "SL should not move when flat"
    assert not trail, "Trail should remain off when flat"


def test_build_be_callback_below_trigger_no_move():
    """Lucro abaixo do trigger%: SL nao move."""
    from vectorbt.portfolio.enums import AdjustSLContext

    from utils.breakeven_orc_bloco2 import build_be_callback

    cb = build_be_callback(trigger_pct=0.006, spread_pips=1.0)
    fn = cb.py_func

    # trigger_pct = 0.006 = 0.6%
    # curr_price = 100.3 -> profit = 0.3% < 0.6%
    ctx = AdjustSLContext(
        i=10, col=0, position_now=1.0, val_price_now=100.3,
        init_i=5, init_price=100.0,
        curr_i=10, curr_price=100.3, curr_stop=98.0, curr_trail=False,
    )
    new_stop, _trail = fn(ctx)
    assert new_stop == 98.0, (
        f"SL should not move below trigger. Got new_stop={new_stop}"
    )


def test_build_be_callback_above_trigger_moves_sl():
    """Lucro acima do trigger%: SL sobe para entry + spread."""
    from vectorbt.portfolio.enums import AdjustSLContext

    from utils.breakeven_orc_bloco2 import build_be_callback

    cb = build_be_callback(trigger_pct=0.006, spread_pips=1.0)
    fn = cb.py_func

    # trigger_pct = 0.006 = 0.6%
    # curr_price = 101.0 -> profit = 1.0% > 0.6% -> ativa BE
    ctx = AdjustSLContext(
        i=10, col=0, position_now=1.0, val_price_now=101.0,
        init_i=5, init_price=100.0,
        curr_i=10, curr_price=101.0, curr_stop=98.0, curr_trail=False,
    )
    new_stop, _trail = fn(ctx)
    assert new_stop > 98.0, (
        f"SL should move up when profit exceeds trigger. Got {new_stop}"
    )
    assert new_stop == pytest.approx(101.0), (
        f"SL should move to entry(100) + spread(1.0) = 101.0. Got {new_stop}"
    )


def test_build_be_callback_short_position_triggers():
    """Posicao short: BE move SL para entry - spread."""
    from vectorbt.portfolio.enums import AdjustSLContext

    from utils.breakeven_orc_bloco2 import build_be_callback

    cb = build_be_callback(trigger_pct=0.006, spread_pips=1.0)
    fn = cb.py_func

    # Short: init_price=100, curr_price=99 -> profit ~1% (preco caiu)
    ctx = AdjustSLContext(
        i=10, col=0, position_now=-1.0, val_price_now=99.0,
        init_i=5, init_price=100.0,
        curr_i=10, curr_price=99.0, curr_stop=102.0, curr_trail=False,
    )
    new_stop, _trail = fn(ctx)
    assert new_stop < 102.0, (
        f"SL should move down for short when profit exceeds trigger. Got {new_stop}"
    )
    assert new_stop == pytest.approx(99.0), (
        f"SL should move to entry(100) - spread(1.0) = 99.0. Got {new_stop}"
    )


# --------------------------------------------------------------
# OCO ATR
# --------------------------------------------------------------


def test_calc_oco_bands_basic():
    """calc_oco_bands deve retornar (sl_price, tp_price) para long."""
    from utils.oco_atr_orc_bloco2 import calc_oco_bands

    sl, tp = calc_oco_bands(atr_value=10.0, multiplier=1.5, entry_price=100.0)
    assert sl == pytest.approx(85.0, rel=0.01)  # 100 - 15
    assert tp == pytest.approx(130.0, rel=0.01)  # 100 + 30


def test_calc_oco_bands_sl_tp_ratio():
    """TP deve ser 2x a distancia do SL."""
    from utils.oco_atr_orc_bloco2 import calc_oco_bands

    entry = 1500.0
    atr = 25.0
    mult = 2.0

    sl, tp = calc_oco_bands(atr_value=atr, multiplier=mult, entry_price=entry)
    sl_dist = entry - sl
    tp_dist = tp - entry
    assert tp_dist == pytest.approx(sl_dist * 2.0, rel=0.01), (
        f"TP distance ({tp_dist}) should be 2x SL distance ({sl_dist})"
    )


def test_calc_oco_bands_returns_floats():
    """Os offsets devem ser floats."""
    from utils.oco_atr_orc_bloco2 import calc_oco_bands

    sl, tp = calc_oco_bands(atr_value=10.0, multiplier=1.5, entry_price=100.0)
    assert isinstance(sl, float)
    assert isinstance(tp, float)


def test_calc_oco_bands_zero_atr():
    """ATR zero: SL e TP no preco de entrada (sem offset)."""
    from utils.oco_atr_orc_bloco2 import calc_oco_bands

    sl, tp = calc_oco_bands(atr_value=0.0, multiplier=1.5, entry_price=100.0)
    assert sl == 100.0, "SL should be at entry when ATR=0"
    assert tp == 100.0, "TP should be at entry when ATR=0"


def test_calc_oco_bands_high_multiplier():
    """Multiplier alto -> bandas largas proporcionais."""
    from utils.oco_atr_orc_bloco2 import calc_oco_bands

    sl, tp = calc_oco_bands(atr_value=5.0, multiplier=10.0, entry_price=2000.0)
    assert sl == pytest.approx(1950.0, rel=0.01)  # 2000 - 50
    assert tp == pytest.approx(2100.0, rel=0.01)  # 2000 + 100
    assert tp > sl


def test_calc_oco_bands_no_entry_price():
    """Sem entry_price: retorna offsets relativos."""
    from utils.oco_atr_orc_bloco2 import calc_oco_bands

    sl, tp = calc_oco_bands(atr_value=10.0, multiplier=1.5)
    assert sl == -15.0  # -ATR * mult
    assert tp == 30.0   # +ATR * mult * 2


# --------------------------------------------------------------
# LAYER COMPARATOR
# --------------------------------------------------------------


@pytest.fixture
def sample_results():
    """Fixture: resultados simulados de 5 camadas."""
    return {
        "baseline": {
            "sharpe": 0.45, "max_dd": 12.3, "win_rate": 48.2,
            "profit_factor": 1.15, "expectancy": 0.12,
        },
        "tp_80": {
            "sharpe": 0.52, "max_dd": 10.1, "win_rate": 52.1,
            "profit_factor": 1.28, "expectancy": 0.18,
        },
        "be": {
            "sharpe": 0.48, "max_dd": 8.7, "win_rate": 48.2,
            "profit_factor": 1.22, "expectancy": 0.15,
        },
        "trail": {
            "sharpe": 0.55, "max_dd": 11.2, "win_rate": 46.8,
            "profit_factor": 1.31, "expectancy": 0.20,
        },
        "oco_atr": {
            "sharpe": 0.61, "max_dd": 7.3, "win_rate": 54.5,
            "profit_factor": 1.45, "expectancy": 0.25,
        },
    }


def test_compare_layers_returns_dataframe(sample_results):
    """compare_layers deve retornar um DataFrame."""
    from utils.layer_comparator_orc_bloco2 import compare_layers

    df = compare_layers(sample_results)
    assert isinstance(df, pd.DataFrame), "Result must be a DataFrame"


def test_compare_layers_has_correct_columns(sample_results):
    """DataFrame deve ter colunas: Camada, Sharpe, MaxDD, WinRate, ProfitFactor, Expectancy."""
    from utils.layer_comparator_orc_bloco2 import compare_layers

    df = compare_layers(sample_results)
    expected = {"Camada", "Sharpe", "MaxDD", "WinRate", "ProfitFactor", "Expectancy"}
    actual = set(df.columns)
    assert expected.issubset(actual), (
        f"Missing columns: {expected - actual}"
    )


def test_compare_layers_has_five_rows(sample_results):
    """Deve ter 5 linhas (uma por camada)."""
    from utils.layer_comparator_orc_bloco2 import compare_layers

    df = compare_layers(sample_results)
    assert len(df) == 5, f"Expected 5 rows, got {len(df)}"


def test_compare_layers_camada_names(sample_results):
    """Nomes das camadas devem corresponder."""
    from utils.layer_comparator_orc_bloco2 import compare_layers

    df = compare_layers(sample_results)
    expected_names = {"baseline", "tp_80", "be", "trail", "oco_atr"}
    actual_names = set(df["Camada"].values)
    assert expected_names == actual_names, (
        f"Layer name mismatch: {expected_names - actual_names}"
    )


def test_compare_layers_sortable(sample_results):
    """O DataFrame deve ser ordenavel por Sharpe."""
    from utils.layer_comparator_orc_bloco2 import compare_layers

    df = compare_layers(sample_results)
    sorted_df = df.sort_values("Sharpe", ascending=False)
    assert sorted_df.iloc[0]["Camada"] == "oco_atr", (
        "oco_atr should have highest Sharpe"
    )


# --------------------------------------------------------------
# ORQUESTRADOR lab_orc_bloco2
# --------------------------------------------------------------


def test_run_bloco2_is_callable():
    """run_bloco2 deve ser uma funcao importavel."""
    from utils.orc_bloco2 import run_bloco2

    assert callable(run_bloco2), "run_bloco2 must be a callable function"


def test_run_bloco2_signature():
    """run_bloco2 deve aceitar signals_validated, ohlcv, tf."""
    import inspect

    from utils.orc_bloco2 import run_bloco2

    sig = inspect.signature(run_bloco2)
    params = set(sig.parameters.keys())
    required = {"signals_validated", "ohlcv", "tf"}
    assert required.issubset(params), (
        f"run_bloco2 must accept {required}, got {params}"
    )


def test_run_bloco2_returns_dict_with_keys():
    """run_bloco2 deve retornar um dict com comparison, best_layer, equity_curves, trades_per_layer."""
    from utils.orc_bloco2 import run_bloco2

    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="5min")
    close = np.cumprod(1 + np.random.randn(n) * 0.002) * 100.0

    ohlcv = pd.DataFrame({
        "open": close * (1 + np.random.randn(n) * 0.0005),
        "high": close * (1 + np.abs(np.random.randn(n) * 0.002)),
        "low": close * (1 - np.abs(np.random.randn(n) * 0.002)),
        "close": close,
        "volume": np.random.randint(100, 1000, n),
    }, index=dates)

    entries = np.zeros(n, dtype=bool)
    entries[20:25] = True
    entries[80:85] = True
    entries[120:125] = True
    exits = np.zeros(n, dtype=bool)
    exits[26] = True
    exits[87] = True
    exits[127] = True

    signals = pd.DataFrame({"entries": entries, "exits": exits}, index=dates)

    result = run_bloco2(signals_validated=signals, ohlcv=ohlcv, tf="M5")

    assert isinstance(result, dict), "Result must be a dict"
    required_keys = {"comparison", "best_layer", "equity_curves", "trades_per_layer"}
    missing = required_keys - set(result.keys())
    assert not missing, f"Missing keys: {missing}"


def test_run_bloco2_best_layer_is_string():
    """best_layer deve ser uma string com nome da melhor camada."""
    from utils.orc_bloco2 import run_bloco2

    n = 200
    dates = pd.date_range("2024-01-01", periods=n, freq="5min")
    close = np.cumprod(1 + np.random.randn(n) * 0.002) * 100.0

    ohlcv = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.randint(100, 1000, n),
    }, index=dates)

    entries = np.zeros(n, dtype=bool)
    entries[[10, 50, 100, 150]] = True
    exits = np.zeros(n, dtype=bool)
    exits[[15, 55, 105, 155]] = True

    signals = pd.DataFrame({"entries": entries, "exits": exits}, index=dates)

    result = run_bloco2(signals_validated=signals, ohlcv=ohlcv, tf="M5")
    assert isinstance(result["best_layer"], str), "best_layer must be a string"
    assert len(result["best_layer"]) > 0, "best_layer must not be empty"


def test_run_bloco2_validate_missing_column():
    """Deve lancar ValueError se colunas obrigatorias ausentes."""
    import pytest as pt

    from utils.orc_bloco2 import run_bloco2

    n = 50
    dates = pd.date_range("2024-01-01", periods=n, freq="5min")
    ohlcv = pd.DataFrame({
        "open": np.ones(n) * 100.0,
        "high": np.ones(n) * 101.0,
        "low": np.ones(n) * 99.0,
        "close": np.ones(n) * 100.0,
    }, index=dates)

    # Missing 'entries' column
    bad_signals = pd.DataFrame({"exits": np.zeros(n, dtype=bool)}, index=dates)
    with pt.raises(ValueError, match="entries"):
        run_bloco2(signals_validated=bad_signals, ohlcv=ohlcv, tf="M5")
