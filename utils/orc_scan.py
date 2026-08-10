"""PROPOSITO: orc_scan.py — Orquestrador do Pattern Scan 730d (S34).
SPEC: S34 (orc_pattern_engine.md)
ROADMAP: S34 — scan batch offline -> status/pattern_library.json + replay signals.

SAT de orc_pattern (R8 naming). Engine numpy em matrix_orc_scan (split DDD).
- cosine similarity em chunks BLAS (normas + transposta pre-computadas)
- outcomes 5/15/60 barras M1 vetorizados, LIQUIDOS de spread (S34 sec.4b)
- sessao rollover excluida da media; amostra minima 30 (A7)
- v1.2: score do replay COMPOSTO (S32 parity) = (quality_f1_trailing x
  QUALITY_WEIGHT + conf x PATTERN_WEIGHT) x coverage_G23; re-scan SUBSTITUI
  replay via orc_calibracao.purge_signals (dedup keep=first manteria velhos)

CLI: python -m utils.orc_scan --scan all --days 730 [--stride 60]
NUNCA roda em runtime live (batch offline, padrao S31). NAO toca MCP.
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from utils import matrix_orc_scan as matrix
from utils.logger import get_logger

logger = get_logger(__name__, "SCAN")

STATUS_DIR = Path(__file__).resolve().parent.parent / "status"
LIBRARY_PATH = STATUS_DIR / "pattern_library.json"

# S34 sec.4b — spread medio estimado (refinar com spread medido do snapshot)
SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 3.5, "EURUSD": 1.0, "GBPUSD": 1.2, "USDJPY": 1.0, "AUDUSD": 1.2,
}
LOOKAHEADS = (5, 15, 60)
MIN_OCCURRENCES = 30
TOP_N_PATTERNS = 50
MAX_REPLAY_ROWS_PER_SYMBOL = 2000
MAX_MATCHES_STATS = 5000  # amostra max por prototipo (custo limitado, R21)


def scan_symbol(
    symbol: str,
    days: int = 730,
    stride: int = 60,
    min_sim: float = 0.999,
) -> dict[str, Any]:
    """Scan completo de um simbolo: prototipos -> matches -> outcomes ponderados.

    R21 (medido 2026-07-30): MEDIA de janela de 20 barras foi TESTADA e
    REJEITADA — destroi a discriminacao (mediana 593k matches/prototipo em
    thr 0.92; tudo e similar a tudo). Engine usa vetor de estado POR BARRA
    + thr 0.999 (mediana ~6,5k matches — base estatistica forte e custo
    viavel). Retorna dict com library entries + replay_rows (S36 PASSADO).
    """
    from f2_fusao.orc_score import PATTERN_WEIGHT, QUALITY_WEIGHT  # R-USE S32
    from utils.orc_mercado import PIP_SPECS
    from utils.storage_orc_consolidated import consolidated_indicator_points

    t0 = time.monotonic()
    spec = PIP_SPECS.get(symbol, {})
    # R21 (medido 2026-07-30): closes do consolidado estao em UNIDADES BRUTAS
    # cTrader (price_divisor) — pip_size x divisor = tamanho do pip em bruto.
    # Sem isto outcomes saiam 100000x inflados (avg_pips_net -85k absurdo).
    pip_raw = spec.get("pip_size", 0.0001) * spec.get("price_divisor", 1)
    spread = SPREAD_PIPS.get(symbol, 1.0)

    # coverage G23 (mesma fonte do S32): score escala com o banco conciliado
    try:
        from utils.orc_metricas import _read_gap_coverage
        cov_pct = float(_read_gap_coverage().get(symbol, 0.0)) or None
    except Exception:
        cov_pct = None
    coverage = round(min(1.0, (cov_pct or 0.0) / 100), 4) if cov_pct else 1.0

    payload = consolidated_indicator_points(symbol, days, max_points=850_000)
    if not payload or len(payload.get("points", [])) < max(LOOKAHEADS) + 10:
        logger.error("%s: consolidado insuficiente para scan", symbol)
        return {"symbol": symbol, "status": "sem_dados", "patterns": [], "replay_rows": []}

    points = payload["points"]
    vectors, ts, closes, rsi, adx = matrix.feature_matrix(points)
    if len(vectors) < 100:
        return {"symbol": symbol, "status": "sem_dados", "patterns": [], "replay_rows": []}

    # v1.2: quality trailing S29-parity por barra (zero lookahead)
    from utils import matrix_orc_quality
    q_series = matrix_orc_quality.trailing_quality_f1(rsi, adx, closes)

    ref_ts = int(ts[-1])
    sess = matrix.session_of(ts)

    # outcomes vetorizados por lookahead (pips brutos)
    max_la = max(LOOKAHEADS)
    idx = np.arange(len(vectors))
    out_pips: dict[int, np.ndarray] = {}
    for la in LOOKAHEADS:
        tgt = idx + la
        valid = tgt < len(closes)
        p = np.zeros(len(vectors))
        p[valid] = (closes[tgt[valid]] - closes[idx[valid]]) / pip_raw
        p[~valid] = np.nan
        out_pips[la] = p

    proto_idx = np.arange(max_la, len(vectors) - max_la, stride)
    patterns: list[dict[str, Any]] = []
    replay_rows: list[dict[str, Any]] = []

    # normas + transposta pre-computadas UMA vez (por chunk era o gargalo real)
    vec_norms = np.linalg.norm(vectors, axis=1)
    vec_norms[vec_norms == 0] = 1.0
    vectors_t = np.ascontiguousarray(vectors.T)
    chunk_size = 128  # 128 x N floats por matmul — BLAS acelera, ops in-place

    for start in range(0, len(proto_idx), chunk_size):
        chunk = proto_idx[start:start + chunk_size]
        sims_chunk = vectors[chunk] @ vectors_t
        outer = vec_norms[chunk][:, None] * vec_norms[None, :]
        outer[outer == 0] = 1.0
        sims_chunk /= outer
        np.clip(sims_chunk, 0.0, 1.0, out=sims_chunk)

        # exclui vizinhanca do prototipo (+-5 barras) vetorizado no chunk inteiro
        for j, p in enumerate(chunk):
            sims_chunk[j, max(0, p - 5):p + 6] = 0.0
        counts = (sims_chunk >= min_sim).sum(axis=1)

        for j, p in enumerate(chunk):
            if counts[j] < MIN_OCCURRENCES:
                continue
            sims = sims_chunk[j]
            m_idx = np.nonzero(sims >= min_sim)[0]
            # exclui sessao rollover da media (conta separado) — S34 sec.4b
            m_sess = sess[m_idx]
            rollover_n = int((m_sess == 3).sum())
            keep = m_idx[m_sess != 3]
            if len(keep) < MIN_OCCURRENCES:
                continue

            # amostra deterministica para stats — custo limitado por prototipo
            occurrences_total = len(keep)
            if len(keep) > MAX_MATCHES_STATS:
                keep = keep[np.linspace(0, len(keep) - 1, MAX_MATCHES_STATS).astype(int)]

            w = matrix.decay_weights(ts[keep], ref_ts)
            stats: dict[str, Any] = {}
            for la in LOOKAHEADS:
                raw = out_pips[la][keep]
                ok = ~np.isnan(raw)
                stats[f"outcome_{la}m"] = matrix.outcome_stats(raw[ok] - spread, w[ok], 2.0)

            o15 = stats["outcome_15m"]
            signal = ("BULLISH" if o15["bullish_pct"] > o15["bearish_pct"] + 5
                      else "BEARISH" if o15["bearish_pct"] > o15["bullish_pct"] + 5
                      else "NEUTRAL")
            conf = max(o15["bullish_pct"], o15["bearish_pct"]) / 100

            patterns.append({
                "proto_ts": int(ts[p]),
                "centroid": [round(float(x), 4) for x in vectors[p]],
                "occurrences": occurrences_total,
                "stats_sample": len(keep),
                "rollover_excluded": rollover_n,
                "avg_similarity": round(float(sims[keep].mean()), 4),
                "signal_15m": signal,
                "confidence": round(conf, 3),
                **stats,
            })

            # replay rows (S36 MODO PASSADO) — amostra limitada por simbolo
            # v1.2: score composto (S32 parity) por ocorrencia; NaN quality =
            # fallback "apenas patterns" (espelho do fallback S32)
            if signal != "NEUTRAL" and len(replay_rows) < MAX_REPLAY_ROWS_PER_SYMBOL:
                room = MAX_REPLAY_ROWS_PER_SYMBOL - len(replay_rows)
                for m in keep[: min(len(keep), room)]:
                    q = float(q_series[m])
                    if np.isnan(q):
                        score = conf
                        q_out = None
                    else:
                        score = q * QUALITY_WEIGHT + conf * PATTERN_WEIGHT
                        q_out = round(q, 3)
                    row = matrix.build_replay_row(
                        int(m), symbol, signal, score * coverage, q_out,
                        cov_pct, spread, ts, closes, out_pips,
                    )
                    if row:
                        replay_rows.append(row)

    patterns.sort(key=lambda x: -x["occurrences"])
    patterns = patterns[:TOP_N_PATTERNS]

    elapsed = time.monotonic() - t0
    logger.info("%s: %d barras, %d prototipos, %d padroes (%.1fs)",
                symbol, len(vectors), len(proto_idx), len(patterns), elapsed)
    return {
        "symbol": symbol,
        "status": "ok",
        "history_days": payload.get("history_days"),
        "windows": len(vectors),
        "prototypes": len(proto_idx),
        "scan_seconds": round(elapsed, 1),
        "patterns": patterns,
        "replay_rows": replay_rows,
    }


def run_scan(symbols: list[str], days: int = 730, stride: int = 60) -> dict[str, Any]:
    """Orquestra o scan batch: library + replay rows no signals_log (S36)."""
    library: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "days": days,
        "stride": stride,
        "min_similarity": 0.999,
        "min_occurrences": MIN_OCCURRENCES,
        "spread_pips": SPREAD_PIPS,
        "symbols": {},
    }
    # merge: runs parciais (1 simbolo) nao apagam simbolos anteriores
    if LIBRARY_PATH.exists():
        try:
            old = json.loads(LIBRARY_PATH.read_text(encoding="utf-8"))
            library["symbols"] = old.get("symbols", {})
        except (json.JSONDecodeError, OSError) as e:
            logger.error("library anterior ilegivel, recriando: %s", e)
    all_replay: list[dict[str, Any]] = []
    for sym in symbols:
        print(f"[SCAN] {sym}: iniciando ({days}d, stride {stride})...")
        r = scan_symbol(sym, days=days, stride=stride)
        library["symbols"][sym] = {k: v for k, v in r.items() if k != "replay_rows"}
        all_replay.extend(r.get("replay_rows", []))
        print(f"[SCAN] {sym}: {r.get('status')} — {len(r.get('patterns', []))} padroes, "
              f"{len(r.get('replay_rows', []))} sinais replay ({r.get('scan_seconds', 0)}s)")

    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_PATH.write_text(json.dumps(library, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[SCAN] library gravada: {LIBRARY_PATH.name}")

    if all_replay:
        from utils.orc_calibracao import append_signals, purge_signals
        # v1.2: re-scan SUBSTITUI replay dos simbolos escaneados (dedup
        # keep=first manteria scores velhos); live NUNCA e purgado
        purge_signals(origem="replay", symbols=symbols)
        n = append_signals(all_replay)
        print(f"[SCAN] signals_log: +{n} linhas replay (origem=replay, purge+replace)")
    return library


def main() -> None:
    ap = argparse.ArgumentParser(description="S34 Pattern Scan batch (730d consolidado)")
    ap.add_argument("--scan", required=True, help="'all' ou lista CSV de simbolos")
    ap.add_argument("--days", type=int, default=730)
    ap.add_argument("--stride", type=int, default=60, help="prototipo a cada N barras (default 60)")
    args = ap.parse_args()

    from utils.orc_metricas import VECTOR_SYMBOLS
    symbols = list(VECTOR_SYMBOLS) if args.scan == "all" else [s.strip() for s in args.scan.split(",")]
    run_scan(symbols, days=args.days, stride=args.stride)


if __name__ == "__main__":
    main()
