"""PROPOSITO: Camada de dados — unico leitor de snapshot.json + contracts.
SPEC: S26
ROADMAP: DataSource Layer
Substitui _read_snapshot() duplicado em orc_mercado, orc_dashboard, orc_metricas.
Cache 5s TTL — uma leitura de disco por request, nao 4+.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

ROOT: Path = Path(__file__).resolve().parent.parent
SNAPSHOT: Path = ROOT / "status" / "snapshot.json"

# Cache
_cache: dict[str, Any] = {}
_cache_ts: float = 0.0
CACHE_TTL: float = 15.0  # segundos (era 5s — ampliado para reduzir leitura de disco)


def refresh() -> dict[str, Any]:
    """Forca releitura do snapshot. Retorna dict cru."""
    global _cache, _cache_ts
    try:
        if SNAPSHOT.exists():
            _cache = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
            _cache_ts = time.time()
            return _cache
    except Exception:
        pass
    _cache = {}
    _cache_ts = time.time()
    return _cache


def _cached() -> dict[str, Any]:
    """Retorna snapshot cacheado. Refresha se TTL expirou."""
    global _cache, _cache_ts, _cache_hits, _cache_misses
    now = time.time()
    if now - _cache_ts > CACHE_TTL or not _cache:
        return refresh()
    return _cache


def get_snapshot() -> dict[str, Any]:
    """Snapshot cru do F0 (cache 5s)."""
    return _cached()


def is_online() -> bool:
    """F0 esta ativo e MCP conectado?"""
    snap = _cached()
    return bool(snap and snap.get("online"))


def get_balance() -> dict[str, Any]:
    """Balance normalizado (cents->USD). Retorna {} se offline."""
    snap = _cached()
    raw = snap.get("balance", {})
    if not raw:
        return {}
    digits = raw.get("moneyDigits", 2)
    divisor = 10 ** digits
    return {
        "balance": round(raw.get("balance", 0) / divisor, 2),
        "equity": round(raw.get("equity", 0) / divisor, 2),
        "free_margin": round(raw.get("freeMargin", 0) / divisor, 2),
        "balance_version": raw.get("balanceVersion", 0),
        "money_digits": digits,
    }


def get_markets_raw() -> dict[str, dict[str, Any]]:
    """Dados brutos dos 5 simbolos (OHLCV + bid/ask/spread)."""
    snap = _cached()
    return snap.get("symbols", {})


def get_positions() -> list[dict[str, Any]]:
    """Posicoes abertas. Retorna [] se offline ou sem posicoes."""
    snap = _cached()
    positions = snap.get("positions", {})
    if isinstance(positions, dict):
        return positions.get("positions", [])
    if isinstance(positions, list):
        return positions
    return []


# Hit-rate tracking
_cache_hits: int = 0
_cache_misses: int = 0


def cache_stats() -> dict[str, Any]:
    """Retorna estatisticas do cache: hits, misses, hit-rate."""
    total = _cache_hits + _cache_misses
    return {
        "hits": _cache_hits,
        "misses": _cache_misses,
        "hit_rate": round(_cache_hits / total * 100, 1) if total > 0 else 0,
        "ttl_s": CACHE_TTL,
    }
