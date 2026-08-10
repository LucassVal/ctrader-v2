"""layer_comparator_orc_bloco2.py — S42: Comparador de camadas.

PROPOSITO: Gerar tabela comparativa das 5 camadas de sobrevivencia.
SPEC: S42

Tabela: Camada x Sharpe x MaxDD x WinRate x ProfitFactor x Expectancy
ROADMAP: FASE 3 (S42)
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def compare_layers(results: dict[str, dict[str, Any]]) -> pd.DataFrame:
    """Compara camadas de sobrevivencia lado a lado.

    Args:
        results: Dict no formato:
            {
                "baseline": {"sharpe": 0.45, "max_dd": 12.3, "win_rate": 48.2, ...},
                "tp_80":    {...},
                "be":       {...},
                "trail":    {...},
                "oco_atr":  {...},
            }

    Returns:
        DataFrame com colunas: Camada, Sharpe, MaxDD, WinRate, ProfitFactor, Expectancy.
        Ordenado por Sharpe descendente.
    """
    rows: list[dict[str, Any]] = []

    for layer_name, metrics in results.items():
        rows.append({
            "Camada": layer_name,
            "Sharpe": round(float(metrics.get("sharpe", 0.0)), 3),
            "MaxDD": round(float(metrics.get("max_dd", 0.0)), 2),
            "WinRate": round(float(metrics.get("win_rate", 0.0)), 2),
            "ProfitFactor": round(float(metrics.get("profit_factor", 0.0)), 3),
            "Expectancy": round(float(metrics.get("expectancy", 0.0)), 3),
        })

    df = pd.DataFrame(rows)

    # Ordenar por Sharpe descendente
    if not df.empty:
        df = df.sort_values("Sharpe", ascending=False).reset_index(drop=True)

    return df
