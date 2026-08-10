"""PROPOSITO: Orquestrador de Indices — agrega DXY sintetico + sentimento dos analisadores F1.
SPEC: S25.10
ROADMAP: Indices globais
DXY: calculado de EURUSD+USDJPY+GBPUSD (dxy_orc_analise.py) — 83.1% da cesta USDX.
Sentiment: bull/bear ratio dos 5 pares (sentiment_orc_analise.py).
Nao depende de yfinance nem de simbolos externos — tudo derivado dos 5 pares.
"""
from __future__ import annotations

from typing import Any


def collect_indices() -> dict[str, Any]:
    """Agrega DXY sintetico + sentiment dos analisadores F1.
    Le snapshot F0 para obter closes, calcula via dxy_orc_analise + sentiment_orc_analise.
    """
    try:
        from utils.data_source import get_markets_raw
        raw = get_markets_raw()
    except Exception:
        return {"online": False, "indices": {}, "source": "DataSource offline"}

    closes: dict[str, list[float]] = {}
    for sym in ["EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "XAUUSD"]:
        m = raw.get(sym, {})
        close = m.get("close", 0)
        if close:
            closes[sym] = [close]

    # -- DXY sintetico --
    dxy_score = 50.0
    dxy_trend = "NEUTRO"
    if all(k in closes for k in ["EURUSD", "USDJPY", "GBPUSD"]):
        try:
            import pandas as pd
            df = pd.DataFrame({k: [v[0]] for k, v in closes.items()})
            from f1_analyzer.dxy_orc_analise import DXY_WEIGHTS
            score = 0.0
            total_w = 0.0
            for pair, w in DXY_WEIGHTS.items():
                if pair in df.columns:
                    c = df[pair].iloc[-1]
                    ref = 1.10 if pair == "EURUSD" else (110.0 if pair == "USDJPY" else 1.30)
                    change = (c - ref) / ref
                    if pair == "USDJPY":
                        change = -change  # inverted
                    score += change * w * 100
                    total_w += w
            if total_w:
                dxy_score = round(50 + score / total_w, 1)
                dxy_score = max(0, min(100, dxy_score))
            dxy_trend = "DOLAR_FORTE" if dxy_score > 60 else ("DOLAR_FRACO" if dxy_score < 40 else "NEUTRO")
        except Exception:
            pass

    # -- Sentiment --
    sentiment = "NEUTRO"
    try:
        from f1_analyzer.sentiment_orc_analise import calc_sentiment_ratio
        ratio = calc_sentiment_ratio()
        if ratio > 0.6:
            sentiment = "BULLISH"
        elif ratio < 0.4:
            sentiment = "BEARISH"
    except Exception:
        pass

    return {
        "online": bool(raw),
        "dxy_score": dxy_score,
        "dxy_trend": dxy_trend,
        "sentiment": sentiment,
        "source": "Sintetico (dxy_orc_analise + sentiment_orc_analise — via F0 snapshot)",
    }


def correlate_with_markets() -> dict[str, Any]:
    """Atalho para compatibilidade com /vector/globals (S25.10 legado)."""
    return collect_indices()


CORR_SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]

_CORR_CACHE: dict[int, tuple[float, dict[str, Any]]] = {}

def correlate_markets_m1(window: int = 200) -> dict[str, Any]:
    """Matriz de correlacao 5x5 (Pearson) sobre closes M_1 dos parquets consolidados (S31).

    Cache: janelas curtas (<=200) tem TTL de 5 min. Janelas longas (1440, 7200) tem TTL de 15 min.
    Leitura local de data/consolidated/{SYM}_M1.parquet — R-NO-MCP-BYPASS.
    """
    import time
    from pathlib import Path

    import pandas as pd

    now = time.time()
    if window in _CORR_CACHE:
        cached_time, cached_data = _CORR_CACHE[window]
        ttl = 300 if window <= 200 else 900
        if now - cached_time < ttl:
            return cached_data

    data_dir = Path(__file__).resolve().parent.parent / "data" / "consolidated"
    series: dict[str, pd.Series] = {}
    samples: dict[str, int] = {}

    for sym in CORR_SYMBOLS:
        file_path = data_dir / f"{sym}_M1.parquet"
        if not file_path.exists():
            continue
        try:
            df = pd.read_parquet(file_path)
            df["timestamp"] = pd.to_numeric(df["timestamp"], errors="coerce")
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
            df = df.drop_duplicates(subset=["timestamp"], keep="last").tail(window)
            s = df.set_index(df["timestamp"].astype("int64"))["close"].astype(float)
            series[sym] = s
            samples[sym] = len(s)
        except Exception:
            continue

    if len(series) < 2:
        return {
            "correlation_matrix": {},
            "note": "serie M_1 insuficiente — consolidated/ pendente",
            "samples": samples,
        }

    df_all = pd.DataFrame(series).dropna()
    if len(df_all) < 14:
        return {
            "correlation_matrix": {},
            "note": f"so {len(df_all)} pontos alinhados — minimo 14",
            "samples": samples,
        }

    corr = df_all.corr(method="pearson").round(3)
    matrix = {sym: {k: (None if pd.isna(v) else v) for k, v in corr[sym].items()} for sym in corr.columns}

    result = {
        "correlation_matrix": matrix,
        "window": window,
        "aligned_points": len(df_all),
        "samples": samples,
        "source": "consolidated/{SYM}_M1.parquet (S31)",
        "note": "Pearson sobre closes M_1 alinhados por timestamp",
    }

    _CORR_CACHE[window] = (now, result)
    return result
