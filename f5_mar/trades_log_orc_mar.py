"""PROPOSITO: Trades Log — persistencia de decisoes + PnL no trades.db (satelite orc_mar).
SPEC: S5
ROADMAP: 5.0 — log de trades para MAR (Monitoramento, Ajuste, Replay).
FLOW:   F4.orc_execucao -> log_trade() -> trades.db -> orc_mar.rules_orc_mar (le pesos via PnL)
        orc_mar -> get_trades_today() -> calculo de performance diaria
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "trades.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def ensure_schema() -> None:
    """Cria tabelas trades + v_historical_candles no trades.db."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trace_id TEXT UNIQUE,
            timestamp_utc TEXT,
            symbol TEXT,
            timeframe TEXT,
            side TEXT,
            entry_price REAL,
            sl_initial REAL,
            tp_initial REAL,
            exit_price REAL,
            pnl_net REAL,
            exit_reason TEXT,
            duration_seconds REAL,
            trail_activated INTEGER DEFAULT 0,
            be_locked INTEGER DEFAULT 0,
            degrau0_triggered INTEGER DEFAULT 0,
            volume REAL,
            scores_json TEXT,
            verdict_json TEXT,
            execution_json TEXT,
            decision TEXT,
            rejection_reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS v_historical_candles (
            timestamp_utc TEXT, symbol TEXT,
            open REAL, high REAL, low REAL, close REAL,
            tick_volume REAL, spread REAL
        );
        CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(timestamp_utc);
        CREATE INDEX IF NOT EXISTS idx_trades_decision ON trades(decision);
    """)
    conn.commit()
    conn.close()
    logger.info("Schema trades.db OK")


def log_trade(
    trace_id: str, symbol: str, timeframe: str,
    scores_json: dict, verdict_json: dict,
    execution_json: dict | None = None,
    decision: str = "REJECT", rejection_reason: str | None = None,
) -> None:
    """Persiste decisao de trade no trades.db (chamado pelo F4.orc_execucao)."""
    conn = _get_conn()
    conn.execute("""
        INSERT OR REPLACE INTO trades
        (trace_id, timestamp_utc, symbol, timeframe, scores_json,
         verdict_json, execution_json, decision, rejection_reason, pnl_net, exit_reason)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        trace_id, datetime.now(UTC).isoformat(), symbol, timeframe,
        json.dumps(scores_json, sort_keys=True) if isinstance(scores_json, dict) else str(scores_json),
        json.dumps(verdict_json, sort_keys=True) if isinstance(verdict_json, dict) else str(verdict_json),
        json.dumps(execution_json, sort_keys=True) if execution_json and isinstance(execution_json, dict) else None,
        decision, rejection_reason,
        execution_json.get("pnl_net") if execution_json else None,
        execution_json.get("exit_reason") if execution_json else None,
    ))
    conn.commit()
    conn.close()


def get_trades_today() -> list[tuple]:
    """Consulta trades do dia (usado pelo orc_mar para performance diaria)."""
    conn = _get_conn()
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    rows = conn.execute(
        "SELECT scores_json, decision, pnl_net FROM trades WHERE date(timestamp_utc)=?",
        (today,),
    ).fetchall()
    conn.close()
    return rows


def log_rotation() -> None:
    """Remove trades com mais de 90 dias."""
    conn = _get_conn()
    conn.execute("DELETE FROM trades WHERE created_at < date('now', '-90 days')")
    conn.execute("VACUUM")
    conn.close()
    logger.info("Log rotation concluida.")
