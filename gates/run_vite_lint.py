"""PROPOSITO: G18 — VITE LINT GATE (oxlint via vite-plugin-oxlint)
SPEC: S20.2
ROADMAP: D.10 — valida todos os .ts/.tsx do react-dashboard com oxlint
R21: oxlint 95+ regras, 8 threads, <50ms por arquivo
"""

from __future__ import annotations

import contextlib
import subprocess
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "10.0_ui_dash" / "react-dashboard"


def run_oxlint() -> tuple[int, str, int]:
    """Executa oxlint em src/. Retorna (exit_code, msg, warning_count)."""
    if not DASHBOARD_DIR.exists():
        return -1, f"Diretorio nao encontrado: {DASHBOARD_DIR}", 0

    oxlint_bin = DASHBOARD_DIR / "node_modules" / ".bin" / "oxlint.cmd"
    if not oxlint_bin.exists():
        oxlint_bin = DASHBOARD_DIR / "node_modules" / ".bin" / "oxlint"
    if not oxlint_bin.exists():
        return -1, "oxlint nao encontrado. Rode: cd react-dashboard && npm install", 0

    try:
        result = subprocess.run(
            [str(oxlint_bin), "src/", "--deny-warnings"],
            capture_output=True, text=True,
            cwd=str(DASHBOARD_DIR),
            timeout=180,
        )
        output = result.stdout + result.stderr

        # oxlint exit code 0 = no errors. Warnings don't affect exit code.
        if result.returncode == 0:
            # Extract warning count
            wc = 0
            for line in output.split('\n'):
                if 'warnings' in line.lower() and '0 errors' in line.lower():
                    wc = 0
                    parts = line.split('warnings')[0].strip().split()
                    if parts:
                        with contextlib.suppress(ValueError):
                            wc = int(parts[-1])
                    return 0, f"0 erros, {wc} warnings", wc
            return 0, "0 erros, 0 warnings", 0
        else:
            # Has errors
            err_lines = [ln for ln in output.split('\n') if 'error' in ln.lower() and 'Found' in ln]
            return 1, f"oxlint encontrou erros: {err_lines[0] if err_lines else 'verificar output'}", 0

    except FileNotFoundError:
        return -1, "oxlint nao instalado", 0
    except subprocess.TimeoutExpired:
        return -1, "oxlint timeout (>30s)", 0


if __name__ == "__main__":
    print("=" * 50)
    print(" G18 — VITE LINT GATE (oxlint)")
    print(f" Dashboard: {DASHBOARD_DIR}")
    print("=" * 50)

    code, msg, warnings = run_oxlint()
    if code == 0:
        print(f"\n[PASS] G18 VITE LINT: {msg}")
        sys.exit(0)
    else:
        print(f"\n[FAIL] G18 VITE LINT: {msg}")
        sys.exit(1)
