"""PROPOSITO: Calculo de sentimento long/short via positions
SPEC: S3
ROADMAP: 2.1 — fix 2026-07-23: recebe positions como parametro (snapshot F0), nao chama MCP direto.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def calc_sentiment_ratio(positions: list[dict[str, Any]] | None = None) -> float:
    """Retorna 0-1: proporcao de posicoes long no portfolio.

    Args:
        positions: Lista de posicoes do snapshot F0. Se None, tenta ler do snapshot.

    >0.7 = maioria comprado (contrarian: score cai).
    <0.3 = maioria vendido (contrarian: score sobe).
    """
    try:
        if positions is None:
            # Fallback: le do snapshot F0 (nao chama MCP direto)
            from f0_collector.orc_coleta import get_snapshot
            snap = get_snapshot()
            positions = snap.get("positions", []) if snap else []

        if not isinstance(positions, list) or len(positions) == 0:
            return 0.5  # neutro

        long_vol = 0
        total_vol = 0
        for pos in positions:
            if not isinstance(pos, dict):
                continue
            volume = abs(pos.get("volume", 0) or 0)
            if volume <= 0:
                continue
            total_vol += volume
            if pos.get("side", "").upper() in ("BUY", "LONG"):
                long_vol += volume

        if total_vol == 0:
            return 0.5
        return round(long_vol / total_vol, 2)
    except Exception as e:
        logger.error("Falha ao obter sentimento: %s", e)
        return 0.5  # fallback neutro


# Alias para compatibilidade
get_sentiment_ratio = calc_sentiment_ratio
