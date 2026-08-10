"""
PROPOSITO: Fusion Output
SPEC: S4
ROADMAP: 3.0
"""

from __future__ import annotations

from typing import TypedDict


class MetaContract(TypedDict):
    trace_id: str
    timestamp_utc: str
    symbol: str  # "XAUUSD" | "EURUSD" | "GBPUSD" | "USDJPY" | "AUDUSD"
    timeframe: str  # "M_5" | "M_15"  (M_10 nao existe)
    slot_used: int
    slot_max: int
    positions_open_symbol: int


class ScorePillar(TypedDict):
    raw: float
    weight: float
    weighted: float


class ScoresContract(TypedDict):
    macro: ScorePillar
    volatilidade: ScorePillar
    tecnico: ScorePillar
    final_raw: float
    reducers_applied: list[str]
    final_adjusted: float
    threshold: float


class ContextContract(TypedDict):
    news_imminent: bool
    spread_pips: float
    session: str  # "SYDNEY" | "TOKYO" | "LONDON" | "NY" | "OVERLAP"
    dxy_trend: str  # "BULLISH" | "BEARISH" | "FLAT"
    atr_14_m5: float
    atr_14_m15: float
    sentiment_ratio: float
    dom_imbalance: float


class AdjustmentsContract(TypedDict):
    lot_multiplier: float
    timeout_min: int
    be_trigger_pct: int


class VerdictContract(TypedDict):
    source: str  # "deepseek_pro" | "mechanical_fallback" | "threshold" | "mcp_pre_check"
    decision: str  # "APPROVE" | "REJECT"
    confidence: float
    reason: str
    reason_detail: str
    adjustments: AdjustmentsContract


class FusionOutput(TypedDict):
    """Schema imutável — blueprint §3."""
    meta: MetaContract
    scores: ScoresContract
    context: ContextContract
    verdict: VerdictContract


# Contrato de entrada da F1
class ScoresRaw(TypedDict):
    trace_id: str
    timestamp_utc: str
    symbol: str
    news_imminent: bool
    scores: dict[str, float]  # {"macro": 72, "volatilidade": 58, "tecnico": 81}


# Contrato de entrada da F4
class ExecutionLog(TypedDict):
    trace_id: str
    symbol: str
    direction: str  # "BUY" | "SELL"
    entry_price: float
    volume: int
    sl_initial: float
    tp_initial: float
    exit_price: float
    exit_reason: str
    pnl_gross: float
    pnl_net: float
    duration_seconds: int
    trail_activated: bool
    be_locked: bool


# Contrato de saída da F5
class CustomRules(TypedDict):
    version: int
    total_trades: int
    last_updated_utc: str
    weights: dict[str, float]
    threshold: float
    stats: dict[str, float]
