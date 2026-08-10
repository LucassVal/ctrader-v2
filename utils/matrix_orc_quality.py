"""PROPOSITO: matrix_orc_quality.py — Engine numpy do quality trailing (S34 v1.2).
SPEC: S29 (orc_quality) + S34 v1.2 (orc_pattern_engine.md)
ROADMAP: S34 v1.2 — split DDD (G12: matrix_orc_scan estourou 200L).

SAT de orc_quality (R8 naming). Sem IO, sem MCP, sem estado:
- trailing_quality_f1: mesmas regras do S29 (RSI/ADX) em janela trailing,
  cumsum vetorizado O(n), zero lookahead (f1[t] usa somente barras <= t)
"""
from __future__ import annotations

import numpy as np


def trailing_quality_f1(
    rsi: np.ndarray,
    adx: np.ndarray,
    closes: np.ndarray,
    window_bars: int = 90 * 1440,
    min_signals: int = 30,
) -> np.ndarray:
    """Quality S29 em janela TRAILING — paridade orc_quality (S34 v1.2).

    Mesmas regras do S29: BUY RSI<35 & ADX>20; SELL RSI>65 & ADX>20;
    lookahead 5 barras; acerto = move direcional > 0,05% do preco.
    f1[t] usa SOMENTE barras <= t (cumsum, zero lookahead). Janela em
    barras M1 (90d ~= 129.600); gaps de cobertura sao ignorados (KISS).
    Minimo 30 sinais na janela (A7) — abaixo disso retorna NaN e o
    orquestrador cai no fallback "apenas patterns" (espelho do S32).
    NOTA R21: no S29, F1 == win-rate (tp=wins, fp=fn=losses); paridade
    mantida de proposito. Empates (exit==entry) contam como perda aqui
    (S29 os pula — efeito desprezivel em M1).
    """
    n = len(closes)
    sig = np.zeros(n, dtype=np.int8)
    sig[(rsi < 35) & (adx > 20)] = 1
    sig[(rsi > 65) & (adx > 20)] = -1
    active = sig != 0

    la = 5
    idx_fwd = np.arange(n - la)
    pct = np.zeros(n)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct[idx_fwd] = (closes[idx_fwd + la] - closes[idx_fwd]) / closes[idx_fwd] * 100
    move_dir = np.where(sig == 1, pct, -pct)
    valid = np.arange(n) < n - la
    win = ((move_dir > 0.05) & active & valid).astype(float)

    cum_total = np.concatenate([[0.0], np.cumsum(active.astype(float))])
    cum_win = np.concatenate([[0.0], np.cumsum(win)])
    idx = np.arange(n)
    lo = np.maximum(0, idx + 1 - window_bars)
    t_total = cum_total[idx + 1] - cum_total[lo]
    t_win = cum_win[idx + 1] - cum_win[lo]

    with np.errstate(divide="ignore", invalid="ignore"):
        f1 = np.where(t_total >= min_signals, t_win / t_total, np.nan)
    return f1
