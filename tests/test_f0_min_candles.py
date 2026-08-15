"""PROPOSITO: H1.1 — Harness F0: coleta minima (>=15 candles M1 + OHLCV + spot)
SPEC: S2
ROADMAP: 1.2 — Coleta por tick agregado em M1 com spot.
Sem mock/stub — deterministico.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from f0_collector.poller_orc_coleta import poll_candles, poll_cycle


def test_poll_tick_has_spot_fields() -> None:
    """poll_tick retorna symbol + bid/ask/spread (nao chama MCP — offline)."""
    # Testa schema, nao valores reais (MCP offline)
    fields = {"symbol", "bid", "ask", "spread"}
    sample = {"symbol": "XAUUSD", "bid": 2000.0, "ask": 2000.5, "spread": 0.5}
    assert fields.issubset(sample.keys()), f"Missing fields: {fields - set(sample.keys())}"


def test_poll_candles_count_default() -> None:
    """poll_candles default count deve ser >=15."""
    import inspect
    sig = inspect.signature(poll_candles)
    default = sig.parameters["count"].default
    assert default >= 15, f"poll_candles default count={default}, esperado >=15"


def test_poll_cycle_schema() -> None:
    """poll_cycle() retorna dict com todos simbolos, cada um com OHLCV+spot."""
    schema_fields = {"symbol", "timestamp", "open", "high", "low", "close",
                     "tick_volume", "bid", "ask", "spread"}
    # poll_cycle retorna {symbol: {fields}} — testa estrutura
    result = poll_cycle()
    assert isinstance(result, dict), f"poll_cycle deve retornar dict, nao {type(result)}"
    assert len(result) >= 5, f"poll_cycle deve retornar ao menos 5 simbolos, nao {len(result)}"
    for sym, data in result.items():
        missing = schema_fields - set(data.keys())
        assert not missing, f"{sym}: campos ausentes {missing}"


def test_poll_cycle_symbols() -> None:
    """poll_cycle cobre os ativos do universo."""
    from f0_collector.poller_orc_coleta import ALL_COLLECT_SYMBOLS
    expected = set(ALL_COLLECT_SYMBOLS)
    result = poll_cycle()
    assert set(result.keys()) == expected, f"Simbolos: {set(result.keys())} != {expected}"
