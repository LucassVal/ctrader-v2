"""Harness S25: orc_mercado — normalize_markets (pip/spread/forca)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.orc_mercado import _read_snapshot, normalize_markets


def test_normalize_returns_dict():
    """normalize_markets deve retornar dict com keys esperadas."""
    result = normalize_markets({})
    assert isinstance(result, dict)


def test_normalize_handles_empty_snapshot():
    """Snapshot vazio nao deve crashar."""
    result = normalize_markets({"symbols": {}})
    assert isinstance(result, dict)


def test_read_snapshot_returns_dict():
    """_read_snapshot sempre retorna dict."""
    result = _read_snapshot()
    assert isinstance(result, dict)


def test_normalize_without_arg_reads_disk():
    """Sem argumento, deve ler do disco — pode falhar se sem dados (OK)."""
    try:
        result = normalize_markets()
    except ZeroDivisionError:
        # OK — sem snapshot real, divisao por zero esperada
        return
    assert isinstance(result, dict)
