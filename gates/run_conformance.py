#!/usr/bin/env python3
"""CONFORMANCE GATES G11-G14 -- cTrader V2 standalone (AUDITADO 2026-07-23)
R-USE: AST + regex ancorado (R-AST, R-PARSER). Zero WARN (R-WARN-FORBIDDEN).
Exits !=0 on any ERR. Allowlists congeladas, cada entrada com ROADMAP item.
Uso: gates/run_conformance.py --check header|ddd|security|robustez|all
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# ═══ ENCODING: stdout/stderr UTF-8 (Windows cp1252-safe) ═══
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = ROOT / "specs"
INDEX_PATH = SPECS_DIR / "INDEX.md"
ROADMAP_PATH = SPECS_DIR / "ROADMAP.md"

# ══════════════════════════════════════════════════════════════
# ALLOWLISTS CONGELADAS (formato G8 v0.3: path -> "motivo -- ROADMAP <item>")
# ══════════════════════════════════════════════════════════════

# G12: GOD objects existentes (nenhum GOD novo permitido)
ALLOWLIST_GOD: dict[str, str] = {
    "f0_collector/backtest_simulator.py": "Simulador legado VBT > 200L -- ROADMAP 6.1",
    "f0_collector/orc_coleta.py": "F0 PONTA DE LANCA — dados+ordens MCP (247L) -- ROADMAP 1.6",
    "f0_collector/backfill_orc_coleta.py": "Backfill 2a gap-aware (261L, satelite F0, roda 1x/dia) -- ROADMAP S2.5-BF",
    "utils/mcp_client.py": "Gateway MCP unico -- ROADMAP 1.5",
    "utils/orc_dashboard.py": "Hub dashboard -- ROADMAP 1.7",
    "utils/orc_metricas.py": "Orquestrador 29 metricas (nao toca MCP) -- ROADMAP 1.7",
    "tests/test_conformancegates_orc_execucao.py": "Fixture suite G11-G14 -- ROADMAP 0.7",
}

# G12: Orquestradores com MCP direto (congelados, ROADMAP 2.2)
ALLOWLIST_ORQ_MCP: dict[str, str] = {
    "f4_executor/orc_ordens.py": "Ordens OCO/trail/BE via MCP -- ROADMAP 2.2",
    "f4_executor/orc_execucao.py": "Executor mutacoes MCP para mutacoes (150L, nao GOD) -- ROADMAP 2.2",
    "f0_collector/orc_coleta.py": "F0 PONTA DE LANCA MCP (ROADMAP 1.6) -- ROADMAP 1.7",
}


# G12: Orquestradores com SQLite direto (apresentacao/metricas — legitimo)
ALLOWLIST_ORQ_SQLITE: dict[str, str] = {
    "utils/orc_dashboard.py": "Hub dashboard — consulta trades.db -- ROADMAP 1.7",
    "utils/orc_metricas.py": "Orquestrador metricas — consulta trades.db -- ROADMAP 1.7",
    "utils/orc_health_fases.py": "Validador por fase — SELECT COUNT read-only -- ROADMAP S33",
}

# G13: Secrets em config.yaml (demo token)
ALLOWLIST_SECRETS: dict[str, str] = {
    "config.yaml": "Bearer token demo cTrader -- ROADMAP D.6",
}

# G13: Tools mutantes tambem no gateway (mcp_client)
MUTANT_TOOLS = {"create_order", "close_position", "cancel_order", "amend_position", "amend_order"}
MUTANT_ALLOWED_DIRS = {"f4_executor", "utils", "f0_collector"}  # F0 = order hub (ROADMAP 5.1)

# G14: Silent-fail justificado (falso-positivo com tupla de erro)
ALLOWLIST_SILENT_FAIL: dict[str, str] = {
    "utils/schema_validator.py": "Retorna (bool, str) como tupla de erro -- ROADMAP D.7",
    "tests/test_conformancegates_orc_execucao.py": "Fixtures que testam o proprio gate de silent-fail -- ROADMAP 0.7",
    "utils/orc_dashboard.py": "Pre-existente, corrigido no ROADMAP 1.7 -- ROADMAP 1.7",
}

# Diretorios excluidos de todos os gates
EXCLUDE_DIRS = {
    "__pycache__", ".git", ".venv", "node_modules",
    "handlers", "adapters_parsers", "ctrader-skills-official",
    "gates", "tests",  # fixtures intencionais não devem ser gateadas
    "legacy", "99_archive",  # fora do INDEX
}

# ══════════════════════════════════════════════════════════════
# UTILITARIOS
# ══════════════════════════════════════════════════════════════

EXIT_CODE = 0


def err(gate: str, msg: str) -> None:
    global EXIT_CODE
    print(f"  [ERR] [{gate}] {msg}")
    EXIT_CODE = 1


def ok(gate: str, msg: str) -> None:
    print(f"  [OK] [{gate}] {msg}")


def allow(gate: str, path: str, reason: str) -> None:
    print(f"  [ALLOW] [{gate}] {path} -- {reason}")


def read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def get_py_files(min_lines: int = 0) -> list[Path]:
    files = []
    for f in sorted(ROOT.rglob("*.py")):
        parts = set(f.relative_to(ROOT).parts)
        if parts & EXCLUDE_DIRS:
            continue
        if any(x in str(f) for x in ["__pycache__", ".pyc", "_archive"]):
            continue
        try:
            lines = len(read_file(f).split("\n"))
        except Exception:
            continue
        if lines < min_lines:
            continue
        files.append(f)
    return files


def get_spec_files() -> list[Path]:
    return sorted(SPECS_DIR.glob("*.md"))


def load_index_data() -> dict:
    """Extrai SPEC IDs e mapeamento SPEC->arquivo do INDEX.md.

    Suporta formatos:
      || S41 | orc_bloco1.md |
      ||| S2.5 | orc_coleta.md |   (sub-specs)
      `orc_bloco1.py`               (backtick references)
    """
    if not INDEX_PATH.exists():
        return {"specs": set(), "files": set(), "spec_files": {}}

    content = read_file(INDEX_PATH)

    # SPEC IDs: captura S# de headers e tabelas
    specs = set(re.findall(r'SPEC\s+([A-Za-z0-9_.-]+)', content))
    # Tabela: || S41 | arquivo.md |  ou  ||| S2.5 | arquivo.md |
    specs |= set(re.findall(r'\|\|\s*\|?\s*\|?\s*([A-Za-z0-9_.-]+)\s*\|', content))

    # Arquivos referenciados
    files = set()
    for m in re.finditer(r'`([^`]+\.(?:py|md|yaml|json|sh))`', content):
        files.add(m.group(1))

    # Mapeamento SPEC S# -> arquivo spec
    # Formatos aceitos:
    #   || S41 | orc_bloco1.md |
    #   ||| S2.5 | orc_coleta.md |
    #   || S41 | orc_bloco1.md (v3.0) |
    spec_files = {}
    for line in content.splitlines():
        # Match: || [|] S# | filename[.md] [| ...]
        m = re.match(r'\|\|?\s*\|?\s*\|?\s*([A-Za-z0-9_.-]+)\s*\|\s*([A-Za-z0-9_.-]+\.[a-z]+)', line)
        if m:
            sid = m.group(1)
            fname = m.group(2)
            if fname.endswith('.md'):
                spec_files[sid] = fname

    return {"specs": specs, "files": files, "spec_files": spec_files}


# ══════════════════════════════════════════════════════════════
# G11 -- HEADER-SPEC
# ══════════════════════════════════════════════════════════════

def check_g11_header() -> None:
    print()
    print("=" * 50)
    print(" G11 -- HEADER-SPEC")
    print("=" * 50)

    index_data = load_index_data()
    valid_specs = index_data["specs"]
    py_ok = 0
    spec_ok = 0

    # .py >50L
    for pf in get_py_files(min_lines=50):
        content = read_file(pf)
        rel = str(pf.relative_to(ROOT)).replace("\\", "/")

        docstring = ""
        try:
            tree = ast.parse(content)
            docstring = ast.get_docstring(tree) or ""
        except SyntaxError:
            err("G11", f"{rel}: SyntaxError -- nao parseavel")
            continue

        if not docstring:
            err("G11", f"{rel}: sem docstring de modulo")
            continue

        has_proposito = bool(re.search(r'PROPOSITO\s*:', docstring, re.IGNORECASE))
        has_spec = bool(re.search(r'SPEC\s*:', docstring))
        has_roadmap = bool(re.search(r'ROADMAP\s*:', docstring))

        spec_valid = False
        if has_spec:
            spec_match = re.search(r'SPEC\s*:\s*(S\d+(?:\.\d+)?)', docstring)
            if spec_match:
                spec_id = spec_match.group(1)
                spec_valid = spec_id in valid_specs
                # G11+: verifica se arquivo do spec EXISTE no disco (R-USE)
                spec_dir = ROOT / "specs"
                # Lookup via INDEX data: spec_id -> actual filename
                spec_filename = index_data.get("spec_files", {}).get(spec_id)
                if spec_filename:
                    spec_path = spec_dir / spec_filename
                    if not spec_path.exists():
                        err("G11", f"{rel}: SPEC {spec_id} -> {spec_filename} NAO encontrado em specs/")
                else:
                    # Fallback: glob match
                    spec_files = list(spec_dir.glob(f"{spec_id}*.md")) if spec_dir.exists() else []
                    if not spec_files:
                        err("G11", f"{rel}: SPEC {spec_id}: arquivo .md NAO existe em specs/ (nem no INDEX)")

        if not has_proposito:
            err("G11", f"{rel}: docstring sem PROPOSITO:")
        if not has_spec:
            err("G11", f"{rel}: docstring sem SPEC:")
        elif not spec_valid:
            err("G11", f"{rel}: SPEC nao encontrada no INDEX.md")
        if not has_roadmap:
            err("G11", f"{rel}: docstring sem ROADMAP:")

        if has_proposito and has_spec and has_roadmap:
            py_ok += 1

    # .md specs
    for sf in get_spec_files():
        content = read_file(sf)
        name = sf.name

        has_spec_id = bool(re.search(r'SPEC\s+S\d+', content[:300]))
        has_version = bool(re.search(r'Vers.o\s*:', content[:300], re.IGNORECASE))
        has_wire = bool(re.search(r'Wire\s*:', content[:300], re.IGNORECASE))
        has_status = bool(re.search(r'Status\s*:', content[:300], re.IGNORECASE))

        if not has_spec_id:
            err("G11", f"specs/{name}: sem SPEC S# no titulo")
        if not has_version:
            err("G11", f"specs/{name}: sem VERSION")
        if not has_wire:
            err("G11", f"specs/{name}: sem WIRE")
        if not has_status:
            err("G11", f"specs/{name}: sem STATUS")

        if has_spec_id and has_version and has_wire and has_status:
            spec_ok += 1

    ok("G11", f"Python: {py_ok}/{sum(1 for _ in get_py_files(min_lines=50))} OK | Specs: {spec_ok}/{len(get_spec_files())} OK")


# ══════════════════════════════════════════════════════════════
# G12 -- DDD
# ══════════════════════════════════════════════════════════════

def check_g12_ddd() -> None:
    print()
    print("=" * 50)
    print(" G12 -- DDD")
    print("=" * 50)

    clean_count = 0
    god_new = 0
    god_allow = 0

    for pf in get_py_files():
        content = read_file(pf)
        lines = len(content.split("\n"))
        rel = str(pf.relative_to(ROOT)).replace("\\", "/")

        is_orc = pf.name.startswith("orc_")  # orquestrador = orc_<funcao>.py (satelites: <nome>_orc_<pai>.py)
        max_lines = 350 if is_orc else 200

        if lines > max_lines:
            if rel in ALLOWLIST_GOD:
                allow("G12", rel, ALLOWLIST_GOD[rel])
                god_allow += 1
            else:
                err("G12", f"{rel}: GOD object ({lines}L > {max_lines}L)")
                god_new += 1

        # >150L sem docstring
        if lines > 150:
            try:
                tree = ast.parse(content)
                doc = ast.get_docstring(tree)
                if not doc:
                    err("G12", f"{rel}: >150L sem docstring de modulo (R117)")
            except SyntaxError:
                pass

        # Orquestrador com MCP direto
        if is_orc:
            has_mcp = bool(re.search(
                r'mcp_client\.\w+\(|get_balance\(|get_spot|get_positions\(|create_order|close_position',
                content))
            has_sql = bool(re.search(r'sqlite3\.connect|\.execute\(|pd\.read_sql', content))
            if (has_mcp or has_sql) and rel not in ALLOWLIST_ORQ_MCP:
                if rel not in ALLOWLIST_ORQ_SQLITE:
                    err("G12", f"{rel}: orquestrador com {'MCP' if has_mcp else 'SQLite'} direto")
            elif has_mcp or has_sql:
                allow("G12", rel, ALLOWLIST_ORQ_MCP[rel])

        if lines <= max_lines or rel in ALLOWLIST_GOD:
            clean_count += 1

    ok("G12", f"{clean_count} OK, {god_allow} GOD(s) allowlist, {god_new} GOD(s) NOVO(S)")


# ══════════════════════════════════════════════════════════════
# G13 -- SEGURANCA
# ══════════════════════════════════════════════════════════════

def check_g13_security() -> None:
    print()
    print("=" * 50)
    print(" G13 -- SEGURANCA")
    print("=" * 50)

    SECRET_PATTERNS = [
        (r'Bearer\s+[A-Za-z0-9_\-\.]{20,}', "Bearer token"),
        (r'api_key\s*=\s*["\'][A-Za-z0-9_\-]{10,}["\']', "API key hardcoded"),
        (r'sk-[A-Za-z0-9]{20,}', "OpenAI/DeepSeek key"),
        (r'[A-Za-z0-9+/]{40,}={0,2}', "Base64 longo (possivel token)"),
    ]

    secret_ok = 0
    secret_allow = 0
    for pf in get_py_files():
        content = read_file(pf)
        rel = str(pf.relative_to(ROOT)).replace("\\", "/")
        if rel in ALLOWLIST_SECRETS:
            allow("G13", rel, ALLOWLIST_SECRETS[rel])
            secret_allow += 1
            continue
        found = False
        for pattern, desc in SECRET_PATTERNS:
            if re.search(pattern, content):
                err("G13", f"{rel}: possivel {desc}")
                found = True
                break
        if not found:
            secret_ok += 1

    # .gitignore
    gitignore = ROOT.parent.parent / ".gitignore"
    if gitignore.exists():
        gi_content = read_file(gitignore)
        for required in [".env", "*.db", "__pycache__"]:
            if required not in gi_content:
                err("G13", f".gitignore: falta '{required}'")
        ok("G13", ".gitignore OK")
    else:
        err("G13", ".gitignore nao encontrado")

    # Call-site allowlist
    mutant_ok = 0
    mutant_viol = 0
    for pf in get_py_files():
        content = read_file(pf)
        rel = str(pf.relative_to(ROOT)).replace("\\", "/")
        parent_dir = rel.split("/")[0] if "/" in rel else "."

        found_tool = None
        for tool in MUTANT_TOOLS:
            if tool in content:
                found_tool = tool
                break

        if found_tool and parent_dir not in MUTANT_ALLOWED_DIRS:
            err("G13", f"{rel}: usa {found_tool}() fora de f4_executor/")
            mutant_viol += 1
        elif found_tool:
            mutant_ok += 1
        # else: arquivo sem tool mutante -- nao conta

    ok("G13", f"Secrets: {secret_ok} OK, {secret_allow} allowlist | Mutant tools: {mutant_ok} OK, {mutant_viol} viol")


# ══════════════════════════════════════════════════════════════
# G14 -- ROBUSTEZ-FORMA
# ══════════════════════════════════════════════════════════════

def check_g14_robustez() -> None:
    print()
    print("=" * 50)
    print(" G14 -- ROBUSTEZ-FORMA")
    print("=" * 50)

    robustez_ok = 0
    total = 0

    for pf in get_py_files():
        content = read_file(pf)
        rel = str(pf.relative_to(ROOT)).replace("\\", "/")
        total += 1
        issues = []

        # Bare except
        if re.search(r'^\s*except\s*:', content, re.MULTILINE):
            issues.append("bare except:")

        # Silent fail: return False/None sem [ERRO] em funcao >10L
        in_func = False
        func_lines = 0
        func_has_error = False
        for line in content.split("\n"):
            if re.match(r'\s*def\s+\w+', line):
                in_func = True
                func_lines = 0
                func_has_error = False
                continue
            if in_func:
                if line.strip() and line[0] not in (" ", "\t"):
                    in_func = False
                    continue
                func_lines += 1
                if re.search(r'\[ERRO\]|stderr|logger\.(error|exception)|raise\s+\w+Error', line):
                    func_has_error = True
            if in_func and func_lines > 10 and re.match(r'\s+return\s+(False|None)\s*$', line) and not func_has_error:
                    allow_key = f"{rel}:{line.strip()[:40]}"
                    if allow_key not in ALLOWLIST_SILENT_FAIL and rel not in ALLOWLIST_SILENT_FAIL:
                        issues.append("return False/None sem [ERRO] em funcao >10L")
                    break

        # Acentos em identificadores (AST, nao comentarios)
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.Name) and node.id and any(ord(c) > 127 for c in node.id):
                        issues.append(f"acento em identificador: {node.id}")
                        break
                if isinstance(node, ast.FunctionDef) and any(ord(c) > 127 for c in node.name):
                    issues.append(f"acento em funcao: {node.name}")
                    break
        except SyntaxError:
            pass

        # ASCII-only em print/log (R-ASCII-OUT)
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                # print(...) ou logger.info/warning/error/debug(...)
                is_print = (isinstance(node.func, ast.Name) and node.func.id == "print")
                is_logger = (isinstance(node.func, ast.Attribute) and
                             isinstance(node.func.value, ast.Name) and
                             node.func.value.id == "logger" and
                             node.func.attr in ("info", "warning", "error", "debug", "exception", "critical"))
                if not is_print and not is_logger:
                    continue
                for arg in node.args:
                    if (isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                            and any(ord(c) > 127 for c in arg.value)):
                            func_name = "print" if is_print else f"logger.{node.func.attr}"
                            issues.append(f"caractere nao-ASCII em {func_name}() -- use [OK]/[ERR]/[ALLOW]")
                            break
                if issues and issues[-1].startswith("caractere nao-ASCII"):
                    break
        except SyntaxError:
            pass

        # Path absoluto hardcoded (exceto bootstrap)
        if re.search(r'["\'](C:\\|/c/|C:/)', content) and not re.search(r'Path\(__file__\)', content):
            issues.append("path absoluto hardcoded (C:\\ ou /c/)")

        # Termo V43 proibido
        v43_terms = ["Eixo 5", "Vector-Sig", "V43_", "NEOCTRADER_LEGACY"]
        for term in v43_terms:
            if term in content and "_archive" not in rel:
                issues.append(f"termo V43 proibido: {term}")
                break

        if issues:
            for issue in issues[:3]:
                err("G14", f"{rel}: {issue}")
        else:
            robustez_ok += 1

    ok("G14", f"Robustez: {robustez_ok}/{total} arquivos OK")


# ══════════════════════════════════════════════════════════════
# G15 — SPEC DRIFT (Orfaos + Duplicatas)
# ══════════════════════════════════════════════════════════════

def check_g15_spec_drift() -> None:
    """G15: Valida integridade do ecossistema de specs.

    Checks:
      1. Orfaos: specs/*.md nao referenciados no INDEX
      2. Duplicatas: mesmo SPEC ID em mais de um arquivo
    """
    print()
    print("=" * 50)
    print(" G15 -- SPEC DRIFT (Orfaos + Duplicatas)")
    print("=" * 50)

    if not SPECS_DIR.exists():
        err("G15", "diretorio specs/ nao encontrado")
        return

    index_data = load_index_data()
    index_spec_files = set(index_data["spec_files"].values())
    # INDEX e ROADMAP sao auto-referenciais
    index_spec_files.add("INDEX.md")
    index_spec_files.add("ROADMAP.md")

    spec_files_on_disk = sorted(f for f in SPECS_DIR.glob("*.md"))

    # -- 1. Orfaos --
    orphans = []
    for sf in spec_files_on_disk:
        if sf.name not in index_spec_files:
            orphans.append(sf.name)

    if orphans:
        for name in orphans:
            err("G15", f"ORFAO: specs/{name} nao referenciado no INDEX.md")
    else:
        ok("G15-ORFAOS", f"{len(spec_files_on_disk)} specs no INDEX — 0 orfas")

    # -- 2. Duplicatas --
    spec_id_to_files = {}
    for sf in spec_files_on_disk:
        content_sf = read_file(sf)
        m = re.search(r'SPEC[\s:]+(S\d+(?:\.\d+)?(?:-[A-Z]+)?)', content_sf[:300])
        if m:
            sid = m.group(1)
            spec_id_to_files.setdefault(sid, []).append(sf.name)

    dupes = {sid: files for sid, files in spec_id_to_files.items() if len(files) > 1}
    if dupes:
        for sid, files in dupes.items():
            err("G15", f"DUPLICATA: SPEC {sid} em {len(files)} arquivos: {', '.join(files)}")
    else:
        ok("G15-DUPES", f"{len(spec_id_to_files)} SPEC IDs unicos — 0 duplicatas")


# ══════════════════════════════════════════════════════════════
# MAIN# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

CHECKS = {
    "header": check_g11_header,
    "ddd": check_g12_ddd,
    "security": check_g13_security,
    "robustez": check_g14_robustez,
    "drift": check_g15_spec_drift,
}


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Conformance Gates G11-G14")
    p.add_argument("--check", choices=["header", "ddd", "security", "robustez", "drift", "all"],
                   default="all")
    p.add_argument("--dir", default=None, help="Diretório alvo (default: diretório do app)")
    args = p.parse_args()

    global ROOT, SPECS_DIR, INDEX_PATH, ROADMAP_PATH
    if args.dir:
        ROOT = Path(args.dir)
        SPECS_DIR = ROOT / "specs"
        INDEX_PATH = SPECS_DIR / "INDEX.md"
        ROADMAP_PATH = SPECS_DIR / "ROADMAP.md"

    if args.check == "all":
        for fn in CHECKS.values():
            fn()
    else:
        CHECKS[args.check]()

    print()
    print("=" * 50)
    if EXIT_CODE == 0:
        print("[OK] CONFORMANCE G11-G14: PASS")
    else:
        print(f"[ERR] CONFORMANCE G11-G14: FAIL ({EXIT_CODE} erros)")
    return EXIT_CODE


if __name__ == "__main__":
    sys.exit(main())
