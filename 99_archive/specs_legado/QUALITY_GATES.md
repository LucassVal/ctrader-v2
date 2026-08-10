# SPEC S0: QUALITY GATES — SUITE G0-G20 DO CTRADER + DASHBOARD
>**Versao:** 1.2.0 (2026-07-24 — G7 ativo, G2 cobertura total, PREFLIGHT SSOT)  
>**Wire:** `gates.sh → specs/QUALITY_GATES.md → specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-24 (execucao real: G0-G18 todos PASS)  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria


---

## AMBIENTE (obrigatorio)

- Interpretador unico: `VENV_PY = ../../.venv/Scripts/python.exe` — **todos** os gates.
  `python` cru e proibido no `gates.sh` (quebrava G1/G5/G6/G8 onde `python` resolvia
  para interpretador sem permissao; harness hardcodava Python312 = R-PATH-SQL).
- `PYTHONUTF8=1` + `PYTHONIOENCODING=utf-8` exportados pelo `gates.sh`: console
  Windows cp1252 crashava G3 (emoji no stdout) e G8 (`read()` sem encoding) com
  FAIL falso. Scripts tambem fazem `stdout.reconfigure(utf-8)` (cinto e suspensorio).
- Deps PINADAS em `requirements-gates.txt` (`ai-slop-detector==3.8.7`,
  `mockbuster==0.1.4`) — venv novo: `pip install -r requirements-gates.txt`.
- **PREFLIGHT obrigatorio (2026-07-24):** `python gates/check_deps.py` e a barreira
  UNICA de dependencias. Verifica 4 deps pip + 2 deps npm + 3 arquivos de config +
  qualidade do ruff.toml. Exit 1 com instrucao clara se ausente.
  **SSOT**: `gates.sh` chama `check_deps.py` diretamente (sem duplicata inline).
- **R-ASCII-OUT (regra sempre-ativa, ver ROADMAP §GOVERNANCA):** print/log de `.py` em
  ASCII puro (`[OK]/[ERR]/[ALLOW]/[START]`), **zero emoji** — cp1252 crasha e vira FAIL
  falso (mordeu 4x em 2026-07-23). `reconfigure(utf-8)` nos entry points e `encoding=
  "utf-8"` em todo I/O sao cinto-e-suspensorio, nao licenca para emoji. Travado no G14.

## OS GATES

| # | Gate | Mecanismo | Bloqueia |
|---|------|-----------|----------|
| G0 | RUFF | `VENV_PY -m ruff check .` (vector/ ATIVO incluido; exclui so vendor/caches) | SIM |
| G1 | COMPILE | `py_compile` em todo .py do app (incl. vector/ e tests/) | SIM |
| G2 | SLOP | `slop_detector.cli --gate` com `--project .` (cobertura total: 61 .py ctrader + 35 arquivos dashboard). LENTO 30-120s; `--fast` pula com aviso explicito | SIM |
| G3 | MOCK | `gates/run_mockbuster.py` (mockbuster 0.1.4) — proibe mock em prod; arquivo ilegivel = FAIL (R-NO-SILENT-FAIL) | SIM |
| G4 | STUB | inline: `raise NotImplementedError` proibido (+ cobertura do G2) | SIM |
| G5 | LINTER | inline: `logger.warning` proibido + comentarios banidos | SIM |
| G6 | HARNESS | `utils/harness_runner.py` (pytest via `sys.executable`) — toda fase F0-F5 com >=1 teste | SIM |
| G7 | ORBITAL | `gates/run_orbital.py` — cross-module DDD: parentesco ORQ→SAT + isolamento de fase. 10 ORQs, 21 SATs, allowlist justificada | SIM |
| G8 | INDEX-SYNC v0.3 | `utils/index_sync_check.py` — ver contrato abaixo | SIM |
| G9 | PS1 | `make gate-g9` no root (ps1_auditor) — **bloqueante** (era WARN-only) | SIM |
| G10 | MCP-CONTRACT | `gates/run_mcp_contract.py` — ver contrato abaixo | SIM |
| G11 | HEADER-SPEC | `gates/run_conformance.py --check header` | SIM |
| G12 | DDD | `gates/run_conformance.py --check ddd` | SIM |
| G13 | SECURITY | `gates/run_conformance.py --check security` | SIM |
| G14 | ROBUSTEZ | `gates/run_conformance.py --check robustez` (inclui R-ASCII-OUT) | SIM |
| G15 | DIFF-LATERAL | `git diff` audit visual de mudancas `.py/.md/.tsx` — **AUDIT-ONLY, nao bloqueia** | NAO |
| **G16** | **METRICS ENDPOINTS** | `gates/run_metrics_gate.py` — 7 entry points + 29 metricas + 3 fontes | SIM |
| **G17** | **REACT LINT** | `gates/run_react_lint.py` — ESLint em `src/*.tsx` (node_modules verificado antes) | SIM |
| **G18** | **VITE LINT** | `gates/run_vite_lint.py` — oxlint 95+ regras em `src/*.tsx` (node_modules verificado antes) | SIM |
| **G21** | **PREFLIGHT PARQUET** | `gates/run_preflight_parquet.py` — integridade m1_*.parquet (dups, futuro, OHLC) | NAO (WARN) |
| **G22** | **PREFLIGHT DEPS V2** | `gates/run_preflight_deps.py` — checklist ON/OFF (VBT Parquet, TF counts) | NAO (WARN) |
| **G23** | **CONSOLIDACAO PARQUET** | `gates/run_consolidate_parquet.py` — merge backfill+m1, gap scan, gap report (`status/gap_report.json`); fill via `backfill_orc_coleta.py --gaps` | NAO (WARN) |

## G8 v0.3 — INDEX-SYNC (derivado do grafo, nao de substring)

```
FALHA se:
 (a) indice concorrente (blueprint/INDEX.md deve ser ponteiro para specs/INDEX.md)
 (b) arquivo indexavel do disco fora do INDEX
 (b2) INDEX citar arquivo inexistente (stale) — aceita 10.0_ui_dash/ e 99_archive/
      como roots legitimos de arquivos movidos
 (c) modulo ORFAO real: zero referencias (dotted-import, string, nome de arquivo)
     vindas do app, do gates.sh OU do dashboard (10.0_ui_dash/*.py) —
     fora da ORPHAN_ALLOWLIST (cada entrada cita o item do ROADMAP que a resolve)
 (d) tool MCP usada no codigo fora do MAPA DE FLUXO do INDEX
Dump maquina-legivel: logs/index_graph.json
```

Allowlist de orfaos (R-WARN-FORBIDDEN: explicita, rastreada, nunca skip):
`f1_analyzer.py`/`f5_mar.py` (D.4) · `_ichimoku.py` (2.3) · `_volume.py` (2.4) ·
`dashboard.py` (entry legado) · `vectorbt_calibrator.py` (6.1) ·
`f4_executor/entry_orc_execucao.py`/`gates_orc_execucao.py` (**achado real do grafo**: `_orc_f4` nunca os
importou — gap da Fase 5.1) · `_archive_*_god.py` (backups pre-DDD).

## G10 — MCP-CONTRACT (padronizacao das chamadas MCP)

Tres fontes -> um diff. Teria pegado o bug 1.0 **e pegou, no primeiro run real,
dois bugs latentes**: `get_order_history`/`get_deals` enviavam `{"days": N}` —
o schema exige `fromTimestamp`/`toTimestamp` (e `days` nem existe em `get_deals`).
A reconciliacao do F5 estava 400 em silencio. Corrigidos e validados ao vivo.

```
(a) CONTRATO  specs/contracts/mcp_tools_snapshot.json
              = tools/list do servidor + overlay `quirks` MEDIDOS onde o schema
                publicado mente (fromTimestamp obrigatorio, timestamps string,
                count<=1000, janela 720h, from+to+count valido)
(b) CODIGO    AST de utils/mcp_client.py: todo call_tool("nome",{...}) literal ->
              tool existe? chave desconhecida? required (schema+quirks) presente?
(c) DOCS      nomes de tool citados em mcp_endpoints.md e no vendor
              remote-http-server.md devem existir no contrato (linhas com
              "sem "/"nao expoe" ignoradas)
Modos: offline (default, deterministico) | --live (diffa servidor x snapshot,
       detecta drift) | --refresh (re-gera snapshot preservando quirks)
```

## G7 — ORBITAL: cross-module DDD (2026-07-24)

Gate ativo desde 2026-07-24. Validador standalone `gates/run_orbital.py` (AST).

```
FALHA se:
 (a) SAT nao importado pelo ORQ pai (exceto allowlist: cortados, transitivos, ROADMAP)
 (b) Cross-phase: modulo de uma fase importa modulo de outra fase nao permitida
     (ex: F1 → F4 direto). F0 (gateway de dados) liberado para todas as fases.
 (c) ORQ com filhos declarados mas nenhum wireado (WARN, nao ERR)

Allowlist: 8 SATs justificados (ichimoku/volume/news cortados, entry/gates nao wireados,
dxy/indicators transitivos, json_log cross-importado)
Fases permitidas: todas podem importar f0_collector (leitura snapshot), utils, contracts.
```

## G15 — DIFF-LATERAL (auditoria de mudancas)

**O que faz:** usa `git diff` para listar todos os arquivos alterados entre commits
(modos `--diff`, `--staged`, `--commit`). No modo `all`, mostra mudancas uncommitted
(vs HEAD) nos escopos `11.0_apps/ctrader` e `10.0_ui_dash`.

**Por que existe:** gate de PASS/FAIL pode ser mock — G15 mostra O QUE MUDOU para
auditoria humana/IA lateral. Complementa G0-G14 com visibilidade de delta.
**AUDIT-ONLY** — nunca bloqueia commit.

**Uso tipico:**
```bash
bash gates.sh --commit    # pre-commit: o que mudou + gates nos changed files
bash gates.sh --diff      # working tree: o que ainda nao foi commitado
```

## COMO RODAR

```bash
bash gates.sh              # all: ctrader + dashboard (G0-G18)
bash gates.sh --fast       # all, pula G2 (slop 30-120s)
bash gates.sh --diff       # so arquivos alterados (git diff HEAD)
bash gates.sh --staged     # so arquivos staged (git diff --cached)
bash gates.sh --commit     # so arquivos do ultimo commit

# Preflight (verificar deps antes de qualquer gate):
python gates/check_deps.py           # pip + npm
python gates/check_deps.py --pip-only
python gates/check_deps.py --npm-only

# Gates isolados:
python gates/run_conformance.py --check all  # so G11-G14 isolado
python gates/run_orbital.py                  # so G7 (ORBITAL DDD)
python gates/run_react_lint.py               # so G17
python gates/run_vite_lint.py                # so G18
```

## ESCOPO

| Componente | Diretório | Porta | Gates |
|-----------|-----------|-------|-------|
| cTrader V2 | `11.0_apps/ctrader/` | — | G0-G18 (G15=AUDIT-ONLY) |
| Dashboard Backend | `10.0_ui_dash/` | 7744 | G0, G1, G2, G11 (via ruff + compile) |
| Dashboard Frontend | `10.0_ui_dash/react-dashboard/` | 5173 | G17 (ESLint), G18 (oxlint) |

> ⚠️ **Excecao ASCII no frontend:** `.tsx`/`.ts` pode ter emoji em strings de UI.
> G14 (R-ASCII-OUT) audita apenas `.py`. Frontend coberto por G15 (diff) + ESLint (manual).

## COMO USAR OS GATES POR FASE (guia para a IA)

> **R-AI-EXECUTOR:** rodar `bash gates.sh --fast` ANTES e DEPOIS de cada item do ROADMAP.
> Gate falhou = item NAO está DONE. Corrigir → re-rodar → DONE.

```
FASE 0:  bash gates.sh --fast          → G0-G14 devem passar (alfândega)
FASE 1:  bash gates.sh --fast          → G6 (harness coleta) + G10 (contrato MCP)
         python gates/run_mcp_contract.py --live  → drift do servidor
FASE 2:  bash gates.sh --fast          → G6 (harness métricas) + G12 (DDD satélites)
FASE 3:  bash gates.sh --fast          → G6 (harness artefatos) + G8 (INDEX sync)
FASE 4:  bash gates.sh --fast          → G13 (security — expurgo IA) + G14 (robustez)
FASE 4.5: bash gates.sh --fast         → G6 (harness regras)
FASE 5:  bash gates.sh --fast          → G13 (mutant tools) + G10 (contrato MCP)
         python gates/run_mcp_contract.py --live  → validar ordens
FASE 6:  bash gates.sh --fast          → G6 (harness replay)
DIVIDA:  bash gates.sh --fast          → G8 (INDEX sync) + G11 (headers .md)
```

### STATUS REAL G0-G18 (executado 2026-07-24 — suite completa, sem --fast)

> ✅ **Suite inteira verde.** G0-G18 todos PASS. Ver APROVACAO & COMPROVACAO no ROADMAP.
> Abaixo o estado final, nao especulado:

| Gate | Estado | Detalhe |
|------|:------:|---------|
| PREFLIGHT | ✅ PASS | check_deps.py: pip 4/4 + npm 2/2 + config 3/3 |
| G0 | ✅ PASS | ruff: 0 lint errors (83 .py ctrader + 16 .py dashboard) |
| G1 | ✅ PASS | compile: 83 arquivos, 0 erros |
| G2 | ✅ PASS | ai_slop: cobertura total (61 .py ctrader + 35 dashboard), CLEAN |
| G3 | ✅ PASS | mockbuster: 65 arquivos, 0 mocks |
| G4 | ✅ PASS | stub: 0 NotImplementedError |
| G5 | ✅ PASS | linter: 0 violacoes (logger.warning + banned comments) |
| G6 | ✅ PASS | harness: boot 10/10 + pytest 71 passed, 2 skipped |
| G7 | ✅ PASS | orbital: 10 ORQs, 21 SATs, 8 allowlists, 0 cross-phase ERR |
| G8 | ✅ PASS | index-sync: 90 arquivos, 50 .py, 16 tools MCP |
| G9 | ✅ PASS | ps1 auditor: 17 scripts, 0 issues |
| G10 | ✅ PASS | mcp-contract: 16 tools, 17 call-sites validados |
| G11 | ✅ PASS | header: 39/39 .py OK, 33/33 specs OK |
| G12 | ✅ PASS | ddd: 2 GOD allowlist, 0 novos |
| G13 | ✅ PASS | security: 0 secrets, 0 mutant tool viol |
| G14 | ✅ PASS | robustez: 50/50 OK (R-ASCII-OUT incluso) |
| G15 | ✅ AUDIT | diff-lateral: mudancas visiveis (11 arquivos alterados) |
| G16 | ✅ PASS | metrics: 7 entry points, API online (9 secoes) |
| G17 | ✅ PASS | ESLint: 0/0 |
| G18 | ✅ PASS | Oxlint: 0/0 |

## EXPANSAO APROVADA — CONFORMANCE G11-G14 (plano Hermes AUDITADO 2026-07-23)

> Proposta original: 29 regras -> 13 gates novos (G10-G22). **Ajustes na aprovacao:**
> (1) G10 ja existe (MCP-CONTRACT) -> novos sao **G11-G14**; (2) 13 gates -> **4 gates
> consolidados num unico runner** `gates/run_conformance.py --check <id>` (R53 +
> R-IA-PROPORCIONAL); (3) **zero WARN** — tudo ERR com allowlist congelada
> (R-WARN-FORBIDDEN, padrao do G8 v0.3); (4) idempotencia e regex-cego REJEITADOS
> como gate (nao-automatizaveis sem ruido) -> checklist manual abaixo; (5) R76
> estreitado para call-site allowlist de tools mutantes; (6) header sem strings de
> regra (cargo-cult) e sem TICKET SQL (**modo standalone**).

| Gate | Checks (`--check`) | Regras cobertas | Mecanismo |
|------|--------------------|-----------------|-----------|
| **G11 HEADER-SPEC** | `header` | R117, R-SDD, R-3W, R-HEADER-TRACE (adaptada standalone) | Todo `.py` >50L do app: docstring de modulo com `PROPOSITO:` + `SPEC:` (S# valido de specs/INDEX.md) + `ROADMAP:` (item existente). Toda spec `.md` nova em specs/: titulo `SPEC S#`, versao, wire. Sem strings de regra no header. |
| **G12 DDD** | `ddd` | R-ANTI-DECAY, R117 | GOD: satelite >200L / orquestrador (`_orc_`) >350L = ERR (limites do precedente `utils/health.py`); allowlist congelada dos ofensores atuais com item de ROADMAP — **nenhum GOD novo**. Arquivo >150L sem docstring de modulo = ERR. Orquestrador chamando MCP/SQLite direto (fora de `mcp_client`/`_db`) = ERR. |
| **G13 SEGURANCA** | `security` | R155, R156, R-PORT-PATH-LOCK, R76 (estatico) | Padrao de segredo (`Bearer `, `api_key=`, `sk-`, token base64 longo) fora de `.env` = ERR (allowlist: `config.yaml` Bearer demo -> divida D.6). `.gitignore` deve conter `.env`, `*.db`, `__pycache__`. Tools MUTANTES (`create_order`, `close_position`, `cancel_order`, `amend_*`) so chamaveis de `f4_executor/` (call-site allowlist) — ordem rogue = ERR. |
| **G14 ROBUSTEZ-FORMA** | `robustez` | R-NO-SILENT-FAIL, R51, R125, R01, R-LANG, R-NAO-V43, R-PATH-SQL, **R-ASCII-OUT** | `except:` bare = ERR. `return False/None` em funcao >10L sem `[ERRO]`/stderr/raise no corpo = ERR (heuristica AST, allowlist p/ falso-positivo justificado). Acento em identificador/chave = ERR (comentario/docstring PT-BR livre). Path absoluto hardcoded (`C:\`, `/c/`) fora de bootstrap L1 = ERR. Termo V43 (`Eixo 5`, `Vector-Sig`) = ERR. **String literal em `print()`/chamada de log com char fora de ASCII = ERR** (emoji/acento em saida de runtime — cp1252 crasha; 8 ofensores atuais mapeados: dashboard, harness_runner, test_f1_scores, gates/run_* — NORMALIZAR, nao allowlistar: e infra de gate, fix barato). |

**Implementacao:** UM arquivo `gates/run_conformance.py` (AST + regex ancorado, stdout
utf-8/ASCII, exit!=0 em ERR), wireado no `gates.sh` como 4 passos G11-G14 apos o G10.
Allowlists no topo do arquivo, cada entrada com motivo + item do ROADMAP (padrao G8 v0.3).

## CHECKLIST MANUAL (nao-automatizavel sem ruido — revisar no code review)

- R49 idempotencia: mutacao verifica pre-existencia? (rejeitado como gate: semantica profunda)
- R-PARSER/R-AST: estrutura sintatica manipulada via parser, nao regex cego? (idem)
- R-RCA/R50: causa raiz atacada? reuso buscado antes de criar? (cognitivo, nao estatico)
- R-TRACE/R-HASH/R-VERSAO: dependem do SQL do V44 — adiados ate o fim do refit (standalone).

## REGRA DE REJEICAO

Qualquer gate falhando = commit rejeitado. NUNCA `--no-verify`.
Gate que "passa" pulando etapa e bug de gate — corrigir na origem (R-SELF-REPAIR).
