"""PROPOSITO: T16 — NEWS DETECTOR — CORTADO
SPEC: S3
ROADMAP: CORTADO — MCP nao prove news. blackout_times.json depende de manutencao manual.
         Nenhum endpoint MCP retorna eventos de news. Skill ctrader-mcp-integration:
         "NOT exposed: get_account_statistics(), DOM, sentiment."
         Mantido no disco como registro, nao wireado ativamente.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

BLACKOUT_PATH = Path(__file__).resolve().parent.parent / "blackout_times.json"
NEWS_WINDOW_MINUTES = 15


def check_news_imminent() -> tuple[bool, str]:
    """Retorna sempre (False, "") — CORTADO. MCP nao prove news."""
    logger.debug("_news.py CORTADO - retornando False (MCP nao prove news)")
    return False, ""


# Codigo original preservado como referencia:
# def check_news_imminent() -> tuple[bool, str]:
#     try:
#         if not BLACKOUT_PATH.exists():
#             return False, ""
#         ...
