"""
PROPOSITO: T22 — MAR RULES
SPEC: S7
ROADMAP: 6.0
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from f5_mar.trades_log_orc_mar import get_trades_today

logger = logging.getLogger(__name__)

RULES_PATH = Path(__file__).resolve().parent.parent / "custom_rules.json"
WEIGHT_UPDATE_RATE = 0.7
DEFAULT_WEIGHTS = {"macro": 0.33, "volatilidade": 0.33, "tecnico": 0.34}


def load_rules() -> dict[str, Any]:
    try:
        with open(RULES_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"weights": dict(DEFAULT_WEIGHTS), "threshold": 70, "version": 0}


def save_rules(rules: dict[str, Any]):
    with tempfile.NamedTemporaryFile(mode='w', dir=str(RULES_PATH.parent),
                                     delete=False, suffix='.json') as f:
        json.dump(rules, f, indent=2, sort_keys=True)
        tmp = f.name
    os.replace(tmp, str(RULES_PATH))


def _calcular_pesos_do_dia() -> dict[str, float] | None:
    rows = get_trades_today()
    if len(rows) < 5:
        return None
    approved = [r for r in rows if r[1] == "APPROVE"]
    ideal = dict(DEFAULT_WEIGHTS)
    if approved:
        wins = sum(1 for r in approved if (r[2] or 0) > 0)
        if wins / len(approved) < 0.5:
            ideal["macro"] *= 0.9
            ideal["tecnico"] *= 1.05
    return ideal


def calibrate_daily():
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    logger.info("MAR: Calibrando pesos para %s", today)
    dia_ideal = _calcular_pesos_do_dia()
    if dia_ideal is None:
        logger.info("MAR: Poucos trades hoje. Mantendo pesos atuais.")
        return

    atuais = load_rules()
    novos = {}
    for k in DEFAULT_WEIGHTS:
        novos[k] = atuais.get("weights", DEFAULT_WEIGHTS).get(k, DEFAULT_WEIGHTS[k]) * (1 - WEIGHT_UPDATE_RATE) \
                   + dia_ideal.get(k, DEFAULT_WEIGHTS[k]) * WEIGHT_UPDATE_RATE

    total = sum(novos.values())
    novos = {k: round(v / total, 4) for k, v in novos.items()}

    # ajuste de threshold (blueprint §5.2 linha 521-523)
    threshold = atuais.get("threshold", 70)
    rows = get_trades_today()
    if len(rows) >= 5:
        approved = [r for r in rows if r[1] == "APPROVE"]
        rejected = [r for r in rows if r[1] == "REJECT"]
        # se muitos APPROVE com score 70-72 dao prejuizo -> sobe threshold
        low_score_loss = [r for r in approved if (r[2] or 0) < 0 and json.loads(r[0]).get("scores", {}).get("final_adjusted", 0) <= 73]
        if len(low_score_loss) > len(approved) * 0.3:
            threshold = min(threshold + 2, 78)
        # se muitos REJECT com score 68-70 seriam lucrativos -> desce threshold
        if len(rejected) > len(rows) * 0.5:
            threshold = max(threshold - 1, 65)

    # stats + threshold ajustado
    today_rows = get_trades_today()
    total_trades = atuais.get("total_trades", 0) + len(today_rows)
    rules = {
        "version": atuais.get("version", 1) + 1,
        "total_trades": total_trades,
        "last_updated_utc": datetime.now(UTC).isoformat(),
        "weights": novos,
        "threshold": threshold,
        "stats": {
            "win_rate_approved": sum(1 for r in today_rows if r[1] == "APPROVE" and (r[2] or 0) > 0) / max(1, sum(1 for r in today_rows if r[1] == "APPROVE")),
            "total_trades": total_trades,
        },
    }
    save_rules(rules)
    logger.info("MAR: Pesos atualizados: %s threshold=%d", novos, threshold)
