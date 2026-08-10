"""test_backtest_simulator.py — Harness S30: validacao ponta a ponta do backtest 2 anos.

R-HARNESS: pytest tests/test_backtest_simulator.py -v
"""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

CTRADER = Path(__file__).resolve().parent.parent
SIMULATOR = CTRADER / "f0_collector" / "backtest_simulator.py"
DB_PATH = CTRADER / "status" / "backtest_trades.db"
PYTHON = sys.executable


def _run_simulator(fast=True):
    """Roda o simulator e retorna (exit_code, stdout)."""
    args = [PYTHON, str(SIMULATOR)]
    if fast:
        args.append("--fast")
    result = subprocess.run(args, capture_output=True, text=True, cwd=str(CTRADER), timeout=180)
    return result.returncode, result.stdout


@pytest.fixture(scope="module")
def simulator_ran():
    """Garante que o simulator --fast rodou uma vez por sessao de teste."""
    returncode, stdout = _run_simulator(fast=True)
    assert returncode == 0, f"Simulator falhou:\n{stdout}"
    return stdout


class TestBacktestSimulator:
    """Validacao do fluxo ponta a ponta."""

    def test_simulator_completes(self, simulator_ran):
        """O simulador --fast completa sem erro."""
        assert "[OK]" in simulator_ran
        assert "trades totais em" in simulator_ran

    def test_db_created(self, simulator_ran):
        """backtest_trades.db criado com trades validos."""
        assert DB_PATH.exists(), f"DB nao encontrado: {DB_PATH}"
        conn = sqlite3.connect(str(DB_PATH))
        count = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        conn.close()
        assert count >= 10000, f"Apenas {count} trades (esperado >= 10000)"

    def test_db_schema(self, simulator_ran):
        """Schema da tabela trades contem colunas obrigatorias."""
        conn = sqlite3.connect(str(DB_PATH))
        cols = {row[1] for row in conn.execute("PRAGMA table_info(trades)")}
        required = {"symbol", "timeframe", "side", "timestamp_utc", "pnl_net", "scores_json", "exit_price"}
        missing = required - cols
        conn.close()
        assert not missing, f"Colunas faltando: {missing}"

    def test_scores_json_format(self, simulator_ran):
        """scores_json tem o formato esperado (scores.final_adjusted)."""
        conn = sqlite3.connect(str(DB_PATH))
        row = conn.execute(
            "SELECT scores_json FROM trades WHERE scores_json IS NOT NULL LIMIT 1"
        ).fetchone()
        conn.close()
        assert row is not None, "Nenhum trade com scores_json"
        parsed = json.loads(row[0])
        assert "scores" in parsed, f"scores_json sem chave 'scores': {list(parsed.keys())}"
        assert "final_adjusted" in parsed["scores"], f"Sem final_adjusted: {parsed['scores']}"

    def test_performance_endpoint_returns_data(self, simulator_ran):
        """orc_metricas.simulation_performance_metrics(mode='backtest') retorna dados."""
        sys.path.insert(0, str(CTRADER))
        from utils.orc_metricas import simulation_performance_metrics

        result = simulation_performance_metrics(mode="backtest")
        assert result["total_trades"] > 0, "total_trades = 0"
        assert len(result["equity_curve"]) > 0, "equity_curve vazio"
        assert len(result["scatter"]) > 0, "scatter vazio"
        assert len(result["monthly"]) > 0, "monthly vazio"

        # PnL total deve ser positivo (estrategia com edge 2:1)
        total_pnl = result["equity_curve"][-1].get("Total", 0)
        assert total_pnl > 0, f"PnL total negativo: {total_pnl}"

    def test_all_symbols_present(self, simulator_ran):
        """Todos os 5 simbolos tem trades."""
        conn = sqlite3.connect(str(DB_PATH))
        symbols = {
            row[0]
            for row in conn.execute("SELECT DISTINCT symbol FROM trades").fetchall()
        }
        conn.close()
        expected = {"XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"}
        missing = expected - symbols
        assert not missing, f"Simbolos sem trades: {missing}"
