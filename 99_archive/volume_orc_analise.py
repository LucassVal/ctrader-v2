"""
PROPOSITO: F1 — DETECTOR DE VOLUME SPIKE
SPEC: S3
ROADMAP: 2.4
"""

from __future__ import annotations

from typing import Any


def detect_volume_spike(
    bars: list[dict[str, Any]],
    window: int = 20,
    multiplier: float = 2.0,
) -> dict[str, Any]:
    """Detecta se o tick_volume atual é um spike (>multiplier x média).

    Args:
        bars: lista de trendbars com campo 'tickVolume'
        window: janela para média móvel (default 20)
        multiplier: fator spike (default 2.0 = 2x média)

    Returns:
        {spike: bool, ratio: float, avg_vol: float, current_vol: float, signal: str}
    """
    if not bars or len(bars) < window + 1:
        return {"spike": False, "ratio": 1.0, "avg_vol": 0, "current_vol": 0, "signal": "INSUFICIENTE"}

    volumes = []
    for b in bars[-window - 1:]:
        tv = b.get("tickVolume", 0)
        if isinstance(tv, (int, float)):
            volumes.append(float(tv))

    if len(volumes) < window:
        return {"spike": False, "ratio": 1.0, "avg_vol": 0, "current_vol": 0, "signal": "INSUFICIENTE"}

    historical = volumes[:-1]
    current = volumes[-1]
    avg = sum(historical) / len(historical) if historical else 0

    if avg <= 0:
        return {"spike": False, "ratio": 1.0, "avg_vol": 0, "current_vol": current, "signal": "NEUTRO"}

    ratio = current / avg

    if ratio >= multiplier:
        signal = "SPIKE_ALTA"  # possível entrada institucional/breakout
    elif ratio <= 1.0 / multiplier:
        signal = "SPIKE_BAIXA"  # baixa participação, cautela
    else:
        signal = "NEUTRO"

    return {
        "spike": ratio >= multiplier,
        "ratio": round(ratio, 2),
        "avg_vol": round(avg, 0),
        "current_vol": current,
        "signal": signal,
    }


def calculate_volume_trend(
    bars: list[dict[str, Any]],
    short_window: int = 5,
    long_window: int = 20,
) -> dict[str, Any]:
    """Tendência de volume: ratio SMA_short / SMA_long.

    Returns:
        {trend: str, ratio: float, short_avg: float, long_avg: float}
    """
    volumes = []
    for b in bars:
        tv = b.get("tickVolume", 0)
        if isinstance(tv, (int, float)):
            volumes.append(float(tv))

    if len(volumes) < long_window:
        return {"trend": "INSUFICIENTE", "ratio": 1.0, "short_avg": 0, "long_avg": 0}

    short_avg = sum(volumes[-short_window:]) / short_window
    long_avg = sum(volumes[-long_window:]) / long_window

    if long_avg <= 0:
        return {"trend": "NEUTRO", "ratio": 1.0, "short_avg": short_avg, "long_avg": long_avg}

    ratio = short_avg / long_avg

    if ratio > 1.3:
        trend = "CRESCENTE"  # volume aumentando — confirma tendência
    elif ratio < 0.7:
        trend = "DECRESCENTE"  # volume caindo — tendência fraca
    else:
        trend = "ESTAVEL"

    return {
        "trend": trend,
        "ratio": round(ratio, 2),
        "short_avg": round(short_avg, 0),
        "long_avg": round(long_avg, 0),
    }
