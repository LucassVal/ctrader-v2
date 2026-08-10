"""
PROPOSITO: T8
SPEC: S0
ROADMAP: D.3
"""

from __future__ import annotations

from datetime import UTC, datetime

SESSIONS = {
    "SYDNEY":  {"start_utc": 22, "end_utc": 7},    # 22:00-07:00
    "TOKYO":   {"start_utc": 0,  "end_utc": 9},     # 00:00-09:00
    "LONDON":  {"start_utc": 8,  "end_utc": 17},    # 08:00-17:00
    "NY":      {"start_utc": 13, "end_utc": 22},    # 13:00-22:00
}

ROLLOVER_START_UTC = 21
ROLLOVER_END_UTC = 22
ROLLOVER_MINUTE_START = 55
ROLLOVER_MINUTE_END = 5


def _hour_in_range(hour: int, start: int, end: int) -> bool:
    """Verifica se hour esta em [start, end), lidando com virada de dia."""
    if start <= end:
        return start <= hour < end
    else:
        return hour >= start or hour < end


def get_current_session(dt: datetime | None = None) -> str:
    """Retorna a sessao atual baseada no horario UTC.

    Returns:
        "SYDNEY" | "TOKYO" | "LONDON" | "NY" | "OVERLAP" | "LOW_LIQUIDITY"
    """
    if dt is None:
        dt = datetime.now(UTC)
    hour = dt.hour

    active = [
        name for name, s in SESSIONS.items()
        if _hour_in_range(hour, s["start_utc"], s["end_utc"])
    ]

    if len(active) == 0:
        return "LOW_LIQUIDITY"
    if len(active) >= 2:
        return "OVERLAP"
    return active[0]


def is_sydney(dt: datetime | None = None) -> bool:
    """True se estamos na sessao de Sydney (baixa liquidez)."""
    return get_current_session(dt) == "SYDNEY"


def is_rollover(dt: datetime | None = None) -> bool:
    """True se estamos na janela de rollover (21:55-22:05 UTC)."""
    if dt is None:
        dt = datetime.now(UTC)
    h, m = dt.hour, dt.minute
    return (
        (h == ROLLOVER_START_UTC and m >= ROLLOVER_MINUTE_START)
        or (h == ROLLOVER_END_UTC and m <= ROLLOVER_MINUTE_END)
    )


def is_trading_allowed(dt: datetime | None = None) -> tuple[bool, str]:
    """Retorna (permitido, motivo)."""
    if is_rollover(dt):
        return False, "ROLLOVER"
    if is_sydney(dt):
        return False, "SYDNEY_LOW_LIQUIDITY"
    return True, get_current_session(dt)
