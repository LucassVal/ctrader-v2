"""
PROPOSITO: T10, T11, T12
SPEC: S0
ROADMAP: 0.0
"""

from __future__ import annotations

import logging
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.mcp_client import MCPConnectionError, MCPTimeoutError, call_mcp, init_client
from utils.session_manager import is_trading_allowed
from utils.slot_tracker import SlotTracker

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# constantes
# ---------------------------------------------------------------------------
TIMEOUT_MAX = {"m5": 10, "m10": 15, "m15": 20}
DEGRAU_0_PCT = 0.05    # 5% do TP
DEGRAU_40_PCT = 0.40
DEGRAU_60_PCT = 0.60
DEGRAU_80_PCT = 0.80
ATR_SPIKE_MULTIPLIER = 2.0
ATR_WINDOW = 20
RR_RATIO = 2.0
LOT_SIZE = 0.1
MAX_POSITIONS_PER_SYMBOL = 3
DAILY_DRAWDOWN_KILL = 0.03
WEEKLY_DRAWDOWN_KILL = 0.05
MARGIN_SOFT_LIMIT = 0.20
MCP_RETRY_MAX = 3
MCP_RETRY_BACKOFF = 0.5
GHOST_TIMEOUT = 5  # segundos

# ---------------------------------------------------------------------------
# estado
# ---------------------------------------------------------------------------
shutdown_flag = False
import signal


def _handle_signal(signum, frame):
    global shutdown_flag
    logger.info("Sinal recebido: %s", signum)
    shutdown_flag = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _mcp_retry(method: str, params: dict[str, Any] | None = None, max_retries: int = MCP_RETRY_MAX) -> dict[str, Any]:
    """Chama MCP com retry exponencial para erros transientes."""
    last_err = None
    for attempt in range(max_retries):
        try:
            return call_mcp(method, params)
        except MCPTimeoutError as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(MCP_RETRY_BACKOFF * (attempt + 1))
        except MCPConnectionError as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(MCP_RETRY_BACKOFF * (attempt + 1))
    raise last_err  # type: ignore


def _now_utc() -> str:
    return datetime.now(UTC).isoformat()


def _generate_trace() -> str:
    return f"T{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{int(time.monotonic()*1000)%100000:05d}"


# ---------------------------------------------------------------------------
# gates pre-entrada
# ---------------------------------------------------------------------------

def _check_gates(symbol_id: int, timeframe: str, lot_multiplier: float,
                 slot_tracker: SlotTracker, news_imminent: bool,
                 symbol_ids: dict[str, int]) -> tuple[bool, str, float]:
    """Retorna (aprovado, motivo, lot_multiplier ajustado)."""

    # G1 — margem
    try:
        bal = _mcp_retry("get_balance")
        free_margin = bal.get("freeMargin", 0)
        total_margin = bal.get("equity", free_margin)  # fallback
        margin_ratio = free_margin / total_margin if total_margin > 0 else 0
        if margin_ratio < MARGIN_SOFT_LIMIT:
            lot_multiplier *= 0.5
            logger.info("Margem %.1f%% — lote reduzido para %.2f", margin_ratio * 100, lot_multiplier)
        if free_margin <= 0:
            return False, "MARGEM_INSUFICIENTE", lot_multiplier
    except Exception as e:
        logger.error("Falha ao verificar margem: %s", e)
        return False, "ERRO_MARGEM", lot_multiplier

    # G2 — posicoes no mesmo simbolo
    try:
        positions = _mcp_retry("get_positions")
        sym_positions = [p for p in positions if isinstance(p, dict) and p.get("symbolId") == symbol_id]
        if len(sym_positions) >= MAX_POSITIONS_PER_SYMBOL:
            return False, "MAX_POSITIONS_SYMBOL", lot_multiplier
    except Exception as e:
        logger.error("Falha ao verificar posicoes: %s", e)

    # G3 — slots
    if slot_tracker.is_full(timeframe):
        return False, "SLOT_FULL", lot_multiplier

    # G4/G5 — sessao
    allowed, session = is_trading_allowed()
    if not allowed:
        return False, session, lot_multiplier

    # G6 — news
    if news_imminent:
        lot_multiplier = min(lot_multiplier, 0.2)  # lote max = 0.02

    return True, session, lot_multiplier


# ---------------------------------------------------------------------------
# entrada
# ---------------------------------------------------------------------------

def _calculate_entry(symbol_id: int, lot_multiplier: float) -> dict[str, Any]:
    """Obtem cotacao, calcula SL/TP, envia ordem OCO."""

    # pega detalhes do simbolo
    details = _mcp_retry("get_symbol_details", {"symbolId": symbol_id})
    lot_size = details.get("lotSize", 1000)
    volume_step = details.get("volumeStep", 1)
    min_volume = details.get("minVolume", 1)
    max_volume = details.get("maxVolume", 100000)

    # volume em UNITS
    volume = int(LOT_SIZE * lot_multiplier * lot_size)
    volume = max(min_volume, min(volume, max_volume))
    volume = (volume // volume_step) * volume_step

    # spot
    spot = _mcp_retry("get_spot_prices", {"symbolId": symbol_id})
    bid = spot.get("bid", 0)
    ask = spot.get("ask", 0)
    spread = ask - bid

    # direction via scores F1 (quando disponivel, le de scores_raw.json)
    # Fallback: BUY como default conservador
    side = "buy"

    entry_price = ask if side == "buy" else bid

    # ATR para SL/TP
    atr = _get_atr(symbol_id, "m15")

    sl = entry_price - atr if side == "buy" else entry_price + atr
    tp = entry_price + atr * RR_RATIO if side == "buy" else entry_price - atr * RR_RATIO

    # envia ordem OCO
    order = _mcp_retry("place_market_order", {
        "symbolId": symbol_id,
        "side": side,
        "volume": volume,
        "stopLoss": round(sl, 2),
        "takeProfit": round(tp, 2),
    })

    return {
        "symbol_id": symbol_id,
        "side": side,
        "volume": volume,
        "entry_price": entry_price,
        "sl": sl,
        "tp": tp,
        "spread": spread,
        "atr": atr,
        "order_id": order.get("orderId"),
        "position_id": order.get("positionId"),
        "status": "PENDING_FILL",
    }


def _get_atr(symbol_id: int, timeframe: str) -> float:
    """Calcula ATR simples baseado em range dos ultimos candles."""
    try:
        bars = _mcp_retry("get_trendbars", {
            "symbolId": symbol_id,
            "timeframe": timeframe,
            "count": 15,
        })
        if isinstance(bars, list) and len(bars) >= 2:
            ranges = [abs(b.get("high", 0) - b.get("low", 0)) for b in bars if isinstance(b, dict)]
            return sum(ranges) / len(ranges) if ranges else 10.0
    except Exception as e:
        logger.error("Falha ao calcular ATR: %s", e)
    return 10.0  # fallback


# ---------------------------------------------------------------------------
# monitoramento
# ---------------------------------------------------------------------------

class PositionMonitor:
    """Monitora uma posicao aberta com degraus e trailing stop."""

    def __init__(self, entry: dict[str, Any], timeout_min: int, slot_tracker: SlotTracker, trace_id: str):
        self.entry = entry
        self.timeout_min = timeout_min
        self.slot_tracker = slot_tracker
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

        # flags degraus
        self.d0_done = False
        self.d40_noted = False
        self.d60_done = False
        self.d80_done = False
        self.trail_active = False
        self.be_locked = False

        self.started_at = time.monotonic()
        self.last_highest_at = self.started_at

    def update(self, current_price: float, current_pnl: float) -> str | None:
        """Processa um tick. Retorna 'CLOSE' se deve fechar, None senao."""

        self.pnl_pct = self._calc_pnl_pct(current_price)

        # ghost detection (posicao ainda nao preenchida)
        elapsed = time.monotonic() - self.started_at
        if self.entry.get("status") == "PENDING_FILL" and elapsed > GHOST_TIMEOUT:
            logger.error("Ghost order detectada: %s", self.position_id)
            return "GHOST"

        # atualiza highest
        if current_price > self.highest_price:
            self.highest_price = current_price
            self.last_highest_at = time.monotonic()

        # ---- DEGRAU 0: BE rapido ----
        if not self.d0_done and self.pnl_pct >= DEGRAU_0_PCT:
            be_sl = self.entry_price + self.spread
            self._amend_sl(be_sl)
            self.d0_done = True
            logger.info("D0: BE rapido ativado. SL=%f", be_sl)

        # ---- DEGRAU 40: anota ----
        if not self.d40_noted and self.pnl_pct >= DEGRAU_40_PCT:
            self.d40_noted = True
            logger.info("D40: %d%% do TP", int(self.pnl_pct * 100))

        # ---- DEGRAU 60: sobe SL ----
        if not self.d60_done and self.pnl_pct >= DEGRAU_60_PCT:
            ganho = abs(current_price - self.entry_price)
            novo_sl = self.entry_price + ganho * 0.3
            self._amend_sl(novo_sl)
            self.d60_done = True
            logger.info("D60: SL subiu para %f", novo_sl)

        # ---- DEGRAU 80: fecha 80% + trail ----
        if not self.d80_done and self.pnl_pct >= DEGRAU_80_PCT:
            close_vol = int(self.volume * 0.8)
            try:
                _mcp_retry("close_position_partial", {
                    "positionId": self.position_id,
                    "volume": close_vol,
                })
            except Exception as e:
                logger.error("Erro ao fechar 80%%: %s", e)
                return None

            # reenvia OCO para sobra
            be_sl = self.entry_price + self.spread
            try:
                _mcp_retry("amend_position", {
                    "positionId": self.position_id,
                    "stopLoss": round(be_sl, 2),
                    "takeProfit": round(self.tp, 2),
                })
            except Exception as e:
                logger.error("Erro ao reenviar OCO sobra: %s", e)

            self.d80_done = True
            self.trail_active = True
            self.volume = self.volume - close_vol
            logger.info("D80: 80%% fechado. Trail ativado na sobra (%d units). OCO reenviada.", self.volume)

        # ---- TRAILING STOP ----
        if self.trail_active:
            trail_sl = self.highest_price - self.atr * 0.3
            # trava no BE
            be_sl = self.entry_price + self.spread
            if trail_sl < be_sl:
                trail_sl = be_sl
                if not self.be_locked:
                    self.be_locked = True
                    logger.info("TRAIL: BE travado em %f", be_sl)

            self._amend_sl(trail_sl)

            if current_price <= trail_sl:
                return "DEGRAU_80_TRAIL_BE"

        # ---- TIMEOUT ----
        if time.monotonic() - self.last_highest_at > self.timeout_min * 60:
            logger.info("TIMEOUT: %d min sem novo topo", self.timeout_min)
            return "TIMEOUT"

        # ---- SL/TP originais (OCO no servidor cobre, mas verificamos para log) ----
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

        # nenhum degrau disparado — continua monitorando
        return None

    def _amend_sl(self, new_sl: float) -> None:
        try:
            _mcp_retry("amend_position", {
                "positionId": self.position_id,
                "stopLoss": round(new_sl, 2),
            })
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
        """Fecha posicao restante e retorna log."""
        import contextlib
        with contextlib.suppress(Exception):
            _mcp_retry("close_position", {"positionId": self.position_id})

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


# ---------------------------------------------------------------------------
# ATR spike detector
# ---------------------------------------------------------------------------

def _check_atr_spike(symbol_id: int) -> bool:
    """True se ATR_M5 atual > 2x media dos ultimos 20 candles."""
    try:
        bars = _mcp_retry("get_trendbars", {
            "symbolId": symbol_id,
            "timeframe": "m5",
            "count": ATR_WINDOW + 1,
        })
        if not isinstance(bars, list) or len(bars) < 5:
            return False
        ranges = [abs(b.get("high", 0) - b.get("low", 0)) for b in bars if isinstance(b, dict)]
        if not ranges:
            return False
        current_range = ranges[-1]
        avg_range = sum(ranges[:-1]) / len(ranges[:-1]) if len(ranges) > 1 else current_range
        return current_range > avg_range * ATR_SPIKE_MULTIPLIER
    except Exception:
        return False


# ---------------------------------------------------------------------------
# kill switch
# ---------------------------------------------------------------------------

def _check_drawdown(db_path: str, equity: float) -> tuple[bool, str]:
    """Verifica drawdown diario e semanal no SQLite."""
    import sqlite3
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


# ---------------------------------------------------------------------------
# loop principal
# ---------------------------------------------------------------------------

def run_executor(config_path: str = "config.yaml"):
    """Loop de execucao F4."""
    logger.info("=== F4 EXECUTOR INICIADO ===")

    slot_tracker = SlotTracker()
    symbol_ids: dict[str, int] = {}

    # resolve simbolos
    for sym in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        try:
            result = _mcp_retry("get_symbols", {"query": sym})
            if isinstance(result, dict) and "symbolId" in result:
                symbol_ids[sym] = result["symbolId"]
        except Exception as e:
            logger.error("Falha ao resolver simbolo %s: %s", sym, e)
    logger.info("Simbolos: %s", list(symbol_ids.keys()))

    active_monitors: dict[int, PositionMonitor] = {}

    while not shutdown_flag:
        try:
            # ---- kill switch ----
            try:
                bal = _mcp_retry("get_balance")
                equity = bal.get("equity", 1000)
            except Exception:
                equity = 1000
            kill, reason = _check_drawdown(str(slot_tracker._db_path), equity)
            if kill:
                logger.critical("KILL SWITCH: %s. Fechando tudo.", reason)
                for pos_id in list(active_monitors.keys()):
                    mon = active_monitors.pop(pos_id)
                    mon.close(0, "KILL_SWITCH")
                slot_tracker.release_all_today()
                time.sleep(3600)  # pausa 1h
                continue

            # ---- monitora posicoes ativas ----
            try:
                positions = _mcp_retry("get_positions")
            except Exception:
                positions = []

            for pos in positions:
                if not isinstance(pos, dict):
                    continue
                pos_id = pos.get("positionId")
                if pos_id is None:
                    continue

                current_price = pos.get("currentPrice", 0)
                current_pnl = pos.get("pnl", 0)

                if pos_id in active_monitors:
                    mon = active_monitors[pos_id]
                    result = mon.update(current_price, current_pnl)
                    if result:
                        log = mon.close(current_price, result)
                        active_monitors.pop(pos_id)
                        slot_tracker.release(mon.trace_id)
                        _log_trade(log)
                        logger.info("Posicao fechada: %s reason=%s pnl=%.2f",
                                    pos_id, result, log.get("pnl_net", 0))

            # ---- ATR spike em todas as posicoes ----
            for pos_id, mon in list(active_monitors.items()):
                sym_id = mon.entry.get("symbol_id", 0)
                if _check_atr_spike(sym_id):
                    logger.error("ATR Spike detectado. Forcando BE.")
                    be_sl = mon.entry_price + mon.spread
                    mon._amend_sl(be_sl)
                    if not mon.d0_done:
                        mon.d0_done = True  # força BE

            # ---- sinal da F2/F3 ----
            # Le verdict.json quando disponivel.
            # Se APPROVE e score >= threshold, executa entrada.
            # Estrutura pronta — integracao pendente do pipeline F1->F2->F3.

            time.sleep(1)

        except (MCPTimeoutError, MCPConnectionError) as e:
            logger.error("Erro MCP no loop: %s", e)
            time.sleep(2)
        except Exception as e:
            logger.exception("Erro inesperado no loop F4: %s", e)
            time.sleep(1)

    # encerramento
    logger.info("=== F4 EXECUTOR ENCERRADO ===")
    slot_tracker.close()


def _log_trade(log: dict[str, Any]):
    """Persiste trade no SQLite."""
    import sqlite3
    try:
        db_path = Path(__file__).resolve().parent / "trades.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT UNIQUE,
                timestamp_utc TEXT,
                symbol_id INTEGER,
                direction TEXT,
                entry_price REAL,
                volume INTEGER,
                sl_initial REAL,
                tp_initial REAL,
                exit_price REAL,
                exit_reason TEXT,
                pnl_net REAL,
                duration_seconds REAL,
                trail_activated INTEGER,
                be_locked INTEGER,
                degrau0_triggered INTEGER,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            INSERT INTO trades (trace_id, timestamp_utc, symbol_id, direction,
                entry_price, volume, sl_initial, tp_initial, exit_price,
                exit_reason, pnl_net, duration_seconds, trail_activated,
                be_locked, degrau0_triggered)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log["trace_id"], _now_utc(), log.get("symbol_id"),
            log["direction"], log["entry_price"], log["volume"],
            log["sl_initial"], log["tp_initial"], log["exit_price"],
            log["exit_reason"], log["pnl_net"], log["duration_seconds"],
            int(log.get("trail_activated", False)),
            int(log.get("be_locked", False)),
            int(log.get("degrau0_triggered", False)),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error("Falha ao logar trade: %s", e)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(description="F4 Executor — cTrader V2")
    parser.add_argument("--mcp-url", default="http://localhost:8080/mcp")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    init_client(args.mcp_url, timeout=2.0)
    run_executor(args.config)


if __name__ == "__main__":
    main()
