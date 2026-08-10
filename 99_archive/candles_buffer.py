"""PROPOSITO: Rolling buffer de velas M_1 para calculo multi-timeframe (S25.9).
SPEC: S25
ROADMAP: Multi-Timeframe
Mantem as ultimas 360 velas por simbolo em status/candles_buffer.json.
Nao armazena candles dummy (ts=0 ou open=close=0).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT: Path = Path(__file__).resolve().parent.parent
BUFFER_PATH: Path = ROOT / "status" / "candles_buffer.json"
MAX_CANDLES: int = 360


def _load() -> dict[str, list[dict[str, Any]]]:
    """Carrega buffer do disco."""
    try:
        if BUFFER_PATH.exists():
            return json.loads(BUFFER_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _save(data: dict[str, list[dict[str, Any]]]) -> None:
    """Salva buffer no disco."""
    BUFFER_PATH.parent.mkdir(parents=True, exist_ok=True)
    BUFFER_PATH.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def push(symbol: str, candle: dict) -> None:
    """Adiciona uma vela M_1 ao buffer. Rolling: max 360 velas. Pula dummies."""
    ts = int(candle.get("timestamp_utc", 0) or 0)
    if ts == 0:
        return
    o_val = float(candle.get("open", 0))
    c_val = float(candle.get("close", 0))
    if o_val == 0 and c_val == 0:
        return
    h_val = float(candle.get("high", 0))
    lo_val = float(candle.get("low", 0))

    data = _load()
    existing = data.get(symbol, [])
    # Ignorar velas com timestamp duplicado
    if existing and existing[-1].get("ts") == ts:
        return
    existing.append({"ts": ts, "o": o_val, "h": h_val, "l": lo_val, "c": c_val})
    if len(existing) > MAX_CANDLES:
        existing = existing[-MAX_CANDLES:]
    data[symbol] = existing
    _save(data)


def get_window(symbol: str, count: int) -> list[dict[str, Any]]:
    """Ultimas N velas do simbolo. Filtra dummies automaticamente."""
    data = _load()
    candles = data.get(symbol, [])
    valid = [c for c in candles if c.get("ts") and c.get("o") != 0]
    return valid[-count:] if count <= len(valid) else valid
