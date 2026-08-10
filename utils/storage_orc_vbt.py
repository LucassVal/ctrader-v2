"""PROPOSITO: storage_orc_vbt.py — Persistencia Vector BT no Parquet.
SPEC: S27 / S39 (MTF — save_indicators timeframe suffix)
ROADMAP: S27, C4 — 1 arquivo vbt_{SYM}[_{TF}].parquet por simbolo/timeframe

R-USE: storage_orc_coleta.py (append_rows no Parquet). S2.5: m1 bruto F0.
Ampliado: save_indicators() + load_indicators() + load_history().
S31-VBT (2026-07-30): fallback para o CONSOLIDADO G23 (2 anos) via SAT
utils/storage_orc_consolidated.py — o vbt so acumula snapshots do F0 vivo
(~1 dia); quem cobre mais historico vence.

Arquitetura:
    data/m1_{SYM}_{ANO}.parquet        -> OHLCV bruto (F0)
    data/vbt_{SYM}.parquet             -> indicadores M1 + timestamps
    data/vbt_{SYM}_M5.parquet          -> indicadores M5 (resample local)
    data/vbt_{SYM}_M15.parquet         -> indicadores M15 (resample local)
    data/consolidated/{SYM}_M1.parquet -> OHLCV canonico 2 anos (G23) -> fallback
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from utils.storage_orc_consolidated import consolidated_indicator_points

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _vbt_path(symbol: str, timeframe: str | None = None) -> Path:
    """Caminho do Parquet de indicadores VBT para 1 simbolo (opcional timeframe)."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if timeframe and timeframe != "M1":
        return DATA_DIR / f"vbt_{symbol}_{timeframe}.parquet"
    return DATA_DIR / f"vbt_{symbol}.parquet"


def _vbt_span_days(symbol: str, days: int, timeframe: str | None = None) -> tuple[list[dict[str, Any]], float]:
    """Le pontos do vbt e o span real (dias) coberto no periodo."""
    path = _vbt_path(symbol, timeframe)
    if not path.exists():
        return [], 0.0
    df = pd.read_parquet(path)
    if df.empty:
        return [], 0.0
    cutoff = int((datetime.now(UTC) - timedelta(days=days)).timestamp())
    df_recent = df[df["timestamp"] >= cutoff]
    points = df_recent.tail(500).to_dict(orient="records")
    for p in points:
        for k, v in p.items():
            if isinstance(v, float) and pd.isna(v):
                p[k] = None
    span = (round(float(df_recent["timestamp"].iloc[-1]
                        - df_recent["timestamp"].iloc[0]) / 86400, 1)
            if len(df_recent) > 1 else 0.0)
    return points, span


def save_indicators(symbol: str, indicators: dict[str, Any], ts: int | None = None,
                    timeframe: str | None = None) -> bool:
    """Grava 1 linha de indicadores VBT no Parquet do simbolo.
    Append-only — cada chamada = 1 snapshot de indicadores.

    Args:
        symbol: par forex (XAUUSD, etc.)
        indicators: dict de indicadores (rsi, macd, atr, ...)
        ts: timestamp unix (segundos). Default: now().
        timeframe: opcional — "M5" ou "M15" salva em vbt_{SYM}_{TF}.parquet
    """
    if ts is None:
        ts = int(datetime.now(UTC).timestamp())

    row = {"timestamp": ts}
    for k, v in indicators.items():
        if isinstance(v, (int, float, bool, str)):
            row[k] = v
        elif v is None:
            row[k] = None
        else:
            row[k] = str(v)[:100]  # fallback seguro

    df_new = pd.DataFrame([row])

    path = _vbt_path(symbol, timeframe)
    if path.exists():
        df_old = pd.read_parquet(path)
        df_all = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df_all = df_new

    df_all.to_parquet(path, index=False)
    return True


def save_indicators_mtf(symbol: str, mtf_indicators: dict[str, dict[str, Any]],
                         ts: int | None = None) -> dict[str, bool]:
    """Grava indicadores para todos os timeframes de uma vez.

    Args:
        symbol: par forex
        mtf_indicators: {"M1": {indicators}, "M5": {...}, "M15": {...}}
        ts: timestamp unix

    Returns:
        {"M1": True/False, "M5": True/False, "M15": True/False}
    """
    if ts is None:
        ts = int(datetime.now(UTC).timestamp())

    results: dict[str, bool] = {}
    for tf, indicators in mtf_indicators.items():
        if indicators and not indicators.get("error"):
            ok = save_indicators(symbol, indicators, ts=ts, timeframe=tf if tf != "M1" else None)
            results[tf] = ok
        else:
            results[tf] = False
    return results


def load_indicators(symbol: str, lookback_days: int = 60,
                    timeframe: str | None = None) -> dict[str, Any]:
    """Carrega ultimos indicadores (snapshot atual + historico recente).

    S31-VBT: se o consolidado G23 cobre mais historico que o vbt (F0 vivo),
    o snapshot/historico vem do consolidado — history_days = SPAN REAL
    (alimenta analysis_days do quality e a confianca do score).

    Args:
        symbol: par forex
        lookback_days: dias de lookback
        timeframe: opcional — "M5" ou "M15" para MTF; None = M1
    """
    if timeframe and timeframe != "M1":
        # MTF: so le do vbt local (consolidado e so M1)
        vbt_points, vbt_days = _vbt_span_days(symbol, lookback_days, timeframe)
        if vbt_points:
            return {
                "status": "ok",
                "symbol": symbol,
                "timeframe": timeframe,
                "latest": vbt_points[-1],
                "history_days": vbt_days,
                "history_points": len(vbt_points),
                "history": vbt_points,
                "source": f"vbt_f0_live_{timeframe}",
            }
        return {"status": "vazio", "symbol": symbol, "timeframe": timeframe,
                "latest": None, "history_days": 0}

    # M1: fallback para consolidado G23
    cons = consolidated_indicator_points(symbol, max(lookback_days, 730), max_points=200,
                                         full_families=True)
    vbt_points, vbt_days = _vbt_span_days(symbol, lookback_days)

    if cons and float(cons.get("history_days", 0)) > vbt_days:
        pts = cons["points"]
        return {
            "status": "ok",
            "symbol": symbol,
            "latest": pts[-1] if pts else None,
            "history_days": cons["history_days"],
            "history_points": cons["history_points"],
            "history": pts,
            "source": cons["source"],
        }

    if vbt_points:
        return {
            "status": "ok",
            "symbol": symbol,
            "latest": vbt_points[-1],
            "history_days": vbt_days,
            "history_points": len(vbt_points),
            "history": vbt_points,
            "source": "vbt_f0_live",
        }

    return {"status": "vazio", "symbol": symbol, "latest": None, "history_days": 0}


def load_history(symbol: str, days: int = 730) -> dict[str, Any]:
    """Carrega historico de indicadores (ate 2 anos / 730 dias).

    S31-VBT: prefere a fonte com MAIOR span real — consolidado G23 (2 anos)
    ou vbt (snapshots F0 vivo). Retorna serie temporal para graficos YoY.
    """
    cons = consolidated_indicator_points(symbol, days)
    vbt_points, vbt_days = _vbt_span_days(symbol, days)

    if cons and float(cons.get("history_days", 0)) > vbt_days:
        return {
            "status": "ok",
            "symbol": symbol,
            "days_requested": days,
            "history_days": cons["history_days"],
            "history_points": cons["history_points"],
            "points": cons["points"],
            "source": cons["source"],
        }

    if not vbt_points:
        return {"status": "vazio", "symbol": symbol, "points": []}

    return {
        "status": "ok",
        "symbol": symbol,
        "days_requested": days,
        "history_days": vbt_days,
        "points": vbt_points,
        "source": "vbt_f0_live",
    }
