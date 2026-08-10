"""PROPOSITO: Harness S33 — validador por fase sempre ativo (orc_health_fases)
SPEC: S33
ROADMAP: S33 — sub-aba "Saude" de cada aba mestra + overview fases x harness.
Read-only: check_fases() nao escreve em disco (G19-compatible). Sem mock/stub.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.orc_health_fases import _FASES, check_fases


def test_check_fases_cobre_todas_as_fases() -> None:
    """check_fases retorna as 9 fases do pipeline (F0..F5 + vector + S29-S32)."""
    r = check_fases()
    esperadas = {
        "f0_coleta", "f1_f2_analise", "f3_ia", "f4_execucao", "f5_mar",
        "vector_s27", "s29_s30", "s31_backfill", "s32_score",
    }
    assert set(r["fases"].keys()) == esperadas, f"Fases: {set(r['fases'].keys())}"
    assert r["fases_ok"].endswith(f"/{len(esperadas)}")
    assert "gerado_em" in r


def test_check_fases_contrato_por_fase() -> None:
    """Cada fase tem ok (bool), checks (lista de {nome, ok, detalhe}) e resumo."""
    r = check_fases()
    for fase_id, fase in r["fases"].items():
        assert isinstance(fase["ok"], bool), fase_id
        assert isinstance(fase["checks"], list) and fase["checks"], fase_id
        for c in fase["checks"]:
            assert set(c.keys()) == {"nome", "ok", "detalhe"}, f"{fase_id}: {c}"
            assert isinstance(c["ok"], bool), f"{fase_id}.{c['nome']}"
        assert fase["resumo"].endswith("checks OK"), fase_id


def test_check_fases_filtro_somente() -> None:
    """somente=['f0_coleta'] devolve so aquela fase (uso pelas sub-abas)."""
    r = check_fases(somente=["f0_coleta"])
    assert set(r["fases"].keys()) == {"f0_coleta"}


def test_check_fases_nunca_levanta_excecao() -> None:
    """Fase com erro interno vira check falho, nao excecao — dashboard nao quebra."""
    def _boom():
        raise RuntimeError("falha proposital")

    original = _FASES["f0_coleta"]
    _FASES["f0_coleta"] = _boom
    try:
        r = check_fases(somente=["f0_coleta"])
    finally:
        _FASES["f0_coleta"] = original
    fase = r["fases"]["f0_coleta"]
    assert fase["ok"] is False
    assert "falha proposital" in fase["checks"][0]["detalhe"]


def test_vector_s27_ruse_orc_metricas() -> None:
    """vector_s27 reporta indicators_count por simbolo (R-USE orc_metricas)."""
    r = check_fases(somente=["vector_s27"])
    checks = r["fases"]["vector_s27"]["checks"]
    assert len(checks) == 5, f"{len(checks)} checks (esperado 1 por simbolo)"
    for c in checks:
        assert "indicadores" in c["nome"]
