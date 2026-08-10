"""PROPOSITO: Banco SQLite do Vector (legado)
SPEC: S18
ROADMAP: 0.9
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

VECTOR_DIR = Path(__file__).resolve().parent
DB_PATH = VECTOR_DIR / "vector.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS vector_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp REAL NOT NULL,
    spotter_score REAL DEFAULT 0,
    sniper_score REAL DEFAULT 0,
    fusion_score REAL DEFAULT 0,
    signal TEXT DEFAULT 'NEUTRAL',
    confidence REAL DEFAULT 0.0,
    payload_json TEXT DEFAULT '{}',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vector_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    signal_id INTEGER REFERENCES vector_signals(id),
    order_id TEXT,
    position_id TEXT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    volume REAL DEFAULT 0,
    entry_price REAL DEFAULT 0,
    sl REAL DEFAULT 0,
    tp REAL DEFAULT 0,
    status TEXT DEFAULT 'PENDING',
    pnl REAL DEFAULT 0,
    exit_reason TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_signals_trace ON vector_signals(trace_id);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON vector_signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_ts ON vector_signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_orders_trace ON vector_orders(trace_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON vector_orders(status);
"""


def init_db() -> None:
    """Inicializa o banco (idempotente)."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def save_signal(
    trace_id: str, symbol: str, timestamp: float,
    spotter_score: float, sniper_score: float, fusion_score: float,
    signal: str, confidence: float, payload: dict[str, Any],
) -> int:
    """Grava sinal do Vector e retorna ID."""
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO vector_signals
               (trace_id, symbol, timestamp, spotter_score, sniper_score,
                fusion_score, signal, confidence, payload_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trace_id, symbol, timestamp, spotter_score, sniper_score,
             fusion_score, signal, confidence, json.dumps(payload)),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def save_order(
    trace_id: str, signal_id: int, order_id: str, position_id: str,
    symbol: str, side: str, volume: float,
    entry_price: float, sl: float, tp: float, status: str = "PENDING",
) -> int:
    """Grava ordem executada."""
    conn = _connect()
    try:
        cur = conn.execute(
            """INSERT INTO vector_orders
               (trace_id, signal_id, order_id, position_id, symbol, side,
                volume, entry_price, sl, tp, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (trace_id, signal_id, order_id, position_id, symbol, side,
             volume, entry_price, sl, tp, status),
        )
        conn.commit()
        return cur.lastrowid or 0
    finally:
        conn.close()


def update_order_status(order_id: str, status: str, pnl: float = 0,
                        exit_reason: str | None = None) -> bool:
    """Atualiza status e PnL de uma ordem."""
    conn = _connect()
    try:
        conn.execute(
            "UPDATE vector_orders SET status=?, pnl=?, exit_reason=? WHERE order_id=?",
            (status, pnl, exit_reason, order_id),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def get_recent_signals(symbol: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """Últimos sinais (para pandas: pd.read_sql)."""
    conn = _connect()
    try:
        if symbol:
            rows = conn.execute(
                "SELECT * FROM vector_signals WHERE symbol=? ORDER BY timestamp DESC LIMIT ?",
                (symbol, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM vector_signals ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_open_orders() -> list[dict[str, Any]]:
    """Ordens abertas (status != CLOSED/CANCELLED)."""
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT * FROM vector_orders WHERE status NOT IN ('CLOSED','CANCELLED')"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_stats(symbol: str | None = None) -> dict[str, Any]:
    """Estatísticas agregadas dos sinais (win rate, avg score, etc.)."""
    conn = _connect()
    try:
        where = "WHERE symbol=?" if symbol else ""
        params = (symbol,) if symbol else ()
        row = conn.execute(
            f"""SELECT
                  COUNT(*) as total_signals,
                  AVG(fusion_score) as avg_score,
                  SUM(CASE WHEN signal='BUY' THEN 1 ELSE 0 END) as buy_count,
                  SUM(CASE WHEN signal='SELL' THEN 1 ELSE 0 END) as sell_count,
                  AVG(confidence) as avg_confidence
               FROM vector_signals {where}""",
            params,
        ).fetchone()
        # Win rate via orders
        order_row = conn.execute(
            f"""SELECT
                  COUNT(*) as total_orders,
                  SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                  SUM(pnl) as total_pnl
               FROM vector_orders
               WHERE status='CLOSED' {'AND symbol=?' if symbol else ''}""",
            params,
        ).fetchone()
        return {
            "total_signals": row["total_signals"] if row else 0,
            "avg_score": round(row["avg_score"] or 0, 2),
            "buy_count": row["buy_count"] if row else 0,
            "sell_count": row["sell_count"] if row else 0,
            "avg_confidence": round(row["avg_confidence"] or 0, 2),
            "total_orders": order_row["total_orders"] if order_row else 0,
            "wins": order_row["wins"] if order_row else 0,
            "total_pnl": order_row["total_pnl"] if order_row else 0,
            "win_rate": round(order_row["wins"] / order_row["total_orders"] * 100, 1)
                       if order_row and order_row["total_orders"] > 0 else 0,
        }
    finally:
        conn.close()


# Inicializa o banco ao importar
init_db()
