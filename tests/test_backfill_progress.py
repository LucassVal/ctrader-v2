"""PROPOSITO: Harness S31-PROG — progresso do backfill wireado (metricas + dashboard)
SPEC: S31
ROADMAP: S31-PROG — backfill_progress.json alimenta /backfill/status, S33 e orc_metricas.
Read-only em producao: escritas apenas em tmp_path via monkeypatch (G19).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from f0_collector import backfill_orc_coleta as bf
from utils import backfill_supervisor_orc_dashboard as sup


def test_progress_contrato_completo(tmp_path, monkeypatch) -> None:
    """_progress_start + _progress_tick gravam o contrato S31-PROG."""
    fake = tmp_path / "backfill_progress.json"
    monkeypatch.setattr(bf, "PROGRESS_PATH", fake)

    import time
    t0 = time.monotonic()
    bf._progress_start("gaps")
    bf._PROGRESS["symbols"]["XAUUSD"]["windows_total"] = 10
    bf._PROGRESS["symbols"]["XAUUSD"]["windows_done"] = 4
    bf._PROGRESS["symbols"]["XAUUSD"]["bars"] = 8000
    bf._progress_tick(t0)

    d = json.loads(fake.read_text(encoding="utf-8"))
    for campo in ("state", "mode", "started_at", "updated_at", "current_symbol",
                  "symbols", "totals", "elapsed_s", "eta_s", "last_error"):
        assert campo in d, f"campo ausente: {campo}"
    assert d["state"] == "running"
    assert d["totals"] == {"windows_done": 4, "windows_total": 10, "bars": 8000, "pct": 40.0}
    assert d["symbols"]["XAUUSD"]["state"] == "pending"
    assert len(d["symbols"]) == 7  # 5 ativos + 2 indices (v2.1)


def test_progress_eta_estimado(tmp_path, monkeypatch) -> None:
    """ETA aparece apos a 1a janela concluida e zera sem janelas."""
    fake = tmp_path / "backfill_progress.json"
    monkeypatch.setattr(bf, "PROGRESS_PATH", fake)
    bf._progress_start("full")
    d = json.loads(fake.read_text(encoding="utf-8"))
    assert d["eta_s"] is None  # sem janelas concluidas ainda


def test_supervisor_status_le_progresso(tmp_path, monkeypatch) -> None:
    """backfill_status expoe progresso + coverage sem tocar MCP (read-only)."""
    fake = tmp_path / "backfill_progress.json"
    fake.write_text(json.dumps({
        "state": "running", "mode": "gaps", "current_symbol": "XAUUSD",
        "symbols": {}, "totals": {"windows_done": 1, "windows_total": 5, "bars": 100, "pct": 20.0},
        "elapsed_s": 10.0, "eta_s": 40.0, "last_error": None,
        "started_at": "2026-07-30T00:00:00+00:00", "updated_at": "2026-07-30T00:00:01+00:00",
    }), encoding="utf-8")
    monkeypatch.setattr(sup, "_PROGRESS_PATH", fake)
    monkeypatch.setattr(sup, "_PID_PATH", tmp_path / "backfill.pid")

    st = sup.backfill_status()
    assert st["running"] is False  # sem pid = processo nao vivo
    assert st["progress"]["totals"]["pct"] == 20.0
    assert st["progress"]["current_symbol"] == "XAUUSD"
    assert "coverage_pct" in st


def test_supervisor_start_recusa_modo_invalido(tmp_path, monkeypatch) -> None:
    """backfill_start valida modo antes de spawnar qualquer processo."""
    monkeypatch.setattr(sup, "_PID_PATH", tmp_path / "backfill.pid")
    monkeypatch.setattr(sup, "_PROGRESS_PATH", tmp_path / "nada.json")
    r = sup.backfill_start("turbo")
    assert r["started"] is False
    assert "modo invalido" in r["reason"]


def test_metricas_backfill_secao() -> None:
    """orc_metricas.backfill_metrics devolve a secao que alimenta o dashboard."""
    from utils.orc_metricas import backfill_metrics
    m = backfill_metrics()
    for campo in ("running", "state", "pct", "bars", "windows",
                  "eta_min", "current_symbol", "coverage_min_pct"):
        assert campo in m, f"campo ausente: {campo}"
