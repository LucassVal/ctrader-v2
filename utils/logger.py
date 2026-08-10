"""
PROPOSITO: Logger
SPEC: S0
ROADMAP: D.2
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "system.log"
JSON_LOG_FILE = LOG_DIR / "system.jsonl"


def ensure_log_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


class JsonFormatter(logging.Formatter):
    """Formata logs como JSON estruturado."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "cat": getattr(record, "category", "OPERATION"),
            "phase": getattr(record, "phase", "SYSTEM"),
            "msg": record.getMessage(),
        }
        if hasattr(record, "data") and record.data:
            entry["data"] = record.data
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        return json.dumps(entry, default=str, ensure_ascii=False)


class CategorizedLogger(logging.Logger):
    """Logger com categoria e fase injetáveis."""

    def _log_cat(self, level: int, msg: str, category: str = "OPERATION",
                 phase: str = "SYSTEM", data: dict | None = None, *args, **kwargs):
        extra = kwargs.pop("extra", {})
        extra["category"] = category
        extra["phase"] = phase
        extra["data"] = data
        self._log(level, msg, args, extra=extra)

    # --- categorias específicas ---

    def operation(self, msg: str, phase: str = "SYSTEM", data: dict | None = None):
        self._log_cat(logging.INFO, msg, "OPERATION", phase, data)

    def mcp_call(self, msg: str, tool: str = "", phase: str = "SYSTEM", data: dict | None = None):
        self._log_cat(logging.INFO, msg, "MCP_CALL", phase, {"tool": tool, **(data or {})})

    def mcp_error(self, msg: str, tool: str = "", phase: str = "SYSTEM", exc_info: bool = False):
        self._log_cat(logging.ERROR, msg, "MCP_ERROR", phase, {"tool": tool},
                      exc_info=exc_info)

    def phase_error(self, msg: str, phase: str = "SYSTEM", data: dict | None = None):
        self._log_cat(logging.ERROR, msg, "PHASE_ERROR", phase, data)

    def trade(self, msg: str, phase: str = "F4", data: dict | None = None):
        self._log_cat(logging.INFO, msg, "TRADE", phase, data)

    def harness(self, msg: str, test: str = "", passed: bool = True):
        self._log_cat(logging.INFO if passed else logging.ERROR, msg, "HARNESS", "TEST",
                      {"test": test, "passed": passed})

    def health(self, msg: str, phase: str = "SYSTEM", data: dict | None = None):
        self._log_cat(logging.INFO, msg, "HEALTH", phase, data)

    def metrics(self, msg: str, data: dict | None = None):
        self._log_cat(logging.INFO, msg, "METRICS", "SYSTEM", data)


# --- setup ---
ensure_log_dir()

# file handler (texto legível, sem campos obrigatórios)
file_handler = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
file_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
))

# json handler (máquina)
json_handler = logging.FileHandler(str(JSON_LOG_FILE), encoding="utf-8")
json_handler.setFormatter(JsonFormatter())

# console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(message)s"
))

# register
logging.setLoggerClass(CategorizedLogger)


def get_logger(name: str, phase: str = "SYSTEM") -> CategorizedLogger:
    """Retorna logger categorizado para um módulo.

    Uso:
        logger = get_logger(__name__, "F4")
        logger.trade("Entrada executada", data={"symbol": "XAUUSD", "pnl": 10.0})
        logger.mcp_error("Timeout", tool="get_spot_prices")
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    # evita duplicar handlers
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(json_handler)
        logger.addHandler(console_handler)

    # injeta fase padrão
    logger.phase = phase  # type: ignore[attr-defined]

    return logger  # type: ignore[return-value]
