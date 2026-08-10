"""PROPOSITO: H1.2 — Harness gateway throttle+cache
SPEC: S1.1
ROADMAP: 1.5 — Token-bucket 50/s live, 5/s historico. Cache TTL.
Sem mock/stub — deterministico.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.mcp_client import _cache_get, _cache_set, _throttle_rate, _throttle_wait


def test_throttle_tokens_decrement() -> None:
    """_throttle_wait consome 1 token."""
    import utils.mcp_client as mcp
    mcp._throttle_tokens = 10.0
    mcp._throttle_last = time.monotonic()
    _throttle_wait()
    assert mcp._throttle_tokens < 10.0, f"Tokens nao decrementaram: {mcp._throttle_tokens}"


def test_throttle_rate_default() -> None:
    """Throttle rate default = 50/s."""
    assert _throttle_rate == 50.0, f"Rate default: {_throttle_rate}, esperado 50.0"


def test_cache_set_get() -> None:
    """Cache armazena e recupera dentro do TTL."""
    _cache_set("test_tool", {"arg": 1}, {"result": "ok"}, ttl=5.0)
    cached = _cache_get("test_tool", {"arg": 1})
    assert cached == {"result": "ok"}, f"Cache miss: {cached}"


def test_cache_expires() -> None:
    """Cache expira apos TTL."""
    _cache_set("test_tool", {"arg": 2}, {"result": "expired"}, ttl=0.1)
    import time as _t
    _t.sleep(0.2)
    cached = _cache_get("test_tool", {"arg": 2})
    assert cached is None, f"Cache nao expirou: {cached}"


def test_cache_key_deterministic() -> None:
    """Cache key e deterministica (args sorted)."""
    from utils.mcp_client import _cache_key
    k1 = _cache_key("t", {"b": 2, "a": 1})
    k2 = _cache_key("t", {"a": 1, "b": 2})
    assert k1 == k2, f"Keys divergem: {k1} != {k2}"
