"""PROPOSITO: Scalp Timeout — verifica timeout do periodo de scalp (F4 satelite).
SPEC: S6
ROADMAP: 4.4 — split de _orc_orders.py.
"""

from __future__ import annotations

import time
from typing import Any

from f4_executor.entry_params_orc_ordens import ORDER_PARAMS


def check_scalp_timeout(
    symbol: str, timeframe: str, entry_time: float, current_pnl_pct: float,
) -> dict[str, Any]:
    """Verifica se posicao excedeu o timeout do scalp.
    Preserva ganhos parciais (>=15% do TP) e corta perdas.
    """
    timeout_min = ORDER_PARAMS["scalp_timeout"].get(timeframe, 15)
    elapsed_min = (time.time() - entry_time) / 60
    remaining_min = max(0, timeout_min - elapsed_min)

    should_close = False
    reason = ""

    if elapsed_min >= timeout_min:
        if current_pnl_pct >= ORDER_PARAMS["scalp_min_pnl_pct"]:
            should_close = True
            reason = (
                f"Timeout {timeframe} ({timeout_min}min) — "
                f"PnL {current_pnl_pct:.1%} >= {ORDER_PARAMS['scalp_min_pnl_pct']:.0%}"
            )
        elif ORDER_PARAMS["scalp_close_loss"]:
            should_close = True
            reason = f"Timeout {timeframe} ({timeout_min}min) — cortando perda ({current_pnl_pct:.1%})"

    return {
        "should_close": should_close, "reason": reason,
        "elapsed_min": round(elapsed_min, 1), "timeout_min": timeout_min,
        "remaining_min": round(remaining_min, 1),
        "current_pnl_pct": round(current_pnl_pct, 4),
    }
