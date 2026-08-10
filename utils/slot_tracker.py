"""
PROPOSITO: T7
SPEC: S0
ROADMAP: D.3
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from utils.config_loader import risk

SLOTS_PER_TF = risk("slots_per_tf", 30)
TIMEFRAMES = ("m5", "m10", "m15")

DB_PATH = Path(__file__).resolve().parent.parent / "trades.db"


def _get_date_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d")


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            symbol TEXT NOT NULL,
            trace_id TEXT,
            status TEXT NOT NULL DEFAULT 'RESERVED',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            released_at TEXT
        )
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_slots_date_tf
        ON slots(date, timeframe)
    """)
    conn.commit()


class SlotTracker:
    """Gerencia slots de entrada por timeframe."""

    def __init__(self, db_path: str | Path | None = None):
        self._db_path = str(db_path or DB_PATH)
        self._conn = sqlite3.connect(self._db_path)
        _ensure_table(self._conn)

    # ------------------------------------------------------------------
    # consulta
    # ------------------------------------------------------------------

    def used(self, timeframe: str, date_utc: str | None = None) -> int:
        """Quantos slots estao ocupados no timeframe hoje."""
        date_utc = date_utc or _get_date_utc()
        row = self._conn.execute(
            "SELECT COUNT(*) FROM slots WHERE date=? AND timeframe=? AND status='RESERVED'",
            (date_utc, timeframe),
        ).fetchone()
        return row[0] if row else 0

    def available(self, timeframe: str) -> int:
        return max(0, SLOTS_PER_TF - self.used(timeframe))

    def is_full(self, timeframe: str) -> bool:
        return self.used(timeframe) >= SLOTS_PER_TF

    def total_used_today(self) -> int:
        date_utc = _get_date_utc()
        row = self._conn.execute(
            "SELECT COUNT(*) FROM slots WHERE date=? AND status='RESERVED'",
            (date_utc,),
        ).fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # mutacao
    # ------------------------------------------------------------------

    def reserve(self, timeframe: str, symbol: str, trace_id: str = "") -> bool:
        """Reserva um slot. Retorna False se cheio."""
        if self.is_full(timeframe):
            logger.error("Slot cheio: %s (%d/%d)", timeframe, self.used(timeframe), SLOTS_PER_TF)
            return False
        date_utc = _get_date_utc()
        self._conn.execute(
            "INSERT INTO slots (date, timeframe, symbol, trace_id, status) VALUES (?,?,?,?,'RESERVED')",
            (date_utc, timeframe, symbol, trace_id),
        )
        self._conn.commit()
        logger.info(
            "Slot reservado: %s/%s [%d/%d]",
            symbol, timeframe, self.used(timeframe), SLOTS_PER_TF,
        )
        return True

    def release(self, trace_id: str) -> None:
        """Libera um slot pelo trace_id."""
        now_utc = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE slots SET status='RELEASED', released_at=? WHERE trace_id=? AND status='RESERVED'",
            (now_utc, trace_id),
        )
        self._conn.commit()
        logger.info("Slot liberado: %s", trace_id)

    def release_all_today(self) -> int:
        """Libera todos os slots de hoje. Retorna contagem."""
        date_utc = _get_date_utc()
        now_utc = datetime.now(UTC).isoformat()
        cur = self._conn.execute(
            "UPDATE slots SET status='RELEASED', released_at=? WHERE date=? AND status='RESERVED'",
            (now_utc, date_utc),
        )
        self._conn.commit()
        count = cur.rowcount
        logger.info("Liberados %d slots de hoje", count)
        return count

    # ------------------------------------------------------------------
    # resumo
    # ------------------------------------------------------------------

    def summary(self) -> dict[str, Any]:
        date_utc = _get_date_utc()
        result: dict[str, Any] = {"date": date_utc, "total_slots": SLOTS_PER_TF * 3, "timeframes": {}}
        for tf in TIMEFRAMES:
            used = self.used(tf, date_utc)
            result["timeframes"][tf] = {
                "used": used,
                "available": SLOTS_PER_TF - used,
                "max": SLOTS_PER_TF,
                "full": used >= SLOTS_PER_TF,
            }
        result["total_used"] = sum(v["used"] for v in result["timeframes"].values())
        return result

    def close(self) -> None:
        self._conn.close()
