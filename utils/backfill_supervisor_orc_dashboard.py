"""
PROPOSITO: Supervisao do processo Backfill (status/start/stop) para o dashboard.
SPEC: S31 (satelite de orc_dashboard)
ROADMAP: S31-PROG — dispara/observa o backfill 2 anos sem cacada de PID.
O backfill (f0_collector/backfill_orc_coleta.py) e o UNICO ponto MCP do fluxo
S31 (R-NO-MCP-BYPASS): este modulo NUNCA fala MCP — so spawna o processo e le
status/backfill_progress.json + status/backfill.pid + status/gap_report.json.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil

from utils.logger import get_logger

logger = get_logger(__name__, "BF-SUP")

_APP_ROOT = Path(__file__).resolve().parent.parent
_PID_PATH = _APP_ROOT / "status" / "backfill.pid"
_PROGRESS_PATH = _APP_ROOT / "status" / "backfill_progress.json"
_CMD_MARKER = "backfill_orc_coleta"


def _read_pid() -> int | None:
    try:
        return int(_PID_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _is_backfill_process(pid: int) -> bool:
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and _CMD_MARKER in " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def read_progress() -> dict[str, Any]:
    """Le o contrato de progresso (S31-PROG). {} se nunca rodou."""
    try:
        if _PROGRESS_PATH.exists():
            return json.loads(_PROGRESS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("backfill_progress ilegivel: %s", e)
    return {}


def backfill_status() -> dict[str, Any]:
    """Estado completo: processo vivo? + progresso + cobertura 2 anos (G23)."""
    pid = _read_pid()
    alive = pid is not None and _is_backfill_process(pid)

    progress = read_progress()
    progress_age_s: float | None = None
    if _PROGRESS_PATH.exists():
        progress_age_s = round(time.time() - _PROGRESS_PATH.stat().st_mtime, 1)

    from utils.orc_metricas import _read_gap_coverage
    coverage = _read_gap_coverage()

    return {
        "running": alive,
        "pid": pid if alive else None,
        "progress": progress or None,
        "progress_age_s": progress_age_s,
        "coverage_pct": coverage,
        "coverage_min_pct": round(min(coverage.values()), 1) if coverage else 0.0,
    }


def backfill_start(mode: str = "gaps") -> dict[str, Any]:
    """Dispara o backfill como subprocesso independente (sobrevive a restart da API)."""
    status = backfill_status()
    if status["running"]:
        return {"started": False, "reason": "backfill ja esta rodando",
                "pid": status["pid"]}
    if mode not in ("gaps", "full"):
        return {"started": False, "reason": f"modo invalido: {mode} (use gaps|full)"}

    args = [sys.executable, "-X", "utf8",
            str(_APP_ROOT / "f0_collector" / "backfill_orc_coleta.py")]
    if mode == "gaps":
        args.append("--gaps")

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    proc = subprocess.Popen(
        args, cwd=str(_APP_ROOT),
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    # O script se auto-registra em status/backfill.pid; fallback: grava o Popen.pid.
    time.sleep(1.0)
    if _read_pid() is None and proc.poll() is None:
        _PID_PATH.write_text(str(proc.pid), encoding="utf-8")
    logger.info("Backfill iniciado via dashboard: mode=%s pid=%s", mode, _read_pid() or proc.pid)
    return {"started": True, "mode": mode, "pid": _read_pid() or proc.pid}


def backfill_stop() -> dict[str, Any]:
    pid = _read_pid()
    if pid is None or not _is_backfill_process(pid):
        _PID_PATH.unlink(missing_ok=True)
        return {"stopped": False, "reason": "backfill nao estava rodando"}
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except psutil.TimeoutExpired:
            proc.kill()
    except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
        return {"stopped": False, "reason": str(e)}
    _PID_PATH.unlink(missing_ok=True)
    logger.info("Backfill encerrado via dashboard: pid=%s", pid)
    return {"stopped": True, "pid": pid}
