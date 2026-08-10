"""PROPOSITO: OCO — validacao de sinal + execucao de ordem OCO (F4 satelite).
SPEC: S6
ROADMAP: 4.4 — split de _orc_orders.py.
FLOW:   validate_signal -> execute_oco_order -> trades.db
"""

from __future__ import annotations

from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__, "OCO")


def validate_signal_for_entry(signal: dict[str, Any]) -> dict[str, Any]:
    """Valida se um sinal ranqueado esta pronto para execucao."""
    errors: list[str] = []
    symbol = signal.get("symbol", "")
    score = signal.get("score", 0)
    action = signal.get("action", "REJECT")

    if score < 70:
        errors.append(f"Score {score} < 70")
    if action != "APPROVE":
        errors.append(f"Acao: {action}")
    if symbol not in ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]:
        errors.append(f"Simbolo nao suportado: {symbol}")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "signal": {"symbol": symbol, "score": score, "action": action},
    }


def execute_oco_order(entry: dict[str, Any]) -> dict[str, Any]:
    """Executa ordem OCO: MARKET + SL/TP relativos. Persiste via json_log."""
    from utils.json_log_orc_metricas import log_trade_json
    from utils.mcp_client import create_order, get_idempotency_label

    try:
        order = create_order(
            symbol=entry["symbol"], side=entry["side"],
            volume=entry["lot_size"], order_type="MARKET",
            sl=entry["sl_pips"], tp=entry["tp_pips"],
        )

        try:
            log_trade_json({
                "symbol": entry["symbol"], "side": entry["side"],
                "volume": entry["lot_size"], "entry_price": entry.get("entry_price", 0),
                "sl": entry.get("sl", 0), "tp": entry.get("tp", 0),
                "order_id": str(order.get("orderId", "")),
                "position_id": str(order.get("positionId", "")),
                "status": "FILLED" if order.get("orderId") else "PENDING",
            })
        except Exception as e:
            logger.error("Falha ao persistir ordem: %s", e)

        return {
            "status": "ok",
            "order_id": order.get("orderId"),
            "position_id": order.get("positionId"),
            "entry": entry,
            "label": get_idempotency_label(entry["symbol"]),
        }
    except Exception as e:
        logger.error("Falha ao executar ordem: %s", e)
        return {"status": "error", "error": str(e)[:200], "entry": entry}
