"""PROPOSITO: H2.1 — Harness DXY multi-par + score generico
SPEC: S3
ROADMAP: 2.5 + 2.6 — DXY com 3 majors, USDJPY invertido, fail-fast <20 barras.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from f1_analyzer.dxy_orc_analise import calculate_multi_dxy_score


def test_dxy_pesos_somam_um() -> None:
    """Pesos dos 3 majors somam ~1.0."""
    from f1_analyzer.dxy_orc_analise import DXY_WEIGHTS
    total = sum(DXY_WEIGHTS.values())
    assert abs(total - 1.0) < 0.01, f"Pesos somam {total}, esperado 1.0"


def test_dxy_multi_par_basico() -> None:
    """DXY multi-par retorna score entre 0-100 com dados sinteticos."""
    closes = pd.DataFrame({
        "EURUSD": [1.10, 1.11, 1.12] * 10,
        "USDJPY": [150.0, 149.0, 148.0] * 10,
        "GBPUSD": [1.30, 1.31, 1.32] * 10,
    })
    score = calculate_multi_dxy_score(closes)
    assert 0 <= score <= 100, f"Score fora do range: {score}"
    assert isinstance(score, (int, float))


def test_dxy_fail_fast_poucas_barras() -> None:
    """<20 barras LEVANTA erro (R-NO-SILENT-FAIL)."""
    closes = pd.DataFrame({"EURUSD": [1.10, 1.11, 1.12]})  # apenas 3 barras
    try:
        calculate_multi_dxy_score(closes)
        raise AssertionError("Deveria ter levantado ValueError para <20 barras")
    except ValueError:
        pass  # esperado


def test_usdjpy_invertido() -> None:
    """USDJPY sobe = dolar fortalecendo = DXY sobe. Sinal INVERTIDO no score."""
    # Cenario 1: EUR caindo, USDJPY subindo -> dolar FORTE -> score alto
    closes_forte = pd.DataFrame({
        "EURUSD": [1.105 - i * 0.0005 for i in range(30)],   # queda = dolar forte
        "USDJPY": [149.0 + i * 0.05 for i in range(30)],      # subida = dolar forte (INVERTIDO)
        "GBPUSD": [1.305 - i * 0.0003 for i in range(30)],
    })
    # Cenario 2: EUR subindo, USDJPY caindo -> dolar FRACO -> score baixo
    closes_fraco = pd.DataFrame({
        "EURUSD": [1.095 + i * 0.0005 for i in range(30)],
        "USDJPY": [152.0 - i * 0.05 for i in range(30)],
        "GBPUSD": [1.295 + i * 0.0003 for i in range(30)],
    })
    score_forte = calculate_multi_dxy_score(closes_forte)
    score_fraco = calculate_multi_dxy_score(closes_fraco)
    assert score_forte > score_fraco, f"Dolar forte={score_forte} deveria > dolar fraco={score_fraco}"
