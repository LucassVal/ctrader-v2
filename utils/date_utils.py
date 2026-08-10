from __future__ import annotations

from datetime import UTC, datetime, timedelta

"""PROPOSITO: Funcoes auxiliares de data para backtests e scans.
SPEC: S41 (dual backtest 2y + 9m)
ROADMAP: FASE 3.1

Convencao de datas:
  - BACKTEST: dados ate ontem 23:59 UTC (dia completo, sem look-ahead)
  - SCAN: janela expande ate hoje 23:59 UTC (cobre gaps do dia atual)
  - MONITOR: dados ate agora (live, parcial)

Uso:
  from utils.date_utils import backtest_end, scan_end, monitor_end
"""

def backtest_end() -> datetime:
    """Retorna ontem 23:59:00 UTC. Uso: backtests (S41 Bloco1 + Bloco2)."""
    return (datetime.now(UTC) - timedelta(days=1)).replace(hour=23, minute=59, second=0, microsecond=0)


def scan_end() -> datetime:
    """Retorna hoje 23:59:00 UTC. Uso: G23 gap scan, janela de cobertura."""
    return datetime.now(UTC).replace(hour=23, minute=59, second=0, microsecond=0)


def monitor_end() -> datetime:
    """Retorna agora UTC. Uso: dashboard live, poller F0."""
    return datetime.now(UTC)


def backtest_start_2y() -> datetime:
    """2 anos atras a partir de ontem 23:59."""
    return backtest_end() - timedelta(days=730)


def backtest_start_9m() -> datetime:
    """9 meses atras a partir de ontem 23:59 (DXY/VIX)."""
    return backtest_end() - timedelta(days=275)  # ~9 meses


def backtest_start_30d() -> datetime:
    """30 dias atras a partir de ontem 23:59 (testes)."""
    return backtest_end() - timedelta(days=30)
