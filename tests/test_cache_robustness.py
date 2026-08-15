"""PROPOSITO: Teste de robustez do cache — deleta barras e verifica scan.
SPEC: S2.6 / S31 | ROADMAP: Cache nao alucina gaps
NOTA: Script standalone (nao pytest). Uso: python tests/test_cache_robustness.py XAUUSD --delete-pct 5
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Pytest: nao coletar
__test__ = False

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VENV_PY = sys.executable
G23_SCRIPT = str(ROOT / "gates" / "run_consolidate_parquet.py")
CONSOLIDATED_DIR = ROOT / "data" / "consolidated"
STATUS_DIR = ROOT / "status"
FMT = "%Y-%m-%dT%H:%M:%SZ"

SYMBOL = "XAUUSD"
DELETE_PCT = 5
if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
    SYMBOL = sys.argv[1]
if "--delete-pct" in sys.argv:
    idx = sys.argv.index("--delete-pct")
    DELETE_PCT = int(sys.argv[idx + 1])


def hr(n): return f"{n:,}"
def banner(text): print(f"\n{'-' * 55}\n  {text}\n{'-' * 55}")


def download_10k() -> int:
    """Baixa 10K barras com fresh session."""
    import pandas as pd

    import utils.mcp_client as mcp
    from utils.mcp_client import get_trendbars, init_client

    mcp._mcp_initialized = False
    mcp._mcp_session_id = ""
    mcp._mcp_url = ""
    init_client(str(ROOT / "config.yaml"), force=True)

    to_dt = datetime.now(UTC)
    frm = to_dt - timedelta(days=10)
    all_bars = []
    page_size = 1000
    while len(all_bars) < 10000:
        bars = get_trendbars(SYMBOL, "M_1", page_size, frm.strftime(FMT), to_dt.strftime(FMT))
        if not bars:
            break
        all_bars.extend(bars)
        ts_ms = [int(b["timestamp"]) for b in bars if b.get("timestamp")]
        if not ts_ms:
            break
        to_dt = datetime.fromtimestamp(min(ts_ms) / 1000, tz=UTC)
    n = len(all_bars)
    if n == 0:
        return 0

    path = CONSOLIDATED_DIR / f"{SYMBOL}_M1.parquet"
    if path.exists():
        df = pd.read_parquet(path)
        if "timestamp" not in df.columns and isinstance(df.index, pd.DatetimeIndex):
            df["timestamp"] = (df.index.astype("int64") // 1_000_000).astype("int64")
            df = df.reset_index(drop=True)
    else:
        df = pd.DataFrame()

    rows_data = [{"timestamp": int(b["timestamp"]), "symbol": SYMBOL,
                  "open": float(b.get("open", 0)), "high": float(b.get("high", 0)),
                  "low": float(b.get("low", 0)), "close": float(b.get("close", 0)),
                  "tick_volume": int(b.get("tickVolume", 0))} for b in all_bars if int(b.get("timestamp", 0)) > 0]
    new_df = pd.DataFrame(rows_data)
    df = pd.concat([df, new_df], ignore_index=True)
    df = df.sort_values("timestamp").drop_duplicates(subset=["timestamp"], keep="last")
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"  +{n:,} barras -> {len(df):,} linhas")
    return len(df)


def run_scan() -> int:
    for f in [STATUS_DIR / "gap_report.json"]:
        if f.exists():
            f.unlink()
    subprocess.run([VENV_PY, G23_SCRIPT, "--check", "--window-days", "730"],
                   capture_output=True, text=True, timeout=120, cwd=str(ROOT))
    rp = STATUS_DIR / "gap_report.json"
    if rp.exists():
        with open(rp) as f:
            return json.load(f).get("symbols", {}).get(SYMBOL, {}).get("total_gaps", 0)
    return -1


def delete_random_bars(pct: int) -> int:
    import pandas as pd
    path = CONSOLIDATED_DIR / f"{SYMBOL}_M1.parquet"
    if not path.exists():
        return 0
    df = pd.read_parquet(path)
    if "timestamp" not in df.columns and isinstance(df.index, pd.DatetimeIndex):
        df["timestamp"] = (df.index.astype("int64") // 1_000_000).astype("int64")
        df = df.reset_index(drop=True)
    n_total = len(df)
    n_delete = max(1, int(n_total * pct / 100))
    block_size = 10
    n_blocks = n_delete // block_size
    indices = set()
    for _ in range(n_blocks):
        start = random.randint(0, n_total - block_size - 1)
        for j in range(block_size):
            indices.add(start + j)
    indices = sorted(indices)[:n_delete]
    df = df.drop(df.index[indices])
    df = df.sort_values("timestamp").reset_index(drop=True)
    df.to_parquet(path, index=False)
    print(f"  Deletadas {n_delete:,} de {n_total:,} barras ({pct}%)")
    return n_delete


def main():
    print("═" * 55)
    print(f"  TESTE ROBUSTEZ CACHE — {SYMBOL} | Delete: {DELETE_PCT}%")
    print("═" * 55)

    banner("1. DOWNLOAD 10K barras")
    rows = download_10k()
    if rows == 0:
        print("  [ERR] Download vazio")
        return 1

    banner("2. SCAN BASELINE")
    gaps_before = run_scan()
    print(f"  Gaps baseline: {gaps_before}")

    banner(f"3. DELETE {DELETE_PCT}%")
    deleted = delete_random_bars(DELETE_PCT)

    banner("4. SCAN POS-DELECAO")
    gaps_after = run_scan()
    delta = gaps_after - gaps_before
    print(f"  Gaps: {gaps_before} -> {gaps_after} (+{delta})")

    banner("5. VERIFICACAO")
    if gaps_after > gaps_before:
        print(f"  OK Cache detectou +{delta} gaps reais (sem alucinacao)")
        print(f"  Barras deletadas: {deleted:,} | Novos gaps: {delta}")
    elif gaps_after == gaps_before and deleted > 0:
        print(f"  WARN️  Cache NAO detectou {deleted:,} barras deletadas")
    else:
        print(f"  WARN️  Gaps diminuíram? {gaps_before} -> {gaps_after}")
    print("═" * 55)
    return 0 if gaps_after >= gaps_before else 1


if __name__ == "__main__":
    sys.exit(main())
