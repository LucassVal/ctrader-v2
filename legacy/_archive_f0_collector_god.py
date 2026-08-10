"""
PROPOSITO: T4
SPEC: S0
ROADMAP: 0.0
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# setup rapido de path (roda da raiz ctrader_v2/)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))

from utils.mcp_client import MCPConnectionError, MCPTimeoutError, call_mcp, init_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# constantes
# ---------------------------------------------------------------------------
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
DXY_PROXY = "EURUSD"

POLL_TICK_INTERVAL = 3    # segundos
POLL_CANDLE_INTERVAL = 60  # segundos

RECONNECT_MAX_RETRIES = 3

COLUMNS = [
    "timestamp", "symbol", "open", "high", "low", "close",
    "tick_volume", "spread", "bid", "ask",
    "dom_bid_wall", "dom_ask_wall", "sentiment_ratio", "dxy_close",
]

# ---------------------------------------------------------------------------
# estado
# ---------------------------------------------------------------------------
shutdown_flag = False


def _handle_signal(signum, frame):
    global shutdown_flag
    logger.info("Sinal recebido: %s. Encerrando...", signum)
    shutdown_flag = True


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ---------------------------------------------------------------------------
# coleta
# ---------------------------------------------------------------------------

class Collector:
    """Coleta dados MCP e mantem df_master em memoria."""

    def __init__(self, dry_run: bool = False, data_dir: str = "data"):
        self.dry_run = dry_run
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.df = pd.DataFrame(columns=COLUMNS)
        self.symbol_ids: dict[str, int] = {}
        self.last_candle_poll = 0.0
        self.consecutive_errors = 0
        self.start_time = time.monotonic()

    # ------------------------------------------------------------------
    # resolucao de simbolos
    # ------------------------------------------------------------------

    def _resolve_symbols(self) -> bool:
        """Obtem symbolId para cada ativo. Retorna False se falhar."""
        try:
            for sym in SYMBOLS:
                result = call_mcp("get_symbols", {"query": sym})
                if isinstance(result, dict) and "symbolId" in result:
                    self.symbol_ids[sym] = result["symbolId"]
                elif isinstance(result, list) and result:
                    self.symbol_ids[sym] = result[0].get("symbolId", 0)
                else:
                    logger.error("Simbolo nao encontrado: %s", sym)
            return len(self.symbol_ids) > 0
        except (MCPTimeoutError, MCPConnectionError) as e:
            logger.error("Falha ao resolver simbolos: %s", e)
            return False

    # ------------------------------------------------------------------
    # polls
    # ------------------------------------------------------------------

    def _poll_tick(self, sym: str) -> dict[str, Any]:
        """Poll de 3s: spot + DOM."""
        sid = self.symbol_ids.get(sym)
        if not sid:
            return {}

        spot = call_mcp("get_spot_prices", {"symbolId": sid})
        # DOM pode nao estar disponivel em todas as versoes
        try:
            dom = call_mcp("get_dom", {"symbolId": sid})
        except Exception:
            dom = {}

        return {
            "symbol": sym,
            "bid": spot.get("bid", 0),
            "ask": spot.get("ask", 0),
            "spread": spot.get("spread", 0),
            "dom_bid_wall": dom.get("bidWall", 0) if dom else 0,
            "dom_ask_wall": dom.get("askWall", 0) if dom else 0,
        }

    def _poll_candles_and_sentiment(self) -> dict[str, Any]:
        """Poll de 60s: candles 1min + sentiment + DXY."""
        result: dict[str, Any] = {"candles": {}, "sentiment_ratio": 0.5, "dxy_close": 0.0}

        # candles para cada simbolo
        for sym in SYMBOLS:
            sid = self.symbol_ids.get(sym)
            if not sid:
                continue
            try:
                bars = call_mcp("get_trendbars", {
                    "symbolId": sid,
                    "timeframe": "m1",
                    "count": 2,
                })
                if isinstance(bars, list) and bars:
                    result["candles"][sym] = bars[-1]  # ultimo candle
            except Exception as e:
                logger.error("Falha trendbars %s: %s", sym, e)

        # sentimento
        try:
            stats = call_mcp("get_account_statistics")
            long_pct = stats.get("longPercentage", 50) / 100.0
            result["sentiment_ratio"] = long_pct
        except Exception as e:
            logger.error("Falha ao obter sentimento: %s", e)

        # DXY proxy
        dxy_sid = self.symbol_ids.get(DXY_PROXY)
        if dxy_sid:
            try:
                bars = call_mcp("get_trendbars", {
                    "symbolId": dxy_sid,
                    "timeframe": "m1",
                    "count": 1,
                })
                if isinstance(bars, list) and bars:
                    result["dxy_close"] = bars[0].get("close", 0)
            except Exception as e:
                logger.error("Falha ao obter DXY proxy: %s", e)

        return result

    # ------------------------------------------------------------------
    # agregacao
    # ------------------------------------------------------------------

    def _append_to_df(self, tick_data: dict[str, Any], candle_data: dict[str, Any], sentiment: float, dxy: float):
        """Adiciona uma linha ao df_master."""
        sym = tick_data.get("symbol", "")
        candle = candle_data.get(sym, {})

        row = {
            "timestamp": datetime.now(UTC).isoformat(),
            "symbol": sym,
            "open": candle.get("open", tick_data.get("bid", 0)),
            "high": candle.get("high", tick_data.get("ask", 0)),
            "low": candle.get("low", tick_data.get("bid", 0)),
            "close": candle.get("close", tick_data.get("bid", 0)),
            "tick_volume": candle.get("tickVolume", 0),
            "spread": tick_data.get("spread", 0),
            "bid": tick_data.get("bid", 0),
            "ask": tick_data.get("ask", 0),
            "dom_bid_wall": tick_data.get("dom_bid_wall", 0),
            "dom_ask_wall": tick_data.get("dom_ask_wall", 0),
            "sentiment_ratio": sentiment,
            "dxy_close": dxy,
        }
        self.df = pd.concat([self.df, pd.DataFrame([row])], ignore_index=True)

    # ------------------------------------------------------------------
    # persistencia
    # ------------------------------------------------------------------

    def _save_parquet(self):
        """Salva snapshot para disco."""
        if self.df.empty:
            return
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = self.data_dir / f"f0_{ts}.parquet"
        self.df.to_parquet(path, index=False)
        logger.info("Parquet salvo: %s (%d linhas)", path, len(self.df))

    # ------------------------------------------------------------------
    # loop principal
    # ------------------------------------------------------------------

    def run(self, hours: float = 0):
        """Loop de coleta. hours=0 -> infinito."""
        logger.info("=== F0 COLECTOR INICIADO === dry_run=%s horas=%s", self.dry_run, hours or "infinito")

        # resolve simbolos
        if not self._resolve_symbols():
            logger.error("Falha ao resolver simbolos. Abortando.")
            return

        logger.info("Simbolos resolvidos: %s", list(self.symbol_ids.keys()))

        deadline = time.monotonic() + hours * 3600 if hours > 0 else float("inf")
        candle_sentiment: dict[str, Any] = {"candles": {}, "sentiment_ratio": 0.5, "dxy_close": 0.0}
        last_save = time.monotonic()

        while not shutdown_flag and time.monotonic() < deadline:
            try:
                now = time.monotonic()

                # ---- poll tick (3s) ----
                for sym in SYMBOLS:
                    tick = self._poll_tick(sym)
                    if tick:
                        self._append_to_df(
                            tick,
                            candle_sentiment["candles"],
                            candle_sentiment["sentiment_ratio"],
                            candle_sentiment["dxy_close"],
                        )

                # ---- poll candle (60s) ----
                if now - self.last_candle_poll >= POLL_CANDLE_INTERVAL:
                    candle_sentiment = self._poll_candles_and_sentiment()
                    self.last_candle_poll = now

                # ---- save parquet (1h) ----
                if now - last_save >= 3600:
                    self._save_parquet()
                    last_save = now

                self.consecutive_errors = 0

            except (MCPTimeoutError, MCPConnectionError) as e:
                self.consecutive_errors += 1
                logger.error("Erro MCP (%d/%d): %s", self.consecutive_errors, RECONNECT_MAX_RETRIES, e)
                if self.consecutive_errors >= RECONNECT_MAX_RETRIES:
                    logger.error("Reconectando MCP...")
                    time.sleep(2)
                    self.consecutive_errors = 0
                else:
                    time.sleep(1)

            # intervalo entre ciclos
            time.sleep(POLL_TICK_INTERVAL)

        # -------- encerramento --------
        self._save_parquet()
        uptime = time.monotonic() - self.start_time
        logger.info(
            "=== F0 COLECTOR ENCERRADO === uptime=%.0fs linhas=%d simbolos=%d",
            uptime, len(self.df), len(self.symbol_ids),
        )


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="F0 Coletor — cTrader MCP")
    parser.add_argument("--dry-run", action="store_true", help="Apenas coleta, sem pipeline")
    parser.add_argument("--hours", type=float, default=0, help="Tempo maximo (0=infinito)")
    parser.add_argument("--mcp-url", default="http://localhost:8080/mcp", help="Endpoint MCP")
    parser.add_argument("--data-dir", default="data", help="Diretorio de saida dos parquets")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    init_client(args.mcp_url, timeout=2.0)

    collector = Collector(dry_run=args.dry_run, data_dir=args.data_dir)
    collector.run(hours=args.hours)


if __name__ == "__main__":
    main()
