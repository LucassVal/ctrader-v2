"""PROPOSITO: Matriz booleana de sinais validados — AND logico das 4 sub-fases.

SPEC: S41 — Bloco 1: Torneio do Passado
SAT: signal_matrix_orc_bloco1

Combina gatilho (trigger), forca (force) e DXY (macro filter) via AND logico.
Colunas: simbolos; Linhas: timestamps.
"""
from __future__ import annotations

import pandas as pd


def build_boolean_matrix(
    gatilho: pd.DataFrame,
    forca: pd.DataFrame,
    dxy_ok: pd.Series | None = None,
) -> pd.DataFrame:
    """Constroi matriz booleana: (Gatilho) & (Forca) & (DXY OK).

    Args:
        gatilho: DataFrame booleano [timestamps x symbols] — sinais de trigger.
        forca: DataFrame booleano [timestamps x symbols] — filtro de forca.
        dxy_ok: Series booleana [timestamps] — filtro DXY (opcional).

    Returns:
        DataFrame booleano [timestamps x symbols] — sinais validados.
    """
    # Alinha os DataFrames pelo index
    common_cols = gatilho.columns.intersection(forca.columns)
    if len(common_cols) == 0:
        common_cols = gatilho.columns

    # Alinha indices: usa interseccao
    result = gatilho[common_cols].copy().astype(bool) & forca[common_cols].copy().astype(bool)

    # Aplica filtro DXY se fornecido
    if dxy_ok is not None:
        # Alinha dxy_ok com o index do resultado
        dxy_aligned = dxy_ok.reindex(result.index, fill_value=True)
        for col in result.columns:
            result[col] = result[col] & dxy_aligned.values

    return result
