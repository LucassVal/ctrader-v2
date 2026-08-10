"""PROPOSITO: matrix_orc_scan.py — Helpers numpy puros do Pattern Scan (S34).
SPEC: S34 (orc_pattern_engine.md)
ROADMAP: S34 — split DDD (G12: orc_scan estourou 200L).

SAT de orc_scan (split DDD G12). Sem IO, sem MCP, sem estado:
- feature_matrix: mesmas 5 features de orc_pattern.extract_feature_vector
- session_of: sessao UTC (tokyo/london/ny/rollover)
- cosine_batch / window_means: similaridade e medias de janela
- decay_weights: peso por recencia (<=90d x2, <=365d x1, antigo x0.5)
- outcome_stats: stats ponderadas (pips liquidos de spread)
- build_replay_row: linha do signals_log (S36 MODO PASSADO)
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np

# peso por recencia (S34 sec.4b)
DECAY_90D = 2.0
DECAY_365D = 1.0
DECAY_OLDER = 0.5


def session_of(ts_s: np.ndarray) -> np.ndarray:
    """Sessao UTC por timestamp (segundos): 0=tokyo 1=london 2=ny 3=rollover."""
    hours = ((ts_s // 3600) % 24).astype(int)
    sess = np.full(len(ts_s), 3, dtype=int)
    sess[(hours >= 0) & (hours < 7)] = 0
    sess[(hours >= 7) & (hours < 12)] = 1
    sess[(hours >= 12) & (hours < 21)] = 2
    return sess


def feature_matrix(points: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Matriz de features (N x 5) — MESMAS features de orc_pattern.extract_feature_vector.

    Defaults do codigo original preservados: rsi=50, adx=20, macd=0, atr=0.
    Retorna (feats, ts_s, closes, rsi, adx) — rsi/adx crus alimentam o
    trailing_quality_f1 (S34 v1.2) sem reler os dicts.
    """
    n = len(points)
    ts = np.zeros(n, dtype=np.int64)
    close = np.zeros(n)
    rsi = np.full(n, 50.0)
    macd_hist = np.zeros(n)
    adx = np.full(n, 20.0)
    bb_u = np.zeros(n)
    bb_l = np.zeros(n)
    atr = np.zeros(n)

    for i, row in enumerate(points):
        ts[i] = int(row.get("timestamp") or 0)
        close[i] = float(row.get("close") or row.get("last_close") or 0)
        v = row.get("rsi")
        if v:
            rsi[i] = float(v)
        v = row.get("macd_hist")
        if v:
            macd_hist[i] = float(v)
        v = row.get("adx")
        if v:
            adx[i] = float(v)
        v = row.get("bb_upper")
        if v:
            bb_u[i] = float(v)
        v = row.get("bb_lower")
        if v:
            bb_l[i] = float(v)
        v = row.get("atr")
        if v:
            atr[i] = float(v)

    with np.errstate(divide="ignore", invalid="ignore"):
        bb_range = bb_u - bb_l
        bb_pos = np.where(bb_range > 0, (close - bb_l) / bb_range, 0.5)
        atr_pct = np.where(close > 0, atr / close * 100, 0)
        macd_norm = np.where(close > 0, macd_hist / close * 10000, 0)

    feats = np.column_stack([
        rsi / 100,
        np.clip(macd_norm / 50, -1, 1),
        np.minimum(adx / 100, 1),
        bb_pos,
        np.minimum(atr_pct / 5, 1),
    ])
    return feats, ts, close, rsi, adx


def window_means(feats: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray]:
    """Medias das janelas deslizantes via cumsum — O(n) memoria (S34 sec.5).

    NOTA R21: media de janela REJEITADA como match space (destroi
    discriminacao) — mantida aqui para usos futuros de suavizacao.
    """
    if len(feats) < window:
        return np.empty((0, feats.shape[1])), np.empty(0, dtype=int)
    csum = np.vstack([np.zeros((1, feats.shape[1])), np.cumsum(feats, axis=0)])
    sums = csum[window:] - csum[:-window]
    vectors = sums / window
    last_idx = np.arange(len(vectors)) + window - 1
    return vectors, last_idx


def cosine_batch(query: np.ndarray, vectors: np.ndarray) -> np.ndarray:
    """Cosine similarity de query contra todas as linhas de vectors (0-1)."""
    qn = np.linalg.norm(query)
    if qn == 0:
        return np.zeros(len(vectors))
    norms = np.linalg.norm(vectors, axis=1)
    denom = norms * qn
    with np.errstate(divide="ignore", invalid="ignore"):
        sims = np.where(denom > 0, vectors @ query / denom, 0.0)
    return np.clip(sims, 0.0, 1.0)


def decay_weights(match_ts: np.ndarray, ref_ts: int) -> np.ndarray:
    """Peso por recencia: <=90d x2.0 / <=365d x1.0 / mais antigo x0.5."""
    age_d = (ref_ts - match_ts) / 86400.0
    w = np.full(len(match_ts), DECAY_OLDER)
    w[age_d <= 365] = DECAY_365D
    w[age_d <= 90] = DECAY_90D
    return w


def outcome_stats(pips: np.ndarray, weights: np.ndarray, min_pips: float) -> dict[str, Any]:
    """Estatisticas ponderadas de outcome (pips ja LIQUIDOS de spread)."""
    if len(pips) == 0:
        return {"n": 0, "bullish_pct": 0.0, "bearish_pct": 0.0, "avg_pips_net": 0.0}
    bull = pips > min_pips
    bear = pips < -min_pips
    wsum = float(weights.sum()) or 1.0
    bull_pct = float(weights[bull].sum()) / wsum * 100
    bear_pct = float(weights[bear].sum()) / wsum * 100
    avg = float(np.average(pips, weights=weights))
    return {
        "n": len(pips),
        "bullish_pct": round(bull_pct, 1),
        "bearish_pct": round(bear_pct, 1),
        "avg_pips_net": round(avg, 2),
    }


def build_replay_row(
    m: int,
    symbol: str,
    signal: str,
    score: float,
    quality_f1: float | None,
    coverage_pct: float | None,
    spread: float,
    ts: np.ndarray,
    closes: np.ndarray,
    out_pips: dict[int, np.ndarray],
) -> dict[str, Any] | None:
    """Linha do signals_log (origem=replay, S36) para a ocorrencia m.

    S34 v1.2: score ja vem COMPOSTO pelo orquestrador (quality x 0.33 +
    conf x 0.67) x coverage — aqui so persiste (0-100) + rastreabilidade.
    """
    o5, o15v, o60 = out_pips[5][m], out_pips[15][m], out_pips[60][m]
    if np.isnan(o60):
        return None
    # R21 (2026-07-30): spread na DIRECAO do sinal — short tambem paga spread.
    # Antes: r = o - spread p/ todo sinal -> BEARISH ganhava ate em alta leve
    # (hit_15m inflado em ~9 pontos). Agora: pips assinados na direcao —
    # positivo = acerto liquido de spread, para os DOIS lados.
    direction = 1.0 if signal == "BULLISH" else -1.0
    r5, r15, r60 = (float(direction * o5 - spread),
                    float(direction * o15v - spread),
                    float(direction * o60 - spread))
    return {
        "ts": datetime.fromtimestamp(int(ts[m]), UTC).isoformat(),
        "symbol": symbol,
        "origem": "replay",
        "strategy_id": None,
        "sinal": signal,
        "score": round(score * 100, 1),
        "quality_f1": quality_f1,
        "coverage_pct": coverage_pct,
        "close_entrada": float(closes[m]),
        "outcome_5m_pips": round(r5, 2),
        "outcome_15m_pips": round(r15, 2),
        "outcome_60m_pips": round(r60, 2),
        "acerto_5m": r5 > 0,
        "acerto_15m": r15 > 0,
        "acerto_60m": r60 > 0,
    }
