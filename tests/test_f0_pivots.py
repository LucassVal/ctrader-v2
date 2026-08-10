"""PROPOSITO: Harness 1.4 — Pivots R1/R2/S1/S2 do D_1 anterior
SPEC: S5.1
ROADMAP: 1.4 — Filtro/alvo de TP para sniper, NAO componente de score.
Valores conhecidos para validacao deterministica.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from f1_analyzer.micro_orc_analise import calc_pivots


def test_pivots_known_values() -> None:
    """P=(H+L+C)/3. Valores conhecidos de uma barra real."""
    bar = {"high": 1.1050, "low": 1.1000, "close": 1.1025}
    pivots = calc_pivots(bar)
    p_expected = (1.1050 + 1.1000 + 1.1025) / 3
    assert abs(pivots["P"] - p_expected) < 0.0001
    assert abs(pivots["R1"] - 1.1050) < 0.0001  # 2*P - L
    assert abs(pivots["S1"] - 1.1000) < 0.0001  # 2*P - H
    assert abs(pivots["R2"] - 1.1075) < 0.0001  # P + (H-L)
    assert abs(pivots["S2"] - 1.0975) < 0.0001  # P - (H-L)


def test_pivots_all_fields() -> None:
    """Retorna dict com P, R1, R2, S1, S2."""
    bar = {"high": 2000.0, "low": 1990.0, "close": 1995.0}
    pivots = calc_pivots(bar)
    for field in ("P", "R1", "R2", "S1", "S2"):
        assert field in pivots, f"Campo ausente: {field}"
        assert isinstance(pivots[field], (int, float)), f"{field} nao e numero"


def test_pivots_r1_above_p() -> None:
    """R1 > P (resistencia acima do pivot)."""
    bar = {"high": 100.0, "low": 90.0, "close": 95.0}
    pivots = calc_pivots(bar)
    assert pivots["R1"] > pivots["P"], f"R1={pivots['R1']} <= P={pivots['P']}"
    assert pivots["R2"] > pivots["R1"], f"R2={pivots['R2']} <= R1={pivots['R1']}"
    assert pivots["S1"] < pivots["P"], f"S1={pivots['S1']} >= P={pivots['P']}"
    assert pivots["S2"] < pivots["S1"], f"S2={pivots['S2']} >= S1={pivots['S1']}"
