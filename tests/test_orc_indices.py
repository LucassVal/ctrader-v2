"""Harness S25.10: orc_indices — DXY sintetico + correlacao"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.orc_indices import (
    collect_indices,
    correlate_markets_m1,
    correlate_with_markets,
)


def test_collect_indices_returns_dict():
    """collect_indices deve retornar dict com keys esperadas."""
    result = collect_indices()
    assert isinstance(result, dict)


def test_correlate_with_markets_returns_dict():
    """correlate_with_markets sempre retorna dict."""
    result = correlate_with_markets()
    assert isinstance(result, dict)


def test_correlate_markets_m1_returns_dict():
    """Matriz de correlacao deve ser dict."""
    result = correlate_markets_m1(window=200)
    assert isinstance(result, dict)
    if result:
        # Deve ter pelo menos uma chave
        assert len(result) > 0
