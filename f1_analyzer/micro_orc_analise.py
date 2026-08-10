"""
PROPOSITO: F1 — INDICADORES MICRO + GLOBAIS POR ATIVO
SPEC: S3
ROADMAP: 2.1
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def extract_symbol_metadata(symbols_data: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Extrai pipDigits e lotSize do get_symbols().
    Retorna: {symbolName: {pipDigits, lotSize, baseAssetId, quoteAssetId}}
    """
    meta = {}
    for s in symbols_data:
        if not isinstance(s, dict):
            continue
        name = s.get("symbolName", "")
        if not name:
            continue
        meta[name] = {
            "pipDigits": s.get("pipDigits", 5),
            "lotSize": s.get("lotSize", 100000),
            "baseAssetId": s.get("baseAssetId"),
            "quoteAssetId": s.get("quoteAssetId"),
            "symbolId": s.get("symbolId"),
            "enabled": s.get("enabled", True),
        }
    return meta


def calculate_spread(bid: float, ask: float) -> float:
    """Spread absoluto em pontos."""
    return abs(ask - bid)


def calculate_spread_pct(bid: float, ask: float) -> float:
    """Spread relativo %."""
    mid = (bid + ask) / 2
    return (abs(ask - bid) / mid * 100) if mid > 0 else 0


def extract_swap_info(positions: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Extrai swap acumulado por símbolo das posições abertas.
    Retorna: {symbolName: {swap, commission}}
    """
    swaps = {}
    for p in positions:
        if not isinstance(p, dict):
            continue
        sym = p.get("symbolName", "")
        if not sym:
            continue
        if sym not in swaps:
            swaps[sym] = {"swap": 0.0, "commission": 0.0}
        swaps[sym]["swap"] += float(p.get("swap", 0) or 0)
        swaps[sym]["commission"] += float(p.get("commission", 0) or 0)
    return swaps


def calculate_correlation_matrix(
    df_master,  # pd.DataFrame com colunas: symbol, close
    symbols: list[str],
) -> dict[str, dict[str, float]]:
    """Matriz de correlação entre os 5 ativos usando closes.
    Retorna: {sym1: {sym2: corr, ...}, ...}
    """

    closes = {}
    for sym in symbols:
        sym_df = df_master[df_master["symbol"] == sym]
        if len(sym_df) > 1:
            closes[sym] = sym_df["close"].astype(float)

    if len(closes) < 2:
        return {}

    df = pd.DataFrame(closes)
    corr_matrix = df.corr().to_dict()
    return corr_matrix


def calculate_global_dxy_score(eurusd_close_series) -> float:
    """Score macro baseado no proxy DXY (EURUSD inverso).
    Retorna 0-100: >50 = dólar forte (bearish EURUSD), <50 = dólar fraco.
    """
    if eurusd_close_series is None or len(eurusd_close_series) < 20:
        return 50.0  # neutro

    closes = pd.Series(eurusd_close_series).dropna()
    if len(closes) < 2:
        return 50.0

    # Tendência: SMA20 vs SMA50
    sma20 = closes.rolling(20).mean().iloc[-1] if len(closes) >= 20 else closes.mean()
    sma50 = closes.rolling(min(50, len(closes))).mean().iloc[-1] if len(closes) >= 5 else closes.mean()

    if sma20 < sma50:  # EURUSD caindo = dólar subindo
        pct = (sma50 - sma20) / sma50 * 100
        return min(100, 50 + pct * 10)
    else:
        pct = (sma20 - sma50) / sma50 * 100
        return max(0, 50 - pct * 10)


# ---------------------------------------------------------------------------
# Re-exportado de _dxy.py (ROADMAP 2.5 split, G12 GOD <200L)

# Pivots R1/R2/S1/S2 do D_1 anterior (ROADMAP 1.4)
# ---------------------------------------------------------------------------

def calc_pivots(d1_bar: dict[str, Any]) -> dict[str, float]:
    """Calcula pivots classicos de uma barra diaria (D_1).

    P = (H + L + C) / 3
    R1 = 2P - L    S1 = 2P - H
    R2 = P + (H-L)  S2 = P - (H-L)

    ROADMAP 1.4: usar como filtro/alvo de TP (sniper), NAO como score.
    Custo: 1 barra D_1 por ativo/dia.
    """
    h = float(d1_bar.get("high", 0))
    lo = float(d1_bar.get("low", 0))
    c = float(d1_bar.get("close", 0))
    if h == 0 or lo == 0 or c == 0:
        return {"P": 0.0, "R1": 0.0, "R2": 0.0, "S1": 0.0, "S2": 0.0}
    P = (h + lo + c) / 3.0
    return {
        "P": round(P, 5),
        "R1": round(2 * P - lo, 5),
        "S1": round(2 * P - h, 5),
        "R2": round(P + (h - lo), 5),
        "S2": round(P - (h - lo), 5),
    }
