"""PROPOSITO: Orquestrador de Ranking (F3 — last mile).
SPEC: S35 (pai) — spotter + sniper mecanicos, IA removida (S26).
ROADMAP: 4.0 — fusion_output.json -> rank_signals -> ranking.json.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.logger import (  # noqa: E402
    get_logger,
)

logger = get_logger(__name__, "RANKING")

FALLBACK_SCORE = 70  # Score minimo para fallback mecanico

# Artefatos do pipeline (F1 -> F2 -> F3)
SCORES_RAW_PATH = ROOT / "scores_raw.json"
FUSION_OUTPUT_PATH = ROOT / "fusion_output.json"
FUSION_STATUS_PATH = ROOT / "status" / "fusion_output.json"  # F2 escreve aqui (boot 2026-07-30)
SCORES_RAW_STATUS_PATH = ROOT / "status" / "scores_raw.json"
SCORE_LIVE_PATH = ROOT / "status" / "score_live.json"  # F1 emissor direto (fallback S38)
RANKING_OUTPUT_PATH = ROOT / "ranking.json"


def _has_multi_symbol_format(data: dict[str, Any]) -> bool:
    """Verifica se o JSON tem formato multi-simbolo valido (post-S38)."""
    symbols = data.get("symbols", [])
    breakdown = data.get("breakdown", {})
    return bool(symbols) and isinstance(breakdown, dict) and bool(breakdown)


def _load_fusion_output() -> dict[str, Any]:
    """Carrega fusion_output.json (F2). Se nao existe ou esta stale (formato antigo),
    tenta score_live.json direto (F1). Procura na raiz E em status/."""
    for path in [FUSION_OUTPUT_PATH, FUSION_STATUS_PATH,
                 SCORES_RAW_PATH, SCORES_RAW_STATUS_PATH]:
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if _has_multi_symbol_format(data):
                    logger.info("fusion_output carregado de %s: %d simbolos",
                                path.name, len(data.get("symbols", [])))
                    return data
                else:
                    logger.info("fusion_output em %s eh formato antigo (single-symbol). Ignorando.",
                                   path.name)
            except Exception:
                pass

    # Fallback: score_live.json direto (F1 emissor)
    if SCORE_LIVE_PATH.exists():
        try:
            live = json.loads(SCORE_LIVE_PATH.read_text(encoding="utf-8"))
            symbols = live.get("symbols", {})
            if symbols:
                logger.info("Fallback: usando score_live.json com %d simbolos", len(symbols))
                return _convert_score_live_to_fusion(live)
        except Exception as e:
            logger.error("Falha ao ler score_live.json como fallback: %s", e)

    return {}


def _convert_score_live_to_fusion(live: dict[str, Any]) -> dict[str, Any]:
    """Converte score_live.json (F1) para formato fusion_output (F2)."""
    symbols_dict = live.get("symbols", {})
    active_symbols = []
    breakdown = {}
    for sym, data in symbols_dict.items():
        if not data.get("online"):
            continue
        score_raw = data.get("score", 0)
        sinal = data.get("sinal", "NEUTRAL")
        active_symbols.append(sym)
        breakdown[sym] = {
            "macro": {"raw": 50, "weight": 0.33, "weighted": 16.5},
            "volatilidade": {"raw": 50, "weight": 0.33, "weighted": 16.5},
            "tecnico": {"raw": score_raw, "weight": 0.34, "weighted": 17.0},
            "final_score": round(score_raw, 2),
            "final_raw": round(score_raw, 2),
            "final_adjusted": round(score_raw, 2),
            "reducers_applied": [],
            "threshold": 70,
            "sinal": sinal,
            "confidence": data.get("confidence", 0.5),
            "spread": 0,
            "sentiment": 0.5,
        }

    return {
        "meta": {
            "trace_id": f"T{live.get('ts', '')}-FALLBACK",
            "timestamp_utc": live.get("ts", ""),
            "timeframe": "M15",
            "slot_used": 0,
            "slot_max": 30,
            "positions_open_symbol": 0,
        },
        "symbols": active_symbols,
        "breakdown": breakdown,
        "context": {
            "news_imminent": False,
            "spread_pips": 0,
            "session": "UNKNOWN",
            "dxy_trend": "FLAT",
            "atr_14_m5": 0,
            "atr_14_m15": 0,
            "sentiment_ratio": 0.5,
            "dom_imbalance": 0,
        },
    }


def _fallback_ranking(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fallback mecanico: ordena por final_score + confidence."""
    ranked = []
    for c in candidates:
        score = c.get("final_score", 0) or c.get("score", 0)
        confidence = c.get("confidence", 0) or 0.5
        ranked.append({
            "symbol": c.get("symbol", "?"),
            "score": score,
            "confidence": confidence,
            "action": "APPROVE" if score >= FALLBACK_SCORE else "REJECT",
            "reason": f"Fallback mecanico (score={score}, cf={confidence})",
        })
    ranked.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
    return ranked


def rank_signals(min_score: int = 75) -> dict[str, Any]:
    """Orquestrador de ranking F3: consome fusion_output.json (F2),
    envia ao DeepSeek para validacao, retorna ranking.json (F3 -> F4).

    NAO toca o vector_db do Neocortex (governanca). O pipeline e:
    F0 (parquet) -> F1 (scores_raw) -> F2 (fusion_output) -> F3 (ranking) -> F4 (ordens).
    """
    fusion = _load_fusion_output()

    if not fusion:
        return {"status": "error", "error": "fusion_output.json nao encontrado. Rode F1 e F2 primeiro.", "ranked": []}

    # Extrai candidatos do fusion_output
    candidates = []
    breakdown = fusion.get("scores", fusion.get("breakdown", {}))
    symbols_list = fusion.get("symbols", []) or [fusion.get("symbol", "XAUUSD")]

    # Se fusion_output tem breakdown multi-simbolo
    if isinstance(breakdown, dict) and any(isinstance(v, dict) for v in breakdown.values()):
        for sym in symbols_list:
            sym_data = breakdown.get(sym, {})
            score = sym_data.get("final_score", fusion.get("final_score", 0))
            # Extrai valores raw dos sub-dicts (macro/volatilidade/tecnico sao dicts no formato S38)
            def _raw(val: Any, default: float = 0.0) -> float:
                return val.get("raw", default) if isinstance(val, dict) else (val if isinstance(val, (int, float)) else default)
            candidates.append({
                "symbol": sym,
                "final_score": score,
                "confidence": sym_data.get("confidence", fusion.get("confidence", 0.5)),
                "macro": _raw(sym_data.get("macro", 0)),
                "volatilidade": _raw(sym_data.get("volatilidade", 0)),
                "tecnico": _raw(sym_data.get("tecnico", 0)),
                "spread": sym_data.get("spread", 0),
                "sentiment": sym_data.get("sentiment", 0),
            })
    else:
        # Single-symbol fusion output
        score = fusion.get("final_score", 0)
        sym = fusion.get("symbol", "XAUUSD")
        candidates.append({
            "symbol": sym,
            "final_score": score,
            "confidence": fusion.get("confidence", 0.5),
            "macro": fusion.get("scores", {}).get("macro", 0),
            "volatilidade": fusion.get("scores", {}).get("volatilidade", 0),
            "tecnico": fusion.get("scores", {}).get("tecnico", 0),
        })

    if not candidates:
        return {
            "status": "ok",
            "candidates": 0,
            "ranked": [],
            "note": f"Nenhum candidato >= {min_score}%",
        }

    # S35: Ranking v2 - Filtros e Penalidades (Correlacao e Confluencia)
    try:
        from utils.orc_indices import correlate_markets_m1
        corr_data = correlate_markets_m1(window=1440)
        corr_matrix = corr_data.get("correlation_matrix", {})
    except Exception as e:
        logger.error("Falha ao puxar correlacao S35: %s", e)
        corr_matrix = {}

    for cand in candidates:
        cand["penalty"] = 0
        cand["bonus"] = 0
        cand["notes"] = []

    # Regra 1: Sobre-exposicao (-10 pts)
    for i, c1 in enumerate(candidates):
        for j, c2 in enumerate(candidates):
            if i >= j:
                continue

            sym1 = c1["symbol"]
            sym2 = c2["symbol"]

            # Precisamos extrair a "direcao" do candidato, porem candidates nao tem side explicito aqui!
            # Como a spec S35 manda penalizar se a "direcao" for mesma: vamos assumir sinal Bullish se tecnico > 50.
            # Sinais vêm do F1. Em `fusion_output`, tecnico >= 50 costuma significar alta, senao baixa.
            dir1 = 1 if c1.get("tecnico", 50) > 50 else -1
            dir2 = 1 if c2.get("tecnico", 50) > 50 else -1

            if dir1 == dir2 and sym1 in corr_matrix and sym2 in corr_matrix[sym1]:
                c_val = corr_matrix[sym1][sym2]
                if c_val is not None and c_val > 0.70:
                    # Penaliza o candidato com menor score original
                    if c1["final_score"] < c2["final_score"]:
                        c1["penalty"] += 10
                        c1["notes"].append(f"Sobre-exposicao com {sym2} (corr={c_val:.2f})")
                    else:
                        c2["penalty"] += 10
                        c2["notes"].append(f"Sobre-exposicao com {sym1} (corr={c_val:.2f})")

    # Regra 2: Confluencia (+5 pts)
    # Exemplo: XAUUSD + EURUSD se movendo juntos contra o dolar
    # EURUSD é proxy primario do DXY.
    for c in candidates:
        sym = c["symbol"]
        dir_c = 1 if c.get("tecnico", 50) > 50 else -1

        # Confluencia com proxy EURUSD (DXY fraco = EURUSD up)
        if sym != "EURUSD":
            # Verificar se EURUSD tambem esta com sinal na mesma direcao (se EURUSD tiver sinal)
            eur_cand = next((x for x in candidates if x["symbol"] == "EURUSD"), None)
            if eur_cand:
                dir_eur = 1 if eur_cand.get("tecnico", 50) > 50 else -1
                if sym in corr_matrix and "EURUSD" in corr_matrix[sym]:
                    c_val = corr_matrix[sym]["EURUSD"]
                    if c_val is not None and c_val > 0.50 and dir_c == dir_eur:
                        c["bonus"] += 5
                        c["notes"].append("Confluencia com EURUSD (USD fraco)")

        # Ajusta score final
        c["final_score_adjusted"] = max(0, c["final_score"] - c["penalty"] + c["bonus"])

    # IA removida (S26) - aplica _fallback_ranking mecanico no score ajustado
    def _adjusted_fallback_ranking(cands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        ranked = []
        for c in cands:
            score = c.get("final_score_adjusted", c.get("final_score", 0))
            confidence = c.get("confidence", 0) or 0.5
            action = "APPROVE" if score >= min_score else "REJECT"
            reason = f"Mecanico (score={score}, cf={confidence}). " + "; ".join(c.get("notes", []))
            ranked.append({
                "symbol": c.get("symbol", "?"),
                "score": score,
                "confidence": confidence,
                "action": action,
                "reason": reason,
                "penalty": c.get("penalty", 0),
                "bonus": c.get("bonus", 0),
            })
        ranked.sort(key=lambda x: (x["score"], x["confidence"]), reverse=True)
        return ranked

    ranked = _adjusted_fallback_ranking(candidates)

    # Persiste ranking.json (F3 -> F4)
    output = {
        "status": "ok",
        "candidates": len(candidates),
        "ranked": ranked,
        "source": "mechanical (IA removida S26)",
        "timestamp_utc": time.time(),
    }
    try:
        RANKING_OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info("ranking.json salvo: %d candidatos, source=%s", len(candidates), output["source"])
    except Exception as e:
        logger.error("Falha ao salvar ranking.json: %s", e)

    return output
