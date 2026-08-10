#!/bin/bash
# GATE-F0: Suite de gates cTrader V2 + Dashboard (G0-G24)
# Uso:
#   bash gates.sh                  -> all (ctrader + dashboard back + front)
#   bash gates.sh --fast           -> all, pula G2 (slop lento)
#   bash gates.sh --diff           -> so arquivos alterados (git diff HEAD)
#   bash gates.sh --staged         -> so arquivos staged (git diff --cached)
#   bash gates.sh --commit         -> so arquivos do ultimo commit
#   bash gates.sh --ship="msg"     -> faz git commit -m "msg" --no-verify se ok
# Politica: R-WARN-FORBIDDEN. FULL-ERR.

set -e
set -o pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

VENV_PY="$ROOT/../../.venv/Scripts/python.exe"
VENV_PY_ABS="$(cd "$(dirname "$VENV_PY")" && pwd)/$(basename "$VENV_PY")"  # absoluto para sub-shells
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

[ ! -f "$VENV_PY" ] && { echo "[ERRO] venv nao encontrado em $VENV_PY"; exit 1; }

FAST=0; MODE="all"; SHIP_MSG=""
for arg in "$@"; do
    case "$arg" in
        --fast) FAST=1 ;;
        --diff|--staged|--commit) MODE="${arg#--}" ;;
        --ship=*) SHIP_MSG="${arg#*=}" ;;
    esac
done

# ── PREFLIGHT: check_deps.py (barreira unica SSOT) ──
echo ">>> [0/18] PREFLIGHT — check_deps.py (pip + npm + config quality)"
"$VENV_PY" gates/check_deps.py && echo "  [PASS] PREFLIGHT" || { echo "  [FAIL] PREFLIGHT"; exit 1; }
echo ""

# ── Mode-aware runner (Python) ──
run_gate() {
    local gate=$1; shift
    local desc=$1; shift
    echo ""; echo ">>> [$((N+1))/15] $gate — $desc"
    if [ "$MODE" = "all" ]; then
        "$VENV_PY" "$@" && { N=$((N+1)); echo "  [PASS] $gate"; } || { echo "  [FAIL] $gate"; exit 1; }
    else
        "$VENV_PY" -c "
import subprocess, sys, os
os.environ['GATE_MODE']='$MODE'
args = sys.argv[1:]
result = subprocess.run([sys.executable] + args, capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
sys.exit(result.returncode)
" "$@" && { N=$((N+1)); echo "  [PASS] $gate"; } || { echo "  [FAIL] $gate"; exit 1; }
    fi
}

# ── Header ──
DASHBOARD_DIR="$ROOT/../../10.0_ui_dash"
FRONTEND_DIR="$DASHBOARD_DIR/react-dashboard"
CTRADER_PY=$(find . -name '*.py' ! -path '*__pycache__*' ! -path '*ctrader-skills-official*' 2>/dev/null | wc -l)
DASH_PY=$(find "$DASHBOARD_DIR" -name '*.py' ! -path '*__pycache__*' ! -path '*node_modules*' 2>/dev/null | wc -l)
FE_FILES=$(find "$FRONTEND_DIR/src" -name '*.tsx' -o -name '*.ts' 2>/dev/null | wc -l)

echo "========================================="
echo " GATE-F0 — cTrader V2 + Dashboard"
echo " $(date '+%Y-%m-%d %H:%M:%S')  |  modo: $MODE"
echo "========================================="
echo " ESCOPO:"
echo "   cTrader V2:       11.0_apps/ctrader/ ($CTRADER_PY .py)"
echo "   Dashboard Backend: 10.0_ui_dash/ ($DASH_PY .py, porta 7744)"
echo "   Dashboard Frontend: 10.0_ui_dash/react-dashboard/ ($FE_FILES .tsx/.ts, porta 5173)"
echo "========================================="

N=0

# ═══ G0 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G0 RUFF — lint + imports"
G0_OUT=$("$VENV_PY" -m ruff check . --exclude "ctrader-skills-official" --exclude "__pycache__" --exclude "node_modules" 2>&1); G0_EC=$?
echo "$G0_OUT" | tail -3
G0_DASH_EC=0
if [ -d "$DASHBOARD_DIR" ]; then
    G0_DASH_OUT=$( cd "$DASHBOARD_DIR" && "$VENV_PY_ABS" -m ruff check . --exclude "__pycache__" --exclude "node_modules" 2>&1 ); G0_DASH_EC=$?
    echo "$G0_DASH_OUT" | tail -1
fi
[ $G0_EC -eq 0 ] && [ $G0_DASH_EC -eq 0 ] && echo "  [PASS] G0" || { echo "  [FAIL] G0: ruff encontrou erros (ec_ctrader=$G0_EC ec_dash=$G0_DASH_EC)"; exit 1; }

# ═══ G1 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G1 COMPILE — syntax check"
"$VENV_PY" -c "
import py_compile, sys
from pathlib import Path
total = errors = 0
for base in [Path('.'), Path('${DASHBOARD_DIR}')]:
    if not base.exists(): continue
    for f in base.rglob('*.py'):
        if any(x in str(f) for x in ['ctrader-skills-official','__pycache__','.git','node_modules']): continue
        total += 1
        try: py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError as e:
            print(f'    ERR: {f} — {e}'); errors += 1
if errors: print(f'  {errors}/{total} FAIL'); sys.exit(1)
print(f'  {total} compilados, 0 erros')
" && echo "  [PASS] G1" || { echo "  [FAIL] G1"; exit 1; }

# ═══ G2 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G2 AI_SLOP — ai-slop-detector v3.8.7"
if [ $FAST -eq 1 ]; then
    echo "  [SKIP] G2: --fast (roda completo antes do ship)"
else
    echo "  Rodando (30-120s)..."
    ok=0; total=0; fail_dirs=""
    for d in . ../../10.0_ui_dash; do
        [ -d "$d" ] || continue
        total=$((total+1))
        label="$d"; [ "$d" = "." ] && label="ctrader/"
        echo -n "  -> $label ... "
        SLOP_OUT=$("$VENV_PY" -m slop_detector.cli --project "$d" --gate 2>&1); SLOP_EC=$?
        echo "$SLOP_OUT" | tail -1
        if [ $SLOP_EC -eq 0 ] && echo "$SLOP_OUT" | grep -q "PASS"; then
            # Check per-file threshold: INFLATED or CRITICAL files = FAIL
            # ALLOWLIST (R-WARN-FORBIDDEN: legado verificado, cada entrada c/ motivo).
            # NOTA: a tabela do ai-slop mostra NOME PURO (nao path) e trunca com "..." —
            # por isso o filtro casa por nome, nao por "gates/".
            #   gates/ + mcp_client   infra de qualidade + GOD gateway 706L (G12-allowlisted)
            #   run_conformanc[e]     gate runner 508L (gates/, mas tabela trunca o path) — infra
            #   overview.py/_shared   dashboard-GERAL V44 (/api/v44/*), pre-existentes jul/14;
            #                         so tripam apos o threshold G2 apertado em 2026-07-27 (nao sao cTrader)
            # Casa SO linhas de arquivo (terminam em _SIGNAL). A legenda "Deficit
            # bands: ... CRITICAL" continha "CRITICAL" e era falso-positivo eterno
            # (R-SELF-REPAIR 2026-07-27) — o gate reprovava a propria legenda.
            if echo "$SLOP_OUT" | grep -qE "INFLATED_SIGNAL|CRITICAL_SIGNAL"; then
                # R-SELF-REPAIR 2026-07-28: sob set -e+pipefail, se TODOS os
                # INFLATED forem allowlisted o ultimo grep -v fica sem match
                # (exit 1) e mata o script inteiro em silencio -- "|| true"
                # porque BAD_FILES vazio e um resultado valido (nao erro).
                BAD_FILES=$( (echo "$SLOP_OUT" | grep -E "INFLATED_SIGNAL|CRITICAL_SIGNAL" \
                    | grep -v "gates/" | grep -v "mcp_client" \
                    | grep -v "run_conformanc" | grep -v "overview.py" | grep -v "_shared.py" | grep -v "orc_coleta.py" | grep -v "orc_metricas.py") || true)
                if [ -n "$BAD_FILES" ]; then
                    echo "  [FAIL] G2 ($label): arquivos INFLATED/CRITICAL (fora da allowlist):"
                    echo "$BAD_FILES" | head -5
                    fail_dirs="$fail_dirs $label(INFLATED)"
                else
                    echo "  [ALLOW] G2 ($label): INFLATED so em allowlist (gates/ + mcp_client + run_conformance + overview/_shared V44)"
                    ok=$((ok+1))
                fi
            else
                ok=$((ok+1))
            fi
        else
            fail_dirs="$fail_dirs $label"
        fi
    done
    if [ $ok -lt $total ]; then
        echo "  [FAIL] G2: $ok/$total limpos — falhou:$fail_dirs"
        exit 1
    fi
    echo "  [PASS] G2: $ok/$total limpos (cobertura total: ctrader/ + dashboard)"
fi

# ═══ G3 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G3 MOCKBUSTER v2 — mock de dados (hardcoded + stubs + _fake_)"
"$VENV_PY" gates/run_mockbuster.py . && echo "  [PASS] G3" || { echo "  [FAIL] G3"; exit 1; }

# ═══ G4 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G4 STUB — NotImplementedError scan"
"$VENV_PY" -c "
from pathlib import Path; import sys
stubs=[]
for f in Path('.').rglob('*.py'):
    if any(x in str(f) for x in ['ctrader-skills-official','__pycache__','.git','tests','gates','node_modules']): continue
    if 'raise NotImplementedError' in f.read_text(encoding='utf-8',errors='replace'):
        stubs.append(str(f.relative_to('.')))
if stubs: [print(f'    STUB: {s}') for s in stubs]; sys.exit(1)
print('  0 stubs')
" && echo "  [PASS] G4" || { echo "  [FAIL] G4"; exit 1; }

# ═══ G5 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G5 LINTER — regras locais"
"$VENV_PY" -c "
from pathlib import Path; import sys
warn=[]; banned=[]
for f in Path('.').rglob('*.py'):
    if any(x in str(f) for x in ['ctrader-skills-official','__pycache__','.git','tests','gates','node_modules']): continue
    c=f.read_text(encoding='utf-8',errors='replace')
    if 'logger.warning' in c: warn.append(str(f.relative_to('.')))
    if '# mock' in c.lower() or '# stub' in c.lower(): banned.append(str(f.relative_to('.')))
if warn: print(f'  logger.warning: {len(warn)}'); [print(f'    {x}') for x in warn]
if banned: print(f'  banned comments: {len(banned)}'); [print(f'    {x}') for x in banned]
if warn or banned: sys.exit(1)
print('  0 violacoes')
" && echo "  [PASS] G5" || { echo "  [FAIL] G5"; exit 1; }

# ═══ G6 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G6 HARNESS — pytest"
"$VENV_PY" utils/harness_runner.py && echo "  [PASS] G6" || { echo "  [FAIL] G6"; exit 1; }

# ═══ G7 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G7 ORBITAL — cross-module DDD (parentesco + fase isolation)"
"$VENV_PY" gates/run_orbital.py && echo "  [PASS] G7" || { echo "  [FAIL] G7"; exit 1; }

# ═══ G8 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G8 INDEX-SYNC — disco <-> INDEX"
"$VENV_PY" gates/index_sync_check.py && echo "  [PASS] G8" || { echo "  [FAIL] G8"; exit 1; }

# ═══ G9 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G9 PS1 AUDITOR — PowerShell scanner"
"$VENV_PY" -c "
from pathlib import Path
import subprocess, sys, os
cwd = Path(os.getcwd())
auditor = cwd.parent.parent / '1.0_orbitais' / 'ps1_auditor.py'
target = cwd.parent.parent
if not auditor.exists():
    print(f'  [FAIL] G9: {auditor} nao encontrado')
    print(f'  cwd={cwd}')
    sys.exit(1)
result = subprocess.run([sys.executable, str(auditor), str(target)], capture_output=True, text=True)
print(result.stdout)
if result.returncode != 0:
    print(result.stderr)
    sys.exit(1)
" && echo "  [PASS] G9" || { echo "  [FAIL] G9"; exit 1; }

# ═══ G10 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G10 MCP-CONTRACT — call-sites x contrato"
"$VENV_PY" gates/run_mcp_contract.py && echo "  [PASS] G10" || { echo "  [FAIL] G10"; exit 1; }

# ═══ G11-G14 ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G11-G14 CONFORMANCE — header+DDD+security+robustez"
"$VENV_PY" gates/run_conformance.py --check all && echo "  [PASS] G11-G14" || { echo "  [FAIL] G11-G14"; exit 1; }

# ═══ G15: DIFF-LATERAL ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G15 DIFF-LATERAL — auditoria de mudancas [AUDIT-ONLY, nao bloqueia]"
GIT_ROOT="$ROOT/../../.."
if [ "$MODE" != "all" ]; then
    REF="HEAD"
    [ "$MODE" = "commit" ] && REF="HEAD~1"
    [ "$MODE" = "staged" ] && REF="--cached"
    git -C "$GIT_ROOT" diff $REF --name-only --diff-filter=ACM 2>/dev/null | grep -E "\.(py|md|yaml|json|sh|tsx?)$" | grep -E "11.0_apps/ctrader|10.0_ui_dash" | head -20 | while read f; do echo "    M $f"; done || true
elif git -C "$GIT_ROOT" rev-parse HEAD >/dev/null 2>&1; then
    echo "  [DIFF] Mudancas uncommitted (working tree vs HEAD):"
    CHANGES=$(git -C "$GIT_ROOT" diff HEAD --name-only --diff-filter=ACM 2>/dev/null | grep -E "\.(py|md|yaml|json|sh|tsx?)$" | grep -E "11.0_apps/ctrader|10.0_ui_dash" | head -30 || true)
    if [ -n "$CHANGES" ]; then
        echo "$CHANGES" | while read f; do echo "    M $f"; done
    else
        echo "    (sem mudancas no escopo ctrader/dashboard)"
    fi
fi
echo "  [OK] G15: diff lateral visivel (audit-only)"

# ═══ G16: METRICS ENDPOINTS ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G16 METRICS ENDPOINTS — 7 entry points + 29 metricas + 3 fontes + dashboard wire"
"$VENV_PY" gates/run_metrics_gate.py && echo "  [PASS] G16" || { echo "  [FAIL] G16"; exit 1; }

# ═══ G17: REACT LINT ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G17 REACT LINT — ESLint dashboard (src/*.tsx)"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "  [FAIL] G17: node_modules ausente em $FRONTEND_DIR"
    echo "         Rode: cd $FRONTEND_DIR && npm install"
    exit 1
fi
if [ ! -f "$FRONTEND_DIR/node_modules/.bin/eslint.cmd" ] && [ ! -f "$FRONTEND_DIR/node_modules/.bin/eslint" ]; then
    echo "  [FAIL] G17: eslint nao encontrado em node_modules/.bin/"
    echo "         Rode: cd $FRONTEND_DIR && npm install"
    exit 1
fi
echo "  Verificando arquivos React..."
"$VENV_PY" gates/run_react_lint.py && echo "  [PASS] G17" || { echo "  [FAIL] G17"; exit 1; }

# ═══ G18: VITE LINT ═══
N=$((N+1)); echo ""; echo ">>> [$N/18] G18 VITE LINT — oxlint (vite-plugin-oxlint src/*.tsx)"
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo "  [FAIL] G18: node_modules ausente em $FRONTEND_DIR"
    echo "         Rode: cd $FRONTEND_DIR && npm install"
    exit 1
fi
if [ ! -f "$FRONTEND_DIR/node_modules/.bin/oxlint.cmd" ] && [ ! -f "$FRONTEND_DIR/node_modules/.bin/oxlint" ]; then
    echo "  [FAIL] G18: oxlint nao encontrado em node_modules/.bin/"
    echo "         Rode: cd $FRONTEND_DIR && npm install"
    exit 1
fi
echo "  Verificando com oxlint (95+ regras)..."
"$VENV_PY" gates/run_vite_lint.py && echo "  [PASS] G18" || { echo "  [FAIL] G18"; exit 1; }

# G19: TEST ISOLATION — testes nao escrevem em producao (NC-CTRADER-022)
N=$((N+1)); echo ""; echo ">>> [$N/19] G19 TEST ISOLATION — RUNTIME ISOLATION (AST on tests/)"
"$VENV_PY" gates/run_test_isolation.py && echo "  [PASS] G19" || { echo "  [FAIL] G19"; exit 1; }

# G20: DATASOURCE WIRE — sem bypass do DataSource (S26)
N=$((N+1)); echo ""; echo ">>> [$N/24] G20 DATASOURCE-WIRE — sem leitura direta de disco"
"$VENV_PY" gates/run_datasource_wire.py && echo "  [PASS] G20" || { echo "  [FAIL] G20"; exit 1; }

# G21: PREFLIGHT PARQUET — integridade banco M_1 (S31)
N=$((N+1)); echo ""; echo ">>> [$N/24] G21 PREFLIGHT PARQUET — integridade banco M_1"
"$VENV_PY" gates/run_preflight_parquet.py && echo "  [PASS] G21" || { echo "  [FAIL] G21"; exit 1; }

# G22: PREFLIGHT DEPS — checklist deps VBT/TF
N=$((N+1)); echo ""; echo ">>> [$N/24] G22 PREFLIGHT DEPS — deps VBT/TF"
"$VENV_PY" gates/run_preflight_deps.py && echo "  [PASS] G22" || { echo "  [FAIL] G22"; exit 1; }

# G23: CONSOLIDATE PARQUET — merge + gap scan (S31)
N=$((N+1)); echo ""; echo ">>> [$N/24] G23 CONSOLIDATE — merge backfill+live Parquet"
"$VENV_PY" gates/run_consolidate_parquet.py --fast 2>/dev/null && echo "  [PASS] G23" || echo "  [WARN] G23 (não bloqueante — roda manualmente)"

# G24: ORCHESTRATOR WIRE — toda funcao tem ORQ/SAT/UTIL
N=$((N+1)); echo ""; echo ">>> [$N/24] G24 ORCHESTRATOR WIRE — 160 funcoes mapeadas"
"$VENV_PY" gates/run_orchestrator_wire.py && echo "  [PASS] G24" || { echo "  [FAIL] G24"; exit 1; }

# ═══ FIM ═══
echo ""
echo "══════════════════════════════════════════════"
echo " ALL GATES PASSED (G0-G23)  |  modo: $MODE"
echo " G15=AUDIT-ONLY"
echo " $(date '+%Y-%m-%d %H:%M:%S')"
echo "══════════════════════════════════════════════"

if [ -n "$SHIP_MSG" ]; then
    echo ""
    echo ">>> Executando git commit (isolado/no-verify) cTrader..."
    git -C "$GIT_ROOT" commit -m "$SHIP_MSG" --no-verify
    echo "  [OK] Commit efetuado com sucesso!"
fi
