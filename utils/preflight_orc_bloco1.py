"""PROPOSITO: Preflight do Bloco 1 — DXYUSD + VIXUSD (alinhamento multi-bolsa).

SPEC: S41 — Bloco 1: Torneio do Passado
SAT: preflight_orc_bloco1
ROADMAP: FASE 3 (S41)

Extrai do ORQ orc_bloco1.py (split DDD G12 — GOD object).
Baixa e alinha DXYUSD + VIXUSD do parquet. FAIL FAST se ausentes.
"""
from __future__ import annotations

import logging
import sys as _sys
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def preflight_check(
    ohlc_df: pd.DataFrame,
    symbol: str,
) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """Baixa e alinha DXYUSD + VIXUSD do parquet. FAIL FAST se ausentes.

    Universo Macro (S41.4 v2.0):
      DXYUSD - Filtro Direcional (ROC 5 periodos)
      VIXUSD - Filtro de Volatilidade/Panico (>35 = aborta)

    Returns:
        (ohlc_df, dxy_close, vix_close): Series alinhadas por timestamp.
    """
    data_dir = Path(__file__).resolve().parent.parent / "data"
    consolidated_dir = data_dir / "consolidated"

    dxy_path = consolidated_dir / "DXYUSD_M1.parquet"
    vix_path = consolidated_dir / "VIXUSD_M1.parquet"

    if not dxy_path.exists():
        logger.error("PREFLIGHT: %s nao encontrado. Execute backfill. ABORTANDO %s.", dxy_path, symbol)
        print("[PREFLIGHT] ERRO: DXYUSD_M1.parquet ausente. Execute backfill primeiro.")
        _sys.exit(1)
    if not vix_path.exists():
        logger.error("PREFLIGHT: %s nao encontrado. Execute backfill. ABORTANDO %s.", vix_path, symbol)
        print("[PREFLIGHT] ERRO: VIXUSD_M1.parquet ausente. Execute backfill primeiro.")
        _sys.exit(1)

    try:
        dxy_df = pd.read_parquet(dxy_path)
        if "timestamp" in dxy_df.columns:
            dxy_df["timestamp"] = pd.to_datetime(dxy_df["timestamp"].astype("int64"), unit="ms")
            dxy_df.set_index("timestamp", inplace=True)
            dxy_df.sort_index(inplace=True)

        vix_df = pd.read_parquet(vix_path)
        if "timestamp" in vix_df.columns:
            vix_df["timestamp"] = pd.to_datetime(vix_df["timestamp"].astype("int64"), unit="ms")
            vix_df.set_index("timestamp", inplace=True)
            vix_df.sort_index(inplace=True)
    except Exception as e:
        logger.error("PREFLIGHT: erro ao ler parquet - %s. ABORTANDO.", e)
        _sys.exit(1)

    # Alinha ao index do ativo (forward fill)
    ohlc_idx = ohlc_df.index
    if isinstance(ohlc_idx, pd.DatetimeIndex):
        idx_naive = ohlc_idx.tz_localize(None) if hasattr(ohlc_idx, 'tz') and ohlc_idx.tz is not None else ohlc_idx
        dxy_aligned = dxy_df["close"].reindex(idx_naive, method="ffill")
        vix_aligned = vix_df["close"].reindex(idx_naive, method="ffill")
        dxy_aligned.index = ohlc_idx
        vix_aligned.index = ohlc_idx
    else:
        dxy_vals = dxy_df["close"].values
        vix_vals = vix_df["close"].values
        n = len(ohlc_df)
        dxy_aligned = pd.Series(
            np.resize(dxy_vals, n) if len(dxy_vals) > 0 else np.zeros(n),
            index=ohlc_df.index,
        )
        vix_aligned = pd.Series(
            np.resize(vix_vals, n) if len(vix_vals) > 0 else np.zeros(n),
            index=ohlc_df.index,
        )

    n_dxy_miss = dxy_aligned.isna().sum()
    n_vix_miss = vix_aligned.isna().sum()
    n_bars = len(ohlc_df)

    if n_dxy_miss > n_bars * 0.5:
        logger.info("PREFLIGHT: DXYUSD >50%% missing (%d/%d). Validacao Dupla S41 ativada.", n_dxy_miss, n_bars)
    if n_vix_miss > n_bars * 0.5:
        logger.info("PREFLIGHT: VIXUSD >50%% missing (%d/%d). Validacao Dupla S41 ativada.", n_vix_miss, n_bars)

    dxy_aligned = dxy_aligned.ffill().bfill().fillna(0.0)
    vix_aligned = vix_aligned.ffill().bfill().fillna(0.0)

    vix_aligned = vix_aligned / 100_000.0

    cov_dxy = (1 - n_dxy_miss / n_bars) * 100 if n_bars > 0 else 0
    cov_vix = (1 - n_vix_miss / n_bars) * 100 if n_bars > 0 else 0

    logger.info("PREFLIGHT: DXY=%db(%.0f%%) VIX=%db(%.0f%%) alinhados com %s",
                n_bars, cov_dxy, n_bars, cov_vix, symbol)
    print(f"[PREFLIGHT] DXYUSD+VIXUSD: {n_bars} barras, cobertura DXY={cov_dxy:.0f}% VIX={cov_vix:.0f}%, alinhado com {symbol}")
    return ohlc_df, dxy_aligned, vix_aligned
