"""
PROPOSITO: T20
SPEC: S5
ROADMAP: 4.0
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from utils.schema_validator import validate_verdict


def _get_balance_safe() -> dict[str, Any]:
    """Le balance do snapshot F0. SEM bypass MCP.
    Se snapshot vazio, retorna dict vazio. F0 actualiza a cada ciclo.
    """
    try:
        from f0_collector.orc_coleta import get_snapshot
        snap = get_snapshot()
        if snap and snap.get("balance"):
            return snap["balance"]
    except Exception:
        pass
    logger.info("Snapshot F0 vazio - balance offline.")
    return {}
from utils.logger import get_logger

logger = get_logger(__name__, "F3")

TIMEOUT_MAX = {"M_5": 5, "M_15": 15}
TIMEOUT_FALLBACK = {"M_5": 4, "M_15": 12}
IA_TIMEOUT_SECONDS = 3.0
FALLBACK_SCORE = 70


def _mechanical_fallback(final_adjusted: float, timeframe: str) -> dict[str, Any]:
    """Fallback mecanico quando a IA falha."""
    if final_adjusted >= FALLBACK_SCORE:
        return {
            "decision": "APPROVE",
            "confidence": 0.5,
            "adjustments": {
                "lot_multiplier": 0.5,
                "timeout_min": TIMEOUT_FALLBACK.get(timeframe, 10),
                "be_trigger_pct": 70,
            },
        }
    else:
        return {
            "decision": "REJECT",
            "reason": "IA_TIMEOUT",
            "reason_detail": f"Score {final_adjusted} abaixo do threshold de fallback ({FALLBACK_SCORE})",
        }

def _apply_hard_cap(verdict: dict[str, Any], timeframe: str) -> dict[str, Any]:
    """Trunca timeout_min ao maximo do timeframe."""
    if verdict.get("decision") != "APPROVE":
        return verdict

    max_timeout = TIMEOUT_MAX.get(timeframe.upper(), 20)
    adj = verdict.get("adjustments", {})
    adj["timeout_min"] = min(adj.get("timeout_min", max_timeout), max_timeout)
    verdict["adjustments"] = adj

    # garante source
    verdict["source"] = verdict.get("source", "mechanical")  # IA removida (ROADMAP 4.0)
    return verdict

def validate(fusion_output_path: str = "fusion_output.json",
             api_key: str | None = None) -> dict[str, Any]:
    """Valida fusion_output.json via IA (ou fallback). Retorna verdict dict."""

    with open(fusion_output_path) as f:
        fusion = json.load(f)

    final_adjusted = fusion["scores"]["final_adjusted"]
    timeframe = fusion["meta"].get("timeframe", "m15").lower()

    # pre-check MCP: margem
    try:
        bal = _get_balance_safe()
        free_margin = bal.get("freeMargin", 0)
        if free_margin <= 0:
            logger.error("Margem insuficiente. Rejeitado sem chamar IA.")
            return {
                "decision": "REJECT",
                "reason": "MARGEM_INSUFICIENTE",
                "reason_detail": f"freeMargin={free_margin}",
                "source": "mcp_pre_check",
            }
    except Exception as e:
        logger.error("Falha ao verificar margem: %s. Prosseguindo...", e)

    # se score abaixo do threshold, nem chama IA
    threshold = fusion["scores"]["threshold"]
    if final_adjusted < threshold:
        logger.info("Score %.2f abaixo do threshold %d. Rejeitado.", final_adjusted, threshold)
        return {
            "decision": "REJECT",
            "reason": "SCORE_INSUFICIENTE",
            "reason_detail": f"Score {final_adjusted} < threshold {threshold}",
            "source": "threshold",
        }

    # tenta IA
    # fusion_str = json.dumps(...)  # IA removida (ROADMAP 4.0)

    # IA removida (ROADMAP 4.0) — sempre fallback mecanico
    verdict = _mechanical_fallback(final_adjusted, timeframe)
    verdict["source"] = "mechanical"
    logger.info("Fallback mecanico: %s (score %.1f)", verdict.get("decision"), final_adjusted)

    # hard cap
    verdict = _apply_hard_cap(verdict, timeframe)

    # valida
    errors = validate_verdict(verdict)
    if errors:
        logger.error("Verdict invalido: %s. Usando fallback.", errors)
        verdict = _mechanical_fallback(final_adjusted, timeframe)
        verdict["source"] = "mechanical_fallback_validation_error"

    return verdict

def validate_and_save(fusion_output_path: str = "fusion_output.json",
                      output_path: str = "verdict.json",
                      api_key: str | None = None) -> dict[str, Any]:
    """Valida e salva verdict.json."""
    verdict = validate(fusion_output_path, api_key)
    with open(output_path, "w") as f:
        json.dump(verdict, f, indent=2, sort_keys=True)
    logger.info("verdict.json salvo: %s", verdict.get("decision"))
    return verdict

def main():
    import argparse
    parser = argparse.ArgumentParser(description="F3 Validator — DeepSeek Pro + Fallback")
    parser.add_argument("--fusion", default="fusion_output.json")
    parser.add_argument("--output", default="verdict.json")
    parser.add_argument("--api-key", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    validate_and_save(args.fusion, args.output, args.api_key)

if __name__ == "__main__":
    main()
