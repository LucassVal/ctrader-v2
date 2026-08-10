"""PROPOSITO: JSON Log — structured metrics log em JSON para pipeline de analise (satelite orc_metricas).
SPEC: S20
ROADMAP: D.10 — substitui logs dispersos (trail_viewer, log_trade) por log centralizado.
FLOW:   orc_execucao -> log_trade_json() -> status/metrics.json
        orc_metricas -> collect_all() -> le metrics.json + trades.db -> /api/ctrader/metrics
        vectorbt -> le metrics.json -> replay/calibracao -> realimenta F2
"""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

STATUS_DIR = Path(__file__).resolve().parent.parent / "status"
METRICS_JSON = STATUS_DIR / "metrics.json"
DB_PATH = Path(__file__).resolve().parent.parent / "trades.db"


# ═══════════════════════════════════════════
# JSON structured log
# ═══════════════════════════════════════════

def log_metrics_json(phase: str, data: dict[str, Any]) -> None:
    """Escreve metricas de uma fase no metrics.json (upsert por fase).

    Estrutura: {"f0_coleta": {...}, "f4_execucao": {...}, "timestamp": "..."}
    """
    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if METRICS_JSON.exists():
        try:
            existing = json.loads(METRICS_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    existing[phase] = data
    existing["timestamp"] = datetime.now(UTC).isoformat()
    existing["updated_at"] = time.time()

    METRICS_JSON.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")


def read_metrics_json() -> dict[str, Any]:
    """Le o metrics.json completo."""
    if not METRICS_JSON.exists():
        return {"status": "offline", "phases": {}}
    try:
        return json.loads(METRICS_JSON.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"status": "corrupt", "phases": {}}


# ═══════════════════════════════════════════
# Trail log (dashboard) — movido de trail_viewer
# ═══════════════════════════════════════════

def get_trail_log() -> dict[str, Any]:
    """Log em tempo real do trail de ordens ativas (dashboard).

    Migrado de trail_viewer_orc_ordens -> orc_metricas.
    Le do trades.db em vez do vector_db legado.
    """
    try:
        conn = sqlite3.connect(str(DB_PATH))
        cur = conn.execute(
            "SELECT order_id, position_id, symbol, side, entry_price, "
            "sl_initial, tp_initial, exit_price, pnl_net, exit_reason, "
            "trail_activated, be_locked, degrau0_triggered "
            "FROM trades WHERE exit_price IS NULL OR exit_reason IS NULL "
            "ORDER BY timestamp_utc DESC LIMIT 20"
        )
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
        conn.close()

        return {
            "active_orders": len(rows),
            "trail_log": rows,
            "source": "trades.db",
        }
    except Exception as e:
        return {"active_orders": 0, "trail_log": [], "error": str(e)[:200], "source": "trades.db"}


# ═══════════════════════════════════════════
# Log de trade (escrita) — movido de log_trade_orc_execucao
# ═══════════════════════════════════════════

def log_trade_json(log: dict[str, Any]) -> None:
    """Persiste trade concluido: trades.db + metrics.json.

    Substitui log_trade_orc_execucao.log_trade().
    Schema unificado com trades_log_orc_mar (F5).
    """
    # 1. Garante schema e persiste no trades.db
    try:
        from f5_mar.trades_log_orc_mar import ensure_schema
        ensure_schema()
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""
            INSERT INTO trades (trace_id, timestamp_utc, symbol, side,
                entry_price, volume, sl_initial, tp_initial, exit_price,
                exit_reason, pnl_net, duration_seconds, trail_activated,
                be_locked, degrau0_triggered)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log["trace_id"], datetime.now(UTC).isoformat(),
            log.get("symbol_id", log.get("symbol")), log.get("direction", log.get("side")),
            log["entry_price"], log.get("volume", 0),
            log["sl_initial"], log["tp_initial"],
            log["exit_price"], log["exit_reason"],
            log["pnl_net"], log.get("duration_seconds", 0),
            int(log.get("trail_activated", False)),
            int(log.get("be_locked", False)),
            int(log.get("degrau0_triggered", False)),
        ))
        conn.commit()
        conn.close()
    except Exception:
        pass  # DB offline — nao bloqueia

    # 2. Atualiza metrics.json
    log_metrics_json("f4_execucao", {
        "last_trade": {
            "symbol": log.get("symbol_id"),
            "pnl": log.get("pnl_net"),
            "exit_reason": log.get("exit_reason"),
            "duration_s": log.get("duration_seconds"),
            "trail_activated": bool(log.get("trail_activated")),
        },
        "logged_at": datetime.now(UTC).isoformat(),
    })
