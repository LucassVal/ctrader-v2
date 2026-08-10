"""PROPOSITO: orc_pattern.py — Pattern Matching via sliding window + cosine similarity.
SPEC: S30
ROADMAP: S30 — "Este setup atual ja apareceu antes? O que aconteceu depois?"

R-USE: storage_orc_vbt.py (load_history) + numpy/scipy (sem novas deps).
Pipeline: VBT history -> sliding windows -> cosine similarity -> top-K -> outcome stats.

Principio:
  Compara o VETOR de indicadores (nao so preco) — captura o "estado do mercado".

Metricas:
  - similarity: quao parecido e o padrao (0-1, quanto maior melhor)
  - bullish_pct: % matches que resultaram em alta
  - avg_gain_pips: ganho medio apos o match
  - confidence: similarity x bullish_pct (score combinado)
"""

from __future__ import annotations

from typing import Any


def extract_feature_vector(row: dict[str, Any]) -> list[float]:
    """Extrai vetor de features de 1 snapshot VBT.
    Features escolhidas: RSI, MACD, ADX, BB position, ATR normalizado.
    """
    close = float(row.get("close") or row.get("last_close") or 0)
    rsi = float(row.get("rsi") or 50)
    macd_hist = float(row.get("macd_hist") or 0)
    adx = float(row.get("adx") or 20)
    bb_upper = float(row.get("bb_upper") or 0)
    bb_lower = float(row.get("bb_lower") or 0)
    float(row.get("bb_middle") or 0)
    atr = float(row.get("atr") or 0)

    # BB position: 0 = lower, 0.5 = middle, 1 = upper
    bb_range = bb_upper - bb_lower
    bb_position = (close - bb_lower) / bb_range if bb_range > 0 else 0.5

    # ATR as % of price
    atr_pct = (atr / close * 100) if close > 0 else 0

    # Normalize MACD histogram
    macd_norm = macd_hist / close * 10000 if close > 0 else 0

    return [
        rsi / 100,           # 0-1
        max(-1, min(1, macd_norm / 50)),  # ~ -1 to 1
        min(1, adx / 100),   # 0-1
        bb_position,         # 0-1
        min(1, atr_pct / 5),  # 0-1
    ]


def extract_windows(
    history: list[dict[str, Any]], window_size: int = 20
) -> tuple[list[list[float]], list[int], list[float]]:
    """Sliding window: extrai vetor medio de features para cada janela de N velas.
    Retorna: (vectors, timestamps, close_prices)
    """
    if len(history) < window_size:
        return [], [], []

    vectors: list[list[float]] = []
    timestamps: list[int] = []
    closes: list[float] = []

    for i in range(len(history) - window_size + 1):
        window = history[i : i + window_size]
        # Media dos vetores de feature na janela
        feat_sums = [0.0] * 5
        count = 0
        for row in window:
            feats = extract_feature_vector(row)
            if any(f != 0 for f in feats):
                for j in range(5):
                    feat_sums[j] += feats[j]
                count += 1

        if count > 0:
            avg_feats = [s / count for s in feat_sums]
            vectors.append(avg_feats)

            ts = window[-1].get("timestamp")
            timestamps.append(int(ts) if ts else 0)

            close_val = window[-1].get("close") or window[-1].get("last_close") or 0
            closes.append(float(close_val))

    return vectors, timestamps, closes


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity entre dois vetores (0-1). Implementacao numpy-free."""
    dot = sum(x * y for x, y in zip(a, b, strict=False))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (norm_a * norm_b)))


def find_similar(
    query: list[float],
    vectors: list[list[float]],
    timestamps: list[int],
    closes: list[float],
    top_k: int = 10,
    min_similarity: float = 0.7,
) -> list[dict[str, Any]]:
    """Encontra top-K janelas mais similares a query.
    Exclui a propria query (ultima janela).
    """
    if len(vectors) < 2:
        return []

    scores: list[tuple[int, float]] = []
    for i in range(len(vectors) - 1):  # exclui a ultima (query)
        sim = cosine_similarity(query, vectors[i])
        if sim >= min_similarity:
            scores.append((i, sim))

    scores.sort(key=lambda x: -x[1])
    top = scores[:top_k]

    results: list[dict[str, Any]] = []
    for idx, sim in top:
        results.append({
            "index": idx,
            "timestamp": timestamps[idx],
            "close": closes[idx],
            "similarity": round(sim, 4),
        })

    return results


def outcome_analysis(
    matches: list[dict[str, Any]],
    closes: list[float],
    timestamps: list[int],
    lookahead: int = 5,
    min_pips: float = 5.0,
    pip_size: float = 0.0001,
) -> dict[str, Any]:
    """Para cada match, verifica o que aconteceu nas proximas N velas.
    Retorna estatisticas agregadas de outcome.
    pip_size: tamanho de 1 pip em preco (R-USE PIP_SPECS.pip_size, S30-PIPS).
    """
    if not matches or len(closes) < lookahead:
        return {"total_matches": len(matches), "analysed": 0, "note": "dados insuficientes"}

    bullish = 0
    bearish = 0
    neutral = 0
    gains: list[float] = []
    details: list[dict[str, Any]] = []

    for m in matches:
        idx = m["index"]
        if idx + lookahead >= len(closes):
            continue

        entry = closes[idx]
        exit_p = closes[idx + lookahead]

        if entry == 0 or exit_p == 0:
            continue

        # Pips por ativo (S30-PIPS): XAUUSD 1 pip = $0.10, JPY 0.01, demais 0.0001
        pips = (exit_p - entry) / pip_size if pip_size > 0 else 0

        if pips > min_pips:
            bullish += 1
        elif pips < -min_pips:
            bearish += 1
        else:
            neutral += 1

        gains.append(pips)
        details.append({
            "ts": m.get("timestamp"),
            "entry": entry,
            "exit": exit_p,
            "pips": round(pips, 1),
            "similarity": m["similarity"],
        })

    total = bullish + bearish + neutral
    avg_gain = sum(gains) / len(gains) if gains else 0
    bullish_pct = (bullish / total * 100) if total else 0
    bearish_pct = (bearish / total * 100) if total else 0
    confidence = bullish_pct / 100 if bullish_pct > bearish_pct else bearish_pct / 100

    return {
        "total_matches": len(matches),
        "analysed": total,
        "bullish": bullish,
        "bearish": bearish,
        "neutral": neutral,
        "bullish_pct": round(bullish_pct, 1),
        "bearish_pct": round(bearish_pct, 1),
        "avg_gain_pips": round(avg_gain, 1),
        "min_gain_pips": round(min(gains), 1) if gains else 0,
        "max_gain_pips": round(max(gains), 1) if gains else 0,
        "confidence": round(confidence, 2),
        "signal": "BULLISH" if bullish_pct > 60 else ("BEARISH" if bearish_pct > 60 else "NEUTRAL"),
        "top_match": details[0] if details else None,
        "details": details[:5],
    }


def pattern_analysis(symbol: str, window_size: int = 20, top_k: int = 10) -> dict[str, Any]:
    """Orquestrador S30: carrega historico -> sliding windows -> query atual -> top-K matches -> outcome.

    R-USE:
      - storage_orc_vbt.load_history() para dados historicos
      - orc_quality.quality_metrics() para combinar scores

    Args:
        symbol: par (XAUUSD, EURUSD...)
        window_size: tamanho da janela de comparacao (velas)
        top_k: quantos matches retornar
    """
    try:
        from utils.orc_mercado import PIP_SPECS
        from utils.storage_orc_vbt import load_history

        # Pip size por ativo (S30-PIPS): R-USE PIP_SPECS (XAUUSD=0.1, JPY=0.01)
        pip_size = PIP_SPECS.get(symbol, {}).get("pip_size", 0.0001)

        vbt_history = load_history(symbol, days=730)
        points = vbt_history.get("points", [])

        if len(points) < window_size + 10:
            return {
                "symbol": symbol,
                "status": "sem_dados",
                "total_points": len(points),
                "min_required": window_size + 10,
                "note": f"Execute backfill. Precisamos de {window_size + 10}+ velas no vbt_{symbol}.parquet",
            }

        # Sliding windows
        vectors, timestamps, closes = extract_windows(points, window_size)

        if len(vectors) < 2:
            return {
                "symbol": symbol,
                "status": "sem_dados",
                "total_points": len(points),
                "windows": len(vectors),
                "note": "Precisa de mais dados para formar janelas",
            }

        # Query = ultima janela (estado atual do mercado)
        query = vectors[-1]

        # Top-K matches
        matches = find_similar(query, vectors, timestamps, closes, top_k=top_k)

        if not matches:
            return {
                "symbol": symbol,
                "status": "sem_matches",
                "total_points": len(points),
                "windows_compared": len(vectors) - 1,
                "note": "Nenhum padrao similar encontrado (min similarity 0.7). Mercado em regime novo?",
            }

        # Outcome analysis
        outcome = outcome_analysis(matches, closes, timestamps, pip_size=pip_size)

        # Estatisticas de similaridade
        similarities = [m["similarity"] for m in matches]
        avg_sim = sum(similarities) / len(similarities) if similarities else 0

        # Periodo de analise
        all_ts = [t for t in timestamps if t > 0]
        first_ts = min(all_ts) if all_ts else 0
        last_ts = max(all_ts) if all_ts else 0
        analysis_days = (last_ts - first_ts) / 86400 if first_ts and last_ts else 0

        return {
            "symbol": symbol,
            "status": "ok",
            "analysis_days": round(analysis_days, 1),
            "total_points": len(points),
            "windows_compared": len(vectors) - 1,
            "window_size": window_size,
            "matches_found": len(matches),
            "avg_similarity": round(avg_sim, 4),
            "outcome": outcome,
            "query_features": [round(f, 4) for f in query],
            "feature_labels": ["rsi", "macd", "adx", "bb_pos", "atr_pct"],
            "note": (
                f"Confianca: {outcome.get('confidence', 0):.0%}. "
                f"Sinal: {outcome.get('signal', '?')}. "
                f"Base: {len(matches)} padroes similares em {analysis_days:.0f}d"
            ),
        }

    except Exception as e:
        return {
            "symbol": symbol,
            "status": "erro",
            "error": str(e)[:200],
        }
