"""PROPOSITO: resample.py — Resample M1 OHLCV para timeframes superiores (M5, M15).
SPEC: S39 (MTF resample)
ROADMAP: C4 — substitui get_trendbars MCP por resample local do parquet M1.

Regra de ouro S25.11: MTF deve ser calculado por resample() local do M1,
preservando o padrao de nao sobrecarregar o MCP. get_trendbars removido por design.

Usa pandas.resample() (ja disponivel no ambiente).
"""

from __future__ import annotations

import pandas as pd

# Timeframes suportados e seus periodos de resample em minutos
MTF_PERIODS: dict[str, str] = {
    "M5": "5min",
    "M15": "15min",
}


def resample_m1_to_mtf(
    df_m1: pd.DataFrame,
    timeframes: tuple[str, ...] = ("M5", "M15"),
) -> dict[str, pd.DataFrame]:
    """Resample M1 OHLCV data para timeframes superiores (M5, M15).

    Args:
        df_m1: DataFrame M1 com colunas obrigatorias:
               - timestamp (int, ms epoch) OU datetime index
               - open, high, low, close, tick_volume (ou volume)
        timeframes: tupla de timeframes alvo (default: M5, M15)

    Returns:
        {timeframe: DataFrame} com OHLCV agregado:
        open=first, high=max, low=min, close=last, volume=sum
        Indexado por timestamp datetime.

    Raise:
        ValueError: se df_m1 vazio ou sem colunas obrigatorias.
    """
    if df_m1.empty:
        raise ValueError("df_m1 vazio — impossivel resample")

    df = df_m1.copy()

    # -- Normaliza timestamp -> datetime index --
    if "timestamp" in df.columns:
        ts_col = df["timestamp"]
        if pd.api.types.is_integer_dtype(ts_col):
            # ms epoch -> datetime
            df["_dt"] = pd.to_datetime(ts_col, unit="ms", utc=True)
        elif pd.api.types.is_datetime64_any_dtype(ts_col):
            df["_dt"] = ts_col
        else:
            # tenta string ISO
            df["_dt"] = pd.to_datetime(ts_col, utc=True)
    elif isinstance(df.index, pd.DatetimeIndex):
        df["_dt"] = df.index
    else:
        # tenta usar o index como timestamp
        try:
            if pd.api.types.is_integer_dtype(df.index):
                df["_dt"] = pd.to_datetime(df.index, unit="ms", utc=True)
            else:
                df["_dt"] = pd.to_datetime(df.index, utc=True)
        except Exception as e:
            raise ValueError(f"Nao foi possivel extrair timestamp: {e}") from e

    df = df.set_index("_dt").sort_index()

    # -- Normaliza nome da coluna de volume --
    vol_col = "tick_volume" if "tick_volume" in df.columns else "volume"
    if vol_col not in df.columns:
        vol_col = None

    # -- Colunas OHLCV obrigatorias --
    required = {"open", "high", "low", "close"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Colunas obrigatorias ausentes: {missing}")

    results: dict[str, pd.DataFrame] = {}

    for tf in timeframes:
        rule = MTF_PERIODS.get(tf)
        if rule is None:
            continue

        ohlcv_agg: dict[str, str] = {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
        }
        if vol_col:
            ohlcv_agg[vol_col] = "sum"

        resampled = df[list(ohlcv_agg.keys())].resample(rule).agg(ohlcv_agg)

        # Remove barras incompletas (NaN na vela final se ainda formando)
        resampled = resampled.dropna(subset=["open", "high", "low", "close"])

        # Renomeia volume de volta pra padrao
        if vol_col and vol_col != "volume":
            resampled = resampled.rename(columns={vol_col: "volume"})

        # Garante coluna volume
        if "volume" not in resampled.columns:
            resampled["volume"] = 0

        results[tf] = resampled

    return results
