"""
PROPOSITO: Poller F0 — coleta de spot + candles M1 por ciclo
SPEC: S2
ROADMAP: 1.2
FLOW:   MCP (remoto) -> poll_cycle() -> _orc_f0.take_snapshot()
        backfill_symbol() -> save_backfill_parquet()
"""

from __future__ import annotations

import logging
from datetime import UTC
from typing import Any

from utils.mcp_client import get_balance, get_spot_prices, get_trendbars

logger = logging.getLogger(__name__)


def poll_tick(symbol: str) -> dict[str, Any]:
    """Poll de 3s: spot. Retorna schema com zeros se MCP offline (harness)."""
    try:
        spot = get_spot_prices(symbol=symbol)
        return {
            "symbol": symbol,
            "bid": spot.get("bid", 0),
            "ask": spot.get("ask", 0),
            "spread": spot.get("spread") or (spot.get("ask", 0) - spot.get("bid", 0)),
        }
    except Exception:
        return {"symbol": symbol, "bid": 0, "ask": 0, "spread": 0}


def poll_candles(symbol: str, timeframe: str = "m1", count: int = 15) -> dict[str, Any] | None:
    """Poll de 60s: candles M1 (min 15 para F1 ter serie estatistica)."""
    try:
        bars = get_trendbars(symbol=symbol, timeframe=timeframe, count=count)
        if isinstance(bars, list) and bars:
            return bars[-1]
    except Exception as e:
        logger.error("Falha trendbars %s: %s", symbol, e)
    return None


def poll_sentiment() -> float:
    """Sentimento da conta (long %)."""
    try:
        _ = get_balance()  # verifica conectividade
        return 0.5  # MCP v0.4.0 nao tem endpoint de sentimento
    except Exception:
        return 0.5


# Universo de ativos (spec S2 + S5.1)
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]

# Indices macro — coleta de dados (nao trading)
INDEX_SYMBOLS = ["DXYUSD", "VIXUSD"]

# Todos os simbolos para coleta (ativos + indices)
ALL_COLLECT_SYMBOLS = SYMBOLS + INDEX_SYMBOLS


def poll_cycle() -> dict[str, dict[str, Any]]:
    """Coleta unificada por ciclo (ROADMAP 1.2 + 1.6): spot + ultima candle M1.

    Para cada um dos 5 ativos, retorna dict com:
      symbol, timestamp, open, high, low, close, tick_volume, bid, ask, spread

    tick_volume = proxy de atividade (ticks brutos nao existem no MCP).
    Offline: retorna schema dummy para testes (MCP offline nao quebra harness).
    """
    result: dict[str, dict[str, Any]] = {}
    for sym in ALL_COLLECT_SYMBOLS:
        spot = poll_tick(sym)
        candle = poll_candles(sym, timeframe="m1", count=15)
        if candle is None:
            candle = {}
        result[sym] = {
            "symbol": sym,
            "timestamp": candle.get("timestamp", 0),
            "open": candle.get("open", 0),
            "high": candle.get("high", 0),
            "low": candle.get("low", 0),
            "close": candle.get("close", 0),
            "tick_volume": candle.get("tickVolume", candle.get("tick_volume", candle.get("volume", 0))),
            "bid": spot.get("bid", 0),
            "ask": spot.get("ask", 0),
            "spread": spot.get("spread") or (spot.get("ask", 0) - spot.get("bid", 0)),
        }
    return result


# ---------------------------------------------------------------------------
# Backfill 2 anos M_1 (ROADMAP 1.3) — throttle <=5 req/s via gateway 1.5
# ---------------------------------------------------------------------------

def backfill_symbol(symbol: str, data_dir: str = "data", years: int = 2,
                    count: int = 1000) -> int:
    """Backfill de M_1 para um simbolo. Retorna total de barras baixadas.

    Janelas de 30d encadeadas do presente para tras.
    Throttle delegado ao gateway (call_tool em mcp_client.py — ROADMAP 1.5).
    Salva parquet via _storage.save_backfill_parquet ao final.
    """
    import time as _t
    from datetime import datetime, timedelta

    from f0_collector.storage_orc_coleta import (
        append_rows,
        make_empty_df,
        save_backfill_parquet,
    )

    now = datetime.now(UTC)
    end = now
    start = now - timedelta(days=365 * years)
    window_days = 30  # cap 720h = 30d

    all_rows: list[dict[str, Any]] = []
    current = end
    total_bars = 0

    logger.info("Backfill %s: %s -> %s (%d anos, janelas de %dd)",
                symbol, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
                years, window_days)

    while current > start:
        from_dt = max(start, current - timedelta(days=window_days))
        from_ts = int(from_dt.timestamp() * 1000)
        to_ts = int(current.timestamp() * 1000)

        try:
            bars = get_trendbars(symbol=symbol, timeframe="m1", count=count,
                                 from_timestamp=from_ts, to_timestamp=to_ts)
            if isinstance(bars, list) and bars:
                for b in bars:
                    all_rows.append({
                        "symbol": symbol,
                        "timestamp": b.get("timestamp", 0),
                        "open": b.get("open", 0),
                        "high": b.get("high", 0),
                        "low": b.get("low", 0),
                        "close": b.get("close", 0),
                        "tick_volume": b.get("tickVolume", 0),
                        "bid": 0, "ask": 0, "spread": 0,  # backfill sem spot
                    })
                total_bars += len(bars)
                logger.info("  %s: %s -> %s = %d barras (total=%d)",
                            symbol, from_dt.strftime("%Y-%m-%d"),
                            current.strftime("%Y-%m-%d"), len(bars), total_bars)
        except Exception as e:
            logger.error("  %s: falha %s -> %s: %s",
                         symbol, from_dt.strftime("%Y-%m-%d"),
                         current.strftime("%Y-%m-%d"), str(e)[:80])

        current = from_dt
        _t.sleep(0.2)  # backoff entre janelas (throttle interno ao call_tool)

    if all_rows:
        df = make_empty_df()
        df_simple = append_rows(df, all_rows)
        path = save_backfill_parquet(df_simple, data_dir, symbol)
        logger.info("Backfill %s DONE: %d barras -> %s", symbol, total_bars, path)

    return total_bars


def backfill_all(data_dir: str = "data", years: int = 2) -> dict[str, int]:
    """Backfill M_1 para todos os 5 ativos. Retorna {symbol: barras}."""
    results: dict[str, int] = {}
    for sym in SYMBOLS:
        results[sym] = backfill_symbol(sym, data_dir=data_dir, years=years)
    total = sum(results.values())
    logger.info("Backfill ALL DONE: %d barras em %d simbolos", total, len(results))
    return results
