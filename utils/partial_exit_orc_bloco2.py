"""partial_exit_orc_bloco2.py — S42.1: Alvo 80% via adjust_tp_func_nb.

PROPOSITO: Callback Numba para saida parcial — fecha 80% no TP1, deixa 20% correr.
SPEC: S42
R-USE: adjust_tp_func_nb do vectorbt.Portfolio.from_signals

O callback recebe AdjustTPContext e retorna (new_stop, exit_flag):
  - new_stop: float — novo valor de TP (nan = manter atual)
  - exit_flag: bool — True para disparar saida da posicao remanescente

Quando o preco atinge TP1 (+tp1_target%), o callback:
  1. Fecha tp1_pct (ex: 80%) da posicao (via allow_partial + exit_flag)
  2. Deixa o restante correr com um novo TP mais distante
ROADMAP: FASE 3 (S42)
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

try:
    from numba import njit  # type: ignore[import-untyped]
    _HAS_NUMBA = True
except ImportError:
    _HAS_NUMBA = False
    # Fallback decorator
    def njit(fn=None, **kwargs):  # type: ignore[no-redef]
        return fn if fn else (lambda f: f)


def build_tp_callback(
    tp1_pct: float = 0.8,
    tp1_target: float = 0.02,
) -> Callable[..., Any]:
    """Cria callback Numba para saida parcial no TP1.

    Args:
        tp1_pct: % da posicao a fechar no TP1 (default 0.8 = 80%)
        tp1_target: % de lucro para TP1 (default 0.02 = 2%)

    Returns:
        Callable compativel com adjust_tp_func_nb(c: AdjustTPContext, *args)
        que retorna (new_stop: float, exit_flag: bool).
    """

    @njit
    def _tp_callback_nb(c: Any, *_args: Any) -> float:
        """Numba-jitted TP callback.

        Context (AdjustTPContext):
          - init_price: entry price
          - val_price_now: current valuation price
          - position_now: current position (0=flat, 1=long, -1=short)
          - curr_stop: current TP stop (nan if none)
          - i: current bar index
          - init_i: entry bar index

        Returns:
            float — novo valor de TP (nan = manter atual, 0 = saida imediata).
            Para saida parcial (80%), retornamos 0 para fechar a posicao quando
            o preco atinge o TP1. O allow_partial=True controla o % fechado.
        """
        # Flat position — nothing to adjust
        if c.position_now == 0.0:
            return c.curr_stop

        # Calcula lucro atual em %
        if c.init_price <= 0.0:
            return c.curr_stop

        profit_pct = (c.val_price_now - c.init_price) / c.init_price

        # Long position (position_now > 0): lucro positivo
        # Short position (position_now < 0): lucro quando preco cai
        if c.position_now > 0.0:
            effective_profit = profit_pct
        else:
            effective_profit = -profit_pct

        # Gatilho: preco atingiu TP1
        if effective_profit >= tp1_target:
            # Fecha a posicao parcial — TP stop = 0 dispara saida imediata
            return 0.0

        # Ainda nao atingiu TP1 — manter stop atual
        return c.curr_stop

    return _tp_callback_nb
