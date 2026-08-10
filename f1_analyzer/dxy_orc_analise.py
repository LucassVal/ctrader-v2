"""PROPOSITO: DXY Score multi-par — 3 majors da cesta USDX
SPEC: S3
ROADMAP: 2.5 + 2.6
"""
from __future__ import annotations

import pandas as pd

# Pesos renormalizados dos 3 majors no DXY (USDX futures basket)
# EURUSD 57.6%, USDJPY 13.6%, GBPUSD 11.9% -> normalizado para 1.0
DXY_WEIGHTS = {"EURUSD": 0.693, "USDJPY": 0.164, "GBPUSD": 0.143}
# AUDUSD e XAUUSD NAO compoem o DXY — sao consumidores do sinal


def calculate_multi_dxy_score(closes: pd.DataFrame) -> float:
    """Score DXY multi-par com 3 majors (83.1% da cesta).

    Args:
        closes: DataFrame com colunas EURUSD, USDJPY, GBPUSD.
                >=20 barras obrigatorio (R-NO-SILENT-FAIL).

    Returns:
        Score 0-100. >50 = dolar forte (pressiona ouro/commodities).
        USDJPY com sinal INVERTIDO (USD e moeda-base, sobe = dolar forte).
    """
    if closes is None or len(closes) < 20:
        raise ValueError(f"DXY multi-par requer >=20 barras, tem {len(closes) if closes is not None else 0}")

    scores: dict[str, float] = {}
    for pair, _weight in DXY_WEIGHTS.items():
        if pair not in closes.columns:
            continue
        series = closes[pair].dropna()
        if len(series) < 20:
            continue

        sma20 = series.rolling(20).mean().iloc[-1]
        sma50 = series.rolling(min(50, len(series))).mean().iloc[-1] if len(series) >= 5 else sma20

        if pair == "USDJPY":
            # USDJPY sobe = dolar forte = sinal INVERTIDO
            if sma20 > sma50:
                pct = (sma20 - sma50) / sma50 * 100
                pair_score = min(100, 50 + pct * 10)
            else:
                pct = (sma50 - sma20) / sma50 * 100
                pair_score = max(0, 50 - pct * 10)
        else:
            # EURUSD/GBPUSD: par cai = dolar sobe
            if sma20 < sma50:
                pct = (sma50 - sma20) / sma50 * 100
                pair_score = min(100, 50 + pct * 10)
            else:
                pct = (sma20 - sma50) / sma50 * 100
                pair_score = max(0, 50 - pct * 10)

        scores[pair] = pair_score

    if not scores:
        raise ValueError("DXY multi-par: nenhum par com dados suficientes")

    # Media ponderada pelos pesos da cesta DXY
    weighted = sum(scores[p] * DXY_WEIGHTS[p] for p in scores)
    return round(weighted, 2)
