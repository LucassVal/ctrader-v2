"""PROPOSITO: Filtro DXY + VIX - travas macro para sinais do Bloco 1.

SPEC: S41.4 - Contrapeso Macro
SAT: dxy_filter_orc_bloco1

Regras (v2.0 - correlacao DURA por ROC):
- XAUUSD/EURUSD/GBPUSD/AUDUSD: correlacao INVERSA com DXY
  (BUY so se DXY em QUEDA; SELL so se DXY em ALTA)
- USDJPY: correlacao DIRETA com DXY
  (BUY exige DXY em ALTA; SELL exige DXY em QUEDA)
- VIX: filtro de panico - VIX > threshold -> ABORTA todos os sinais
- DXY neutro (|ROC| < threshold) -> sempre passa
ROADMAP: FASE 3 (S41.4)
"""

from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

# Simbolos com correlacao INVERSA ao DXY
_INVERSE_SYMBOLS: set[str] = {"XAUUSD", "EURUSD", "GBPUSD", "AUDUSD"}

# Simbolos com correlacao DIRETA ao DXY
_DIRECT_SYMBOLS: set[str] = {"USDJPY"}

# Thresholds padrao
_DEFAULT_DXY_NEUTRAL: float = 0.0005  # |ROC| < 0.05% = DXY neutro
_DEFAULT_ANOMALY: float = 0.003       # anomalia ouro+dolar > 0.3% -> aborta
_DEFAULT_VixMax: float = 35.0         # VIX > 35 = panico -> aborta sinais


def check_dxy_alignment(
    symbol: str,
    signal_direction: str,
    dxy_roc: float,
    anomaly_threshold: float = _DEFAULT_ANOMALY,
    neutral_threshold: float = _DEFAULT_DXY_NEUTRAL,
) -> bool:
    """Verifica se o sinal esta alinhado com o ROC do DXY.

    Args:
        symbol: par (XAUUSD, EURUSD, etc.)
        signal_direction: "BULLISH" ou "BEARISH"
        dxy_roc: Rate of Change do DXY no periodo (>0 = subindo, <0 = caindo)
        anomaly_threshold: |ROC| acima disto com sinal oposto = anomalia -> aborta
        neutral_threshold: |ROC| abaixo disto = DXY neutro -> sempre OK

    Returns:
        True se alinhamento OK, False se deve abortar o sinal.
    """
    direction = signal_direction.upper().strip()

    # DXY neutro: sempre OK
    if abs(dxy_roc) < neutral_threshold:
        return True

    dxy_up = dxy_roc > 0
    direction_bull = direction == "BULLISH"
    direction_bear = direction == "BEARISH"

    if direction not in ("BULLISH", "BEARISH"):
        logger.info("DXY: direcao desconhecida '%s' para %s - passando", signal_direction, symbol)
        return True

    if symbol in _INVERSE_SYMBOLS:
        # Correlacao INVERSA: BUY -> DXY CAINDO; SELL -> DXY SUBINDO
        if direction_bull and dxy_up:
            # Anomalia: ativo sobe E dolar sobe
            return not abs(dxy_roc) > anomaly_threshold
        if direction_bear and not dxy_up:
            return not abs(dxy_roc) > anomaly_threshold
        return True  # alinhado

    if symbol in _DIRECT_SYMBOLS:
        # Correlacao DIRETA: BUY -> DXY SUBINDO; SELL -> DXY CAINDO
        if direction_bull and not dxy_up:
            return not abs(dxy_roc) > anomaly_threshold
        if direction_bear and dxy_up:
            return not abs(dxy_roc) > anomaly_threshold
        return True

    # Simbolo desconhecido: passa sem filtro
    logger.debug("DXY: simbolo '%s' nao mapeado - passando", symbol)
    return True


def check_vix_filter(
    vix_value: float,
    max_vix: float = _DEFAULT_VixMax,
) -> bool:
    """Filtro de volatilidade/panico: VIX > threshold -> ABORTA.

    Args:
        vix_value: valor atual do VIXUSD
        max_vix: threshold maximo (default 35 - acima disto e panico)

    Returns:
        True se VIX OK (abaixo do threshold), False se deve abortar.
    """
    if vix_value <= 0:
        return True  # VIX indisponivel -> passa (sem filtro)
    return vix_value <= max_vix


def get_dxy_roc(
    dxy_series: np.ndarray,
    lookback: int = 5,
) -> float:
    """Calcula ROC (Rate of Change) do DXY nos ultimos N periodos.

    Args:
        dxy_series: array de precos do DXY
        lookback: periodos para calculo (default 5)

    Returns:
        ROC percentual (>0 = subindo, <0 = caindo)
    """
    if len(dxy_series) < lookback + 1:
        return 0.0
    current = float(dxy_series[-1])
    previous = float(dxy_series[-1 - lookback])
    if previous == 0:
        return 0.0
    return (current - previous) / previous
