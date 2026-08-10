"""PROPOSITO: signal_emitter_orc_score.py — Emissor de sinais live (S36 MODO PRESENTE).
SPEC: S36 (orc_calibracao.md) + S20 v2.2 (REGRA-MET) + S39/C4 (MTF scores)
ROADMAP: S36 / C4 — a cada barra M1 fechada: scores M1+M5+M15 -> score_live.json + signals_log.

SAT de orc_score (R8 naming). NAO toca MCP — orc_score le snapshot/parquet.
- Grava status/score_live.json com scores por timeframe: {symbol: {M1: score, M5: score, M15: score}}
  -> orc_metricas le e expoe na secao score_mercados do /metrics (REGRA-MET, S20 v2.2).
- Append em data/signals_log.parquet (origem="live") com anti-flood:
  max 1 sinal/simbolo/minuto; dedup por (sinal, faixa_score) via
  status/emitter_state.json (KISS — sem reler o parquet inteiro).

CLI: python -m utils.signal_emitter_orc_score [--once]
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from utils.logger import get_logger

logger = get_logger(__name__, "EMIT")

BASE_DIR = Path(__file__).resolve().parent.parent
SCORE_LIVE = BASE_DIR / "status" / "score_live.json"
EMITTER_STATE = BASE_DIR / "status" / "emitter_state.json"


def _score_bin(score: float) -> str:
    for lo, hi in ((0, 50), (50, 70), (70, 85), (85, 101)):
        if lo <= score < hi:
            return f"{lo}-{hi if hi <= 100 else 100}"
    return "0-50"


def _load_state() -> dict[str, Any]:
    try:
        if EMITTER_STATE.exists():
            return json.loads(EMITTER_STATE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.error("emitter_state ilegivel: %s", e)
    return {}


def emit_once(symbols: list[str] | None = None) -> dict[str, Any]:
    """Emite 1 ciclo: score por simbolo/por timeframe -> score_live.json + append signals_log.

    S39/C4: score_live.json agora tem {symbol: {M1: {...}, M5: {...}, M15: {...}}}.
    O sinal principal (para anti-flood e signals_log) usa o score M1 (completo).
    """
    from f2_fusao.orc_score import combined_score_mtf
    from utils.orc_calibracao import append_signals
    from utils.orc_mercado import PIP_SPECS
    from utils.orc_metricas import VECTOR_SYMBOLS

    symbols = symbols or list(VECTOR_SYMBOLS)
    now = datetime.now(UTC)
    state = _load_state()
    live: dict[str, Any] = {"ts": now.isoformat(), "symbols": {}}
    rows: list[dict[str, Any]] = []

    for sym in symbols:
        try:
            r = combined_score_mtf(sym)
        except Exception as e:
            logger.error("%s: combined_score_mtf falhou: %s", sym, e)
            live["symbols"][sym] = {tf: {"online": False, "error": str(e)[:100]}
                                    for tf in ("M1", "M5", "M15")}
            continue

        # -- Monta entry por timeframe --
        sym_entry: dict[str, dict[str, Any]] = {}
        m1_online = False

        for tf in ("M1", "M5", "M15"):
            tf_data = r.get(tf, {})
            if tf_data.get("status") != "ok":
                sym_entry[tf] = {"online": False, "motivo": tf_data.get("status")}
                continue

            tf_score = (round(float(tf_data.get("adjusted_confidence", 0)) * 100, 1)
                      if tf == "M1" and "adjusted_confidence" in tf_data
                      else float(tf_data.get("score", 0)))
            tf_signal = tf_data.get("signal", "NEUTRAL")

            sym_entry[tf] = {
                "online": True,
                "sinal": tf_signal,
                "score": tf_score,
                "ts_emissao": now.isoformat(),
            }
            # Adiciona detalhes extras so para M1 (completo)
            if tf == "M1":
                sym_entry[tf]["quality_f1"] = tf_data.get("quality_f1")
                sym_entry[tf]["pattern_conf"] = tf_data.get("pattern_confidence")
                sym_entry[tf]["coverage_pct"] = tf_data.get("coverage_pct")
                m1_online = True

        live["symbols"][sym] = sym_entry

        # -- Anti-flood: usa score M1 como referencia principal --
        if not m1_online:
            continue

        m1_entry = sym_entry.get("M1", {})
        m1_score = m1_entry.get("score", 0)
        m1_sinal = m1_entry.get("sinal", "NEUTRAL")
        faixa = _score_bin(m1_score)

        prev = state.get(sym) or {}
        last_ts = prev.get("ts")
        age_min = (now.timestamp() - float(last_ts)) / 60 if last_ts else 999
        if m1_sinal == "NEUTRAL" or (prev.get("sinal") == m1_sinal and prev.get("faixa") == faixa
                                      and age_min < 15):
            continue

        state[sym] = {"sinal": m1_sinal, "faixa": faixa, "ts": now.timestamp()}
        pip_size = PIP_SPECS.get(sym, {}).get("pip_size", 0.0001)

        # Extrai close do M1
        close_val = (
            (r.get("M1", {}).get("details", {})
             .get("patterns", {}).get("outcome", {})
             .get("top_match", {}) or {}).get("close")
            or pip_size
        )
        rows.append({
            "ts": now.isoformat(),
            "symbol": sym,
            "origem": "live",
            "strategy_id": None,
            "sinal": m1_sinal,
            "score": m1_score,
            "coverage_pct": m1_entry.get("coverage_pct"),
            "close_entrada": close_val,
        })

    SCORE_LIVE.parent.mkdir(parents=True, exist_ok=True)
    SCORE_LIVE.write_text(json.dumps(live, ensure_ascii=False, indent=1), encoding="utf-8")
    EMITTER_STATE.write_text(json.dumps(state), encoding="utf-8")

    added = append_signals(rows) if rows else 0
    online_count = sum(
        1 for s in live["symbols"].values()
        if s.get("M1", {}).get("online")
    )
    logger.info("ciclo emitido: %d simbolos online, +%d sinais live", online_count, added)
    return {"live": live, "signals_added": added}


def main() -> None:
    ap = argparse.ArgumentParser(description="S36 signal emitter (MODO PRESENTE)")
    ap.add_argument("--once", action="store_true", help="emite 1 ciclo e sai")
    ap.parse_args()
    r = emit_once()
    online = sum(1 for s in r["live"]["symbols"].values()
                 if s.get("M1", {}).get("online"))
    print(f"[EMIT] ciclo ok: {online}/5 online, +{r['signals_added']} sinais no log")


if __name__ == "__main__":
    main()
