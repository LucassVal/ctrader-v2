"""PROPOSITO: Orquestrador de testes — Fase 2.
SPEC: S2.5 (test harness)
ROADMAP: Validacao completa do pipeline

Fluxo:
  1. PREFLIGHT MCP (handshake, ping, rate limits, health)
  2. TESTES SINTETICOS (cache, gaps, merge, calendar — zero MCP)
  3. TESTE REAL (backfill 15 dias, 7 simbolos — MCP real)
  4. RESULTADO FINAL

Uso:
  python tests/orchestrator.py [--skip-real] [--days 15]
"""
from __future__ import annotations

import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

VENV_PY = sys.executable
TESTS_DIR = ROOT / "tests"
STATUS_DIR = ROOT / "status"

# --- Config ---
SKIP_REAL = "--skip-real" in sys.argv
DAYS = 15
if "--days" in sys.argv:
    idx = sys.argv.index("--days")
    DAYS = int(sys.argv[idx + 1])

# ============================================================
# SECTION HEADER
# ============================================================

_results: list[tuple[str, bool, str, float]] = []  # (name, ok, detail, elapsed)


def section(title: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def result(name: str, ok: bool, detail: str, elapsed: float) -> None:
    icon = "[OK]" if ok else "[FAIL]"
    _results.append((name, ok, detail, elapsed))
    print(f"  {icon} {name} ({elapsed:.1f}s) — {detail}")


# ============================================================
# 1. PREFLIGHT MCP
# ============================================================

def preflight_mcp() -> dict:
    """Handshake + ping + health. Retorna status."""
    section("1. PREFLIGHT MCP")
    t0 = time.monotonic()

    try:
        from utils.mcp_client import get_balance, get_symbols, init_client
        config = ROOT / "config.yaml"
        init_client(str(config))
        hs_time = time.monotonic() - t0
        print(f"  Handshake: {hs_time:.1f}s")

        # Ping (get_balance)
        t1 = time.monotonic()
        bal = get_balance()
        ping_time = time.monotonic() - t1
        balance = bal.get("balance", 0) if isinstance(bal, dict) else 0
        eq = bal.get("equity", 0) if isinstance(bal, dict) else 0
        md = bal.get("moneyDigits", 2) if isinstance(bal, dict) else 2
        div = 10 ** md if md else 1
        print(f"  Ping:      {ping_time:.3f}s")
        print(f"  Balance:   ${balance / div:,.2f} (equity: ${eq / div:,.2f})")

        # Rate limits
        print("  Rate:      50 req/s (live) | 5 req/s (historico)")
        print("  Cap:       720h range, 1000 barras/req")

        # Symbols
        syms = get_symbols({})
        n_syms = len(syms) if isinstance(syms, list) else "?"
        print(f"  Symbols:   {n_syms} disponiveis")

        # Health
        print("  Health:    OK")
        result("MCP", True, f"HS={hs_time:.1f}s ping={ping_time:.3f}s", time.monotonic() - t0)
        return {"ok": True}

    except Exception as e:
        print(f"  [FAIL] MCP FALHOU: {e}")
        result("MCP", False, str(e)[:80], time.monotonic() - t0)
        return {"ok": False, "error": str(e)}


# ============================================================
# 2. TESTES SINTETICOS
# ============================================================

def run_synthetic_tests() -> bool:
    """Roda test_consolidation_cache.py — zero MCP."""
    section("2. TESTES SINTETICOS (cache, gaps, merge, pipeline)")
    t0 = time.monotonic()

    script = str(TESTS_DIR / "test_consolidation_cache.py")
    proc = subprocess.run(
        [VENV_PY, script],
        capture_output=True, text=True, timeout=30, cwd=str(ROOT),
    )
    elapsed = time.monotonic() - t0

    ok = proc.returncode == 0
    # Extrai contagem de suites
    n_pass = proc.stdout.count("PASS")
    n_fail = proc.stdout.count("FAIL")
    result("Sinteticos", ok, f"{n_pass} pass, {n_fail} fail", elapsed)

    if not ok:
        print(proc.stdout[-2000:])
        print(proc.stderr[-500:])
    return ok


# ============================================================
# 3. TESTE REAL
# ============================================================

def run_real_test() -> bool:
    """Roda test_per_symbol.py — fresh-session por simbolo."""
    section(f"3. TESTE REAL (fresh-session, {DAYS}d, 7 simbolos)")
    t0 = time.monotonic()

    script = str(TESTS_DIR / "test_per_symbol.py")
    proc = subprocess.Popen(
        [VENV_PY, script, "--days", str(DAYS)],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, cwd=str(ROOT),
    )
    for line in proc.stdout:
        print(line, end="")
    proc.wait(timeout=300)
    elapsed = time.monotonic() - t0
    ok = proc.returncode == 0

    result("Fresh-Session", ok, f"{elapsed:.0f}s", elapsed)
    return ok


# ============================================================
# 4. RESUMO
# ============================================================

def summary(mcp_ok: bool) -> None:
    section("4. RESUMO FINAL")

    passed = sum(1 for _, ok, _, _ in _results if ok)
    total = len(_results)
    total_time = sum(elapsed for _, _, _, elapsed in _results)

    print(f"  Testes: {passed}/{total} passaram ({total_time:.0f}s total)")
    for name, ok, detail, elapsed in _results:
        icon = "[OK]" if ok else "[FAIL]"
        print(f"    {icon} {name}: {detail} ({elapsed:.0f}s)")

    if not mcp_ok:
        print("\n  [WARN]  MCP offline — teste real pulado")
    elif passed == total:
        print("\n  [OK] Pipeline funcional!")

    print(f"{'=' * 70}")


# ============================================================
# MAIN
# ============================================================

def main() -> int:
    print("=" * 70)
    print("  NEOCORTEX V44 — ORQUESTRADOR DE TESTES (Fase 2)")
    print(f"  Data: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"  Real: {'SIM' if not SKIP_REAL else 'NAO'} | Janela: {DAYS}d")
    print("=" * 70)

    # 1. Preflight
    mcp = preflight_mcp()
    if not mcp["ok"]:
        print("\n  [WARN]  MCP offline — pulando teste real")
        # Continua com sintéticos

    # 2. Sintéticos (sempre roda)
    syn_ok = run_synthetic_tests()

    # 3. Real (se MCP ok)
    real_ok = True
    if not SKIP_REAL and mcp.get("ok"):
        real_ok = run_real_test()
    elif SKIP_REAL:
        print("\n  [SKIP] Teste real (--skip-real)")
    else:
        print("\n  [SKIP] Teste real (MCP offline)")

    # 4. Resumo
    summary(mcp.get("ok", False))

    all_ok = syn_ok and real_ok and mcp.get("ok", True)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
