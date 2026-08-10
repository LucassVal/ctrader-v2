"""
PROPOSITO: Supervisao do processo F0 (status/start/stop/restart) para o dashboard.
SPEC: S21 (satelite de orc_dashboard)
ROADMAP: 1.8 -- controle de F0 sem cacada manual de PID. F0 se auto-registra em
status/f0.pid (orc_coleta.py); este modulo so le/gerencia esse arquivo via psutil,
o que funciona mesmo com elevacao (o processo que inicia o filho consegue
sempre encerra-lo, independente de quem chamou start()).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import psutil

from utils.logger import get_logger

logger = get_logger(__name__, "F0-SUP")

_APP_ROOT = Path(__file__).resolve().parent.parent
_PID_PATH = _APP_ROOT / "status" / "f0.pid"
_SNAPSHOT_PATH = _APP_ROOT / "status" / "snapshot.json"
_F0_CMD_MARKER = "f0_collector.orc_coleta"
_SNAPSHOT_STALE_S = 30


def _read_pid() -> int | None:
    if not _PID_PATH.exists():
        return None
    try:
        return int(_PID_PATH.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def _is_f0_process(pid: int) -> bool:
    """Confirma que o PID e realmente o F0 (evita falso-positivo por reuso de PID)."""
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and _F0_CMD_MARKER in " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def f0_status() -> dict[str, Any]:
    pid = _read_pid()
    alive = pid is not None and _is_f0_process(pid)
    uptime_s: float | None = None
    if alive:
        try:
            uptime_s = round(time.time() - psutil.Process(pid).create_time(), 1)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            alive = False

    snapshot_age_s: float | None = None
    if _SNAPSHOT_PATH.exists():
        snapshot_age_s = round(time.time() - _SNAPSHOT_PATH.stat().st_mtime, 1)

    return {
        "running": alive,
        "pid": pid if alive else None,
        "uptime_s": uptime_s,
        "snapshot_age_s": snapshot_age_s,
        "snapshot_stale": snapshot_age_s is None or snapshot_age_s > _SNAPSHOT_STALE_S,
    }


def f0_start() -> dict[str, Any]:
    status = f0_status()
    if status["running"]:
        return {"started": False, "reason": "F0 ja esta rodando", **status}

    # A9 (INDEX.md/harness.md): pre-flight obrigatorio antes do F0 subir.
    harness = subprocess.run(
        [sys.executable, str(_APP_ROOT / "tests" / "harness_boot.py")],
        capture_output=True, text=True, timeout=30, cwd=str(_APP_ROOT),
    )
    if harness.returncode != 0:
        logger.error("harness_boot FALHOU -- F0 nao iniciado (A9)")
        return {"started": False, "reason": "harness_boot FALHOU (A9)",
                "detail": harness.stdout[-500:]}

    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [sys.executable, "-X", "utf8", "-m", "f0_collector.orc_coleta", "--hours", "0"],
        cwd=str(_APP_ROOT), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    # F0 se auto-registra em status/f0.pid logo no inicio de main() -- aguarda curto.
    for _ in range(20):
        time.sleep(0.25)
        if _read_pid() is not None:
            break
    logger.info("F0 iniciado via dashboard: pid=%s", _read_pid())
    return {"started": True, "pid": _read_pid()}


def f0_stop() -> dict[str, Any]:
    pid = _read_pid()
    if pid is None or not _is_f0_process(pid):
        _PID_PATH.unlink(missing_ok=True)
        return {"stopped": False, "reason": "F0 nao estava rodando"}
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
    logger.info("F0 encerrado via dashboard: pid=%s", pid)
    return {"stopped": True, "pid": pid}


def f0_restart() -> dict[str, Any]:
    stop_result = f0_stop()
    time.sleep(1)
    start_result = f0_start()
    return {"stop": stop_result, "start": start_result}
