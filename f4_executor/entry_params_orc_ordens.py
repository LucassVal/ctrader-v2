"""PROPOSITO: Entry Params — config e calculo de SL/TP/BE (F4 satelite).
SPEC: S6
ROADMAP: 4.4 — split de _orc_orders.py (261L -> <80L).
"""

from __future__ import annotations

from typing import Any

# ═══════════════════════════════════════════════════════════════
# PARAMETROS DE ORDEM (spec-driven)
# ═══════════════════════════════════════════════════════════════

ORDER_PARAMS: dict[str, Any] = {
    "rr_ratio": 2.0,
    "retirada_80_pct": 0.80,
    "retirada_20_residual": 0.20,
    "saida_60_pct": 0.60,
    "be_trigger_pct": 0.60,
    "trail_d60_pct": 0.30,
    "spread_factor": 2.0,
    "scalp_timeout": {"M_5": 5, "M_15": 15},
    "scalp_min_pnl_pct": 0.15,
    "scalp_close_loss": True,
}


def get_params() -> dict[str, Any]:
    """Retorna parametros ativos de ordem."""
    return {
        "params": ORDER_PARAMS,
        "be_rule": "BE = entry + spread(entrada+saida) via MCP get_spot_prices",
        "oco_rule": "OCO: STOP_LOSS + TAKE_PROFIT na mesma ordem",
        "trail_rule": (
            "D0: SL original | D40: registra | "
            "D60: SL sobe para BE (entrada + 2xspread) | "
            "D80: fecha 80%, SL vira BE, deixa 20% correr | "
            "Saida: topo ou retrocesso a 60% do ganho maximo"
        ),
        "mitigacao_perdas": "BE ao atingir D60 evita que posicao volte ao negativo",
    }


def calculate_entry_params(
    symbol: str, side: str, entry_price: float, atr: float,
    lot_size: float = 0.1,
) -> dict[str, Any]:
    """Calcula SL, TP, BE e niveis de saida a partir do ATR."""
    rr = ORDER_PARAMS["rr_ratio"]
    spread_factor = ORDER_PARAMS["spread_factor"]
    spread_est = 0.0002 if "JPY" not in symbol else 0.02

    if side.upper() == "BUY":
        sl = entry_price - atr
        tp = entry_price + atr * rr
        be = entry_price + spread_est * spread_factor
        exit_80 = entry_price + (tp - entry_price) * ORDER_PARAMS["retirada_80_pct"]
        exit_60 = entry_price + (tp - entry_price) * ORDER_PARAMS["saida_60_pct"]
    else:
        sl = entry_price + atr
        tp = entry_price - atr * rr
        be = entry_price - spread_est * spread_factor
        exit_80 = entry_price - (entry_price - tp) * ORDER_PARAMS["retirada_80_pct"]
        exit_60 = entry_price - (entry_price - tp) * ORDER_PARAMS["saida_60_pct"]

    return {
        "symbol": symbol, "side": side.upper(), "entry_price": entry_price,
        "atr": atr, "lot_size": lot_size,
        "sl": round(sl, 5), "tp": round(tp, 5), "be": round(be, 5),
        "spread_est": spread_est,
        "exit_80pct": round(exit_80, 5), "exit_60pct": round(exit_60, 5),
        "sl_pips": int(atr * 100_000) if "JPY" not in symbol else int(atr * 1000),
        "tp_pips": int(atr * rr * 100_000) if "JPY" not in symbol else int(atr * rr * 1000),
        "params": ORDER_PARAMS,
    }
