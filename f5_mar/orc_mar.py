"""PROPOSITO: F5 — MAR (Monitoramento, Ajuste, Replay). Pesos PnL + sync MCP.
SPEC: S7 (pai) — filhos: rules_orc_mar, trades_log_orc_mar, mcp_sync_orc_mar
ROADMAP: 6.0
FLOW:   trades.db -> rules_orc_mar (calculo pesos) -> custom_rules.json
        mcp_sync_orc_mar (historico MCP) -> vectorbt replay -> realimenta F2
"""

from __future__ import annotations

import argparse
import logging

from f5_mar.mcp_sync_orc_mar import sync_candles_from_mcp, sync_trades_from_mcp
from f5_mar.rules_orc_mar import calibrate_daily
from f5_mar.trades_log_orc_mar import ensure_schema, log_rotation

SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def calibrate(config_path: str = "config.yaml") -> dict:
    """Entry point: calcula pesos por PnL real -> custom_rules.json (spec S7)."""
    ensure_schema()
    result = calibrate_daily()
    logging.getLogger(__name__).info("Calibracao concluida: %s", result)
    return result


def sync_history(config_path: str = "config.yaml", days: int = 7) -> dict:
    """Entry point: sincroniza historico MCP -> vectorbt replay (spec S7)."""
    ensure_schema()
    trades = sync_trades_from_mcp(config_path, days)
    candles = sync_candles_from_mcp(SYMBOLS, config_path)
    logging.getLogger(__name__).info("Sync concluido: %s trades, %s candles",
                                      len(trades) if isinstance(trades, list) else "?",
                                      len(candles) if isinstance(candles, list) else "?")
    return {"trades": len(trades) if isinstance(trades, list) else 0,
            "candles": len(candles) if isinstance(candles, list) else 0}


def main():
    parser = argparse.ArgumentParser(description="F5 MAR + MCP Sync")
    parser.add_argument("--init-db", action="store_true")
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--sync-mcp", action="store_true")
    parser.add_argument("--sync-candles", action="store_true")
    parser.add_argument("--rotate", action="store_true")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.init_db:
        ensure_schema()
        logging.info("Schema SQLite inicializado.")
    if args.calibrate:
        calibrate(args.config)
    if args.sync_mcp:
        sync_history(args.config, args.days)
    if args.sync_candles:
        ensure_schema()
        sync_candles_from_mcp(SYMBOLS, args.config)
    if args.rotate:
        log_rotation()


if __name__ == "__main__":
    main()
