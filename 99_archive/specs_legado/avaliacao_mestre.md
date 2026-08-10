# AVALIAÇÃO MESTRE CONSOLIDADA v2.0: cTrader V2 | SPEC S0
> **Versao:** 2.0.0 | **Wire:** specs/avaliacao_mestre.md → specs/INDEX.md → G8/G11 | **Status:** active
> **Data da Auditoria:** 2026-07-30 (rev. 2 — pós-sessão S33 + auditoria de gates 10/10)
> **Motor de Análise:** R21 (Validação de Extrema Profundidade: Código × Specs × INDEX × Gates × Runtime)
> **Escopo Ampliado:** v1 (Gemini) revisada item a item contra a verdade atual do disco e do runtime;
> inclui S27-S33, validador por fase ao vivo, e o estado real do VectorBT após warmup S2.5.

Esta é a "Ground Truth" do cTrader V2. A v1 (gerada por outra sessão) foi **verificada fato a fato**:
o que estava certo foi mantido, o que estava desatualizado foi corrigido com evidência, e as
lacunas (S27-S33, gates G21-G23, estado ao vivo) foram ampliadas.

---

## PARTE 0: CORREÇÕES DA v1 (o que mudou desde a avaliação original)

| # | Afirmação da v1 | Verdade verificada (2026-07-30) |
|---|-----------------|--------------------------------|
| 1 | "Coverage 0.0 — VectorBT retorna tensores vazios, F1 falha ao emitir scores" | **DESATUALIZADO.** Warmup S2.5 (200 velas M_1/boot) + persistência Parquet: VBT calcula **16/16 indicadores nos 5 mercados**, 341+ pontos/símbolo. `scores_raw.json` existe e F1 emite. O "coverage 0%" que resta é a **barra de progresso do fill de 2 anos** (S31), não falha matemática. |
| 2 | "G20 possui 16+ regras na allowlist" | **ERRADO.** `run_datasource_wire.py` tem **4 entradas** allowlistadas. O ideal S26 está parcialmente atingido, mas o número correto importa para o R21. |
| 3 | "G21/G22/G23 NÃO ESTÃO PLUGADOS no gates.sh" | **RESOLVIDO nesta revisão.** Os três gates foram wireados no `gates.sh` (suite agora G0-G23). O "bug de escape (shell quoting)" era desculpa de patch — bastava 3 blocos de 4 linhas. |
| 4 | "run.py invoca scripts refatorados, F4/F5 não engatam" | **RESOLVIDO nesta revisão.** `run.py` apontava para `f1_analyzer.py`, `f2_fusion.py`, `f3_validator.py` e `dashboard.py` — **arquivos que nem existem no disco** (mortos na allowlist G8). F1-F3 agora sobem como `-m f1_analyzer.orc_analise`, `-m f2_fusao.orc_fusao`, `-m f3_validacao.orc_validacao`. Streamlit legado removido (UI oficial = 10.0_ui_dash). |
| 5 | "Colisão S22/S23/S24 + S5.1 órfão + S18 rotulado S17:S12" | **RESOLVIDO nesta revisão** (expurgo documental — ver Parte 4). |
| 6 | "18 gates integrados (G0-G20), pipeline cessa no G20" | **AMPLIADO.** Suite agora é **G0-G23** e todos passam: 10/10 gates standalone + harness 16/16 + 76 testes pytest. |

---

## PARTE 1: ARQUITETURA E ALINHAMENTO COM A SPEC (DDD & SSOT)

### 1.1 O Dogma do "Ponto Único de Contato" (MCP & Dashboard) — CONFIRMADO
- **MCP Gateway (F0 - S2 / S1.1):** `mcp_client.py` é o Gateway exclusivo (token-bucket 50req/s ao vivo, 5req/s refill, cache TTL 1s/30s). **R-NO-MCP-BYPASS íntegro**: G10 (contrato 16 tools) PASS, Mockbuster v3 MCP-aware: 57 arquivos, **0 bypass**.
- **1 orquestrador toca o MCP** (regra do dono): só `f0_collector/orc_coleta.py` (+ seu satélite CLI `backfill_orc_coleta.py`) fala MCP. Backfill, health, métricas — todos leem artefatos locais (snapshot/parquet/status), nunca competem pelo servidor. Isso é o que evita as quedas de MCP.
- **Dashboard Hub (S21):** `orc_dashboard.py` lê `status/snapshot.json` — sem conexão MCP própria (sem race condition, sem exaustão de rate limit).
- **DataSource (S26):** unificação de leitura existe e G20 fiscaliza bypass. Allowlist real: **4 entradas** (não 16+). Ideal parcialmente atingido, sob controle.

### 1.2 DDD — Hierarquia Orquestrador × Satélite — CONFIRMADO E REFORÇADO
- **G7 (orbital):** isolamento por fase fiscalizado via AST. PASS com allowlist justificada (cada entrada cita ROADMAP): backfill é CLI standalone, `storage_orc_vbt` tem naming debt documentado, `utils→f1_analyzer` permitido e justificado (S25.10: orc_indices consome dxy/sentiment p/ /vector/globals; debt: mover SATs p/ utils).
- **G12 (GOD objects):** teto 200L SAT / 350L ORQ. `orc_vectorbt.py` estava com **456L — foi feito split DDD nesta revisão**: helpers numpy puros (ADX, Donchian, HMA, Keltner, CCI, PSAR, Williams %R, Aroon, ZLEMA) migraram para o satélite `indicators_orc_vectorbt.py` → orquestrador com 284L. **0 GODs novos.**
- **Toda fase/dado passa por orquestrador** (regra do dono): score saiu do router para `orc_score.py` (S32); saúde por fase vive em `orc_health_fases.py` (S33); routers são **proxies puros** (G16 valida o wire).
- **Boot central (`run.py`):** corrigido nesta revisão (ver Parte 0, item 4). Pendente: validação de um boot F0-F5 completo de ponta a ponta.

---

## PARTE 2: MOTOR QUANTI (VECTORBT) — ESTADO REAL

### 2.1 Pipeline de dados M_1 (S2.5) — A "torneira" está aberta
- **Warmup no boot:** 200 velas M_1/símbolo via `get_trendbars` (1 chamada por símbolo por boot) → VBT calcula já no 1º ciclo, sem esperar 200 minutos.
- **Persistência:** `data/m1_{SYM}_{ANO}.parquet` (OHLCV bruto, append por ciclo, timestamp **milissegundos** int64) + `data/vbt_{SYM}.parquet` (indicadores, 1 arquivo/símbolo — S27).
- **Higiene do banco:** removida linha-semente `timestamp=0/close=0` dos 5 parquets (artefato de init que o G21 agora flagraria).
- **TF padrão do Vector:** **M_1** (confirmado: pré-análise calcula sobre M_1; multi-TF 15m/1h/6h derivado por resample na aba de mercado).

### 2.2 Indicadores (S25/S27/S28) — 16/16 reais por mercado
- Motor `vectorbt` + numpy puro (split DDD): RSI, MACD, ATR, BBANDS, ADX, OBV, STOCH, SMA fast/slow + Donchian, breakout%, HMA, Keltner, CCI, PSAR, Williams %R, Aroon, ZLEMA.
- **Ao vivo agora:** 16/16 calculados em XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD (ex.: XAU rsi 50.5/adx 30; EUR adx 72). Sem NaN estrutural.
- `vector_metrics()` (S20 v2.1) expõe ao dashboard: indicadores considerados × ausentes, bars usados, coverage_pct, últimos valores — **é o orquestrador que alimenta o dashboard e conecta as peças**.

### 2.3 Análise de sinais (S29/S30/S32) — honesta enquanto aquece
- **S29 (quality):** walk-forward backtest + F1/precision/recall sobre VBT. Com 29 pontos reportava `sem_dados` (mín. 30) — **sem mentir**; já cruzou 341 pontos, quality ativa.
- **S30 (patterns):** "este setup já apareceu antes?" — sliding windows + cosine similarity sobre o VETOR de indicadores (não só preço). Mín. 30 pontos; reporta `aquecendo` honestamente.
- **S32 (score combinado):** `combined = quality_f1 × 0.33 + pattern_conf × 0.67`, `adjusted = combined × min(1, data_days/730)` — **confiança progressiva**: o Vector trabalha com o que tem enquanto o fill de 2 anos avança; o índice de confiança sobe junto com a cobertura (exatamente o desenho pedido pelo dono).
- **Fix pips XAUUSD:** pip = $0.10 (não $0.01) via `PIP_SPECS.pip_size` (S30-PIPS).
- **Correlação 5×5 real (S25.10):** Pearson sobre closes M_1 alinhados (200 pontos), não mais stub.

### 2.4 O que o passado responde ao presente (pergunta do dono)
O S30 tira padrões do histórico assim: o vetor de indicadores atual vira uma "assinatura"; o matcher varre as janelas passadas com a mesma assinatura (cosine ≥ threshold) e mede **o que aconteceu depois** de cada ocorrência (outcome stats: bullish_pct, move médio). Com 2 anos de M_1 (~700k velas), as janelas de referência saem do backfill; hoje saem do que já acumulou — por isso `adjusted_confidence` escala com `data_days/730`.

---

## PARTE 3: IMPERMEABILIDADE DOS QUALITY GATES (G0-G23) — ESTADO ATUAL

### 3.1 Histórico de reparo (mantido da v1 — correto)
Exit codes fantasmas mortos: G0 (ruff com echo [PASS]), G2 (slop sem dependência), G17/G18 (sucesso sem node_modules). `check_deps.py` (PREFLIGHT) é bloqueio nível zero. R-NO-SILENT-FAIL selada.

### 3.2 Auditoria 2026-07-30 (esta revisão) — 10/10 PASS
| Gate | Estado | O que foi sanado nesta revisão |
|------|--------|-------------------------------|
| G0-G6, G9, G15 | PASS | — |
| G7 Orbital | PASS | 4 violações cross-module da véspera (S25.10/S31) → allowlist justificada + fase permitida |
| G8 Index-sync | PASS | 3 utils não indexados + 2 órfãos reais → INDEX/allowlist |
| G10 MCP-contract | PASS | 16/16 tools |
| G11 Header-spec | PASS | 3 arquivos sem header; mapa S2.5/S25.10/S5.1; ROADMAP sem SPEC no título → **49/49 py, 33/33 specs** |
| G12 DDD | PASS | split orc_vectorbt 456→284L; allowlist orc_health_fases (SQLite read-only) |
| G13 Security | PASS | 0 secrets |
| G14 Robustez | PASS | ASCII no backfill; logger.warning→error (G5) |
| G16 Metrics wire | PASS | sub-aba "saude" mapeada → /health/fases |
| G17 React lint | **limitação conhecida** | timeout interno de 60s do gate; oxlint direto: **0 erros/0 warnings** no CtraderTab.tsx |
| G19 Test isolation | PASS | 17 arquivos de teste isolados |
| G20 DataSource | PASS | 0 bypass |
| G21 Preflight Parquet | PASS | **bug real**: numpy.int64 lido como nanossegundos ("última vela há 56 anos") + tz naive/aware; linha-semente ts=0 removida |
| G22 Preflight Deps | PASS | — |
| G23 Consolidate | PASS | gap_report.json presente; coverage 0% honesta (fill pendente) |
| Harness boot | **16/16 PASS** | — |
| pytest | **76 passed, 2 skipped** | 5 testes novos S33 |

### 3.3 Gates que NÃO validavam código novo (a pergunta do dono, respondida)
Antes desta revisão, **nada** validava `orc_score`, `vector_metrics`, `correlate_markets_m1`, warmup e G23 em runtime. Dupla cobertura criada:
1. **CI:** `tests/test_health_fases.py` (5 testes read-only, G19-compatible).
2. **Runtime:** S33 `orc_health_fases.check_fases()` → `/api/ctrader/health/fases` → **sub-aba "Saúde" (item 1 de todas as 5 abas mestras)**. O dashboard agora mostra, por etapa, se a mecânica e o código dela estão OK — e o Overview principal mostra **todas as fases × checks**.

---

## PARTE 4: AUDITORIA DO INDEX/SSOT — EXPURGO EXECUTADO

| Drift da v1 | Ação desta revisão |
|-------------|-------------------|
| `audit_codigo_x_skill_oficial.md` se dizia "SPEC S22" (colidia com orc_dashboard_abas) | Retitulado: "(ref SPEC S0 — documento passivo, sem ID próprio)" |
| `audit_fontes_dados.md` se dizia "SPEC S23" (fantasma) | Idem |
| `audit_skill_x_funcoes.md` se dizia "SPEC S24" (fantasma) | Idem |
| `strategy_3scalps_5markets.md` se dizia "SPEC S5.1" (órfão no INDEX) | **S5.1 registrado no INDEX** (tabela + spec_files) — é spec viva, merecia ID |
| `vectorbt_ecosystem.md` titulado "SPEC S17: SPEC S12" (duplo erro) | Corrigido para **SPEC S18** (como o INDEX sempre disse) |
| S3 e S17 → mesma spec (`orc_analise.md`) | **MANTIDO e justificado**: o header de `orc_analise.py` declara "SPEC: S3 (pai) + S17 (_indicators)" — é mapeamento intencional, não drift |
| S2 e S2.5 → mesma spec (`orc_coleta.md`) | **MANTIDO**: backfill declara `SPEC: S2.5`; a linha S2.5 no INDEX é o que faz o G11 resolver |

---

## PARTE 5: O QUE A v1 NÃO COBRIU (S27-S33) — AMPLIAÇÃO

| Spec | Entrega | Estado |
|------|---------|--------|
| S27 | Persistência VBT Parquet + overview por mercado (indicadores considerados × ausentes) | ✅ 16/16 ao vivo |
| S28 | 5 abas por mercado (XAUUSD..AUDUSD) + multi-TF | ✅ React + /vector/symbol/{sym} |
| S29 | Signal quality (walk-forward, F1) | ✅ ativo (341+ pontos) |
| S30 | Pattern matching (cosine sobre vetor de indicadores) | ✅ ativo; fix pips XAUUSD |
| S31 | Consolidação Parquet: G23 merge backfill+m1, gap scan, gap fill + **confiança progressiva** (coverage → adjusted_confidence) | ✅ mecanismo pronto; **fill de 2 anos pendente (coverage 0%)** |
| S32 | `orc_score` — score combinado sai do router → orquestrador | ✅ router é proxy puro |
| S33 | **Validador por fase sempre ativo** — sub-aba "Saúde" ×5 + endpoint /health/fases | ✅ **AO VIVO na :7744 — 7/9 fases OK** |

**Leitura honesta do painel Saúde agora:** os 2 "✗" não são bugs — são verdade:
- **f4_execucao:** tabela `trades` ainda não existe (F4 nunca registrou trade). Antes, `orc_metricas` mascarava com zeros via fallback; o S33 expõe.
- **s31_backfill:** coverage 0% — o fill de 2 anos nunca rodou. Todo o resto (F0 snapshot 3s, pid vivo, m1 <2min, F1-F3 artefatos, F5 regras, 16/16 indicadores, 341 pontos VBT, orc_score importável) está verde.

---

## PARTE 6: PLANO DE EXECUÇÃO CIRÚRGICA (ATUALIZADO)

Dos 4 passos da v1, **3 foram executados nesta revisão** (expurgo SSOT ✅, wire G21-G23 ✅, boot central run.py ✅). O que resta para habilitar F4 com segurança:

1. **Backfill 2 anos gap-aware** (`python f0_collector/backfill_orc_coleta.py --gaps`, ~60min na 1ª vez, MCP online) — tira o S31 do 0%, alimenta S29/S30 com histórico cheio e leva `adjusted_confidence` ao teto. Depois: `run_consolidate_parquet.py` (G23) + rebuild `vbt_{SYM}.parquet` (S31-VBT).
2. **Validar boot central:** subir `run.py` e confirmar F0-F5 engatando (agora que F1-F3 apontam para módulos reais). F4 com `restart_on_crash: False` — intervenção humana por desenho.
3. **Primeiro dry-run F4:** com trades.db populado, saem S28-G3 (precisão YoY), S28-G5 (scatter score×PnL) e /performance real — e o painel Saúde vira 9/9.
4. **Debts documentados (não bloqueantes):** mover `dxy/sentiment` de f1_analyzer p/ utils (SPEC-2); naming `storage_orc_vbt→orc_vbt` (S27); vetorizar `extract_windows` O(n×20) antes das 700k velas (S30-PERF); G17 timeout 60s.

> *A governança para dry-runs autônomos está a 1 backfill + 1 boot validado de distância. O sistema não mente mais em nenhuma camada: gates, métricas e dashboard reportam o mesmo chão.*
