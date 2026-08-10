"""
PROPOSITO: T10 — ENTRY
SPEC: S6
ROADMAP: 5.1
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from utils.mcp_client import create_order, get_spot_prices, get_trendbars

logger = logging.getLogger(__name__)

LOT_SIZE = 0.1
RR_RATIO = 2.0
PAPER_MODE = True  # S38: Modo de execucao em Paper Trading (simulador local)


def _get_atr(symbol: str, timeframe: str) -> float:
    try:
        bars = get_trendbars(symbol=symbol, timeframe=timeframe, count=15)
        if isinstance(bars, list) and len(bars) >= 2:
            ranges = [abs(b.get("high", 0) - b.get("low", 0)) for b in bars if isinstance(b, dict)]
            return sum(ranges) / len(ranges) if ranges else 10.0
    except Exception as e:
        logger.error("Falha ao calcular ATR: %s", e)
    return 10.0


def calculate_entry(symbol: str, lot_multiplier: float) -> dict[str, Any]:
    """Obtem cotacao, calcula SL/TP, envia ordem OCO (ou simulada se PAPER_MODE)."""

    spot = get_spot_prices(symbol=symbol)
    bid = spot.get("bid", 0)
    ask = spot.get("ask", 0)
    spread = ask - bid

    side = "buy"  # TODO: receber side da estrategia (S37)
    entry_price = ask if side == "buy" else bid

    atr = _get_atr(symbol, "M_15")
    sl_pips = int(atr * 100_000)  # ATR em pips (ex: 10.0 -> 1000000)
    tp_pips = int(sl_pips * RR_RATIO)

    if PAPER_MODE:
        logger.info("[PAPER_MODE] Simulando ordem OCO para %s", symbol)
        order_id = f"sim_order_{uuid.uuid4().hex[:8]}"
        position_id = f"sim_pos_{uuid.uuid4().hex[:8]}"
    else:
        order = create_order(
            symbol=symbol, side=side, volume=LOT_SIZE,
            order_type="MARKET", sl=sl_pips, tp=tp_pips,
        )
        order_id = order.get("orderId")
        position_id = order.get("positionId")

    return {
        "symbol_id": symbol,
        "side": side,
        "volume": LOT_SIZE,
        "entry_price": entry_price,
        "sl_pips": sl_pips,
        "tp_pips": tp_pips,
        "spread": spread,
        "atr": atr,
        "order_id": order_id,
        "position_id": position_id,
        "status": "PENDING_FILL" if not PAPER_MODE else "FILLED",
        "is_paper": PAPER_MODE,
    }
