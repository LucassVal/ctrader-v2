"""PROPOSITO: G7 ORBITAL — cross-module DDD validation (ORQ parentesco + fase isolation).
SPEC: S0 (QUALITY_GATES.md)
ROADMAP: 0.G7 — valida hierarquia DDD: ORQ importa SATs, sem cross-phase, sem circular.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

CTRADER = Path(__file__).resolve().parent.parent

EXCLUDE_DIRS = {
    "ctrader-skills-official", "__pycache__", ".git",
    "99_archive", "legacy", "tests", "gates", "contracts",
    "data", "status", "logs", "specs", "node_modules",
}

# SATs known to be cortados/offline — allowlisted
ALLOWLIST_UNWIRED_SAT: dict[str, str] = {
    "ichimoku_orc_analise": "cortado da v1 — ROADMAP 2.3",
    "volume_orc_analise": "zero importadores — ROADMAP 2.4",
    "news_orc_analise": "cortado, MCP nao prove news — ROADMAP 2.5",
    "entry_orc_execucao": "nao wireado ao orc_execucao — ROADMAP 5.1",
    "gates_orc_execucao": "nao wireado ao orc_execucao — ROADMAP 5.1",
    "dxy_orc_analise": "transitivo: micro_orc_analise -> dxy — ROADMAP 2.2",
    "indicators_orc_analise": "transitivo: pillars_orc_analise -> indicators — ROADMAP 2.2",
    "json_log_orc_metricas": "importado por orc_dashboard+orc_execucao, nao direto pelo parent — ROADMAP 1.7",
    "backfill_supervisor_orc_dashboard": "importado pelo router (10.0_ui_dash), nao pelo parent orc_dashboard — ROADMAP S31-PROG",
    "backfill_orc_coleta": "CLI standalone (python backfill_orc_coleta.py --gaps), entry point nao importado — ROADMAP S2.5-BF",
    "storage_orc_vbt": "SAT persistencia VBT importado por orc_metricas/quality/pattern — parent nominal orc_vbt nao existe (naming debt) — ROADMAP S27",
    "storage_orc_consolidated": "SAT fallback S31-VBT (indicadores do consolidado G23) importado por storage_orc_vbt — parent nominal orc_consolidated nao existe (naming debt) — ROADMAP S31",
    "orc_scan": "ORQ CLI batch S34 (python -m utils.orc_scan --scan), nunca importado em runtime — mesmo padrao backfill CLI — ROADMAP S34",
    "matrix_orc_scan": "SAT de orc_scan: helpers numpy importados pelo ORQ (split DDD G12) — ROADMAP S34",
    "matrix_orc_quality": "SAT de orc_quality: engine numpy trailing_quality_f1 importada pelo ORQ orc_scan (split DDD G12) — ROADMAP S34 v1.2",
    "families_orc_vectorbt": "SAT de orc_vectorbt: latest_families na cauda do consolidado (fix 16/16) — ROADMAP S39",
    "vista_orc_mercado": "SAT de orc_mercado: drill-down MTF consumido pelo router /vector/symbol/{sym} — ROADMAP S39",
    "matrix_orc_vista": "SAT de vista_orc_mercado: engine de regime MTF (split DDD G12) — ROADMAP S39",
    "signal_emitter_orc_score": "CLI/ciclo S36 (python -m utils.signal_emitter_orc_score), importado por ninguem em runtime — ROADMAP S36",
}

# Fase -> fases que PODE importar (incluindo a propria)
PHASE_ALLOWED_IMPORTS: dict[str, set[str]] = {
    "f0_collector":  {"f0_collector", "utils", "contracts"},
    "f1_analyzer":   {"f1_analyzer", "utils", "contracts", "f0_collector"},
    "f2_fusao":      {"f2_fusao", "utils", "contracts", "f0_collector"},
    "f3_validacao":  {"f3_validacao", "utils", "contracts", "f0_collector"},
    "f4_executor":   {"f4_executor", "utils", "contracts", "f0_collector", "f5_mar"},
    "f5_mar":        {"f5_mar", "utils", "contracts", "f0_collector"},
    # f1_analyzer permitido em utils desde S25.10: orc_indices consome
    # dxy_orc_analise + sentiment_orc_analise p/ /vector/globals.
    # Debt DDD: mover esses SATs para utils/ (ROADMAP SPEC-2).
    "utils":         {"utils", "contracts", "f0_collector", "f1_analyzer", "f2_fusao", "f3_validacao", "f4_executor", "f5_mar"},
    "gates":         {"*"},
    "tests":         {"*"},
}

# Known project-internal phase prefixes (all phases + utils + contracts)
PROJECT_PHASES = {
    "f0_collector", "f1_analyzer", "f2_fusao", "f3_validacao",
    "f4_executor", "f5_mar", "utils", "contracts",
}

# STDLIB and common third-party prefixes to skip
SKIP_IMPORT_PREFIXES = {
    "", "abc", "argparse", "asyncio", "base64", "builtins", "collections",
    "contextlib", "copy", "csv", "datetime", "decimal", "enum", "functools",
    "glob", "hashlib", "http", "importlib", "inspect", "io", "itertools",
    "json", "logging", "math", "multiprocessing", "operator", "os",
    "pathlib", "pickle", "platform", "pprint", "queue", "random", "re",
    "shlex", "shutil", "signal", "sqlite3", "statistics", "string",
    "struct", "subprocess", "sys", "tempfile", "textwrap", "threading",
    "time", "traceback", "types", "typing", "typing_extensions",
    "unittest", "urllib", "uuid", "warnings", "weakref", "xml",
    "yaml", "pandas", "numpy", "requests", "pydantic", "fastapi",
    "uvicorn", "pytest", "anyio", "pytz", "zoneinfo", "dateutil",
    "tqdm", "dotenv", "ruff", "slop_detector", "mockbuster",
    "__future__", "vectorbt",
}


def phase_of(filepath: str) -> str:
    """Extrai a fase do path: 'f0_collector/orc_coleta.py' -> 'f0_collector'."""
    parts = filepath.replace("\\", "/").split("/")
    if len(parts) >= 1:
        return parts[0]
    return "root"


def module_of(import_path: str) -> str:
    """Extrai a fase do import: 'f0_collector.poller_orc_coleta' -> 'f0_collector'."""
    return import_path.split(".")[0]


def scan() -> tuple[dict, dict, dict]:
    """Scan all .py files, building ORQ catalog, SAT catalog, and import graph."""
    orqs: dict[str, str] = {}   # orc_name -> relpath
    sats: dict[str, tuple[str, str]] = {}  # sat_name -> (parent_orc, relpath)
    imports: dict[str, set[str]] = {}  # relpath -> set of imported modules

    for pyfile in sorted(CTRADER.rglob("*.py")):
        rel = str(pyfile.relative_to(CTRADER)).replace("\\", "/")
        phase = phase_of(rel)
        if phase in EXCLUDE_DIRS:
            continue

        try:
            tree = ast.parse(pyfile.read_text(encoding="utf-8"))
        except SyntaxError:
            continue

        name = pyfile.stem

        # Classify as ORQ or SAT
        if name.startswith("orc_") and not name.startswith("orc_dashboard") and not name.startswith("orc_metricas") and not name.startswith("orc_ranking"):
            # True orchestrator: starts with orc_, not a utility ORQ
            pass
        elif name.startswith("orc_"):
            # Utility ORQs (dashboard, metricas, ranking) — still track
            pass

        if name.startswith("orc_"):
            orqs[name] = rel
        elif "_orc_" in name:
            parts = name.split("_orc_")
            if len(parts) == 2:
                parent = parts[1]
                sats[name] = (parent, rel)

        # Extract imports
        imps: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imps.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imps.add(node.module)

        imports[rel] = imps

    return orqs, sats, imports


def validate(orqs: dict, sats: dict, imports: dict) -> list[str]:
    errors: list[str] = []

    # === 1. SAT -> ORQ: each SAT MUST be imported by its parent ===
    for sat_name, (parent, sat_path) in sorted(sats.items()):
        parent_orq = f"orc_{parent}"
        if sat_name in ALLOWLIST_UNWIRED_SAT:
            errors.append(f"  [ALLOW] SAT orfao: {sat_name} — {ALLOWLIST_UNWIRED_SAT[sat_name]}")
            continue
        if parent_orq not in orqs:
            errors.append(f"  [ERR] SAT {sat_name}: parent orquestrador '{parent_orq}' nao encontrado")
            continue

        parent_path = orqs[parent_orq]
        parent_imports = imports.get(parent_path, set())

        # Check if any import from parent references this SAT
        found = any(sat_name in imp for imp in parent_imports)
        if not found:
            errors.append(f"  [ERR] SAT {sat_path}: nao importado pelo parent {parent_path}")

    # === 2. Cross-phase isolation (project-internal only) ===
    for filepath, file_imports in sorted(imports.items()):
        file_phase = phase_of(filepath)
        if file_phase in EXCLUDE_DIRS:
            continue
        allowed = PHASE_ALLOWED_IMPORTS.get(file_phase, {"*"})
        if "*" in allowed:
            continue

        for imp in file_imports:
            imp_phase = module_of(imp)
            # Skip stdlib and third-party
            if imp_phase in SKIP_IMPORT_PREFIXES:
                continue
            if imp_phase in EXCLUDE_DIRS or imp_phase == file_phase:
                continue
            if imp_phase == "vector":
                continue
            # Only flag project-internal cross-phase
            if imp_phase in PROJECT_PHASES and imp_phase not in allowed:
                errors.append(f"  [ERR] Cross-phase: {filepath} importa '{imp}' (fase={imp_phase}), "
                              f"mas fase={file_phase} so permite: {sorted(allowed)}")

    # === 3. ORQ -> at least 1 SAT imported (unless leaf ORQ) ===
    leaf_orqs = {"orc_fusao", "orc_validacao", "orc_ranking", "orc_dashboard", "orc_metricas"}
    for orq_name, orq_path in sorted(orqs.items()):
        if orq_name in leaf_orqs:
            continue
        orq_imports = imports.get(orq_path, set())
        child_sats = [s for s, (p, _) in sats.items() if p in orq_name.replace("orc_", "")]
        if child_sats:
            wired = [s for s in child_sats if any(s in imp for imp in orq_imports)]
            if not wired and orq_name not in ALLOWLIST_UNWIRED_SAT:
                errors.append(f"  [WARN] ORQ {orq_path}: nenhum SAT wireado ({len(child_sats)} filhos: {child_sats})")

    return errors


def main() -> int:
    print("=" * 50)
    print(" G7 — ORBITAL: DDD cross-module")
    print(f" ctrader: {CTRADER}")
    print("=" * 50)

    orqs, sats, imports = scan()
    print(f"\n  ORQs: {len(orqs)} | SATs: {len(sats)} | Modulos: {len(imports)}")

    errors = validate(orqs, sats, imports)

    if not errors:
        print("\n[OK] G7 ORBITAL: PASS — hierarquia DDD valida")
        return 0

    print(f"\n  {len(errors)} issue(s):")
    for e in errors:
        print(e)

    # Check if all errors are ALLOW/WARN (non-blocking)
    fatals = [e for e in errors if "[ERR]" in e]
    if fatals:
        print(f"\n[ERR] G7 ORBITAL: FAIL — {len(fatals)} erro(s) cross-module")
        return 1

    print("\n[OK] G7 ORBITAL: PASS — allowlist justificada")
    return 0


if __name__ == "__main__":
    sys.exit(main())
