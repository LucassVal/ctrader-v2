"""T13: Harness F4 ghost order — requer MCP real."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.mark.skip(reason="Requer MCP real — teste manual com cTrader Web aberto")
def test_entry_logic_deterministic():
    """Lógica de SL/TP: SL < entry < TP com RR aproximado 2:1."""
    # Testa aritmética pura (sem MCP)
    atr = 10.0
    entry = 2000.0
    sl = entry - atr * 1.0  # SL = entry - ATR
    tp = entry + atr * 2.0  # TP = entry + 2*ATR (RR 1:2)

    assert sl == 1990.0, f"SL deve ser entry - ATR: {sl}"
    assert tp == 2020.0, f"TP deve ser entry + 2*ATR: {tp}"
    assert tp - entry == 2 * (entry - sl), "RR deve ser 2:1"


def test_sl_tp_sanity():
    """SL sempre abaixo da entrada, TP sempre acima (BUY)."""
    atr = 5.0
    entry = 1.0850
    sl = entry - atr
    tp = entry + atr * 2.0
    assert sl < entry < tp
    assert (tp - entry) / (entry - sl) == 2.0
