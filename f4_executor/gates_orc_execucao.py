"""
PROPOSITO: T10 -- GATES
SPEC: S6
ROADMAP: 5.0
"""

from __future__ import annotations

import logging

from utils.mcp_client import get_balance, get_positions
from utils.session_manager import is_trading_allowed
from utils.slot_tracker import SlotTracker

logger = logging.getLogger(__name__)

MAX_POSITIONS_PER_SYMBOL = 3
MARGIN_SOFT_LIMIT = 0.20


def check_gates(symbol_id: int, timeframe: str, lot_multiplier: float,
                slot_tracker: SlotTracker, news_imminent: bool) -> tuple[bool, str, float]:
    """Retorna (aprovado, motivo, lot_multiplier ajustado)."""

    # G1 -- margem
    try:
        bal = get_balance()
        free_margin = bal.get("freeMargin", 0)
        total_margin = bal.get("equity", free_margin)
        margin_ratio = free_margin / total_margin if total_margin > 0 else 0
        if margin_ratio < MARGIN_SOFT_LIMIT:
            lot_multiplier *= 0.5
            logger.info("Margem %.1f%% | lote reduzido para %.2f", margin_ratio * 100, lot_multiplier)
        if free_margin <= 0:
            return False, "MARGEM_INSUFICIENTE", lot_multiplier
    except Exception as e:
        logger.error("Falha ao verificar margem: %s", e)
        return False, "ERRO_MARGEM", lot_multiplier

    # G2 -- posicoes no mesmo simbolo
    try:
        positions = get_positions()
        sym_positions = [p for p in positions if isinstance(p, dict) and p.get("symbolId") == symbol_id]
        if len(sym_positions) >= MAX_POSITIONS_PER_SYMBOL:
            return False, "MAX_POSITIONS_SYMBOL", lot_multiplier
    except Exception as e:
        logger.error("Falha ao verificar posicoes: %s", e)

    # G3 -- slots
    if slot_tracker.is_full(timeframe):
        return False, "SLOT_FULL", lot_multiplier

    # G4/G5 -- sessao
    allowed, session = is_trading_allowed()
    if not allowed:
        return False, session, lot_multiplier

    # G6 -- news
    if news_imminent:
        lot_multiplier = min(lot_multiplier, 0.2)

    return True, session, lot_multiplier
