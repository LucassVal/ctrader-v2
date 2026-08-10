"""PROPOSITO: Teste fresh-session — 5 chamadas de ~1000 candles cada, MCP fresco por chamada.
SPEC: S2.6
ROADMAP: Validacao fresh-session-per-call

Cada chamada:
  1. Abre handshake MCP novo
  2. Baixa ~1000 candles M1 recentes
  3. Reporta handshake time, barras, bars/s

Uso: python tests/test_fresh_session.py XAUUSD 5
"""
from __future__ import annotations

import contextlib
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SYMBOL = "XAUUSD"
CALLS = 5
CANDLES = 1000

if len(sys.argv) > 1 and sys.argv[1] not in ("tests/", "-"):
    SYMBOL = sys.argv[1]
if len(sys.argv) > 2 and not sys.argv[2].startswith("-"):
    with contextlib.suppress(ValueError):
        CALLS = int(sys.argv[2])
FMT = "%Y-%m-%dT%H:%M:%SZ"


def fresh_session_download(call_num: int) -> dict:
    """Abre sessao MCP nova, baixa candles, fecha. Retorna metricas."""
    # 1. Handshake fresco (forca reset do estado global)
    import utils.mcp_client as mcp
    from utils.mcp_client import get_trendbars, init_client
    mcp._mcp_initialized = False
    mcp._mcp_session_id = ""
    mcp._mcp_url = ""

    t0 = time.monotonic()
    config = ROOT / "config.yaml"
    init_client(str(config), force=True)
    hs_time = time.monotonic() - t0

    # 2. Download (ultimas ~17h de M1)
    to_dt = datetime.now(UTC)
    frm = to_dt - timedelta(minutes=CANDLES * 3)

    t1 = time.monotonic()
    bars = get_trendbars(
        symbol=SYMBOL, timeframe="M_1", count=CANDLES,
        from_timestamp=frm.strftime(FMT), to_timestamp=to_dt.strftime(FMT),
    )
    dl_time = time.monotonic() - t1

    n = len(bars) if bars else 0
    return {
        "call": call_num,
        "hs_s": hs_time,
        "dl_s": dl_time,
        "bars": n,
        "bars_per_s": n / dl_time if dl_time > 0 else 0,
        "first_ts": bars[0]["timestamp"] if bars else None,
        "last_ts": bars[-1]["timestamp"] if bars else None,
    }


def main():
    print(f"\n{'═' * 55}")
    print(f"  FRESH-SESSION TEST: {SYMBOL} x {CALLS} chamadas")
    print(f"  Cada chamada: handshake proprio + ~{CANDLES} candles M1")
    print(f"{'═' * 55}\n")

    results = []
    total_bars = 0
    total_time = 0.0

    for i in range(1, CALLS + 1):
        print(f"  [{i}/{CALLS}] {SYMBOL}...", end=" ", flush=True)
        t0 = time.monotonic()
        try:
            r = fresh_session_download(i)
            elapsed = time.monotonic() - t0
            total_bars += r["bars"]
            total_time += elapsed
            results.append(r)
            ts_info = ""
            if r["bars"] > 0:
                first_dt = datetime.fromtimestamp(r["first_ts"] / 1000, tz=UTC)
                last_dt = datetime.fromtimestamp(r["last_ts"] / 1000, tz=UTC)
                ts_info = f" | {first_dt.strftime('%H:%M')}->{last_dt.strftime('%H:%M')}"
            print(f"HS={r['hs_s']:.1f}s | DL={r['dl_s']:.1f}s | "
                  f"{r['bars']} barras | {r['bars_per_s']:.0f} bars/s{ts_info}")
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"FAIL {e}")
            results.append({"call": i, "hs_s": 0, "dl_s": 0, "bars": 0, "bars_per_s": 0, "error": str(e)})

    # Resumo
    ok = [r for r in results if r.get("bars", 0) > 0]
    errors = [r for r in results if r.get("error")]
    avg_hs = sum(r["hs_s"] for r in results) / len(results) if results else 0
    avg_bps = total_bars / total_time if total_time > 0 else 0

    print(f"\n{'═' * 55}")
    print("  RESUMO")
    print(f"  Chamadas: {CALLS} | OK: {len(ok)} | Erros: {len(errors)}")
    print(f"  Total barras: {total_bars:,} ({total_time:.0f}s, {avg_bps:.0f} bars/s)")
    print(f"  HS medio: {avg_hs:.1f}s")
    if ok:
        print("  OK Fresh-session funciona!")
    if errors:
        print(f"  WARN️  {len(errors)} falhas — sessao expirou?")
    print(f"{'═' * 55}")

    return 0 if errors == [] else 1


if __name__ == "__main__":
    sys.exit(main())
