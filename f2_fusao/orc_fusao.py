"""
PROPOSITO: F2 — Fusao ponderada. Score final = Sigma(componente x peso_F5).
SPEC: S4
ROADMAP: 3.0
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.schema_validator import validate_fusion_output
from utils.session_manager import get_current_session, is_rollover, is_sydney

logger = logging.getLogger(__name__)

DEFAULT_WEIGHTS = {"macro": 0.33, "volatilidade": 0.33, "tecnico": 0.34}
ENTRY_THRESHOLD = 70


def _generate_trace() -> str:
    return f"T{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-FUSION"


def _load_custom_rules(path: str = "custom_rules.json") -> dict[str, Any]:
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def fuse(scores_live: dict[str, Any], context: dict[str, Any] | None = None,
         rules_path: str = "custom_rules.json") -> dict[str, Any]:
    """Funde scores usando os dados calibrados reais (S36) lidos do score_live.json.

    S39/C4: score_live.json agora tem {symbols: {sym: {M1, M5, M15}}}.
    Scores multi-timeframe incluidos no breakdown.
    """

    symbols = scores_live.get("symbols", {})
    if not symbols:
        logger.error("Nenhum simbolo recebido em score_live.json")
        return {}

    rules = _load_custom_rules(rules_path)
    ctx = context or {}

    # Pre-calcula redutores globais
    global_reducers: list[str] = []
    global_reduction = 0

    if ctx.get("news_imminent"):
        global_reduction += 15
        global_reducers.append("NEWS_IMMINENT")

    spread = ctx.get("spread_pips", ctx.get("spread", 0))
    if spread > 2.0:
        global_reduction += 10
        global_reducers.append("SPREAD_ALTO")

    dom = ctx.get("dom_imbalance", 0)
    if abs(dom) > 0.7:
        global_reduction += 10
        global_reducers.append("DOM_WALL")

    if is_sydney():
        global_reduction += 20
        global_reducers.append("SYDNEY")

    if is_rollover():
        global_reduction = 999  # rejeicao total
        global_reducers.append("ROLLOVER")

    threshold = rules.get("threshold", ENTRY_THRESHOLD)

    breakdown = {}
    active_symbols = []

    for sym, data in symbols.items():
        # S39/C4: data agora e {M1: {...}, M5: {...}, M15: {...}} (ou flat legado)
        if "M1" not in data:
            data = {"M1": data, "M5": {}, "M15": {}}

        m1_data = data.get("M1", {})
        if not m1_data.get("online"):
            continue

        score_raw = m1_data.get("score", 0)
        sinal = m1_data.get("sinal", "NEUTRAL")

        # Scores por timeframe
        m5_score = data.get("M5", {}).get("score")
        m15_score = data.get("M15", {}).get("score")

        final_adjusted = max(score_raw - global_reduction, 0)

        breakdown[sym] = {
            "macro": {"raw": 50, "weight": 0.33, "weighted": 16.5},
            "volatilidade": {"raw": 50, "weight": 0.33, "weighted": 16.5},
            "tecnico": {"raw": score_raw, "weight": 0.34, "weighted": 17.0},
            "final_score": round(final_adjusted, 2),
            "final_raw": round(score_raw, 2),
            "final_adjusted": round(final_adjusted, 2),
            "reducers_applied": global_reducers.copy(),
            "threshold": threshold,
            "sinal": sinal,
            "confidence": m1_data.get("confidence", m1_data.get("score", 50) / 100),
            "spread": spread,
            "sentiment": ctx.get("sentiment_ratio", 0.5),
            # S39/C4 — scores por timeframe
            "scores_mtf": {
                "M1": score_raw,
                "M5": m5_score,
                "M15": m15_score,
            },
        }
        active_symbols.append(sym)

    if not active_symbols:
        logger.error("Nenhum simbolo online encontrado com pontuacao valida")
        return {}

    result = {
        "meta": {
            "trace_id": _generate_trace(),
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "timeframe": "M5",  # S39/C4: primario do scalping (nao hardcoded M15)
            "timeframes_disponiveis": ["M1", "M5", "M15"],
            "slot_used": 0,
            "slot_max": 30,
            "positions_open_symbol": 0,
        },
        "symbols": active_symbols,
        "breakdown": breakdown,
        "context": {
            "news_imminent": ctx.get("news_imminent", False),
            "spread_pips": spread,
            "session": get_current_session(),
            "dxy_trend": ctx.get("dxy_trend", "FLAT"),
            "atr_14_m5": ctx.get("atr_14_m5", 0),
            "atr_14_m15": ctx.get("atr_14_m15", 0),
            "sentiment_ratio": ctx.get("sentiment_ratio", 0.5),
            "dom_imbalance": dom,
        },
    }

    errors = validate_fusion_output(result)
    if errors:
        logger.error("Validacao fusion_output falhou: %s", errors)

    return result


_ROOT = Path(__file__).resolve().parent.parent

def fuse_and_save(scores_live_path: str = "status/score_live.json",
                  output_path: str = "fusion_output.json",
                  rules_path: str = "custom_rules.json"):
    """Le score_live, funde, salva fusion_output."""

    path = _ROOT / scores_live_path
    if not path.exists():
        logger.error("Arquivo %s nao encontrado. F1 falhou?", path)
        return {}

    with open(path) as f:
        scores_live = json.load(f)

    result = fuse(scores_live, rules_path=rules_path)
    if not result:
        return {}

    # Usa path absoluto para garantir que escreve em ctrader/ independente do CWD
    output_abs = _ROOT / output_path if not Path(output_path).is_absolute() else Path(output_path)
    with open(output_abs, "w") as f:
        json.dump(result, f, indent=2, sort_keys=True)

    logger.info("fusion_output.json salvo: syms=%s", result.get("symbols", []))
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="F2 Fusion — Lê score_live.json")
    parser.add_argument("--live", default="status/score_live.json", help="Caminho relativo para score_live.json")
    parser.add_argument("--output", default="fusion_output.json")
    parser.add_argument("--rules", default="custom_rules.json")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    fuse_and_save(args.live, args.output, args.rules)


if __name__ == "__main__":
    main()
