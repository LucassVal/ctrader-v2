"""Harness S30-VBT: orc_vbt_portfolio — run_vbt_portfolio (VBT Portfolio.from_signals)

Nota: run_vbt_portfolio tem numba JIT (30s+), testamos apenas a interface.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_module_imports():
    """Modulo deve importar sem crash."""
    from utils.orc_vbt_portfolio import run_all_vbt, run_vbt_portfolio
    assert callable(run_vbt_portfolio)
    assert callable(run_all_vbt)


def test_compute_signals_returns_arrays():
    """Funcao interna de sinais deve retornar arrays booleanos."""
    import numpy as np

    from utils.orc_vbt_portfolio import _compute_signals
    close = np.ones(200) * 100.0
    close[50:100] = 90.0  # simulando queda
    entries, exits = _compute_signals(close)
    assert isinstance(entries, np.ndarray)
    assert isinstance(exits, np.ndarray)
    assert entries.dtype == bool
    assert exits.dtype == bool
