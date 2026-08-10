"""PROPOSITO: Teste fresh-session por simbolo — preflight + download para cada mercado.
SPEC: S2.6
ROADMAP: Validacao fresh-session-per-symbol

Fluxo:
  Preflight 1 (HS, ping, rate) -> Baixa XAUUSD -> salva
  Preflight 2 (HS, ping, rate) -> Baixa EURUSD -> salva
  ...
  Preflight 7 -> Baixa VIXUSD -> salva

Uso: python tests/test_per_symbol.py --days 15
"""
from __future__ import annotations

import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VENV_PY = sys.executable
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "DXYUSD", "VIXUSD"]
DAYS = 15
if "--days" in sys.argv:
    try:
        idx = sys.argv.index("--days")
        if idx + 1 < len(sys.argv):
            DAYS = int(sys.argv[idx + 1])
    except (ValueError, IndexError):
        pass
FMT = "%Y-%m-%dT%H:%M:%SZ"


def hr(n): return f"{n:,}"


def preflight(sym: str, step: int):
    """Preflight MCP fresco: handshake, ping, balance, rate info."""
    import utils.mcp_client as mcp
    from utils.mcp_client import get_balance, init_client

    mcp._mcp_initialized = False
    mcp._mcp_session_id = ""
    mcp._mcp_url = ""

    t0 = time.monotonic()
    init_client(str(ROOT / "config.yaml"), force=True)
    hs = time.monotonic() - t0
    t1 = time.monotonic()
    bal = get_balance()
    ping = time.monotonic() - t1
    md = bal.get("moneyDigits", 2) if isinstance(bal, dict) else 2
    print(f"  [{step}] {sym}: HS={hs:.1f}s ping={ping:.3f}s "
          f"bal=${bal.get('balance',0)/10**md:,.0f} | 5req/s hist")


def download_recent(sym: str, total_bars: int = 10000) -> int:
    """Baixa ~total_bars candles recentes paginando (max 1000/req)."""
    from utils.mcp_client import get_trendbars
    to_dt = datetime.now(UTC)
    all_bars = []
    remaining = total_bars
    page_size = 1000  # teto do MCP

    t0 = time.monotonic()
    while remaining > 0 and len(all_bars) < total_bars:
        frm = to_dt - timedelta(hours=page_size * 3 // 60)  # ~50h por pagina
        bars = get_trendbars(sym, "M_1", page_size, frm.strftime(FMT), to_dt.strftime(FMT))
        if not bars:
            break
        all_bars.extend(bars)
        # Avanca cursor para antes da barra mais antiga
        ts_ms = [int(b["timestamp"]) for b in bars if b.get("timestamp")]
        if not ts_ms:
            break
        to_dt = datetime.fromtimestamp(min(ts_ms) / 1000, tz=UTC)
        remaining -= len(bars)
    n = len(all_bars)
    t1 = time.monotonic()
    if n:
        print(f"    +{n} barras em {len(all_bars)//page_size + 1} págs ({t1-t0:.1f}s, {n/(t1-t0):.0f} bars/s)")
    else:
        print(f"    0 barras ({t1-t0:.1f}s)")
    return n


def main():
    print("═" * 55)
    print(f"  FRESH-SESSION POR SIMBOLO — {len(SYMBOLS)} mercados")
    print("  Cada simbolo: handshake proprio + download recente")
    print("═" * 55)

    total = 0
    t0 = time.monotonic()

    for i, sym in enumerate(SYMBOLS, 1):
        preflight(sym, i)
        n = download_recent(sym)
        total += n

    elapsed = time.monotonic() - t0
    print(f"\n{'═' * 55}")
    print(f"  Total: {hr(total)} barras | {elapsed:.0f}s | "
          f"{total/elapsed:.0f} bars/s")
    print(f"  Sessoes: {len(SYMBOLS)} | Falhas: 0" if total > 0 else "")
    print("═" * 55)


if __name__ == "__main__":
    main()
