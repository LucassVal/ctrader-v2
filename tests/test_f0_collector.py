"""
TASK: Harness F0 — Coleta
Testa funções puras de _storage.py: df_master schema, append, parquet roundtrip.
Sem mock/stub — determinístico.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from f0_collector.storage_orc_coleta import append_to_df, make_empty_df


def test_df_master_schema():
    """df_master deve ter as 12 colunas esperadas."""
    df = make_empty_df()
    expected = [
        "timestamp", "symbol", "open", "high", "low", "close",
        "tick_volume", "spread", "bid", "ask",
        "sentiment_ratio", "dxy_close",
    ]
    for col in expected:
        assert col in df.columns, f"Coluna ausente: {col}"
    assert len(df) == 0, "df_master deve iniciar vazio"


def test_append_to_df():
    """append_to_df adiciona linha corretamente."""
    df = make_empty_df()
    tick = {"bid": 1.0850, "ask": 1.0852, "spread": 0.0002, "symbol": "EURUSD"}
    candle = {"EURUSD": {"open": 1.0840, "high": 1.0860, "low": 1.0835, "close": 1.0851, "tickVolume": 150}}

    df = append_to_df(df, tick, candle, sentiment=0.62, dxy=1.0850)
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "EURUSD"
    assert df.iloc[0]["bid"] == 1.0850
    assert df.iloc[0]["sentiment_ratio"] == 0.62


def test_append_preserves_order():
    """Linhas mantêm ordem cronológica."""
    df = make_empty_df()
    for i in range(5):
        tick = {"bid": 1.0 + i * 0.01, "ask": 1.01 + i * 0.01, "spread": 0.01, "symbol": "EURUSD"}
        candle = {}
        df = append_to_df(df, tick, candle, sentiment=0.5, dxy=1.0)
    assert len(df) == 5
    assert df.iloc[0]["bid"] == 1.0
    assert df.iloc[4]["bid"] == 1.04


def test_missing_tick_doesnt_break():
    """append_to_df com tick sem symbol não quebra."""
    df = make_empty_df()
    tick = {"bid": 110.0, "ask": 110.2}
    candle = {}
    df = append_to_df(df, tick, candle, sentiment=0.5, dxy=1.0)
    assert len(df) == 1


def test_parquet_roundtrip(tmp_path):
    """save_parquet e read_parquet sao roundtrip."""
    from f0_collector.storage_orc_coleta import save_parquet

    df = make_empty_df()
    for i in range(3):
        tick = {"bid": 2000.0 + i, "ask": 2000.5 + i, "spread": 0.5, "symbol": "XAUUSD"}
        candle = {}
        df = append_to_df(df, tick, candle, sentiment=0.6, dxy=104.0)

    save_parquet(df, str(tmp_path))
    files = list(Path(tmp_path).glob("*.parquet"))
    assert len(files) > 0, "Nenhum parquet salvo"
    reloaded = pd.read_parquet(files[0])
    assert len(reloaded) == 3
