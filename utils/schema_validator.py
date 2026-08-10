"""PROPOSITO: Schema validator para JSONs de status.
SPEC: S32 (ampliado M4)
ROADMAP: FASE 6
Validacao barata (sem jsonschema lib) — verifica campos obrigatorios e tipos.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

STATUS_DIR = Path(__file__).resolve().parent.parent / "status"

SCHEMAS: dict[str, dict[str, Any]] = {
    "fusion_output.json": {
        "required": ["timestamp_utc", "signals", "score"],
        "types": {"signals": list, "score": (int, float)},
    },
    "ranking.json": {
        "required": ["timestamp_utc", "rankings"],
        "types": {"rankings": list},
    },
    "metrics.json": {
        "required": ["timestamp_utc"],
        "types": {},
    },
    "gap_report.json": {
        "required": ["generated_at", "symbols", "_script_version"],
        "types": {"symbols": dict},
    },
    "backfill_progress.json": {
        "required": ["state", "totals", "symbols"],
        "types": {"totals": dict, "symbols": dict},
    },
}


def validate_file(filename: str) -> tuple[bool, str]:
    """Valida um arquivo JSON contra seu schema. Retorna (ok, mensagem)."""
    path = STATUS_DIR / filename
    if not path.exists():
        return False, f"{filename}: arquivo ausente"

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return False, f"{filename}: JSON invalido — {e}"

    schema = SCHEMAS.get(filename)
    if not schema:
        return True, f"{filename}: sem schema definido (skip)"

    # Check required fields
    for field in schema.get("required", []):
        if field not in data:
            return False, f"{filename}: campo obrigatorio '{field}' ausente"

    # Check types
    for field, expected in schema.get("types", {}).items():
        if field in data and not isinstance(data[field], expected):
            return False, f"{filename}: '{field}' tipo errado (esperado {expected}, obtido {type(data[field]).__name__})"

    return True, f"{filename}: schema OK"


def validate_all() -> dict[str, Any]:
    """Valida todos os JSONs de status. Retorna dict com resultado por arquivo."""
    results = {}
    all_ok = True
    for filename in SCHEMAS:
        ok, msg = validate_file(filename)
        results[filename] = {"ok": ok, "detail": msg}
        if not ok:
            all_ok = False
    results["all_ok"] = all_ok
    return results


def validate_fusion_output(data: dict[str, Any]) -> list[str]:
    """Valida semantica do fusion_output.json. Retorna lista de erros (vazia = OK).
    Usado por f2_fusao/orc_fusao.py.
    """
    errors = []
    if not isinstance(data, dict):
        return ["fusion_output: esperado dict"]
    if "signals" not in data:
        errors.append("fusion_output: campo 'signals' ausente")
    elif not isinstance(data["signals"], list):
        errors.append("fusion_output: 'signals' deve ser lista")
    if "score" not in data:
        errors.append("fusion_output: campo 'score' ausente")
    return errors


def validate_scores_raw(data: dict[str, Any]) -> list[str]:
    """Valida scores_raw.json (saida do F1 orc_analise.analyze()).
    Retorna lista de erros (vazia = OK). Usado por f1_analyzer/orc_analise.py.
    """
    errors = []
    if not isinstance(data, dict):
        return ["scores_raw: esperado dict"]

    # Required top-level fields
    for field in ("trace_id", "timestamp_utc", "symbol", "scores"):
        if field not in data:
            errors.append(f"scores_raw: campo '{field}' ausente")

    # Validate scores sub-dict
    scores = data.get("scores", {})
    if not isinstance(scores, dict):
        errors.append("scores_raw: 'scores' deve ser dict")
    else:
        for score_field in ("macro", "volatilidade", "tecnico", "spread", "sentiment"):
            if score_field not in scores:
                errors.append(f"scores_raw: scores['{score_field}'] ausente")

    return errors


def validate_verdict(data: dict[str, Any]) -> list[str]:
    """Valida verdict.json (saida do F3 orc_validacao).
    Retorna lista de erros (vazia = OK). Usado por f3_validacao/orc_validacao.py.
    """
    errors = []
    if not isinstance(data, dict):
        return ["verdict: esperado dict"]

    if "decision" not in data:
        errors.append("verdict: campo 'decision' ausente")
    elif data["decision"] not in ("APPROVE", "REJECT"):
        errors.append(f"verdict: 'decision' invalida: {data.get('decision')}")

    if "confidence" not in data:
        errors.append("verdict: campo 'confidence' ausente")

    return errors
