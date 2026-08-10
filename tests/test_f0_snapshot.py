"""PROPOSITO: H1.4 — Harness snapshot F0 (hub de dados)
SPEC: S2
ROADMAP: 1.6 — Snapshot unico por ciclo, F1/F4/F5 consomem sem MCP direto.
Sem mock/stub — deterministico.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from f0_collector.orc_coleta import get_snapshot, take_snapshot


@pytest.mark.skip(reason="Requer MCP ativo — roda manualmente com MCP online")
def test_take_snapshot_returns_dict(tmp_path, monkeypatch) -> None:
    """take_snapshot retorna dict com campos obrigatorios (MCP pode estar offline)."""
    monkeypatch.setattr("f0_collector.orc_coleta._SNAPSHOT_PATH", tmp_path / "snapshot.json")
    snap = take_snapshot()
    assert isinstance(snap, dict)
    for field in ("timestamp_utc", "symbols", "balance", "positions", "online"):
        assert field in snap, f"Campo ausente: {field}"


def test_get_snapshot_has_5_symbols() -> None:
    """Snapshot do disco contem 5 simbolos (leitura, sem MCP)."""
    snap = get_snapshot()
    if snap is None:
        return  # skip se snapshot nao existe ainda
    assert len(snap["symbols"]) == 5, f"Simbolos: {len(snap['symbols'])}"
    for sym in ("XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"):
        assert sym in snap["symbols"], f"Simbolo ausente: {sym}"


def test_get_snapshot_symbol_schema() -> None:
    """Cada simbolo no snapshot do disco tem OHLCV + spot."""
    snap = get_snapshot()
    if snap is None:
        return
    fields = {"symbol", "timestamp", "open", "high", "low", "close",
              "tick_volume", "bid", "ask", "spread"}
    for sym, data in snap["symbols"].items():
        missing = fields - set(data.keys())
        assert not missing, f"{sym}: campos ausentes {missing}"


def test_get_snapshot_reads_back(tmp_path, monkeypatch) -> None:
    """get_snapshot le o que take_snapshot escreveu."""
    monkeypatch.setattr("f0_collector.orc_coleta._SNAPSHOT_PATH", tmp_path / "snapshot.json")
    snap1 = take_snapshot()
    snap2 = get_snapshot()
    assert snap2 is not None, "get_snapshot retornou None"
    assert snap2["timestamp_utc"] == snap1["timestamp_utc"]
    assert len(snap2["symbols"]) == 5


def test_get_snapshot_file_exists() -> None:
    """Snapshot file existe no disco."""
    snap_path = Path(__file__).resolve().parent.parent / "status" / "snapshot.json"
    assert snap_path.exists(), f"Arquivo nao encontrado: {snap_path}"
    data = json.loads(snap_path.read_text(encoding="utf-8"))
    assert "symbols" in data
