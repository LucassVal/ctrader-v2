"""Harness S27: orc_vectorbt — compute_indicators + portfolio_stats"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.orc_vectorbt import compute_indicators, compute_portfolio_stats


def test_compute_indicators_returns_dict():
    """compute_indicators deve retornar dict vazio ou com indicadores."""
    # Testa sem dados (deve retornar vazio, nao crashar)
    result = compute_indicators({})
    assert isinstance(result, dict)


def test_compute_portfolio_stats_returns_dict():
    """compute_portfolio_stats sempre retorna dict (sem dados = status 'sem_dados')."""
    result = compute_portfolio_stats([])
    assert isinstance(result, dict)
    # Com lista vazia, deve retornar status sem_dados
    if result.get("status") == "sem_dados":
        return  # OK, esperado
    # Se tiver dados, verificar keys
    for k in ("sharpe", "max_drawdown", "profit_factor", "win_rate"):
        assert k in result, f"Key ausente: {k}"
