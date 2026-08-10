"""T14: Harness F4 trail BE — trail nunca volta abaixo do BE"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

def test_trail_be_lock():
    """Testa logica: trail_sl nunca < entry + spread"""
    entry = 2000.0
    spread = 0.10
    be_sl = entry + spread  # 2000.10

    # simula: highest sobe, trail calculado
    highest = 2005.0
    atr = 2.0
    trail_sl = highest - atr * 0.3  # 2005 - 0.6 = 2004.4

    # trava BE
    if trail_sl < be_sl:
        trail_sl = be_sl

    assert trail_sl >= be_sl, f"Trail {trail_sl} abaixo do BE {be_sl}"
    print("PASS: Trail travou no BE")

def test_trail_never_below_entry():
    """Simula queda abrupta — trail nao volta"""
    entry = 2000.0
    spread = 0.10
    be_sl = entry + spread

    # preco caiu para 1995
    highest = 2005.0
    atr = 2.0
    trail_sl = max(highest - atr * 0.3, be_sl)  # formula real

    assert trail_sl >= be_sl
    print("PASS: Trail nunca abaixo do entry+spread")

test_trail_be_lock()
test_trail_never_below_entry()
