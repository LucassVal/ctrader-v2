"""
PROPOSITO: ORQUESTRADOR F1 — analise de metricas
SPEC: S3 (pai) + S17 (_indicators) — filhos: _pillars, _micro, _sentiment, _news, _dxy, _indicators
ROADMAP: 2.1
FLOW:   snapshot.json (F0) -> _pillars + _micro + _sentiment -> scores_raw.json
        _micro -> _dxy (DXY multi-par) | _pillars -> _indicators (compartilhado)
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from f1_analyzer.micro_orc_analise import calculate_correlation_matrix, calculate_spread
from f1_analyzer.pillars_orc_analise import (
    calculate_macro_score,
    calculate_tec_score,
    calculate_vol_score,
)
from f1_analyzer.sentiment_orc_analise import calc_sentiment_ratio
from utils.schema_validator import validate_scores_raw

# CORTADOS da v1 (spec S3):
#   _ichimoku.py -- Senkou B = 52p, nuvem 26min a frente > holding. Reavaliar out-of-sample.
#   _volume.py  -- zero importadores. Wirear ou arquivar (ROADMAP 2.4).
# Correlation (F1 -> F2): _micro.calculate_correlation_matrix() -- computa aqui, consome no F2.

logger = logging.getLogger(__name__)


def _generate_trace() -> str:
    return f"T{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-ANALYZE"


def analyze(df: pd.DataFrame, symbol: str, news_imminent: bool = False) -> dict[str, Any]:
    """Analisa df_master e retorna scores_raw.json como dict.

    NUCLEO v1 (spec S3): 3 pilares (_pillars) + spread (_micro) + sentiment (_sentiment).
    Correlation 5x5 computada aqui, consumida no F2 (ranking).
    Ichimoku + Volume CORTADOS da v1.
    """
    # Satelites wireados (spec S3 §indicadores v1 + §globais)
    sentiment_ratio = calc_sentiment_ratio()

    # Correlation 5x5 — F1 computa, F2 consome (spec S3 §globais)
    corr_matrix: dict[str, dict[str, float]] = {}
    try:
        symbols = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
        corr_matrix = calculate_correlation_matrix(df, symbols)
    except Exception:
        pass

    result = {
        "trace_id": _generate_trace(),
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "symbol": symbol,
        "news_imminent": news_imminent,
        "scores": {
            "macro": round(calculate_macro_score(df), 1),
            "volatilidade": round(calculate_vol_score(df), 1),
            "tecnico": round(calculate_tec_score(df), 1),
            "spread": calculate_spread(
                float(df.iloc[-1]["bid"]) if not df.empty else 0,
                float(df.iloc[-1]["ask"]) if not df.empty else 0,
            ),
            "sentiment": round(sentiment_ratio * 100, 1),  # 0-100
        },
        # Correlation passa-through para F2 (nao entra no score F1)
        "correlation": corr_matrix if corr_matrix else {},
    }

    errors = validate_scores_raw(result)
    if errors:
        logger.error("Validacao scores falhou: %s", errors)

    return result


def analyze_and_save(df: pd.DataFrame, symbol: str,
                     news_imminent: bool = False, output_path: str = "scores_raw.json"):
    """Analisa e salva scores_raw.json com escrita atomica (ROADMAP 3.2)."""
    result = analyze(df, symbol, news_imminent)
    from utils._artifacts import save_scores_raw
    path = save_scores_raw(result)
    logger.info("scores_raw.json salvo: %s scores=%s", path, result["scores"])
    return result


def main():
    import argparse
    parser = argparse.ArgumentParser(description="F1 Analyzer -- 3 pilares + spread + sentiment")
    parser.add_argument("--parquet", required=True, help="Arquivo parquet da F0")
    parser.add_argument("--symbol", default="XAUUSD")
    parser.add_argument("--output", default="scores_raw.json")
    parser.add_argument("--news", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    df = pd.read_parquet(args.parquet)
    news = args.news if hasattr(args, 'news') else False
    if news:
        logger.error("News imminent detectado. Scores mantidos, lote reduzido na F4.")
    analyze_and_save(df, args.symbol, news_imminent=news, output_path=args.output)


if __name__ == "__main__":
    main()
