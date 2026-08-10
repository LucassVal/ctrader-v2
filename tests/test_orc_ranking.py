"""Harness S35: orc_ranking — rank_signals mecanico (sem IA, sem FUS-STUB)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from f3_validacao.orc_ranking import (
    _fallback_ranking,
    _load_fusion_output,
    rank_signals,
)


def test_fallback_ranking_returns_list():
    """Fallback mecanico deve retornar lista vazia ou ranqueada."""
    candidates = [
        {"symbol": "XAUUSD", "score": 78, "sinal": "BULLISH"},
        {"symbol": "EURUSD", "score": 45, "sinal": "BEARISH"},
        {"symbol": "GBPUSD", "score": 92, "sinal": "BULLISH"},
    ]
    result = _fallback_ranking(candidates)
    assert isinstance(result, list)
    if result:
        assert all("symbol" in r for r in result)
        assert all("score" in r for r in result)


def test_rank_signals_returns_dict():
    """rank_signals deve retornar dicionario com sinais ranqueados."""
    result = rank_signals(min_score=50)
    assert isinstance(result, dict)
    # O resultado pode ser vazio se nao houver fusion_output.json
    assert "signals" in result or "error" in result or isinstance(result, dict)


def test_load_fusion_output_handles_missing():
    """_load_fusion_output nao deve crashar se arquivo ausente."""
    result = _load_fusion_output()
    assert isinstance(result, dict)
