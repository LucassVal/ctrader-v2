"""oco_atr_orc_bloco2.py — S42.4: OCO Adaptativo ATR.

PROPOSITO: Calcular bandas OCO (One-Cancels-Other) escaladas por ATR.
SPEC: S42
R-USE: OHLCSTX.run(sl_stop, tp_stop) ou from_signals(sl_stop, tp_stop)

SL = entry - (ATR x multiplier)
TP = entry + (ATR x multiplier x 2)  # ratio 1:2
ROADMAP: FASE 3 (S42)
"""

from __future__ import annotations


def calc_oco_bands(
    atr_value: float,
    multiplier: float = 1.5,
    entry_price: float | None = None,
) -> tuple[float, float]:
    """Calcula os precos de SL e TP para OCO adaptativo.

    Args:
        atr_value: Valor do ATR (Average True Range) atual.
        multiplier: Multiplicador do ATR para SL (default 1.5).
        entry_price: Preco de entrada. Se None, retorna offsets relativos
                     (SL = -ATR*mult, TP = +ATR*mult*2).

    Returns:
        (sl_price, tp_price) — precos absolutos se entry_price fornecido,
        ou offsets relativos.

    Regras:
        - SL = entry - ATR * multiplier (protecao)
        - TP = entry + ATR * multiplier * 2 (ratio 1:2 risco:retorno)
        - Se atr_value <= 0, retorna (entry, entry) ou (0.0, 0.0)
    """
    if atr_value <= 0.0:
        if entry_price is not None:
            return (float(entry_price), float(entry_price))
        return (0.0, 0.0)

    sl_offset = atr_value * multiplier
    tp_offset = atr_value * multiplier * 2.0

    if entry_price is not None:
        return (
            float(entry_price - sl_offset),
            float(entry_price + tp_offset),
        )

    return (float(-sl_offset), float(tp_offset))


def calc_sl_tp_pcts(
    atr_value: float,
    entry_price: float,
    multiplier: float = 1.5,
) -> tuple[float, float]:
    """Calcula SL e TP como percentuais (para from_signals).

    Args:
        atr_value: Valor do ATR.
        entry_price: Preco de entrada.
        multiplier: Multiplicador ATR.

    Returns:
        (sl_pct, tp_pct) — percentuais para sl_stop e tp_stop.
        Ex: sl_pct=0.02 significa 2% de stop.
    """
    if entry_price <= 0.0 or atr_value <= 0.0:
        return (0.0, 0.0)

    sl_offset = atr_value * multiplier
    tp_offset = atr_value * multiplier * 2.0

    sl_pct = sl_offset / entry_price
    tp_pct = tp_offset / entry_price

    return (float(sl_pct), float(tp_pct))
