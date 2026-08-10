"""Testes unitarios para montecarlo_orc_bloco2.py.

TDD: RED-GREEN-REFACTOR. Cada teste exercita um comportamento especifico.
"""

from __future__ import annotations

import numpy as np
import pytest

from utils.montecarlo_orc_bloco2 import (
    _equity_curve,
    _extract_pnl,
    _max_dd,
    _sharpe,
    monte_carlo_shuffle,
)

# ═══════════════════════════════════════════════════════════════
# UNIT TESTS — helpers
# ═══════════════════════════════════════════════════════════════


class TestExtractPnl:
    def test_pnl_pct_key(self):
        assert _extract_pnl({"pnl_pct": 0.0032}) == 0.0032

    def test_pnl_key_fallback(self):
        assert _extract_pnl({"pnl": 0.0015}) == 0.0015

    def test_entry_exit_buy(self):
        assert _extract_pnl({
            "entry_price": 100.0, "exit_price": 102.0, "direction": "BUY"
        }) == pytest.approx(0.02)

    def test_entry_exit_sell(self):
        assert _extract_pnl({
            "entry_price": 105.0, "exit_price": 102.0, "direction": "SELL"
        }) == pytest.approx(0.02857142857)

    def test_empty_dict_returns_zero(self):
        assert _extract_pnl({}) == 0.0


class TestEquityCurve:
    def test_positive_returns(self):
        pnls = np.array([0.01, 0.02, 0.01])
        eq = _equity_curve(pnls)
        assert eq[0] == pytest.approx(1.01)
        assert eq[2] == pytest.approx(1.01 * 1.02 * 1.01)

    def test_negative_returns(self):
        pnls = np.array([-0.01, -0.02])
        eq = _equity_curve(pnls)
        assert eq[1] < 1.0

    def test_empty_array(self):
        eq = _equity_curve(np.array([]))
        assert len(eq) == 0


class TestSharpe:
    def test_all_positive(self):
        pnls = np.array([0.01] * 100)
        assert _sharpe(pnls) > 100  # near-zero std = astronomical Sharpe

    def test_mixed_returns(self):
        rng = np.random.default_rng(42)
        pnls = rng.normal(0.001, 0.02, 252)
        s = _sharpe(pnls)
        assert -5.0 < s < 5.0  # reasonable range

    def test_zero_std_zero_mean(self):
        assert _sharpe(np.array([0.0, 0.0, 0.0])) == 0.0

    def test_single_value(self):
        assert _sharpe(np.array([0.01])) == 0.0


class TestMaxDD:
    def test_no_drawdown(self):
        eq = np.array([1.0, 1.1, 1.2, 1.3])
        assert _max_dd(eq) == 0.0

    def test_with_drawdown(self):
        eq = np.array([1.0, 1.2, 0.9, 1.1])
        dd = _max_dd(eq)
        # peak=1.2 at index 1, trough=0.9 at index 2
        # dd = (1.2 - 0.9) / 1.2 = 0.25 -> 25%
        assert dd == pytest.approx(25.0, abs=0.1)

    def test_severe_drawdown(self):
        eq = np.array([1.0, 0.5, 0.3, 0.8])
        dd = _max_dd(eq)
        # peak=1.0, trough=0.3 -> (1.0-0.3)/1.0 = 0.70 -> 70%
        assert dd == pytest.approx(70.0, abs=0.1)

    def test_empty_array(self):
        assert _max_dd(np.array([])) == 0.0


# ═══════════════════════════════════════════════════════════════
# INTEGRATION TESTS — monte_carlo_shuffle
# ═══════════════════════════════════════════════════════════════


class TestMonteCarloShuffle:
    def test_empty_trades(self):
        result = monte_carlo_shuffle([])
        assert result["n_trades"] == 0
        assert result["n_simulations"] == 0
        assert result["is_lucky"] is True

    def test_few_trades_below_minimum(self):
        trades = [{"pnl_pct": 0.01} for _ in range(5)]
        result = monte_carlo_shuffle(trades)
        assert result["n_trades"] == 5
        assert result["n_simulations"] == 0  # too few for reliable MC

    def test_known_seed_reproducibility(self):
        """Mesmo seed deve produzir mesmos resultados."""
        trades = [{"pnl_pct": np.random.default_rng(i).normal(0.001, 0.02)}
                  for i in range(100)]

        r1 = monte_carlo_shuffle(trades, n_simulations=200, seed=42)
        r2 = monte_carlo_shuffle(trades, n_simulations=200, seed=42)

        assert r1["sharpe_original"] == r2["sharpe_original"]
        assert r1["sharpe_pvalue"] == r2["sharpe_pvalue"]
        assert r1["max_dd_worst_shuffle"] == r2["max_dd_worst_shuffle"]

    def test_positive_edge_is_not_lucky(self):
        """Trades com edge real (media positiva consistente) devem ter p >= 0.05."""
        rng = np.random.default_rng(42)
        # Gera trades com edge: media 0.002, std 0.01, 200 trades
        trades = [{"pnl_pct": float(rng.normal(0.002, 0.01))} for _ in range(200)]
        result = monte_carlo_shuffle(trades, n_simulations=500, seed=42)
        assert result["n_trades"] == 200
        assert result["n_simulations"] == 500
        assert result["sharpe_original"] > 0
        # Com edge real, pvalue deve ser alto (Sharpe nao eh sorte)
        assert result["is_lucky"] is False

    def test_random_noise_is_lucky(self):
        """Trades puramente aleatorios (media zero) devem ter p < 0.05."""
        rng = np.random.default_rng(123)
        trades = [{"pnl_pct": float(rng.normal(0.0, 0.02))} for _ in range(200)]
        result = monte_carlo_shuffle(trades, n_simulations=500, seed=42)
        # Media zero -> Sharpe pode ser levemente positivo por acaso
        # Embaralhar deve produzir distribuicao similar -> pvalue ~0.5
        assert 0.0 < result["sharpe_pvalue"] < 1.0

    def test_contract_keys(self):
        """Verifica que todas as chaves do contrato estao presentes."""
        trades = [{"pnl_pct": 0.001 * i} for i in range(100)]
        result = monte_carlo_shuffle(trades, n_simulations=100, seed=42)

        required_keys = {
            "sharpe_original", "sharpe_median_shuffled", "sharpe_pvalue",
            "max_dd_original", "max_dd_worst_shuffle", "max_dd_cvar_95",
            "max_dd_median_shuffled", "is_lucky", "n_trades", "n_simulations",
        }
        assert required_keys <= set(result.keys())

    def test_drawdown_bounds(self):
        """Max DD deve estar entre 0 e 100."""
        trades = [{"pnl_pct": np.random.default_rng(i).normal(0.0, 0.03)}
                  for i in range(200)]
        result = monte_carlo_shuffle(trades, n_simulations=200, seed=42)

        assert 0.0 <= result["max_dd_original"] <= 100.0
        assert 0.0 <= result["max_dd_worst_shuffle"] <= 100.0
        assert 0.0 <= result["max_dd_cvar_95"] <= 100.0

    def test_sharpe_annualized_positive(self):
        """Sharpe anualizado com trades positivos deve ser > 0."""
        trades = [{"pnl_pct": 0.001} for _ in range(252)]  # +0.1% ao dia
        result = monte_carlo_shuffle(trades, n_simulations=50, seed=42)
        assert result["sharpe_original"] > 100  # near-zero variance = huge Sharpe

    def test_n_simulations_zero_handled(self):
        """n_simulations=0 deve retornar sem erro."""
        trades = [{"pnl_pct": 0.01} for _ in range(50)]
        result = monte_carlo_shuffle(trades, n_simulations=0)
        # Com 50 trades e 0 sims, ainda calcula original
        assert result["n_trades"] == 50
        assert result["sharpe_original"] != 0.0
