"""
PROPOSITO: T11 — MONITOR
SPEC: S6
ROADMAP: 5.2
"""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from utils.mcp_client import amend_position, close_position

logger = logging.getLogger(__name__)

DEGRAU_0_PCT = 0.05
DEGRAU_40_PCT = 0.40
DEGRAU_60_PCT = 0.60
DEGRAU_80_PCT = 0.80
GHOST_TIMEOUT = 5


class PositionMonitor:
    """Monitora uma posicao aberta com degraus e trailing stop."""

    def __init__(self, entry: dict[str, Any], timeout_min: int, trace_id: str):
        self.entry = entry
        self.timeout_min = timeout_min
        self.trace_id = trace_id

        self.position_id = entry.get("position_id")
        self.entry_price = entry.get("entry_price", 0)
        self.sl = entry.get("sl", 0)
        self.tp = entry.get("tp", 0)
        self.spread = entry.get("spread", 0)
        self.atr = entry.get("atr", 10)
        self.side = entry.get("side", "buy")
        self.volume = entry.get("volume", 0)

        self.highest_price = self.entry_price
        self.pnl_pct = 0.0
        self.d0_done = False
        self.d40_noted = False
        self.d60_done = False
        self.d80_done = False
        self.trail_active = False
        self.be_locked = False

        self.started_at = time.monotonic()
        self.last_highest_at = self.started_at

    def update(self, current_price: float, current_pnl: float) -> str | None:
        self.pnl_pct = self._calc_pnl_pct(current_price)

        elapsed = time.monotonic() - self.started_at
        if self.entry.get("status") == "PENDING_FILL" and elapsed > GHOST_TIMEOUT:
            logger.error("Ghost order detectada: %s", self.position_id)
            return "GHOST"

        if current_price > self.highest_price:
            self.highest_price = current_price
            self.last_highest_at = time.monotonic()

        if not self.d0_done and self.pnl_pct >= DEGRAU_0_PCT:
            be_sl = self.entry_price + self.spread
            self._amend_sl(be_sl)
            self.d0_done = True
            logger.info("D0: BE rapido ativado. SL=%f", be_sl)

        if not self.d40_noted and self.pnl_pct >= DEGRAU_40_PCT:
            self.d40_noted = True
            logger.info("D40: %d%% do TP", int(self.pnl_pct * 100))

        if not self.d60_done and self.pnl_pct >= DEGRAU_60_PCT:
            ganho = abs(current_price - self.entry_price)
            novo_sl = self.entry_price + ganho * 0.3
            self._amend_sl(novo_sl)
            self.d60_done = True
            logger.info("D60: SL subiu para %f", novo_sl)

        if not self.d80_done and self.pnl_pct >= DEGRAU_80_PCT:
            close_vol = self.volume * 0.8  # lots (float), convertido a cents pelo mcp_client
            try:
                close_position(position_id=str(self.position_id), volume=close_vol)
            except Exception as e:
                logger.error("Erro ao fechar 80%%: %s", e)
                return None

            be_sl = self.entry_price + self.spread
            try:
                amend_position(
                    position_id=str(self.position_id),
                    sl=round(be_sl, 2),
                    tp=round(self.tp, 2),
                )
            except Exception as e:
                logger.error("Erro ao reenviar OCO sobra: %s", e)

            self.d80_done = True
            self.trail_active = True
            self.volume = self.volume - close_vol
            logger.info("D80: 80%% fechado. Trail ativado (%d units).", self.volume)

        if self.trail_active:
            trail_sl = self.highest_price - self.atr * 0.3
            be_sl = self.entry_price + self.spread
            if trail_sl < be_sl:
                trail_sl = be_sl
                if not self.be_locked:
                    self.be_locked = True
                    logger.info("TRAIL: BE travado em %f", be_sl)
            self._amend_sl(trail_sl)
            if current_price <= trail_sl:
                return "DEGRAU_80_TRAIL_BE"

        if time.monotonic() - self.last_highest_at > self.timeout_min * 60:
            logger.info("TIMEOUT: %d min sem novo topo", self.timeout_min)
            return "TIMEOUT"

        if self.side == "buy":
            if current_price <= self.sl:
                return "STOP_LOSS"
            if current_price >= self.tp:
                return "TAKE_PROFIT"
        else:
            if current_price >= self.sl:
                return "STOP_LOSS"
            if current_price <= self.tp:
                return "TAKE_PROFIT"

        return None

    def _amend_sl(self, new_sl: float) -> None:
        try:
            amend_position(
                position_id=str(self.position_id),
                sl=round(new_sl, 2),
                tp=round(self.tp, 2),  # quirk #2: sempre enviar ambos
            )
            self.sl = new_sl
        except Exception as e:
            logger.error("Falha ao mover SL: %s", e)

    def _calc_pnl_pct(self, current_price: float) -> float:
        tp_distance = abs(self.tp - self.entry_price)
        if tp_distance == 0:
            return 0
        if self.side == "buy":
            return (current_price - self.entry_price) / tp_distance
        else:
            return (self.entry_price - current_price) / tp_distance

    def close(self, exit_price: float, exit_reason: str) -> dict[str, Any]:
        with contextlib.suppress(Exception):
            close_position(position_id=str(self.position_id), volume=self.volume)

        pnl = abs(exit_price - self.entry_price) * self.volume
        if self.side == "sell":
            pnl = -pnl
        if exit_reason in ("STOP_LOSS", "GHOST"):
            pnl = -pnl

        duration = time.monotonic() - self.started_at

        return {
            "trace_id": self.trace_id,
            "symbol_id": self.entry.get("symbol_id"),
            "direction": self.side.upper(),
            "entry_price": self.entry_price,
            "volume": self.volume,
            "sl_initial": self.entry.get("sl"),
            "tp_initial": self.tp,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "pnl_net": round(pnl, 2),
            "duration_seconds": round(duration, 1),
            "trail_activated": self.trail_active,
            "be_locked": self.be_locked,
            "degrau0_triggered": self.d0_done,
        }
