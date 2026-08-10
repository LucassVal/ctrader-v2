"""
PROPOSITO: Health Check + Decay Detection
SPEC: S21
ROADMAP: 1.7
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

STATUS_DIR = Path(__file__).resolve().parent.parent / "status"
HEALTH_PATH = STATUS_DIR / "health.json"


def ensure_status_dir():
    STATUS_DIR.mkdir(parents=True, exist_ok=True)


def write_heartbeat(phase: str):
    """Escreve heartbeat da fase. Chamado a cada 5s por cada processo."""
    ensure_status_dir()
    heartbeat_file = STATUS_DIR / f"{phase}.heartbeat"
    heartbeat_file.write_text(datetime.now(UTC).isoformat())


def read_heartbeat(phase: str) -> float | None:
    """Le timestamp do heartbeat. Retorna None se arquivo nao existe."""
    heartbeat_file = STATUS_DIR / f"{phase}.heartbeat"
    if not heartbeat_file.exists():
        return None
    try:
        ts_str = heartbeat_file.read_text().strip()
        ts = datetime.fromisoformat(ts_str)
        return (datetime.now(UTC) - ts).total_seconds()
    except Exception:
        return None


def check_all_heartbeats(phases: list[str]) -> dict[str, str]:
    """Verifica todos os heartbeats. Retorna {phase: status}."""
    results = {}
    for phase in phases:
        age = read_heartbeat(phase)
        if age is None:
            results[phase] = "MISSING"
        elif age > 15:
            results[phase] = f"STALE ({age:.0f}s)"
        else:
            results[phase] = f"OK ({age:.0f}s)"
    return results


# ---------------------------------------------------------------------------
# decay detection
# ---------------------------------------------------------------------------


def collect_metrics() -> dict[str, Any]:
    """Coleta metricas de saude do sistema para deteccao de decay."""
    ensure_status_dir()
    metrics: dict[str, Any] = {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "phases": {},
    }

    # heartbeats
    for phase in ["f0", "f1", "f2", "f3", "f4", "f5"]:
        age = read_heartbeat(phase)
        metrics["phases"][phase] = {
            "heartbeat_age_s": round(age, 1) if age else None,
            "alive": age is not None and age < 15,
        }

    # ruff count (decay: se > 0, codigo esta degradando)
    try:
        import subprocess
        result = subprocess.run(
            ["ruff", "check", "--output-format", "json", "."],
            capture_output=True, text=True, timeout=10,
            cwd=str(Path(__file__).resolve().parent.parent),
        )
        if result.returncode == 0:
            metrics["ruff_errors"] = 0
        else:
            try:
                issues = json.loads(result.stdout)
                metrics["ruff_errors"] = len(issues) if isinstance(issues, list) else 0
            except json.JSONDecodeError:
                metrics["ruff_errors"] = -1  # erro ao parsear
    except Exception:
        metrics["ruff_errors"] = -1

    # GOD files (decay: arquivos > 200L que nao sao orquestradores)
    try:
        root = Path(__file__).resolve().parent.parent
        god_files = []
        for f in sorted(root.rglob("*.py")):
            # Exclusoes = so o que existe de fato (legado foi para 99_archive/ em 2026-07-23)
            if any(x in str(f) for x in ['ctrader-skills-official', '__pycache__',
                                          '.git', 'tests', 'node_modules']):
                continue
            if '_orc_' in f.name:
                continue  # orquestradores tem teto maior (350L)
            lines = len(f.read_text().split('\n'))
            if lines > 200:
                god_files.append(f"{f.relative_to(root)} ({lines}L)")
        metrics["god_files"] = god_files
        metrics["god_count"] = len(god_files)
    except Exception:
        metrics["god_files"] = []
        metrics["god_count"] = 0

    return metrics


def save_health_report():
    """Salva relatorio de saude em status/health.json."""
    metrics = collect_metrics()
    ensure_status_dir()
    with open(HEALTH_PATH, "w") as f:
        json.dump(metrics, f, indent=2, default=str)
    return metrics


def check_decay() -> list[str]:
    """Retorna lista de alertas de decay detectados."""
    alerts = []
    metrics = collect_metrics()

    if metrics.get("ruff_errors", 0) > 0:
        alerts.append(f"RUFF: {metrics['ruff_errors']} errors — codigo degradando")

    god_count = metrics.get("god_count", 0)
    if god_count > 0:
        alerts.append(f"GOD_FILES: {god_count} arquivos acima de 200L: {metrics.get('god_files', [])}")

    for phase, data in metrics.get("phases", {}).items():
        if not data.get("alive", False):
            alerts.append(f"PHASE_DOWN: {phase} sem heartbeat")

    return alerts
