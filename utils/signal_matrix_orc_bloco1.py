"""PROPOSITO: Matriz booleana de sinais validados — AND logico das sub-fases.

SPEC: S41 — Bloco 1: Torneio do Passado
SAT: signal_matrix_orc_bloco1
ROADMAP: FASE 3 (S41)

Combina gatilho (trigger), forca (force) e DXY (macro filter) via AND logico.
Suporta filtro DXY unico (dxy_ok) ou separado por direcao (dxy_ok_buy/dxy_ok_sell).
Colunas: simbolos; Linhas: timestamps.
"""
from __future__ import annotations

import pandas as pd


def build_boolean_matrix(
    gatilho: pd.DataFrame,
    forca: pd.DataFrame,
    dxy_ok: pd.Series | None = None,
    dxy_ok_buy: pd.Series | None = None,
    dxy_ok_sell: pd.Series | None = None,
) -> pd.DataFrame:
    """Constroi matriz booleana: (Gatilho) & (Forca) & (DXY OK).

    Args:
        gatilho: DataFrame booleano [timestamps x symbols] — sinais de trigger.
        forca: DataFrame booleano [timestamps x symbols] — filtro de forca.
        dxy_ok: Series booleana [timestamps] — filtro DXY unico (opcional).
        dxy_ok_buy: Series booleana — filtro DXY para coluna BUY (opcional).
        dxy_ok_sell: Series booleana — filtro DXY para coluna SELL (opcional).

    Returns:
        DataFrame booleano [timestamps x symbols] — sinais validados.
    """
    # Alinha os DataFrames pelo index
    common_cols = gatilho.columns.intersection(forca.columns)
    if len(common_cols) == 0:
        common_cols = gatilho.columns

    result = gatilho[common_cols].copy().astype(bool) & forca[common_cols].copy().astype(bool)

    # Filtro DXY unico (compatibilidade retroativa)
    if dxy_ok is not None:
        dxy_aligned = dxy_ok.reindex(result.index, fill_value=True)
        for col in result.columns:
            result[col] = result[col] & dxy_aligned.values

    # Filtro DXY separado por direcao (v2.1 — validacao dupla S41)
    if dxy_ok_buy is not None and "BUY" in result.columns:
        buy_aligned = dxy_ok_buy.reindex(result.index, fill_value=True)
        result["BUY"] = result["BUY"] & buy_aligned.values
    if dxy_ok_sell is not None and "SELL" in result.columns:
        sell_aligned = dxy_ok_sell.reindex(result.index, fill_value=True)
        result["SELL"] = result["SELL"] & sell_aligned.values

    return result
