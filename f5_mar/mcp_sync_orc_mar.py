"""
PROPOSITO: T21 — MCP SYNC
SPEC: S0
ROADMAP: 0.0
"""

from __future__ import annotations

import logging
import sqlite3
import time as _time
from datetime import UTC, datetime
from pathlib import Path

from utils.mcp_client import get_deals, get_order_history, get_trendbars, init_client

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).resolve().parent.parent / "trades.db"


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def sync_trades_from_mcp(config_path: str = "config.yaml", days: int = 7) -> int:
    """Reconcilia trades locais com get_order_history + get_deals."""
    init_client(config_path)

    try:
        orders = get_order_history(days=days)
        logger.info("Order history: %d ordens", len(orders) if isinstance(orders, list) else 0)
    except Exception as e:
        logger.error("Falha ao obter order_history: %s", e)

    try:
        deals = get_deals(days=days)
    except Exception as e:
        logger.error("Falha ao obter deals: %s", e)
        return 0

    conn = _get_conn()
    synced = 0
    for deal in (deals if isinstance(deals, list) else []):
        if not isinstance(deal, dict):
            continue
        deal_id = deal.get("dealId", "")
        if not deal_id:
            continue
        if conn.execute("SELECT id FROM trades WHERE trace_id=?", (f"mcp-{deal_id}",)).fetchone():
            continue
        conn.execute(
            """INSERT OR IGNORE INTO trades
            (trace_id, timestamp_utc, symbol, timeframe, decision, pnl_net, exit_reason)
            VALUES (?, ?, ?, ?, 'SYNCED', ?, 'mcp_sync')""",
            (f"mcp-{deal_id}", deal.get("timestamp", datetime.now(UTC).isoformat()),
             deal.get("symbol", ""), "m15", deal.get("pnl", 0)),
        )
        synced += 1
    conn.commit()
    conn.close()
    logger.info("MCP sync: %d trades importados", synced)
    return synced


def sync_candles_from_mcp(symbols: list[str], config_path: str = "config.yaml",
                          timeframe: str = "m1", count: int = 100) -> int:
    """Popula v_historical_candles via get_trendbars. Rate limit 5 req/s."""
    init_client(config_path)
    conn = _get_conn()
    total = 0
    for sym in symbols:
        try:
            bars = get_trendbars(symbol=sym, timeframe=timeframe, count=count)
            if not isinstance(bars, list):
                continue
            for bar in bars:
                if not isinstance(bar, dict):
                    continue
                conn.execute(
                    """INSERT OR IGNORE INTO v_historical_candles
                    (timestamp_utc, symbol, open, high, low, close, tick_volume, spread)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (bar.get("time", ""), sym, bar.get("open", 0), bar.get("high", 0),
                     bar.get("low", 0), bar.get("close", 0),
                     bar.get("tickVolume", 0), bar.get("spread", 0)),
                )
                total += 1
            _time.sleep(0.2)  # rate limit 5 req/s
        except Exception as e:
            logger.error("Falha candles %s: %s", sym, e)
    conn.commit()
    conn.close()
    logger.info("MCP candles: %d barras, %d symbols", total, len(symbols))
    return total
