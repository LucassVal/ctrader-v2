"""PROPOSITO: stability_analyzer_orc_grid.py — SAT S43.3: analyze_stability().
SPEC: S43 (orc_grid.md)
ROADMAP: S43 Grid/Walk-Forward

Analisa estabilidade dos parametros entre janelas walk-forward.
Calcula moda de cada parametro e flag de overfitting.
"""
from __future__ import annotations

from collections import Counter
from typing import Any


def analyze_stability(window_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Analisa estabilidade e overfitting entre janelas walk-forward.

    Args:
        window_results: lista de resultados de janelas, cada uma com:
            - best_params: dict de parametros otimos da janela
            - train_mae: MAE no treino
            - test_mae: MAE no teste

    Returns:
        dict com:
            - <param>_mode: valor modal de cada parametro entre janelas
            - <param>_stability: % de janelas com o valor modal
            - overfit_flag: True se train_mae < test_mae * 0.5 em >50% das janelas
    """
    result: dict[str, Any] = {
        "overfit_flag": False,
    }

    if not window_results:
        return result

    # Coletar todos os parametros de todas as janelas
    all_param_keys: set[str] = set()
    for w in window_results:
        params = w.get("best_params", {})
        all_param_keys.update(params.keys())

    # Calcular moda e estabilidade para cada parametro
    for key in sorted(all_param_keys):
        values = []
        for w in window_results:
            params = w.get("best_params", {})
            if key in params:
                values.append(params[key])

        if not values:
            continue

        # Moda = valor mais frequente
        counter = Counter(values)
        mode_value, mode_count = counter.most_common(1)[0]
        stability = mode_count / len(values)

        result[f"{key}_mode"] = mode_value
        result[f"{key}_stability"] = round(stability, 4)

    # Flag de overfitting: train_mae < test_mae * 0.5 em >50% das janelas
    overfit_count = 0
    valid_count = 0
    for w in window_results:
        train_mae = w.get("train_mae")
        test_mae = w.get("test_mae")
        if train_mae is not None and test_mae is not None and test_mae > 0:
            valid_count += 1
            if train_mae < test_mae * 0.5:
                overfit_count += 1

    if valid_count > 0 and (overfit_count / valid_count) > 0.5:
        result["overfit_flag"] = True

    return result
