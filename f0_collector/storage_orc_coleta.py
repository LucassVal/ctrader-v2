"""
PROPOSITO: T4 — STORAGE
SPEC: S2
ROADMAP: 1.3
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

COLUMNS = [
    "timestamp", "symbol", "open", "high", "low", "close",
    "tick_volume", "spread", "bid", "ask",
    "dom_bid_wall", "dom_ask_wall", "sentiment_ratio", "dxy_close",
]


def make_empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=COLUMNS)


def append_to_df(df: pd.DataFrame, tick_data: dict[str, Any],
                 candle_data: dict[str, Any], sentiment: float,
                 dxy: float) -> pd.DataFrame:
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
        # poll_cycle() normaliza para snake_case; MCP cru manda camelCase.
        # Aceita os dois (mesmo padrao do poller) — so tickVolume zerava o volume.
        "tick_volume": candle.get("tick_volume", candle.get("tickVolume", 0)),
        "spread": tick_data.get("spread", 0),
        "bid": tick_data.get("bid", 0),
        "ask": tick_data.get("ask", 0),
        "dom_bid_wall": tick_data.get("dom_bid_wall", 0),
        "dom_ask_wall": tick_data.get("dom_ask_wall", 0),
        "sentiment_ratio": sentiment,
        "dxy_close": dxy,
    }
    return pd.concat([df, pd.DataFrame([row])], ignore_index=True)


def save_parquet(df: pd.DataFrame, data_dir: str = "data") -> Path | None:
    """Salva snapshot para disco."""
    if df.empty:
        return None
    ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    path = Path(data_dir) / f"f0_{ts}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    logger.info("Parquet salvo: %s (%d linhas)", path, len(df))
    return path


def load_parquet(path: Path | str) -> pd.DataFrame:
    """Carrega parquet do disco."""
    return pd.read_parquet(path)


def save_backfill_parquet(df: pd.DataFrame, data_dir: str, symbol: str) -> Path:
    """Salva parquet de backfill particionado por simbolo."""
    out_dir = Path(data_dir) / "backfill"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{symbol}_M1.parquet"
    df.to_parquet(path, index=False)
    logger.info("Backfill salvo: %s (%d linhas)", path, len(df))
    return path


def append_rows(df: pd.DataFrame, rows: list[dict[str, Any]]) -> pd.DataFrame:
    """Append em lote (para backfill)."""
    if not rows:
        return df
    new_df = pd.DataFrame(rows)
    return pd.concat([df, new_df], ignore_index=True)
