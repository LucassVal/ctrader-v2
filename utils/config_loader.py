"""
PROPOSITO: Config Loader
SPEC: S0
ROADMAP: D.5
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


@lru_cache(maxsize=1)
def get_config() -> dict:
    """Carrega config.yaml (cacheada)."""
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def reload_config() -> dict:
    """Força recarga do config (pós-MAR update)."""
    get_config.cache_clear()
    return get_config()


# --- acessores diretos ---

def risk(key: str, default=None):
    return get_config().get("risk", {}).get(key, default)


def monitor(key: str, default=None):
    return get_config().get("monitor", {}).get(key, default)


def polling(key: str, default=None):
    return get_config().get("polling", {}).get(key, default)


def thresholds(key: str, default=None):
    return get_config().get("thresholds", {}).get(key, default)


def ia(key: str, default=None):
    return get_config().get("ia", {}).get(key, default)


def mar(key: str, default=None):
    return get_config().get("mar", {}).get(key, default)


def symbols():
    return get_config().get("symbols", {})


def mcp(key: str, default=None):
    return get_config().get("mcp", {}).get(key, default)
