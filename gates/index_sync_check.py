#!/usr/bin/env python3
"""
PROPOSITO: specs/INDEX.md 1:1 com o disco E com o grafo de referencias real.
SPEC: S0
ROADMAP: 0.G8
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        _s.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent          # 11.0_apps/ctrader
REPO = ROOT.parent.parent                              # neocortex/
INDEX_PATH = ROOT / "specs" / "INDEX.md"
BLUEPRINT_INDEX = ROOT / "blueprint" / "INDEX.md"
GRAPH_OUT = ROOT / "logs" / "index_graph.json"

# Fora do escopo de indexacao (vendor, runtime, caches). Legado real foi para 99_archive/.
EXCLUDE_PARTS = {
    "ctrader-skills-official", "__pycache__", ".git", ".pytest_cache",
    "node_modules", "logs", "data", "status",
    "gates", "tests",  # infra de qualidade, nao pipeline ctrader
    "99_archive", "legacy",  # fora do INDEX — arquivado
}
INDEXABLE_EXT = {".py", ".md", ".yaml", ".json", ".sh", ".txt", ".toml"}

# Orfaos conhecidos e rastreados — cada um aponta o item do ROADMAP que o resolve.
# R-WARN-FORBIDDEN: allowlist explicita, nunca skip silencioso.
ORPHAN_ALLOWLIST = {
    "f1_analyzer.py": "morto (pacote sombreia) — ROADMAP D.4",
    "f5_mar.py": "morto (pacote sombreia) — ROADMAP D.4",
    "f1_analyzer/ichimoku_orc_analise.py": "cortado da v1 — ROADMAP 2.3",
    "f1_analyzer/volume_orc_analise.py": "zero importadores — ROADMAP 2.4",
    "dashboard.py": "entry point streamlit legado",
    "utils/orc_vbt_portfolio.py": "VBT legacy ou WIP",
    "vectorbt_calibrator.py": "entry point manual (replay) — ROADMAP 6.1",
    "f4_executor/entry_orc_execucao.py": "nao wireado ao orc_execucao — ROADMAP 5.1",
    "f4_executor/gates_orc_execucao.py": "nao wireado ao orc_execucao — ROADMAP 5.1",
    "f0_collector/backfill_orc_coleta.py": "CLI backfill 2a gap-aware (entry point, --gaps) — ROADMAP S2.5-BF",
    "utils/orc_scan.py": "ORQ CLI batch S34 (python -m utils.orc_scan --scan) — ROADMAP S34",
    "utils/matrix_orc_scan.py": "SAT de orc_scan importado via 'from utils import' (split DDD G12) — ROADMAP S34",
    "utils/matrix_orc_quality.py": "SAT de orc_quality importado via 'from utils import' (split DDD G12) — ROADMAP S34 v1.2",
    "utils/families_orc_vectorbt.py": "SAT de orc_vectorbt importado pelo storage_orc_consolidated (S39 fix 16/16)",
    "utils/vista_orc_mercado.py": "SAT de orc_mercado importado pelo router ctrader_v2 (S39 drill-down MTF)",
    "utils/matrix_orc_vista.py": "SAT de vista_orc_mercado importado via from utils import (split DDD G12) — S39",
    "utils/signal_emitter_orc_score.py": "SAT CLI S36 (python -m utils.signal_emitter_orc_score) — ROADMAP S36",
    "HANDOFF_KIMI.md": "handoff doc de sessao — fora do SSOT de codigo",
    "f1_analyzer/dxy_orc_analise.py": "importado por orc_analise via __init__ — INDEX F1",
    "utils/orc_dashboard.py": "importado por run_api.py (10.0_ui_dash) — INDEX DASHBOARD",
    "f2_fusao/orc_fusao.py": "importado por run.py — INDEX F2",
    "f3_validacao/orc_validacao.py": "importado por run.py — INDEX F3",
    "blackout_times.json": "runtime config — ROADMAP D.6",
    "requirements-gates.txt": "gate deps pinadas — ROADMAP 0.G1",
    "contracts/__init__.py": "pacote re-export — INDEX CONTRACTS",
    "f0_collector/__init__.py": "pacote re-export",
    "f1_analyzer/__init__.py": "pacote re-export",
    "f2_fusao/__init__.py": "pacote re-export",
    "f3_validacao/__init__.py": "pacote re-export",
    "f4_executor/__init__.py": "pacote re-export",
    "f5_mar/__init__.py": "pacote re-export",
    "utils/__init__.py": "pacote re-export",
    "_archive_f0_collector_god.py": "backup pre-DDD (referencia)",
    "_archive_f4_executor_god.py": "backup pre-DDD (referencia)",
    "contracts/fusion_output.py": "TypedDict contract — INDEX CONTRACTS",
    "specs/harness.md": "harness spec — INDEX Specs ativos",
    "utils/_artifacts.py": "atomic write util — INDEX UTILS",
    "utils/config_loader.py": "config loader — INDEX UTILS",
    "utils/schema_validator.py": "schema validator — INDEX UTILS",
    "utils/session_manager.py": "session manager — INDEX UTILS",
    "utils/slot_tracker.py": "slot tracker — INDEX UTILS",
    "specs/orc_ordens.md": "orc_ordens spec — INDEX Specs ativos",
    "specs/orc_ranking.md": "orc_ranking spec — INDEX Specs ativos",
    "specs/QUALITY_GATES.md": "quality gates — INDEX Specs ativos",
    "specs/ROADMAP.md": "roadmap — INDEX Specs ativos",
    "specs/ruse_alternatives.md": "ruse — INDEX Specs ativos",
    "specs/strategy_3scalps_5markets.md": "strategy — INDEX Specs ativos",
    "specs/vectorbt_ecosystem.md": "vectorbt — INDEX Specs ativos",
    "specs/S0.md": "G11 redirect",
    "specs/S1.1.md": "G11 redirect",
    "specs/S2.md": "G11 redirect",
    "specs/S3.md": "G11 redirect",
    "specs/S4.md": "G11 redirect",
    "specs/S5.md": "G11 redirect",
    "specs/S6.md": "G11 redirect",
    "specs/S7.md": "G11 redirect",
    "specs/S17.md": "G11 redirect",
    "specs/S18.md": "G11 redirect",
    "specs/S19.md": "G11 redirect",
    "specs/S20.md": "G11 redirect",
    "specs/S21.md": "G11 redirect",
}

# Stale planejados — arquivos citados no INDEX mas ainda NAO CRIADOS (harnesses pendentes,
# artefatos de pipeline). Cada entrada cita o item do ROADMAP que o cria.
# R-WARN-FORBIDDEN: qdo o arquivo for criado, REMOVER desta lista (senao o stale vira orfao real).
STALE_ALLOWLIST = {
    "99_DEAD_vectorbt_calibrator.md": "DEAD — substituido por S18_vector_db.md",
    "verdict.json": "artefato F3 — ROADMAP 3.3",
    "custom_rules.json": "artefato F5 — ROADMAP 3.4",
    "scores_raw.json": "artefato F1 — ROADMAP 3.2",
    "fusion_output.json": "artefato F2 — ROADMAP 3.3",
    "ranking.json": "artefato orc_ranking — ROADMAP 4.0",
    "status/metrics.json": "artefato json_log — ROADMAP 5.0",
    "status/calibration.json": "artefato orc_calibracao — PLANNED S36 (specs/orc_calibracao.md)",
    "status/score_live.json": "artefato signal_emitter_orc_score — PLANNED S36 (specs/orc_calibracao.md)",
    "status/pattern_library.json": "artefato orc_pattern --scan — PLANNED S34 (specs/orc_pattern_engine.md)",
    "snapshot.json": "artefato F0 runtime — ROADMAP 1.6 (status/snapshot.json, em .gitignore)",
    "1.0_orbitais/ps1_auditor.py": "no root do V44, referenciado pelo G9 — ROADMAP 0.6",
    # 25 harnesses pendentes (specs/INDEX.md -> HARNESS PENDENTES)
    "tests/test_f0_min_candles.py": "H1.1 — ROADMAP 1.1",
    "tests/test_f0_gateway_throttle.py": "H1.2 — ROADMAP 1.5",
    "tests/test_f0_backfill.py": "H1.3 — ROADMAP 1.3",
    "tests/test_f0_snapshot.py": "H1.4 — ROADMAP 1.6",
    "tests/test_f0_resample.py": "H1.5 — ROADMAP 1.3b",
    "tests/test_f1micro_orc_analise.py": "H2.1 — ROADMAP 2.5",
    "tests/test_f1sentiment_orc_analise.py": "H2.2 — ROADMAP 2.1",
    "tests/test_f1_indicators_parity.py": "H2.3 — ROADMAP 2.2b",
    "tests/test_f1_dxy_constante.py": "H2.4 — ROADMAP 2.6",
    "tests/test_pipeline_artifacts.py": "H3.1 — ROADMAP 3.1-3.4",
    "tests/test_pipeline_atomic_write.py": "H3.2 — ROADMAP 3.3",
    "tests/test_ranking_deterministic.py": "H4.1 — ROADMAP 4.1",
    "tests/test_ranking_fonte.py": "H4.2 — ROADMAP 4.2",
    "tests/test_gatilho_s1.py": "H4.5.1 — ROADMAP 4.5.2",
    "tests/test_gatilho_s2.py": "H4.5.2 — ROADMAP 4.5.3",
    "tests/test_slot_tracker.py": "H5.1 — ROADMAP 5.0",
    "tests/test_oco_bracket.py": "H5.2 — ROADMAP 5.2",
    "tests/test_dryrun_s1_s2.py": "H5.3 — ROADMAP 5.1",
    "tests/test_mcp_retry.py": "H5.4 — ROADMAP 5.3",
    "tests/test_timeout_unificado.py": "H5.5 — ROADMAP 5.0b",
    "tests/test_replay_fidelidade.py": "H6.1 — ROADMAP 6.1",
    "tests/test_replay_parciais.py": "H6.2 — ROADMAP 6.1b",
    "tests/test_previsto_realizado.py": "H6.3 — ROADMAP 6.2",
    "tests/test_dashboard_contract.py": "HX.1 — ROADMAP 1.7",
    "tests/test_encoding_regression.py": "HX.2 — R-ASCII-OUT",
}
# Entry points: nao precisam de referencia inbound.
ENTRY_POINTS = {"run.py", "gates.sh"}

# Roots externos onde um arquivo citado pelo INDEX pode legitimamente morar.
OTHER_ROOTS = [REPO / "10.0_ui_dash", REPO / "99_archive"]

EXIT = 0


def fail(msg: str) -> None:
    global EXIT
    print(f"  [ERR] {msg}")
    EXIT = 1


def ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _excluded(p: Path) -> bool:
    return any(part in EXCLUDE_PARTS for part in p.parts)


def read_utf8(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# (a) Indices concorrentes
# ---------------------------------------------------------------------------
print("=== (a) INDICES CONCORRENTES ===")
if not INDEX_PATH.exists():
    fail("specs/INDEX.md NAO EXISTE")
    sys.exit(1)
index_content = read_utf8(INDEX_PATH)

if BLUEPRINT_INDEX.exists():
    bp = read_utf8(BLUEPRINT_INDEX)
    if "SSOT" not in bp or "specs/INDEX.md" not in bp:
        fail("blueprint/INDEX.md e indice paralelo, nao ponteiro")
    else:
        ok("blueprint/INDEX.md e ponteiro (correto)")
for oi in ROOT.rglob("INDEX.md"):
    if oi not in (INDEX_PATH, BLUEPRINT_INDEX) and not _excluded(oi):
        fail(f"Indice duplicado: {oi.relative_to(ROOT)}")
if EXIT == 0:
    ok("nenhum indice duplicado")

# ---------------------------------------------------------------------------
# Inventario do disco
# ---------------------------------------------------------------------------
disk_files: list[Path] = []
for f in sorted(ROOT.rglob("*")):
    if f.is_dir() or _excluded(f):
        continue
    if f == BLUEPRINT_INDEX:
        continue
    if f.suffix in INDEXABLE_EXT:
        disk_files.append(f)

py_files = [f for f in disk_files if f.suffix == ".py"]

# ---------------------------------------------------------------------------
# (b) Disco -> INDEX (todo arquivo indexavel esta citado?)
# ---------------------------------------------------------------------------
print("\n=== (b) DISCO -> INDEX ===")
# Build set of filenames from INDEX (plain text + backtick + table references)
index_filenames: set[str] = set()
# Plain text: f.name in index_content catches most cases
# Backtick: `filename.py` or `path/filename.py`
for m in re.finditer(r'`([^`]+\.(?:py|md|yaml|json|sh|txt|toml))`', index_content):
    fname = Path(m.group(1)).name
    index_filenames.add(fname)
    index_filenames.add(m.group(1))
# Table rows without backticks: | filename.py | ...
for m in re.finditer(r'\|\s*([A-Za-z0-9_/-]+\.(?:py|md|yaml|json|sh|txt|toml))\s*\|', index_content):
    fname = Path(m.group(1)).name
    index_filenames.add(fname)

not_in_index = [
    str(f.relative_to(ROOT)) for f in disk_files
    if (f.name not in index_content
        and f.name not in index_filenames
        and str(f.relative_to(ROOT)) not in index_filenames)
]
# Filter allowlisted orphans (normalize path separators)
not_in_index = [nf for nf in not_in_index if nf.replace("\\", "/") not in ORPHAN_ALLOWLIST]
if not_in_index:
    for nf in not_in_index:
        fail(f"NAO INDEXADO: {nf}")
else:
    ok(f"todos {len(disk_files)} arquivos do disco citados no INDEX")

# ---------------------------------------------------------------------------
# (b2) INDEX -> disco (entradas stale)
# ---------------------------------------------------------------------------
print("\n=== (b2) INDEX -> DISCO (stale) ===")
cited = set(re.findall(r"`([A-Za-z0-9_\-./]+\.(?:py|md|yaml|json|sh|txt|toml))`", index_content))
disk_names = {f.name for f in disk_files}
stale: list[str] = []
for entry in sorted(cited):
    name = Path(entry).name
    if name in disk_names:
        continue
    # citado com path relativo pode existir em dir EXCLUIDO do scan (ex.: logs/
    # index_graph.json, artefato runtime documentado) — existencia real conta
    if (ROOT / entry).exists():
        continue
    # arquivo pode morar legitimamente em outro root (dashboard, arquivo morto)
    found_elsewhere = any(
        any(r.rglob(name)) for r in OTHER_ROOTS if r.exists()
    )
    if not found_elsewhere:
        if entry in STALE_ALLOWLIST:
            ok(f"STALE planejado: {entry} — {STALE_ALLOWLIST[entry]}")
        else:
            stale.append(entry)
if stale:
    for s_ in stale:
        fail(f"STALE no INDEX (nao existe em app/10.0_ui_dash/99_archive): {s_}")
else:
    ok(f"{len(cited)} arquivos citados no INDEX existem (app ou roots legitimos)")

# ---------------------------------------------------------------------------
# (c) GRAFO DE REFERENCIAS (dotted-import + string + nome de arquivo)
# ---------------------------------------------------------------------------
print("\n=== (c) GRAFO DE REFERENCIAS (orfaos reais) ===")


def module_key(f: Path) -> str:
    rel = f.relative_to(ROOT)
    if rel.name == "__init__.py":
        return ".".join(rel.parts[:-1])
    return ".".join(rel.parts)[: -len(".py")]


keys = {module_key(f): f for f in py_files}
texts: dict[Path, str] = {f: read_utf8(f) for f in py_files}

# Fontes extras de referencia: gates.sh + o dashboard (10.0_ui_dash importa
# orc_dashboard/_micro/_sentiment/orc_ranking dinamicamente — wire legitimo).
extra_sources: dict[str, str] = {}
gates_sh = ROOT / "gates.sh"
if gates_sh.exists():
    extra_sources["gates.sh"] = read_utf8(gates_sh)
dash_root = REPO / "10.0_ui_dash"
if dash_root.exists():
    for dp in sorted(dash_root.rglob("*.py")):
        if any(x in dp.parts for x in ("__pycache__", "node_modules", "react-dashboard")):
            continue
        extra_sources[f"10.0_ui_dash/{dp.relative_to(dash_root)}"] = read_utf8(dp)

refs: dict[str, set[str]] = {k: set() for k in keys}
for k, target in keys.items():
    fname = target.name
    for src, text in texts.items():
        if src == target:
            continue
        src_rel = str(src.relative_to(ROOT)).replace("\\", "/")
        if (k and re.search(rf"(?<![\w.]){re.escape(k)}(?![\w])", text)) or (
            fname != "__init__.py" and fname in text
        ):
            refs[k].add(src_rel)
    for sname, text in extra_sources.items():
        if k in text or fname in text:
            refs[k].add(sname)

orphans: list[str] = []
for k, f in sorted(keys.items()):
    rel = str(f.relative_to(ROOT)).replace("\\", "/")
    if f.name in ENTRY_POINTS or rel in ENTRY_POINTS:
        continue
    if rel.startswith(("tests/", "gates/")):
        continue
    if not refs.get(k):
        note = ORPHAN_ALLOWLIST.get(rel) or ORPHAN_ALLOWLIST.get(f.name)
        if note:
            print(f"  [ALLOW] orfao rastreado: {rel} ({note})")
        else:
            orphans.append(rel)
if orphans:
    for o in orphans:
        fail(f"ORFAO real (zero referencias e fora da allowlist): {o}")
else:
    ok(f"grafo com {len(keys)} modulos; nenhum orfao fora da allowlist")

# ---------------------------------------------------------------------------
# (d) Tools MCP usadas no codigo estao no contrato? (delega ao G10)
# ---------------------------------------------------------------------------
print("\n=== (d) TOOLS MCP -> CONTRATO (G10) ===")
mcp_client = ROOT / "utils" / "mcp_client.py"
mcp_snapshot = ROOT / "gates" / "mcp_tools_snapshot.json"
tools_in_code: set[str] = set()
tools_in_contract: set[str] = set()
if mcp_client.exists():
    tools_in_code = set(re.findall(r'call_tool\(\s*"([a-z_]+)"', read_utf8(mcp_client)))
if mcp_snapshot.exists():
    import json as _json
    snapshot = _json.loads(mcp_snapshot.read_text(encoding="utf-8"))
    tools_data = snapshot.get("tools", {})
    if isinstance(tools_data, dict):
        tools_in_contract = set(tools_data.keys())
    elif isinstance(tools_data, list):
        tools_in_contract = {t.get("name", "") for t in tools_data}
missing_tools = sorted(tools_in_code - tools_in_contract)
extra_tools = sorted(tools_in_contract - tools_in_code)
if missing_tools:
    for t in missing_tools:
        fail(f"tool MCP no codigo mas fora do contrato: {t}")
else:
    ok(f"todas {len(tools_in_code)} tools MCP batem com contrato ({len(tools_in_contract)} no snapshot)")

# ---------------------------------------------------------------------------
# Dump do grafo (maquina-legivel) + resultado
# ---------------------------------------------------------------------------
try:
    GRAPH_OUT.parent.mkdir(exist_ok=True)
    GRAPH_OUT.write_text(
        json.dumps(
            {
                "modules": {k: sorted(v) for k, v in sorted(refs.items())},
                "orphan_allowlist": ORPHAN_ALLOWLIST,
                "tools_in_code": sorted(tools_in_code),
                "files_indexed": len(disk_files),
            },
            indent=1,
            ensure_ascii=True,
        ),
        encoding="utf-8",
    )
except OSError as e:
    print(f"  [WARN-IO] nao gravou {GRAPH_OUT.name}: {e}", file=sys.stderr)

print(f"\n{'=' * 50}")
if EXIT == 0:
    print("[OK] G8 INDEX-SYNC v0.3: PASS")
    print(f"   {len(disk_files)} arquivos | {len(py_files)} .py | "
          f"{len(tools_in_code)} tools MCP | grafo: logs/index_graph.json")
    sys.exit(0)
print("[ERR] G8 INDEX-SYNC v0.3: FAIL")
sys.exit(1)
