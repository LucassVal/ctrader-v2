"""PROPOSITO: Orc Orders — orquestrador F4 de ordens (OCO + trail + BE + scalp).
SPEC: S6 (pai) — satelites: _entry_params, _oco, _scalp_timeout, _trail_log
ROADMAP: 4.4 — split DDD (261L -> ~40L orquestrador + 4 satelites <80L)
FLOW:   _entry_params (config + calculo) -> _oco (validacao + execucao)
        _scalp_timeout (timeout) | _trail_log (dashboard)
        Trail/BE em _monitor.py (D0->D40->D60->D80 degraus)
"""

from __future__ import annotations

# Re-export para compatibilidade
from f4_executor.entry_params_orc_ordens import (
    ORDER_PARAMS,
    calculate_entry_params,
    get_params,
)
from f4_executor.oco_orc_ordens import execute_oco_order, validate_signal_for_entry
from f4_executor.scalp_timeout_orc_ordens import check_scalp_timeout

# get_trail_log movido para utils/json_log_orc_metricas.py

__all__ = [
    "ORDER_PARAMS",
    "calculate_entry_params",
    "check_scalp_timeout",
    "execute_oco_order",
    "get_params",
        "validate_signal_for_entry",
]
