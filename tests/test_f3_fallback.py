"""T20-Harness: F3 — fallback mecanico funciona"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from f3_validacao.orc_validacao import _apply_hard_cap, _mechanical_fallback


def test_fallback_approve():
    v = _mechanical_fallback(90, "m5")
    assert v["decision"] == "APPROVE"
    assert v["adjustments"]["lot_multiplier"] == 0.5
    print("PASS: Fallback APPROVE para score alto")

def test_fallback_reject():
    v = _mechanical_fallback(60, "m15")
    assert v["decision"] == "REJECT"
    assert v["reason"] == "IA_TIMEOUT"
    print("PASS: Fallback REJECT para score baixo")

def test_hard_cap():
    v = {"decision": "APPROVE", "adjustments": {"timeout_min": 30}}
    v = _apply_hard_cap(v, "M_5")
    assert v["adjustments"]["timeout_min"] == 5, f"Timeout nao truncado: {v['adjustments']['timeout_min']}"  # M_5 max = 5 (80% de 15), f"Timeout nao truncado: {v['adjustments']['timeout_min']}"
    print("PASS: Hard cap M5=10")

if __name__ == "__main__":
    test_fallback_approve()
    test_fallback_reject()
    test_hard_cap()
