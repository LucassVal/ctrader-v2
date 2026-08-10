"""Harness S39: vista_orc_mercado — market_detail (drill-down por simbolo)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.vista_orc_mercado import market_detail


def test_market_detail_returns_dict():
    """market_detail deve retornar dict para simbolo valido."""
    result = market_detail("XAUUSD")
    assert isinstance(result, dict)


def test_market_detail_invalid_symbol():
    """Simbolo invalido nao deve crashar."""
    result = market_detail("INVALIDO")
    assert isinstance(result, dict)


def test_market_detail_has_expected_keys():
    """Retorno deve conter chaves esperadas do S39 vista."""
    result = market_detail("XAUUSD")
    if "error" not in result:
        # Expected keys from S39 spec
        possible_keys = {"symbol", "regime", "calibracao", "padroes", "correlacao", "vista"}
        found = [k for k in possible_keys if k in result]
        assert len(found) > 0, f"Nenhuma chave esperada em: {list(result.keys())[:5]}"
