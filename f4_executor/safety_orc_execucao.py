"""
PROPOSITO: T12 — SAFETY
SPEC: S6
ROADMAP: 5.0
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import UTC, datetime

from utils.mcp_client import get_trendbars

logger = logging.getLogger(__name__)

ATR_SPIKE_MULTIPLIER = 2.0
ATR_WINDOW = 20
DAILY_DRAWDOWN_KILL = 0.03


def check_atr_spike(symbol: str) -> bool:
    """True se ATR_M5 atual > 2x media dos ultimos 20 candles."""
    try:
        bars = get_trendbars(symbol=symbol, timeframe="m5", count=ATR_WINDOW + 1)
        if not isinstance(bars, list) or len(bars) < 5:
            return False
        ranges = [abs(b.get("high", 0) - b.get("low", 0)) for b in bars if isinstance(b, dict)]
        if not ranges:
            return False
        current_range = ranges[-1]
        avg_range = sum(ranges[:-1]) / len(ranges[:-1]) if len(ranges) > 1 else current_range
        return current_range > avg_range * ATR_SPIKE_MULTIPLIER
    except Exception as e:
        logger.error("Erro ao verificar ATR spike: %s", e)
        return False


def check_drawdown(db_path: str, equity: float) -> tuple[bool, str]:
    """Verifica drawdown diario no SQLite."""
    try:
        conn = sqlite3.connect(db_path)
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl_net), 0) FROM trades WHERE date(timestamp_utc)=?",
            (today,),
        ).fetchone()
        daily_pnl = row[0] if row else 0
        if equity > 0 and daily_pnl / equity <= -DAILY_DRAWDOWN_KILL:
            conn.close()
            return True, f"DRAWDOWN_DIARIO: {daily_pnl/equity*100:.1f}%"
        conn.close()
    except Exception as e:
        logger.error("Falha ao verificar drawdown: %s", e)
    return False, ""
