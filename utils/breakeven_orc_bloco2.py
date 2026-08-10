"""breakeven_orc_bloco2.py — S42.2: Breakeven via adjust_sl_func_nb.

PROPOSITO: Callback Numba para mover SL para entry+spread quando lucro > D%.
SPEC: S42
R-USE: adjust_sl_func_nb do vectorbt.Portfolio.from_signals

O callback recebe AdjustSLContext e retorna (new_stop, trail_flag):
  - new_stop: float — novo valor de stop-loss
  - trail_flag: bool — ativar/desativar trailing

Quando o lucro atinge trigger_pct% do alvo:
  -> SL sobe para entry_price + spread_pips (breakeven + custo)
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

    def njit(fn=None, **kwargs):  # type: ignore[no-redef]
        return fn if fn else (lambda f: f)


def build_be_callback(
    trigger_pct: float = 0.6,
    spread_pips: float = 1.0,
) -> Callable[..., Any]:
    """Cria callback Numba para breakeven.

    Args:
        trigger_pct: % do lucro (sobre o entry) para ativar BE
                     Ex: 0.6 significa que quando o lucro atinge 0.6%
                     (em relacao a um TP implicito), move SL para entry+spread.
        spread_pips: Pips/valor a adicionar ao entry como margem de seguranca.
                     Ex: 1.0 = SL sobe para entry + 1.0.

    Returns:
        Callable compativel com adjust_sl_func_nb(c: AdjustSLContext, *args)
        que retorna (new_stop: float, trail_flag: bool).
    """

    @njit
    def _be_callback_nb(c: Any, *_args: Any) -> tuple[float, bool]:
        """Numba-jitted BE callback.

        Context (AdjustSLContext):
          - init_price: entry price
          - curr_price: current close price
          - position_now: current position
          - curr_stop: current stop-loss value
          - curr_trail: current trailing flag
          - val_price_now: current valuation price
        """
        # Flat position — nothing to adjust
        if c.position_now == 0.0:
            return c.curr_stop, c.curr_trail

        if c.init_price <= 0.0:
            return c.curr_stop, c.curr_trail

        profit_pct = (c.curr_price - c.init_price) / c.init_price

        # Long: profit > 0 is good, Short: profit < 0 is good
        if c.position_now > 0.0:
            effective_profit = profit_pct
        else:
            effective_profit = -profit_pct

        # Gatilho: lucro > trigger_pct%
        # trigger_pct e interpretado como % sobre o entry_price
        # (ex: trigger_pct=0.006 = 0.6%)
        if effective_profit >= trigger_pct:
            # Mover SL para entry + spread (breakeven)
            if c.position_now > 0.0:
                new_sl = c.init_price + spread_pips
            else:
                new_sl = c.init_price - spread_pips
            return new_sl, c.curr_trail

        # Ainda nao atingiu o gatilho — manter SL atual
        return c.curr_stop, c.curr_trail

    return _be_callback_nb
