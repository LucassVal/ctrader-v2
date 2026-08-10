"""PROPOSITO: G17 — REACT LINT GATE (eslint dashboard completo)
SPEC: S20.2
ROADMAP: D.10 — valida todos os arquivos .ts/.tsx do react-dashboard
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "10.0_ui_dash" / "react-dashboard"


def run_eslint() -> tuple[int, str]:
    """Executa ESLint em todos os arquivos .ts/.tsx do dashboard."""
    if not DASHBOARD_DIR.exists():
        return -1, f"Diretorio nao encontrado: {DASHBOARD_DIR}"

    eslint_bin = DASHBOARD_DIR / "node_modules" / ".bin" / "eslint.cmd"
    if not eslint_bin.exists():
        eslint_bin = DASHBOARD_DIR / "node_modules" / ".bin" / "eslint"
    if not eslint_bin.exists():
        return -1, f"ESLint nao encontrado em {eslint_bin}. Rode: cd react-dashboard && npm install"

    try:
        result = subprocess.run(
            [str(eslint_bin), "src/", "--ext", ".ts,.tsx", "--max-warnings", "0"],
            capture_output=True, text=True,
            cwd=str(DASHBOARD_DIR),
            timeout=60,
        )
        if result.returncode == 0:
            return 0, "Todos os arquivos TSX/TS passaram no ESLint"
        else:
            # Extract error count
            errors = result.stdout + result.stderr
            _ = [line for line in errors.split('\n') if 'error' in line.lower() and '✖' not in line]
            err_count = len([line for line in errors.split('\n') if line.strip().startswith('✖')])
            return 1, f"{err_count} problemas ESLint encontrados"
    except FileNotFoundError:
        return -1, "ESLint nao instalado. Rode: npm install"
    except subprocess.TimeoutExpired:
        return -1, "ESLint timeout (>60s)"


if __name__ == "__main__":
    print("=" * 50)
    print(" G17 — REACT LINT GATE")
    print(f" Dashboard: {DASHBOARD_DIR}")
    print("=" * 50)

    code, msg = run_eslint()
    if code == 0:
        print(f"\n[PASS] G17 REACT LINT: {msg}")
        sys.exit(0)
    else:
        print(f"\n[FAIL] G17 REACT LINT: {msg}")
        sys.exit(1)
