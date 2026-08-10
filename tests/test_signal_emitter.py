"""PROPOSITO: test_signal_emitter.py — Harness S36 MODO PRESENTE (emissor).
SPEC: S36 (orc_calibracao.md) + S20 v2.2 (REGRA-MET) + S27 v3.0 (MTF)
G19: SCORE_LIVE / EMITTER_STATE em tmp_path; combined_score_mtf mockado
— zero escrita em producao, zero MCP.
"""

from __future__ import annotations

import json

from utils import signal_emitter_orc_score as emit


def _fake_score_mtf(symbol: str) -> dict:
    """Mock multi-TF score (S27 v3.0). adjusted_confidence em 0-1, codigo multiplica por 100."""
    return {
        "M1": {
            "status": "ok", "signal": "BULLISH",
            "adjusted_confidence": 0.573, "score": 57.3,
            "quality_f1": 0.3, "pattern_confidence": 0.7, "coverage_pct": 98.5,
        },
        "M5": {"status": "ok", "signal": "BULLISH", "score": 62.1},
        "M15": {"status": "ok", "signal": "NEUTRAL", "score": 45.0},
    }


def _setup(monkeypatch, tmp_path):
    monkeypatch.setattr(emit, "SCORE_LIVE", tmp_path / "score_live.json")
    monkeypatch.setattr(emit, "EMITTER_STATE", tmp_path / "emitter_state.json")
    captured: list[list[dict]] = []

    import utils.orc_calibracao as cal
    monkeypatch.setattr(cal, "append_signals", lambda rows: captured.append(rows) or len(rows))

    # Mock combined_score_mtf (S27 v3.0 — multi-TF)
    import f2_fusao.orc_score as orc_score
    monkeypatch.setattr(orc_score, "combined_score_mtf", _fake_score_mtf)
    return captured


def test_emite_e_grava_score_live(monkeypatch, tmp_path):
    captured = _setup(monkeypatch, tmp_path)
    r = emit.emit_once(symbols=["EURUSD"])
    live = json.loads((tmp_path / "score_live.json").read_text(encoding="utf-8"))

    # Multi-TF structure: {symbol: {M1: {online, sinal, score}, M5: {...}, M15: {...}}}
    eur = live["symbols"]["EURUSD"]
    assert eur["M1"]["online"] is True
    assert eur["M1"]["sinal"] == "BULLISH"
    assert eur["M1"]["score"] == 57.3
    assert eur["M5"]["sinal"] == "BULLISH"
    assert eur["M15"]["online"] is True

    assert len(captured) == 1 and len(captured[0]) == 1
    row = captured[0][0]
    assert row["origem"] == "live" and row["sinal"] == "BULLISH"
    assert r["signals_added"] == 1


def test_anti_flood_dedup(monkeypatch, tmp_path):
    """Mesmo (sinal, faixa) em <15 min nao gera nova linha."""
    captured = _setup(monkeypatch, tmp_path)
    emit.emit_once(symbols=["EURUSD"])
    r2 = emit.emit_once(symbols=["EURUSD"])
    assert len(captured) == 1          # so o primeiro ciclo logou
    assert r2["signals_added"] == 0


def test_neutral_nao_loga(monkeypatch, tmp_path):
    captured = _setup(monkeypatch, tmp_path)

    import f2_fusao.orc_score as orc_score
    def _fake_neutral(symbol: str) -> dict:
        return {
            "M1": {"status": "ok", "signal": "NEUTRAL", "score": 0},
            "M5": {"status": "ok", "signal": "NEUTRAL", "score": 0},
            "M15": {"status": "ok", "signal": "NEUTRAL", "score": 0},
        }
    monkeypatch.setattr(orc_score, "combined_score_mtf", _fake_neutral)
    r = emit.emit_once(symbols=["EURUSD"])
    assert r["signals_added"] == 0
    assert len(captured) == 0
