"""
HARNESS: Testes para vector._vector_db
Spec: specs/ruse_alternatives.md §"Banco de Dados do Vector"
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vector._vector_db import (
    get_open_orders,
    get_recent_signals,
    get_stats,
    init_db,
    save_order,
    save_signal,
    update_order_status,
)


def test_init_db():
    """G6: Banco inicializa sem erro."""
    init_db()
    assert Path(__file__).resolve().parent.parent / "vector" / "vector.db"


def test_save_and_retrieve_signal():
    """G6: Sinal é persistido e recuperado."""
    trace = f"test-{int(time.time())}"
    sid = save_signal(
        trace_id=trace, symbol="EURUSD", timestamp=time.time(),
        spotter_score=85, sniper_score=78, fusion_score=81,
        signal="BUY", confidence=0.85,
        payload={"source": "test"},
    )
    assert sid > 0

    signals = get_recent_signals(symbol="EURUSD", limit=5)
    found = [s for s in signals if s["trace_id"] == trace]
    assert len(found) >= 1
    assert found[0]["signal"] == "BUY"
    assert found[0]["fusion_score"] == 81


def test_save_order():
    """G6: Ordem é persistida."""
    trace = f"test-order-{int(time.time())}"
    oid = save_order(
        trace_id=trace, signal_id=1, order_id="ord-001",
        position_id="pos-001", symbol="XAUUSD", side="BUY",
        volume=0.1, entry_price=2000.0, sl=1990.0, tp=2020.0,
        status="PENDING",
    )
    assert oid > 0

    orders = get_open_orders()
    assert any(o["order_id"] == "ord-001" for o in orders)


def test_update_order_status():
    """G6: Status e PnL são atualizados."""
    trace = f"test-update-{int(time.time())}"
    save_order(
        trace_id=trace, signal_id=1, order_id="ord-upd",
        position_id="pos-upd", symbol="GBPUSD", side="SELL",
        volume=0.1, entry_price=1.2500, sl=1.2600, tp=1.2400,
        status="PENDING",
    )
    result = update_order_status("ord-upd", "CLOSED", pnl=50.0, exit_reason="TAKE_PROFIT")
    assert result is True


def test_get_stats():
    """G6: Estatísticas são calculadas."""
    stats = get_stats()
    assert "total_signals" in stats
    assert "win_rate" in stats
    assert isinstance(stats["total_signals"], int)
