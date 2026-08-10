"""PROPOSITO: Harness Runner -- executa harness boot + pytest e reporta (G6).
SPEC: S0
ROADMAP: 0.G6 -- pre-flight health check de todos os orquestradores.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

EXPECTED_PHASES = ["f0", "f1", "f2", "f3", "f4", "f5"]


def run_boot_harness() -> tuple[bool, str]:
    """Executa harness_boot.py -- validacao de todos os orquestradores."""
    test_dir = Path(__file__).resolve().parent.parent / "tests"
    harness = test_dir / "harness_boot.py"
    if not harness.exists():
        return False, "[ERR] harness_boot.py nao encontrado"

    python = sys.executable
    result = subprocess.run(
        [python, str(harness)],
        capture_output=True, text=True, timeout=30,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    return result.returncode == 0, result.stdout + result.stderr


def run_pytest() -> tuple[bool, str]:
    """Executa pytest em tests/."""
    test_dir = Path(__file__).resolve().parent.parent / "tests"
    python = sys.executable

    # Verifica se cada fase tem pelo menos 1 teste
    missing = []
    for phase in EXPECTED_PHASES:
        pattern = f"test_{phase}"
        found = any(pattern in f.name for f in test_dir.glob("test_*.py"))
        if not found:
            missing.append(phase)

    output_parts = []
    if missing:
        output_parts.append(f"[WARN] FASES SEM TESTE UNITARIO: {missing}")

    result = subprocess.run(
        [python, "-m", "pytest", str(test_dir), "-v", "--tb=short", "-x"],
        capture_output=True, text=True, timeout=120,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    output_parts.append(result.stdout + result.stderr)
    return result.returncode == 0, "\n".join(output_parts)


def run_harness() -> tuple[bool, str]:
    """Executa boot harness + pytest. Retorna (passou, output)."""
    output_parts = []

    # 1. Boot harness (pre-flight)
    boot_ok, boot_out = run_boot_harness()
    output_parts.append("=== HARNESS BOOT ===")
    output_parts.append(boot_out)

    # 2. Pytest (unit tests)
    pytest_ok, pytest_out = run_pytest()
    output_parts.append("\n=== PYTEST ===")
    output_parts.append(pytest_out)

    return boot_ok and pytest_ok, "\n".join(output_parts)


def main():
    print("=" * 60)
    print("G6 HARNESS -- cTrader V2")
    print("=" * 60)

    passed, output = run_harness()
    print(output)

    if passed:
        print("\n[OK] G6 HARNESS: PASS")
        sys.exit(0)
    else:
        print("\n[ERR] G6 HARNESS: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
