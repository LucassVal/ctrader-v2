"""PROPOSITO: H1.3 — Harness backfill 2 anos M_1
SPEC: S2
ROADMAP: 1.3 — Backfill com throttle <=5 req/s, parquet particionado.
Testa funcoes puras de _storage.py. Sem MCP.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from f0_collector.storage_orc_coleta import (
    append_rows,
    load_parquet,
    make_empty_df,
    save_backfill_parquet,
)


def test_make_empty_df_schema() -> None:
    """DataFrame vazio tem colunas do schema atual."""
    df = make_empty_df()
    assert len(df.columns) >= 8, f"Colunas insuficientes: {len(df.columns)}"


def test_append_rows_adds_data() -> None:
    """append_rows adiciona linhas em lote."""
    df = make_empty_df()
    rows = [{
        "symbol": "EURUSD", "timestamp": 1784800000000,
        "open": 1.10, "high": 1.11, "low": 1.09, "close": 1.105,
        "tick_volume": 100, "bid": 0, "ask": 0, "spread": 0,
    }]
    df2 = append_rows(df, rows)
    assert len(df2) == 1
    assert df2.iloc[0]["symbol"] == "EURUSD"


def test_parquet_roundtrip() -> None:
    """Parquet salva e carrega sem perda."""
    df = make_empty_df()
    rows = [
        {"symbol": "XAUUSD", "timestamp": 1784850000000 + i * 60000,
         "open": 3000.0 + i, "high": 3005.0, "low": 2995.0, "close": 3002.0,
         "tick_volume": 50, "bid": 0, "ask": 0, "spread": 0}
        for i in range(5)
    ]
    df2 = append_rows(df, rows)
    with tempfile.TemporaryDirectory() as tmp:
        path = save_backfill_parquet(df2, str(tmp), "XAUUSD")
        loaded = load_parquet(path)
        assert len(loaded) == 5


def test_empty_append_noop() -> None:
    """append_rows com lista vazia nao altera df."""
    df = make_empty_df()
    df2 = append_rows(df, [])
    assert len(df2) == 0
