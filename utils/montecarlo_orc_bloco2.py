"""PROPOSITO: Monte Carlo Shuffle — valida se Sharpe nao eh sorte.
SAT: montecarlo_orc_bloco2
SPEC: S42 — Bloco 2: Sobrevivencia, FASE 4.0a
ROADMAP: Pre-requisito bloqueante antes da Fase 5 (Live).

R-USE: NumPy puro. Zero dependencias externas alem de stdlib.
Complexidade: O(N x M) onde N=len(trades), M=n_simulations.
Memoria: ~2 arrays de tamanho N (pnls + equity) — < 1MB.

Contrato de saida conforme SPEC S42 v2.1.
"""

from __future__ import annotations

import numpy as np


def monte_carlo_shuffle(
    trades: list[dict[str, float]],
    n_simulations: int = 1000,
    confidence: float = 0.95,
    seed: int | None = 42,
) -> dict[str, float | int | bool]:
    """Embaralha a ordem dos trades N vezes e mede significancia estatistica.

    Args:
        trades: Lista de trades, cada um com chave 'pnl_pct' (ex: 0.0032 = 0.32%).
                Tambem aceita 'pnl' bruto — normalizado internamente.
        n_simulations: Numero de embaralhamentos (default 1000).
        confidence: Nivel de confianca para CVaR (default 0.95 = 95%).
        seed: Semente para reprodutibilidade (default 42, None = aleatorio).

    Returns:
        {
            "sharpe_original": float,          # Sharpe da sequencia real
            "sharpe_median_shuffled": float,   # Mediana dos Sharpes embaralhados
            "sharpe_pvalue": float,            # Prob(sharpe_embaralhado >= sharpe_real)
            "max_dd_original": float,          # Max Drawdown original (%)
            "max_dd_worst_shuffle": float,     # Pior DD em todos os shuffles (%)
            "max_dd_cvar_95": float,           # CVaR 95% dos DDs (%)
            "max_dd_median_shuffled": float,   # Mediana dos DDs embaralhados
            "is_lucky": bool,                  # True se pvalue < 0.05 (Sharpe eh sorte)
            "n_trades": int,                   # Numero de trades analisados
            "n_simulations": int,              # Numero de simulacoes executadas
        }

    Interpretacao:
      - is_lucky = False (p >= 0.05): Sharpe NAO eh sorte — a sequencia importa.
        A estrategia tem edge estatistico real.
      - is_lucky = True (p < 0.05): Sharpe EH sorte — embaralhar produz resultado
        igual ou melhor. A estrategia nao tem edge.
      - max_dd_worst_shuffle: Se >25%, o risco de ruina em cenarios adversos
        eh alto — reduzir tamanho de posicao.
    """
    if not trades:
        return {
            "sharpe_original": 0.0,
            "sharpe_median_shuffled": 0.0,
            "sharpe_pvalue": 1.0,
            "max_dd_original": 0.0,
            "max_dd_worst_shuffle": 0.0,
            "max_dd_cvar_95": 0.0,
            "max_dd_median_shuffled": 0.0,
            "is_lucky": True,
            "n_trades": 0,
            "n_simulations": 0,
        }

    # -- Extrai PnLs ------------------------------------------
    pnls = np.array([_extract_pnl(t) for t in trades], dtype=np.float64)

    if len(pnls) < 10:
        # Amostra muito pequena — Monte Carlo nao confiavel
        return {
            "sharpe_original": _sharpe(pnls),
            "sharpe_median_shuffled": 0.0,
            "sharpe_pvalue": 1.0,
            "max_dd_original": _max_dd(_equity_curve(pnls)),
            "max_dd_worst_shuffle": 0.0,
            "max_dd_cvar_95": 0.0,
            "max_dd_median_shuffled": 0.0,
            "is_lucky": True,
            "n_trades": len(pnls),
            "n_simulations": 0,
        }

    # -- Original ---------------------------------------------
    equity_orig = _equity_curve(pnls)
    sharpe_orig = _sharpe(pnls)
    max_dd_orig = _max_dd(equity_orig)

    # -- Shuffles ---------------------------------------------
    rng = np.random.default_rng(seed)
    sharpes_shuffled = np.empty(n_simulations, dtype=np.float64)
    max_dds_shuffled = np.empty(n_simulations, dtype=np.float64)

    if n_simulations <= 0:
        return {
            "sharpe_original": round(sharpe_orig, 3),
            "sharpe_median_shuffled": 0.0,
            "sharpe_pvalue": 1.0,
            "max_dd_original": round(max_dd_orig, 2),
            "max_dd_worst_shuffle": 0.0,
            "max_dd_cvar_95": 0.0,
            "max_dd_median_shuffled": 0.0,
            "is_lucky": True,
            "n_trades": len(pnls),
            "n_simulations": 0,
        }

    pnls_copy = pnls.copy()

    for i in range(n_simulations):
        rng.shuffle(pnls_copy)
        eq = _equity_curve(pnls_copy)
        sharpes_shuffled[i] = _sharpe(pnls_copy)
        max_dds_shuffled[i] = _max_dd(eq)

    # -- Metricas ---------------------------------------------
    sharpe_median = float(np.median(sharpes_shuffled))
    pvalue = float(np.mean(sharpes_shuffled >= sharpe_orig))

    max_dd_worst = float(np.max(max_dds_shuffled))
    max_dd_cvar = float(np.percentile(max_dds_shuffled, confidence * 100))
    max_dd_median = float(np.median(max_dds_shuffled))

    return {
        "sharpe_original": round(sharpe_orig, 3),
        "sharpe_median_shuffled": round(sharpe_median, 3),
        "sharpe_pvalue": round(pvalue, 4),
        "max_dd_original": round(max_dd_orig, 2),
        "max_dd_worst_shuffle": round(max_dd_worst, 2),
        "max_dd_cvar_95": round(max_dd_cvar, 2),
        "max_dd_median_shuffled": round(max_dd_median, 2),
        "is_lucky": pvalue < 0.05,
        "n_trades": len(pnls),
        "n_simulations": n_simulations,
    }


# ═══════════════════════════════════════════════════════════════
# HELPERS — funcoes puras, sem side effects
# ═══════════════════════════════════════════════════════════════


def _extract_pnl(trade: dict[str, float]) -> float:
    """Extrai PnL percentual de um trade dict.

    Aceita 'pnl_pct' (ex: 0.0032) ou 'pnl' bruto.
    Normaliza para retorno percentual.
    """
    if "pnl_pct" in trade:
        return float(trade["pnl_pct"])
    if "pnl" in trade:
        return float(trade["pnl"])
    # Fallback: calcula de entry/exit se disponivel
    entry = trade.get("entry_price", 0.0)
    exit_p = trade.get("exit_price", 0.0)
    if entry > 0 and exit_p > 0:
        direction = trade.get("direction", "BUY")
        if direction == "BUY":
            return (float(exit_p) - float(entry)) / float(entry)
        else:
            return (float(entry) - float(exit_p)) / float(entry)
    return 0.0


def _equity_curve(pnls: np.ndarray) -> np.ndarray:
    """Curva de capital a partir de retornos percentuais.

    equity[i] = prod(1 + pnls[0..i])
    """
    return np.cumprod(1.0 + pnls)


def _sharpe(pnls: np.ndarray) -> float:
    """Sharpe Ratio anualizado (assumindo trades independentes).

    Formula: mean(pnls) / std(pnls) * sqrt(252)
    Se std = 0 ou < 10 trades, retorna 0.
    """
    if len(pnls) < 2:
        return 0.0
    mu = np.mean(pnls)
    sigma = np.std(pnls, ddof=1)
    if sigma < 1e-12:
        return 0.0 if abs(mu) < 1e-12 else (np.inf if mu > 0 else -np.inf)
    # Anualizado: assumindo ~252 dias de trading
    return float(mu / sigma * np.sqrt(252))


def _max_dd(equity: np.ndarray) -> float:
    """Maximum Drawdown percentual.

    Formula: max((peak - equity) / peak) * 100
    """
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak
    return float(np.max(dd) * 100.0)
