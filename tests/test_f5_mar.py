"""T23: Harness F5 — pesos convergem"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from f5_mar.rules_orc_mar import DEFAULT_WEIGHTS, WEIGHT_UPDATE_RATE


def test_weights_converge():
    """Simula 4 dias de calibracao."""
    w = dict(DEFAULT_WEIGHTS)
    ideal = {"macro": 0.20, "volatilidade": 0.40, "tecnico": 0.40}
    for _day in range(4):
        for k in w:
            w[k] = w[k] * (1 - WEIGHT_UPDATE_RATE) + ideal[k] * WEIGHT_UPDATE_RATE
    # apos 4 dias, pesos devem estar proximos do ideal
    for k in w:
        assert abs(w[k] - ideal[k]) < 0.15, f"{k}: {w[k]} longe de {ideal[k]}"
    print(f"PASS: Pesos convergiram em 4 dias: {w}")

test_weights_converge()
