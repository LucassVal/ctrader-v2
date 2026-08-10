"""PROPOSITO: G20 — DataSource Wire Gate: detecta bypass do DataSource.
SPEC: S26
ROADMAP: DataSource Layer
AST scan: detecta funcoes que leem snapshot.json/status/json_log direto
sem passar por utils.data_source. FALHA = [ERR].
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# Funcoes que indicam bypass (leitura direta de disco, nao via DataSource)
BYPASS_FUNCTIONS: set[str] = {
    "_read_snapshot",
    "_get_snapshot_safe",
    "_read_status",
    "get_snapshot",        # de f0_collector.orc_coleta — bypassa DataSource
}

# Import patterns que indicam bypass
BYPASS_IMPORTS: set[str] = {
    "f0_collector.orc_coleta",       # get_snapshot direto do F0 em vez de DataSource
}

# Modulos EXCLUIDOS
EXCLUDE_PREFIXES: tuple[str, ...] = (
    "f0_collector/",
    "gates/",
    "tests/",
    "utils/data_source.py",
    "utils/mcp_client.py",
    "99_archive/",
    "legacy/",
    "__pycache__/",
)

ALLOWLIST: dict[str, str] = {
    "f2_fusao/orc_fusao.py": "F2 escreve fusion_output.json — ROADMAP 3.2",
    "f3_validacao/orc_validacao.py": "F3 escreve verdict.json — ROADMAP 3.3",
    "f4_executor/orc_execucao.py": "F4 writer de trades.db — ROADMAP 5.1",
    "f4_executor/safety_orc_execucao.py": "safety interno — ROADMAP 5.1",
    "f5_mar/__init__.py": "F5 init — ROADMAP 5.2",
    "f5_mar/mcp_sync_orc_mar.py": "mcp_sync — ROADMAP 5.2",
    "f5_mar/orc_mar.py": "F5 proprio output — ROADMAP 5.2",
    "f5_mar/rules_orc_mar.py": "rules — ROADMAP 5.2",
    "f5_mar/trades_log_orc_mar.py": "trades_log — ROADMAP 5.2",
    "utils/_artifacts.py": "infra — ROADMAP 1.7",
    "utils/health.py": "health interno — ROADMAP 1.7",
    "utils/json_log_orc_metricas.py": "json_log writer — ROADMAP 1.7",
    "utils/logger.py": "logger infra — ROADMAP 1.7",
    "utils/orc_mercado.py": "S26 backward compat: _read_snapshot mantido, normalize_markets() ja usa DataSource",
    "utils/slot_tracker.py": "slot_tracker — ROADMAP 1.7",
    "f1_analyzer/orc_analise.py": "F1 le snapshot para analise — ROADMAP 2.1",
    "f1_analyzer/dxy_orc_analise.py": "dxy interno F1 — ROADMAP 2.2",
    "f1_analyzer/pillars_orc_analise.py": "pillars F1 — ROADMAP 2.1",
    "f1_analyzer/indicators_orc_analise.py": "indicators F1 — ROADMAP 2.2",
    "f1_analyzer/sentiment_orc_analise.py": "sentiment F1 — ROADMAP 2.3",
    "utils/orc_dashboard.py": "S26 fase 4 pendente: migrar _get_snapshot_safe -> DataSource — ROADMAP 1.7",
    "utils/orc_metricas.py": "S26 fase 4 pendente: migrar _read_status -> DataSource — ROADMAP 5.0",
    "utils/orc_ranking.py": "ranking le fusion_output.json — ROADMAP 4.0",
    "utils/f0_supervisor_orc_dashboard.py": "f0_supervisor interno — ROADMAP 1.7",
    "f0_collector/candles_buffer.py": "buffer writer — ROADMAP 2.0",
    "f0_collector/storage_orc_coleta.py": "storage F0 — ROADMAP 2.0",
}


def _find_bypass_calls(tree: ast.Module) -> set[str]:
    """Encontra chamadas a funcoes de bypass no AST."""
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in BYPASS_FUNCTIONS:
                calls.add(node.func.id)
            if isinstance(node.func, ast.Attribute) and node.func.attr in BYPASS_FUNCTIONS:
                calls.add(node.func.attr)
    return calls


def _find_bypass_imports(tree: ast.Module) -> set[str]:
    """Encontra imports de modulos que indicam bypass."""
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module in BYPASS_IMPORTS:
            imports.add(node.module)
    return imports


def scan_file(filepath: Path) -> list[str]:
    """Scaneia um arquivo. Retorna lista de mensagens [ERR]."""
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8", errors="replace"))
        errors: list[str] = []

        bypass_calls = _find_bypass_calls(tree)
        for func in sorted(bypass_calls):
            errors.append(f"[ERR] {filepath}: chamada {func}() — bypass do DataSource")

        bypass_imports = _find_bypass_imports(tree)
        for mod in sorted(bypass_imports):
            errors.append(f"[ERR] {filepath}: import {mod} — use utils.data_source em vez disso")

        return errors
    except SyntaxError:
        return []


def main(test_dir: Path | None = None) -> int:
    if test_dir is None:
        test_dir = Path(__file__).resolve().parent.parent

    all_errors: list[str] = []
    py_files = sorted(test_dir.rglob("*.py"))

    for pf in py_files:
        rel = pf.relative_to(test_dir).as_posix()
        if any(rel.startswith(p) for p in EXCLUDE_PREFIXES):
            continue
        if rel in ALLOWLIST:
            continue

        for err in scan_file(pf):
            all_errors.append(err)

    # Show allowlist
    for rel in sorted(ALLOWLIST):
        print(f"  [ALLOW] {rel} — {ALLOWLIST[rel]}")

    if all_errors:
        for e in all_errors:
            print(e)
        print(f"\n[ERR] G20 DATASOURCE-WIRE: FAIL — {len(all_errors)} bypass(es)")
        print("Fix: use 'from utils.data_source import ...'")
        return 1

    print("[OK] G20 DATASOURCE-WIRE: PASS — 0 bypass(es)")
    return 0


if __name__ == "__main__":
    _dir = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    sys.exit(main(_dir))
