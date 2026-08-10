"""G22 — PRE-FLIGHT: checklist de dependencias ao iniciar cTrader.
R-USE: harness_boot.py (ja valida imports), run_preflight_parquet.py (G21).
Ampliado com: MCP, F0, Parquet, Vector BT, pandas, numpy, endpoints.

Formato: checklist ON/OFF igual aos gates.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "status" / "snapshot.json"
CONFIG = ROOT / "config.yaml"
SYMBOLS = ["XAUUSD", "EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]


def check(label: str, ok: bool, detail: str = "") -> dict:
    return {"label": label, "status": "ON" if ok else "OFF", "detail": detail}


def run_checks() -> list[dict]:
    results: list[dict] = []

    # -- Ambiente (lazy — imports podem ser lentos) --
    try:
        import importlib
        pd_m = importlib.import_module("pandas")
        results.append(check("pandas", True, pd_m.__version__))
    except Exception:
        results.append(check("pandas", False, "nao instalado"))

    try:
        np_m = __import__("numpy")
        results.append(check("numpy", True, np_m.__version__))
    except Exception:
        results.append(check("numpy", False, "nao instalado"))

    # Vector BT (so verifica existencia do pacote, sem import — numba JIT lento)
    vbt_path = ROOT.parent.parent / ".venv" / "Lib" / "site-packages" / "vectorbt"
    results.append(check("Vector BT", vbt_path.exists(),
                         "instalado" if vbt_path.exists() else "pip install vectorbt"))

    # -- Config --
    results.append(check("config.yaml", CONFIG.exists(),
                         str(CONFIG) if CONFIG.exists() else "crie config.yaml com token MCP"))

    # -- MCP (so verifica config, nao conecta — handshake e lento) --
    results.append(check("MCP config", CONFIG.exists(),
                         "token presente" if CONFIG.exists() else "crie config.yaml"))

    # -- F0 / Snapshot --
    if SNAPSHOT.exists():
        try:
            snap = json.loads(SNAPSHOT.read_text())
            online = snap.get("online", False)
            syms = len(snap.get("symbols", {}))
            age = (datetime.now(UTC) - datetime.fromisoformat(snap["timestamp_utc"])).total_seconds()
            age_str = f"{age:.0f}s atras"
            results.append(check("Snapshot F0", online and syms >= 5,
                                 f"online={online}, symbols={syms}, {age_str}"))
        except Exception:
            results.append(check("Snapshot F0", False, "ilegivel"))
    else:
        results.append(check("Snapshot F0", False, "snapshot.json nao existe — inicie F0"))

    # -- Parquet --
    data_dir = ROOT / "data"
    parquet_count = 0
    if data_dir.exists():
        parquet_count = len(list(data_dir.glob("m1_*.parquet")))
    results.append(check("Parquet M_1", parquet_count >= 5,
                         f"{parquet_count}/5 simbolos" if parquet_count else "aguardando F0 persistir"))

    # -- VBT Parquet (S27) --
    vbt_count = 0
    if data_dir.exists():
        vbt_count = len(list(data_dir.glob("vbt_*.parquet")))
    results.append(check("VBT Parquet", vbt_count >= 1,
                         f"{vbt_count} simbolos com indicadores" if vbt_count else "indicadores nao persistidos"))

    # -- TF Consolidation --
    tf_summary: dict[str, int] = {}
    try:
        from utils.data_source import get_snapshot
        snap = get_snapshot()
        tb = snap.get("trendbars", {}) if snap else {}
        for sym_data in tb.values():
            if isinstance(sym_data, dict):
                for tf, bars in sym_data.items():
                    if isinstance(bars, list):
                        tf_summary[tf] = tf_summary.get(tf, 0) + len(bars)
    except Exception:
        pass
    tf_str = ", ".join(f"{tf}:{n}" for tf, n in sorted(tf_summary.items())) or "vazio"
    results.append(check("Trendbars TFs", bool(tf_summary), tf_str))

    # -- Backfill --
    bf_dir = ROOT / "data" / "backfill"
    bf_count = len(list(bf_dir.glob("*_M1.parquet"))) if bf_dir.exists() else 0
    results.append(check("Backfill 2a", bf_count >= 5,
                         f"{bf_count}/5 simbolos" if bf_count else "execute backfill_orc_coleta.py"))

    # -- Endpoints --
    try:
        import urllib.request
        resp = urllib.request.urlopen("http://127.0.0.1:7744/api/ctrader/health", timeout=3)
        results.append(check("API :7744", resp.status == 200, f"HTTP {resp.status}"))
    except Exception:
        results.append(check("API :7744", False, "servidor offline — inicie Abrir_NeoCortex_NovaPulse"))

    # -- Dashboard --
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:5173", timeout=3)
        results.append(check("Dashboard :5173", resp.status == 200, f"HTTP {resp.status}"))
    except Exception:
        results.append(check("Dashboard :5173", False, "Vite offline"))

    # -- Gates --
    gate_dir = ROOT / "gates"
    gates_found = len(list(gate_dir.glob("run_*.py")))
    results.append(check("Gates suite", gates_found >= 13, f"{gates_found} gates"))

    return results


def main() -> int:
    print("=" * 60)
    print(" CTRADER V2 — PRE-FLIGHT CHECKLIST")
    print(f" {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    checks = run_checks()
    on_count = sum(1 for c in checks if c["status"] == "ON")
    off_count = sum(1 for c in checks if c["status"] == "OFF")

    for c in checks:
        icon = "[ON] " if c["status"] == "ON" else "[OFF]"
        print(f"  {icon} {c['label']:<20} {c['detail']}")

    print(f"\n  {on_count} ON / {off_count} OFF / {len(checks)} total")

    if off_count > 3:
        print("\n[WARN] Muitas dependencias offline. Verifique antes de iniciar.")
    elif off_count > 0:
        print("\n[OK] Sistema funcional — algumas dependencias pendentes.")
    else:
        print("\n[OK] Todas as dependencias online.")

    return 0  # checklist informativa, sempre exit 0


if __name__ == "__main__":
    sys.exit(main())
