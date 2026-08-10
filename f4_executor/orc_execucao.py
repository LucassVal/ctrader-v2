"""
PROPOSITO: T10-T12 — ORQUESTRADOR F4
SPEC: S6 (pai) — filhos: _entry, _monitor, _safety, _log_trade, _orc_orders
ROADMAP: 5.0
FLOW:   fusion_output -> _entry (_entry_params + _oco) -> _monitor (trail/BE)
        _safety (ATR spike) -> F0.place_order/exit_position/move_stops
        _orc_orders re-exporta satelites: _entry_params, _oco, _scalp_timeout, _trail_log

"""

from __future__ import annotations

import logging
import signal
import time

from f4_executor.monitor_orc_execucao import PositionMonitor
from f4_executor.safety_orc_execucao import check_atr_spike, check_drawdown
from utils.json_log_orc_metricas import log_trade_json as log_trade
from utils.logger import get_logger
from utils.mcp_client import (
    MCPConnectionError,
    cancel_order,
    get_balance,
    get_pending_orders,
    get_positions,
    get_symbols,
    init_client,
)
from utils.slot_tracker import SlotTracker

logger = get_logger(__name__, "F4")

TIMEOUT_MAX = {"M_5": 5, "M_15": 15}
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]

shutdown_flag = False


def _handle_signal(signum, frame):
    global shutdown_flag
    logger.info("Sinal recebido: %s", signum)
    shutdown_flag = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


def run_executor(config_path: str = "config.yaml"):
    logger.info("=== F4 EXECUTOR INICIADO ===")
    from f5_mar.trades_log_orc_mar import ensure_schema
    ensure_schema()
    init_client(config_path)

    slot_tracker = SlotTracker()
    active_monitors: dict[int, PositionMonitor] = {}

    # verifica se symbols existem
    try:
        all_symbols = get_symbols()
        logger.info("Simbolos disponiveis: %d", len(all_symbols) if isinstance(all_symbols, list) else 0)
    except Exception as e:
        logger.error("Falha ao listar simbolos: %s", e)

    while not shutdown_flag:
        try:
            # kill switch
            try:
                bal = get_balance()
                equity = bal.get("equity", 1000)
            except Exception:
                equity = 1000
            kill, reason = check_drawdown(str(slot_tracker._db_path), equity)
            if kill:
                logger.critical("KILL SWITCH: %s. Cancelando ordens e fechando tudo.", reason)
                # cancela ordens pendentes
                try:
                    for order in get_pending_orders() if isinstance(get_pending_orders(), list) else []:
                        if isinstance(order, dict) and order.get("orderId"):
                            cancel_order(str(order["orderId"]))
                            logger.info("Ordem cancelada: %s", order["orderId"])
                except Exception as e:
                    logger.error("Erro ao cancelar ordens: %s", e)
                # fecha posicoes
                for pos_id in list(active_monitors.keys()):
                    mon = active_monitors.pop(pos_id)
                    mon.close(0, "KILL_SWITCH")
                slot_tracker.release_all_today()
                time.sleep(3600)
                continue

            # monitora posicoes ativas
            try:
                from f4_executor.entry_orc_execucao import (
                    PAPER_MODE,
                )
            except ImportError:
                PAPER_MODE = False  # noqa: N806

            if not PAPER_MODE:
                try:
                    positions = get_positions()
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
                            log_trade(log)
                            logger.info("Posicao fechada: %s reason=%s pnl=%.2f",
                                        pos_id, result, log.get("pnl_net", 0))
            else:
                # PAPER MODE: Simulate positions using current spot prices
                from utils.mcp_client import get_spot_prices
                for pos_id, mon in list(active_monitors.items()):
                    try:
                        spot = get_spot_prices(mon.entry.get("symbol_id", ""))
                        if not spot:
                            continue

                        side = mon.entry.get("side", "buy")
                        current_price = spot["bid"] if side == "buy" else spot["ask"]

                        # Simulate PnL (pips) - rough approximation (1 lot = $10 per pip for most pairs)
                        price_diff = (current_price - mon.entry_price) if side == "buy" else (mon.entry_price - current_price)
                        current_pnl = (price_diff * 100000) * mon.entry.get("volume", 0.1) * 10 # very rough estimate

                        # Simulate TP / SL hits
                        result = None
                        if side == "buy":
                            if current_price >= mon.tp:
                                result = "TAKE_PROFIT"
                            elif current_price <= mon.sl:
                                result = "STOP_LOSS"
                        else:
                            if current_price <= mon.tp:
                                result = "TAKE_PROFIT"
                            elif current_price >= mon.sl:
                                result = "STOP_LOSS"

                        # Apply regular monitor updates (trailing stop etc)
                        mon_update = mon.update(current_price, current_pnl)
                        if mon_update:
                            result = mon_update

                        if result:
                            log = mon.close(current_price, result)
                            active_monitors.pop(pos_id)
                            slot_tracker.release(mon.trace_id)
                            log_trade(log)
                            logger.info("[PAPER_MODE] Posicao fechada: %s reason=%s pnl=%.2f",
                                        pos_id, result, log.get("pnl_net", 0))
                    except Exception as e:
                        logger.error("Erro no paper monitor para %s: %s", pos_id, e)

            # ATR spike em posicoes ativas
            for _pos_id, mon in list(active_monitors.items()):
                sym = mon.entry.get("symbol_id", "")
                if sym and check_atr_spike(str(sym)):
                    logger.error("ATR Spike detectado em %s. Forcando BE.", sym)
                    be_sl = mon.entry_price + mon.spread
                    mon._amend_sl(be_sl)
                    if not mon.d0_done:
                        mon.d0_done = True

            # S38: pipeline F2->F3->F4 integrado (verdict.json + fusion_output.json)
            try:
                import json
                import os

                verdict_path = "verdict.json"
                fusion_path = "fusion_output.json"

                if os.path.exists(verdict_path) and os.path.exists(fusion_path):
                    with open(verdict_path) as f:
                        verdict = json.load(f)
                    with open(fusion_path) as f:
                        fusion = json.load(f)

                    trace_id = fusion.get("meta", {}).get("trace_id", "")
                    # Keep track of executed trace_ids
                    if not hasattr(slot_tracker, "executed_traces"):
                        slot_tracker.executed_traces = set()

                    if trace_id and trace_id not in slot_tracker.executed_traces:
                        slot_tracker.executed_traces.add(trace_id)

                        if verdict.get("decision") == "APPROVE":
                            symbol = fusion.get("meta", {}).get("symbol")
                            score = fusion.get("scores", {}).get("final_adjusted", 0)
                            sinal = fusion.get("scores", {}).get("sinal", "BULLISH")

                            from f4_executor.entry_orc_execucao import calculate_entry
                            from f4_executor.oco_orc_ordens import (
                                execute_oco_order,
                                validate_signal_for_entry,
                            )

                            sig = {
                                "symbol": symbol,
                                "score": score,
                                "action": "APPROVE",
                                "side": "buy" if sinal == "BULLISH" else "sell"
                            }

                            val = validate_signal_for_entry(sig)
                            if val["valid"]:
                                logger.info("Sinal aprovado (F3) para %s com score %.1f", symbol, score)
                                entry_params = calculate_entry(symbol, verdict.get("adjustments", {}).get("lot_multiplier", 1.0))
                                entry_params["side"] = sig["side"]  # Ensure correct side

                                oco_res = execute_oco_order(entry_params)
                                if oco_res["status"] == "ok":
                                    # Create monitor
                                    mon = PositionMonitor(
                                        trace_id=trace_id,
                                        entry=entry_params,
                                        timeout_min=verdict.get("adjustments", {}).get("timeout_min", 15)
                                    )
                                    pos_id = oco_res.get("position_id")
                                    if pos_id:
                                        active_monitors[pos_id] = mon
                                        slot_tracker.acquire(trace_id)
                                        logger.info("Execucao completa e monitor ativa para pos_id: %s", pos_id)
                            else:
                                logger.info("Sinal %s ignorado pela F4: %s", symbol, val["errors"])
            except Exception as e:
                logger.error("Erro na leitura F2/F3: %s", e)

            time.sleep(1)
        except MCPConnectionError as e:
            logger.error("Erro MCP: %s", e)
            time.sleep(2)
        except Exception as e:
            logger.exception("Erro inesperado no loop F4: %s", e)
            time.sleep(1)

    logger.info("=== F4 EXECUTOR ENCERRADO ===")
    slot_tracker.close()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="F4 Executor — cTrader V2")
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    run_executor(args.config)


if __name__ == "__main__":
    main()
