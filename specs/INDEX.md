# SPEC S0-INDEX | Versao: 3.0 | Wire: INDEX.md (SSOT) -> specs/*.md | Status: active

> **P0 — ANTES DE ALTERAR, LEIA:** specs/NC-BP_CTRADER_DEV.md (boas práticas: criação, manutenção, revisão, DDD, rollbacks)
> **SSOT**: Single Source of Truth. Toda regra, pasta, arquivo e fluxo mapeado aqui.
> **DDD SSOT**: Classificação ORQ vs SAT, firewall S41→S42, XAUUSD-first — ver BP00.
> **Parser G11/G8**: valida .py x INDEX.md x specs/.md — estrutura alinhada.

---

## SPEC References (para G11)

| SPEC | Arquivo |
|------|--------|
|| S0 | 00_visao_geral.md |
|| BP00 | NC-BP_CTRADER_DEV.md (P0 — boas práticas: criação, manutenção, revisão) |
|| S1.1 | mcp_endpoints.md |
|| S2 | orc_coleta.md |
|| S2.5 | orc_coleta.md |
||| S2.6 | orc_worker_backfill.md |
|| S3 | orc_analise.md |
|| S4 | orc_fusao.md |
|| S5 | orc_validacao.md |
|| S5.1 | strategy_3scalps_5markets.md |
|| S6 | orc_execucao.md |
|| S7 | orc_mar.md |
|| S17 | orc_analise.md |
|| S18 | vectorbt_ecosystem.md |
|| S19 | fluxo_logs.md |
|| S20 | orc_metricas.md |
|| S21 | orc_dashboard.md |
|| S22 | orc_dashboard_abas.md |
|| S25 | orc_vector_rewire.md |
|| S25.10 | orc_vector_rewire.md |
|| S26 | orc_datasource.md |
|| S27 | orc_vectorbt_overview.md |
|| S28 | orc_estrategia.md |
|| S29 | orc_quality.md |
|| S30 | orc_pattern.md |
|| S31 | orc_consolidacao.md |
|| S32 | orc_score.md |
|| S33 | orc_health.md |
|| S34 | orc_pattern_engine.md |
|| S35 | orc_ranking.md |
|| S36 | orc_calibracao.md |
|| S39 | vista_mercado.md |
|| S44 | orc_pattern_candles.md (v2.0 — Live Execution Architecture) |
||| S45 | orc_portfolio_manager.md (v1.0) |
|| S41 | orc_bloco1.md (v2.1: preflight DXY+VIX) |
||| S41.4 | orc_dxy_filter.md |
|| S42 | orc_bloco2.md (v2.0) |
|| S43 | orc_grid.md (v2.0) |
|| DG01 | domain_gates.md |
|| G24 | g24_orchestrator_wire.md |
||| B01 | boot_unificado.md |
|||| S27-GAP | vectorbt_gap_analysis.md |
|

---

## PROGRESSO POR SPEC (% implementado)

> **Atualizado:** 2026-08-09 | **Legenda:** <100% = features pendentes documentadas no spec
> **ROADMAP:** v4.0 com 39 tasks atômicas SDD-DDD-TDD + rollbacks (ver specs/ROADMAP.md)
> **Session Lifecycle:** `mcp_client.ensure_session_fresh()` SSOT — renovacao proativa MCP a cada 5 min (S2 v2.2)

| SPEC | %% | Pendente |
|------|----|----------|
| S41 (Bloco1) | 60% | VWAP, Panic Override, Slope, Antecipacao (FASE 3.1-3.4 — 17 tasks) |
| S42 (Bloco2) | 50% | MonteCarlo, CircuitBreaker, Spread Gate, OCO dinamico (FASE 4.0-4.2 — 9 tasks) |
| S43 (Grid) | 40% | MOMENTUM_GRID, Walk-Forward XAUUSD (FASE 3.3.6 — 1 task) |
| S44 (Live) | 30% | Buffer 60/5, emit_once(), VWAP exaustao (FASE 5.1 — 3 tasks) |
| S45 (Portfolio) | 10% | Codigo pendente — spec apenas (FASE 5.2 — 5 tasks) |
| S6 (Execucao) | 90% | Requote/Partial Fill handler (FASE 4.0.4 — 1 task) |
| S2 (Coleta) | 100% | Session lifecycle SSOT implementado (v2.2) |
| **Demais 31 specs** | **100%** | — |
| **FASE PRE-BETA** | **0%** | Wire Bloco2→F4, CircuitBreaker, Simulação 30d, Go/No-Go (PRE-BETA.1-.4 — 12 tasks) |
| **FASE 5 (Live)** | **0%** | Buffer 60/5, emit_once(), Portfolio Manager (FASE 5.1-5.2 — 8 tasks) |
| **FASE 3 (Micro)** | **0%** | VWAP, Panic Override, Slope, Antecipação (FASE 3.1-3.4 — 17 tasks) |

> **Nota:** %% de specs (S41-S45) ≠ progresso das fases. Fases são sequenciais: PRE-BETA usa S41+S42 atuais (60%/50%), não requer FASE 3 completa.
> **Ordem de ataque:** FASE 3 (Microestrutura) → FASE 4 (Defesa) → PRE-BETA (XAUUSD Demo) → FASE 5 (Live).

---

## CONTRATOS DE INTERFACE — Spec Gates (v3.0)

### S41 → S42

```python
# S41 entrega: dict com signals_validated + trades
# S42 NUNCA acessa: ohlc_df, dxy_close, vix_close, RSI, MACD, ADX
S41_OUTPUT = {
    "signals_validated": {"total": int, "buy": int, "sell": int},
    "trades": [{"entry_time", "exit_time", "direction", "mae_pct", "mfe_pct", "pnl_pct"}],
    "best_combo": {"buy_trigger": dict, "sell_trigger": dict},
    "vix_spike": bool,
}
```

### S41 → S45

```python
# S45 consome sinal ANTES da execução, aprova/bloqueia por exposição USD
S45_INPUT = {"symbol": str, "signal": "BUY"|"SELL", "confidence": float}
S45_OUTPUT = {"approved": bool, "reason": str|None, "competitor": str|None}
```

### S44 → S41

```python
# S44 é SAT, S41 é ORQ. S44 informa confidence; S41 decide.
S44_OUTPUT = {"signal": "BUY"|"SELL"|None, "confidence": 0..1, "patterns": [str]}
```

### Gate de Violação (S42)

```python
# PROIBIDO em S42:
import talib                          # recalcular indicadores
from utils.orc_bloco1 import _detect   # acessar SAT do Bloco 1

# PERMITIDO em S42:
from vectorbt import Portfolio         # simulação de execução
import numpy as np                     # matemática pura
```

---

## AUDITORIA SPEC DRIFT — Rodada 9

```
18 specs ativas. Nenhuma órfã.

Sobreposições resolvidas:
  S41↔S44: S44 é SAT (confidence), S41 é ORQ (decisão). Sem overlap.
  S42↔S45: S42 = risco por trade. S45 = risco de portfólio. Domínios disjuntos.

Specs removidas/absorvidas:
  S40 → S44 v2.0
  S41.5-micro → S41 v3.0
  S2.5 → S2 v2.1
```

---

## 1. REGRAS GERAIS (RULES.md)

| # | Regra | Descricao |
|---|-------|----------|
| R1 | Spec-driven | Spec (*.md) ANTES do codigo. Nunca inverter. |
| R2 | KISS/YAGNI | Sem infra desnecessaria. Só o que o sistema pede. |
| R3 | DDD | Orquestrador wireia satelites. Satelite = 1 funcao. >200L split. |
| R4 | SSOT | INDEX.md é a verdade. Disco reflete INDEX. G8 valida. |
| R5 | R-NO-WARN | Zero tolerancia a warnings. ESLint/oxlint/ruff: tudo `error`. |
| R6 | R-ASCII-OUT | Prints/logs sem emoji/unicode. G14 flagra. |
| R7 | R-NO-MCP-BYPASS | Só F0 toca MCP. Outros leem snapshot. Snapshot vazio = offline. |
| R8 | R-DDD-NAMING | ORQ = `orc_<funcao>.py`. SAT = `<nome>_orc_<pai>.py`. |
| R9 | R-USE | Validar gate apos implementar. Reaproveitar pacotes pip existentes. |
| R10 | R21 | Proibido imaginar/supor. Sempre pesquisar e validar. |

---

## 2. REGRAS DO APP (ctrader-specific)

| # | Regra | Descricao |
|---|-------|----------|
| A1 | F0 PONTA DE LANCA | Unico ponto MCP: dados + ordens. Throttle 50/5 req/s. |
| A2 | M_1 para tudo | Sinal, entrada, gestao em M_1. M_5/M_15 via resample(). |
| A3 | IA removida (S26) | Decisao 100% mecanica. Fallback score >= 85. |
| A4 | JSON contracts | fusion_output.json imutavel. Runtime contracts em status/. |
| A5 | 5 ativos | XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD. |
| A6 | 2 scalps | S1 rompimento (5min) + S2 respiracao (15min). |
| A7 | Offline honesto | `{online: false, data: null}` — nunca mock. |
| A8 | Dashboard React | Porta 5173 -> backend 7744. IP direto (proxy Vite quebrado). |
| A9 | Pre-flight obrigatorio | harness_boot.py roda antes do F0 iniciar. Falha = bloqueia. |
| A10 | Gates bloqueantes | G0-G24 full suite. `--fast` so pula G2. `--no-verify` proibido. |
| A11 | Isolamento de runtime | Testes nao escrevem em producao. `tmp_path`/`monkeypatch` obrigatorios. G19 valida. |
| A12 | DataSource unico | So F0 escreve snapshot. Leitores usam `utils.data_source`. G20 valida. |
| A13 | ORQ vs SAT | Novo .py: classificar ANTES de criar. ORQ→f{n}/, SAT→utils/. Se importa outros utils ou decide negócio→ORQ. |

---

## 3. ESTRUTURA DE PASTAS

```
ctrader/
├── run.py                         Entry point (boot)
├── config.yaml                    Config
├── SOUL.md                        Personalidade do agente (contexto Hermes)
├── .hermes.md                     Regras operacionais Hermes (R1-R10)
├── ruff.toml / .gitignore         Linter
├── gates.sh / requirements-gates  Gates
│
├── f0_collector/                 F0 — Coleta (5 ativos + 2 indices: DXYUSD, VIXUSD)
│   ├── orc_coleta.py              Coleta MCP → snapshot.json + m1/vbt parquet
│   ├── backfill_orc_coleta.py     Backfill 2 anos (MCP paginado)
│   ├── backtest_simulator.py      Gera backtest_trades.db 2 anos (S30) ✅
├── f1_analyzer/                   F1 — Analise tecnica
├── f2_fusao/                      F2 — Fusao ponderada
├── f3_validacao/                  F3 — Validacao (threshold)
├── f4_executor/                   F4 — Execucao (ordens + trail)
├── f5_mar/                        F5 — MAR (pesos + replay)
│
├── utils/                         INFRA compartilhada
│   ├── mcp_client.py              Gateway MCP
│   ├── orc_dashboard.py           Hub apresentacao
│   ├── orc_metricas.py            Metricas (29)
│   ├── orc_ranking.py             Rank mecanico (MOVED → f3_validacao/)
│   ├── orc_mercado.py             Mercado: pip spread forca (S25)
│   ├── orc_indices.py             Indices: DXY sintetico + sentiment (S25.10)
│   ├── orc_vectorbt.py            Vector BT: Sharpe, DD, profit_factor (S25 Fase2)
│   ├── indicators_orc_vectorbt.py SAT: indicadores avancados numpy puro (split DDD S25)
│   ├── orc_score.py               Score combinado S29+S30 (MOVED → f2_fusao/)
│   ├── orc_quality.py             Qualidade sinais walk-forward F1 (S29)
│   ├── orc_pattern.py             Pattern matching cosine similarity (S30)
│   ├── orc_health_fases.py        Validador por fase sempre ativo (S33)
│   ├── orc_calibracao.py          Calibracao: signals_log + reconcile + calibration.json (S36)
│   ├── resample.py                SAT: resample M1->M5/M15 via pandas (S27 v3.0, C4)
│   ├── orc_pattern_candles.py     SAT: Live Execution — TA-Lib patterns + buffer 60/5 (S44)
│   ├── signal_emitter_orc_score.py SAT: emissor live — score_live.json + signals_log (S36)
│   ├── orc_scan.py                ORQ: scan batch 730d — pattern_library.json + replay (S34)
│   ├── matrix_orc_scan.py         SAT: helpers numpy do scan (split DDD G12)
│   ├── matrix_orc_quality.py      SAT: engine numpy quality trailing S29-parity (S34 v1.2)
│   ├── families_orc_vectorbt.py   SAT: 10 familias avancadas na cauda (S39 fix 16/16)
│   ├── vista_orc_mercado.py       SAT: vista MTF por simbolo — regime/calibracao/padroes/correlacao (S39)
│   ├── matrix_orc_vista.py        SAT: engine de regime MTF (split DDD G12, S39)
│   ├── backfill_supervisor_orc_dashboard.py SAT: backfill status/start/stop (S31-PROG)
│   ├── storage_orc_vbt.py         Persistencia VBT Parquet (S27)
│   ├── storage_orc_consolidated.py SAT: fallback S31-VBT — indicadores do consolidado G23 (730d)
│   ├── data_source.py             DataSource: leitura unificada (S26)
│   └── json_log / logger / ...    Satelites
│
├── contracts/                     CONTRATOS cross-phase
├── gates/                         QUALIDADE G0-G23
│   ├── run_conformance.py         G11-G14 (header+DDD+security+robustez)
│   ├── run_orbital.py             G7 (cross-module DDD)
│   ├── run_metrics_gate.py        G16 (dashboard wire)
│   ├── run_test_isolation.py      G19 (testes nao escrevem producao)
│   ├── run_datasource_wire.py     G20 (bypass DataSource)
│   ├── run_preflight_parquet.py   G21 (integridade Parquet)
│   ├── run_preflight_deps.py      G22 (checklist deps VBT/TF)
|   ├── run_consolidate_parquet.py | G23 (merge + gap scan + gap report)
|   ├── run_orchestrator_wire.py | G24 (ORQ/SAT/UTIL — 160 funcoes mapeadas)
|   └── ...
| ├── tests/                         TESTES unit + harness (276 tests: 274 pass, 2 skip, 188s)
| │   ├── test_backtest_simulator.py    S30 backtest harness (6/6)
| │   ├── test_f2_fusion.py             F2 fusao (2/2)
| │   ├── test_orc_ranking.py           S35 ranking (3/3)
| │   ├── test_orc_pattern.py           S30 pattern (4/4)
| │   ├── test_orc_mercado.py           S25 mercado (3/3)
| │   ├── test_orc_indices.py           S25.10 indices (3/3)
| │   ├── test_orc_vectorbt.py          S27 vectorbt (2/2)
| │   ├── test_orc_vbt_portfolio.py     S30-VBT portfolio (2/2)
| │   ├── test_vista_orc_mercado.py     S39 vista (3/3)
| │   ├── test_f0_supervisor.py         Supervisor F0 (3/3)
| │   ├── test_orc_calibracao.py        S36 calibracao (3/3)
| │   ├── test_bloco1_ranking_metrics.py   S41 ranking empirico (4/4)
| │   ├── test_bloco2_oco_layers.py        S42 camadas OCO + correlacao (2/2)
| │   ├── test_bloco2_backtest_full.py     S42 backtest 7 camadas (4/4)
├── specs/                         DOCS (SSOT)
│
├── data/ status/ logs/            RUNTIME
├── legacy/                        FORA DO INDEX
└── 99_archive/                    ARQUIVADO
```

---

## 4. HIERARQUIA DE BOOT (ordem de execucao)

### Nivel 1 — BOOT (Fase 0)

```
run.ps1 (Abrir_NeoCortex_NovaPulse.ps1)
  ├── PRE-FLIGHT                    Ruff + 5 mercados + harness tests
  ├── PRE-BOOT                      Kill stale processes
  ├── harness_boot.py               Valida 10 orquestradores
  └── G11-G14                       Conformance gates
        └── F0 INIT                 init_client() + resolve_symbols()
```

| Passo | O que faz | Falha = |
|-------|----------|---------|
| 0. PRE-FLIGHT | Ruff, Parquet 5/5, backtest DB, harness tests | Warn — nao bloqueia |
| 1. PRE-BOOT | Encerra processos anteriores | Warn |
| 2. harness_boot | Importa + valida todos ORQ | Bloqueia — ctrader nao sobe |
| 3. G11-G14 | Headers, DDD, security, robustez | Bloqueia |
| 4. F0 init | Conecta MCP, resolve simbolos | Bloqueia |

### Nivel 2 — LATERAIS (executam em paralelo ou sequencia)

```
                    ┌─────────────────┐
                    │     BOOT OK     │
                    └────────┬────────┘
         ┌───────────────────┼───────────────────┐
         ▼                   ▼                   ▼
   ┌──────────┐       ┌──────────┐        ┌──────────┐
   │ DASHBOARD│       │ METRICS  │        │ HARNESS  │
   │  :5173   │       │ :7744    │        │   G6     │
   └──────────┘       └──────────┘        └──────────┘
         │                   │                   │
         └───────────────────┼───────────────────┘
                             ▼
         ┌───────────────────┼───────────────────┐
         ▼         ▼         ▼         ▼         ▼
      ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐  ┌─────┐
      │ F0  │  │ F1  │  │ F2  │  │ F3  │  │ F4  │
      │COLE.│→ │ANAL.│→ │FUS. │→ │VAL. │→ │EXEC.│
      └─────┘  └─────┘  └─────┘  └─────┘  └──┬──┘
                                              │
                            ┌─────────────────┘
                            ▼
                       ┌─────┐     ┌──────────┐
                       │ F5  │────→│ RANKING  │
                       │ MAR │     │ (off-loop)│
                       └─────┘     └──────────┘
```

| Item | Tipo | Execucao | Spec |
|------|------|---------|------|
|| **DASHBOARD** | Hub | Lateral (servidor HTTP) | S21 |
|| **METRICS** | Hub | Lateral (API metrics) | S20 |
|| **MERCADO** | Hub | Lateral (normalizacao mercado) | S25 |
|| **INDICES** | Hub | Lateral (DXY sintetico + sentiment) | S25.10 |
|| **DATASOURCE** | Hub | Lateral (leitura unificada S26) | S26 |
|| **VECTORBT** | Hub | Lateral (indicadores + backtest) | S25 F2 |
|| **STORAGE** | Hub | F0 (persistencia Parquet) | S2.5 |
|| **DATASOURCE** | Infra | Leitura unificada snapshot+contratos (S26) | S26 |
|| **HARNESS** | Gate | Lateral (G6 pre-flight) | S0 |
| **F0** | Fase | Pipeline (coleta) | S2 |
| **F1** | Fase | Pipeline (analise) | S3 |
| **F2** | Fase | Pipeline (fusao) | S4 |
| **F3** | Fase | Pipeline (validacao) | S5 |
| **F4** | Fase | Pipeline (execucao) | S6 |
| **F5** | Fase | Pipeline (MAR) | S7 |
| **RANKING** | Off-loop | Sob demanda | S5 |

### Nivel 3 — DDD: PAIS + FILHOS

#### DASHBOARD (`utils/orc_dashboard.py`, 406L)
```
orc_dashboard (ORQ)                              Comprovacao: boot + test_pipeline_artifacts
  ├── health.py (SAT)           Heartbeat+decay   Comprovacao: SEM PROVA
  ├── f0_supervisor_orc_dashboard.py (SAT, novo)  Comprovacao: SEM PROVA (2026-07-28)
  │     status/start/stop/restart F0 via psutil + status/f0.pid (ROADMAP 1.8)
  └── consome: orc_metricas, orc_ordens, json_log
```

#### METRICS (`utils/orc_metricas.py`, 227L)
```
orc_metricas (ORQ)                               Comprovacao: boot
  └── json_log_orc_metricas.py (SAT)  JSON log   Comprovacao: SEM PROVA (importado indiretamente)
```

#### MERCADO (`utils/orc_mercado.py`, NOVO S25)
```
orc_mercado (ORQ)                                Comprovacao: boot (harness_boot)
  ├── normalize_markets()    indicadores padro.  Comprovacao: boot · testado via curl /vector/markets
  ├── _read_snapshot()       le snapshot F0      Comprovacao: boot
  └── PIP_SPECS              lookup hardcoded    Comprovacao: boot
```

#### INDICES (`utils/orc_indices.py`, NOVO S25.10)
```
orc_indices (ORQ)                                Comprovacao: boot
  ├── fetch_indices()        DXY,VIX,SPX,US10Y   Comprovacao: boot (yfinance cache 5min)
  └── correlate_with_markets()  DXY vs ativos    Comprovacao: boot
```

#### HARNESS (`tests/harness_boot.py`)
```
harness_boot (HARNESS — nao ORQ)                 Comprovacao: boot (valida 10/10 ORQs)
  ├── harness_f0_coleta.py     Exemplo per-fase  Comprovacao: SEM PROVA (template, nao teste)
  └── harness_runner.py (G6)   Orquestra boot    Comprovacao: G6 gate
```

#### F0 — COLETA (`f0_collector/`)
```
orc_coleta (ORQ, 247L)                           Comprovacao: boot + test_f0_collector + test_f0_snapshot
  ├── poller_orc_coleta.py (SAT)   poll_cycle()  Comprovacao: boot + test_f0_min_candles
  └── storage_orc_coleta.py (SAT)  save_parquet  Comprovacao: boot + test_f0_backfill
```

#### F1 — ANALISE (`f1_analyzer/`)
```
orc_analise (ORQ)                                Comprovacao: boot + test_f1_scores
  ├── pillars_orc_analise.py (SAT)    BBANDS/ATR Comprovacao: boot + test_f0_pivots
  ├── micro_orc_analise.py (SAT)      spread+cor Comprovacao: boot + test_f1_micro
  ├── sentiment_orc_analise.py (SAT)  contrarian Comprovacao: SEM PROVA
  ├── dxy_orc_analise.py (SAT)        DXY multi  Comprovacao: boot (transitivo micro) + test_f1_micro
  ├── indicators_orc_analise.py (SAT) compartil. Comprovacao: boot + test_f1_indicators_parity
  ├── news_orc_analise.py (CORT)      MCP s/news Comprovacao: CORTADO — esperado
  ├── ichimoku_orc_analise.py (CORT)  Cortado v1 Comprovacao: CORTADO — esperado
  └── volume_orc_analise.py (CORT)    0 imports  Comprovacao: CORTADO — esperado
```

#### F2 — FUSAO (`f2_fusao/`)
```
orc_fusao (ORQ)                                  Comprovacao: boot + test_f2_fusion
  └── (sem filhos — logica concentrada)
```

#### F3 — VALIDACAO (`f3_validacao/`)
```
orc_validacao (ORQ, 154L)                        Comprovacao: boot + test_f3_fallback
  └── (sem filhos — IA removida, so mecanico)
```

#### F4 — EXECUCAO (`f4_executor/`)
```
orc_execucao (ORQ, 150L)                         Comprovacao: boot
  ├── monitor_orc_execucao.py (SAT)   D0→D80     Comprovacao: boot + test_f4_trail_be
  ├── safety_orc_execucao.py (SAT)    ATR spike  Comprovacao: boot + test_f4_ghost_order
  ├── entry_orc_execucao.py (SAT)    calculate   Comprovacao: SEM PROVA
  └── gates_orc_execucao.py (SAT)    margem      Comprovacao: SEM PROVA

orc_ordens (ORQ, 38L)                            Comprovacao: boot
  ├── entry_params_orc_ordens.py (SAT, 82L)      Comprovacao: SEM PROVA
  ├── oco_orc_ordens.py (SAT, 71L)               Comprovacao: SEM PROVA
  └── scalp_timeout_orc_ordens.py (SAT, 44L)     Comprovacao: SEM PROVA
```

#### F5 — MAR (`f5_mar/`)
```
orc_mar (ORQ)                                    Comprovacao: boot + test_f5_mar
  ├── rules_orc_mar.py (SAT)          Pesos      Comprovacao: SEM PROVA
  ├── trades_log_orc_mar.py (SAT)     Schema     Comprovacao: SEM PROVA
  └── mcp_sync_orc_mar.py (SAT)       Historico  Comprovacao: SEM PROVA
```

#### RANKING (`f3_validacao/orc_ranking.py`) ← MOVED D1
```
orc_ranking (ORQ)                                Comprovacao: boot
  └── (sem filhos — rank_signals() mecanico)     Comprovacao: SEM PROVA (funcao nao testada isoladamente)
```

#### CALIBRACAO (`utils/orc_calibracao.py`, S36)
```
orc_calibracao (ORQ)                             Comprovacao: test_orc_calibracao
  ├── append_signals()      dedup signals_log    Comprovacao: test_orc_calibracao
  ├── reconcile()           fecha outcomes M1    Comprovacao: test_orc_calibracao
  └── calibration_summary() hit-rate/Brier/drift Comprovacao: test_orc_calibracao
```

#### SCORE (`f2_fusao/orc_score.py`) ← MOVED D2
```
orc_score (ORQ)
  └── signal_emitter_orc_score.py (SAT)          Comprovacao: test_signal_emitter
        emissor live: score_live.json + signals_log anti-flood
```

#### SCAN (`utils/orc_scan.py`, ORQ CLI batch — S34)
```
orc_scan (ORQ, CLI offline)                      Comprovacao: test_orc_scan
  └── matrix_orc_scan.py (SAT)                   Comprovacao: test_orc_scan
  └── matrix_orc_quality.py (SAT de orc_quality) Comprovacao: test_orc_scan

#### VISTA (`utils/vista_orc_mercado.py`, SAT de orc_mercado — S39)

vista_orc_mercado (drill-down /vector/symbol/{sym}.vista)
  └── families_orc_vectorbt.py (via storage_orc_consolidated) Comprovacao: manual 16/16 5/5
        helpers numpy: feature_matrix, cosine, decay, stats, replay row
```

#### GATEWAY (`utils/mcp_client.py`, 706L)
```
mcp_client (GATEWAY — GOD justificado)           Comprovacao: test_f0_gateway_throttle (throttle+cache)
  ├── Throttle: token-bucket 50/s live, 5/s      Comprovacao: test_f0_gateway_throttle
  ├── Cache: TTL 1s spot, 30s candles            Comprovacao: test_f0_gateway_throttle
  ├── Keep-alive + reconnect                     Comprovacao: SEM PROVA
  └── 16 tools MCP                               Comprovacao: G10 contract (17 call-sites)
```

#### MODULOS SEM PROVA (achados — nao esconder)

| Modulo | Tipo | Motivo |
|--------|------|--------|
| `sentiment_orc_analise.py` | SAT F1 | Importado pelo ORQ, sem teste isolado |
| `entry_orc_execucao.py` | SAT F4 | Importado pelo ORQ, sem teste isolado |
| `gates_orc_execucao.py` | SAT F4 | Importado pelo ORQ, sem teste isolado |
| `entry_params_orc_ordens.py` | SAT F4 | Importado pelo ORQ, sem teste isolado |
| `oco_orc_ordens.py` | SAT F4 | Importado pelo ORQ, sem teste isolado |
| `scalp_timeout_orc_ordens.py` | SAT F4 | Importado pelo ORQ, sem teste isolado |
| `rules_orc_mar.py` | SAT F5 | Importado pelo ORQ, sem teste isolado |
| `trades_log_orc_mar.py` | SAT F5 | Importado pelo ORQ, sem teste isolado |
| `mcp_sync_orc_mar.py` | SAT F5 | Importado pelo ORQ, sem teste isolado |
| `health.py` | UTIL | Sem teste dedicado |
| `json_log_orc_metricas.py` | SAT metrics | Importado indiretamente, sem teste isolado |
| `orc_ranking.py` (funcoes) | ORQ | ORQ coberto por boot, mas rank_signals() sem teste unitario |
| `mcp_client.py` (keep-alive) | GATEWAY | Throttle/cache testados, keep-alive/reconnect sem teste |
| `f0_supervisor_orc_dashboard.py` | SAT dashboard | Novo 2026-07-28, sem teste isolado (usa psutil, dificil mockar processo real) |

> **Nota:** "SEM PROVA" nao significa codigo quebrado. Significa que o harness_boot valida
> o import e a existencia, mas nao ha teste unitario dedicado exercitando a logica do modulo.
> 10/10 ORQs tem `boot` + teste dedicado (ou funcao core testada).
> 8/8 ORQs uncovered agora cobertos (test_orc_ranking, test_orc_pattern, etc).
> 34/34 modulos totais estao como PROVA (129 tests, 48.9s).

---

## 5. RUNTIME — Artefatos gerados

| Artefato | Gerado por | Consumido por |
|---------|-----------|--------------|
| `status/snapshot.json` | F0 (take_snapshot, a cada tick) | F1..F5, dashboard |
| `status/f0.pid` | F0 (auto-registro em main(), ROADMAP 1.8) | f0_supervisor_orc_dashboard (status/stop) |
| `status/metrics.json` | json_log (F0..F5) | orc_metricas, dashboard, vectorbt |
| `scores_raw.json` | F1 | F2 |
| `fusion_output.json` | F2 | F3, F4, F5 |
| `verdict.json` | F3 | F4 |
| `ranking.json` | orc_ranking | F4 |
| `custom_rules.json` | F5 | F2 (realimenta) |
| `trades.db` | F4 (log_trade_json) | F5 (orc_mar), vectorbt |
| `data/*.parquet` | F0 (storage) | F1, vectorbt |
| `data/backfill/{SYM}_M1.parquet` | backfill_orc_coleta.py (F0) | G23 consolidacao |
| `data/consolidated/{SYM}_M1.parquet` | G23 (run_consolidate_parquet.py) | S29/S30/VBT, gap fill |
| `status/gap_report.json` | G23 (gap scan ANCORADO 730d: window_days, expected_open_minutes, coverage honesto) | backfill --gaps, dev |
| `data/signals_log.parquet` | orc_score/orc_ranking (append na emissao) — PLANNED S36 | orc_calibracao (reconciliador) |
| `status/calibration.json` | orc_calibracao (hit-rate/Brier/ranking qualidade) — PLANNED S36 | aba 1 Geral, S35 pesos |
| `status/score_live.json` | signal_emitter_orc_score (ultimo ciclo por simbolo) — PLANNED S36 | orc_metricas → secao score_mercados (S20 v2.2) |
| `status/pattern_library.json` | orc_pattern --scan (batch offline 730d) — PLANNED S34 | orc_pattern runtime, S29 |
| `logs/system.jsonl` | logger.py | dev |

---

## DASHBOARD — Backend + Frontend

> **Wire**: ctrader → React dashboard. Fase atual: preparacao para wire.

### Backend (`10.0_ui_dash/`, porta 7744)

| Arquivo | Tipo | Funcao |
|---------|------|--------|
| `run_api.py` | SERVER | FastAPI entry point |
| `NC-10_dashboard_api.py` | ROUTER | /api/ctrader/* endpoints |
| `NC-10_tray_server.py` | TRAY | System tray |
| `routers/` | ROUTERS | API route modules |

**Consome**: `utils/orc_dashboard.py` → health_check_full() + collect_all()

### Frontend (`10.0_ui_dash/react-dashboard/`, porta 5173)

| Arquivo/Pasta | Tipo | Funcao |
|--------------|------|--------|
| `src/App.tsx` | APP | Root component |
| `src/main.tsx` | ENTRY | Vite entry |
| `src/domains/ctrader/sub-tabs/RankingView.tsx` | SUB-TAB | Ranking — pre-validacao replay vs live (S35) |
| `src/domains/ctrader/DomainGates.ts` | GATE | Anti-corruption layer — type guards (DG01) |
| `src/domains/audit/` | TAB | Auditoria |
| `src/domains/cascade/` | TAB | Cascata F0→F5 |
| `src/domains/pulse/` | TAB | Health pulse |
| `src/domains/db/` | TAB | DB explorer |
| `src/domains/kanban/` | TAB | Tickets |
| `src/domains/maker/` | TAB | Maker CLI |
| `src/domains/extensions/` | TAB | Extensoes |
| `src/domains/orbitals/` | TAB | Orbitais |
| `src/domains/mcps/` | TAB | MCP servers |
| `src/domains/fabricas/` | TAB | Fabricas |
| `src/domains/search/` | TAB | Busca |
| `src/domains/diagrams/` | TAB | Diagramas |
| `eslint.config.js` | LINT | ESLint (G17) |
| `oxlintrc.json` | LINT | Oxlint (G18) |
| `vite.config.ts` | BUILD | Vite + oxlint plugin |

### Fluxo de dados Dashboard

> **Mapa completo** (routers/ctrader_v2.py, NC-CTRADER-013, ~20 endpoints).
> Todos R-NO-MCP-BYPASS-compliant (leem snapshot F0), exceto os marcados ⚠️.

```
React (:5173) ──HTTP──→ FastAPI (:7744) /api/ctrader/*
                            │
   Aba Overview (nova, S21) ├── /health              → orc_dashboard.health_check_full() [snapshot F0]
                             ├── /banca              → orc_mercado + orc_dashboard (agregador S25.8)
                             ├── /account            → orc_dashboard.get_mcp_balance()    [snapshot F0] (legado, usar /banca)
                             ├── /positions          → orc_dashboard.get_mcp_positions()  [snapshot F0] (legado, usar /banca)
                             ├── /risk               → orc_dashboard.get_mcp_balance()    [snapshot F0]
                             ├── /metrics             → orc_dashboard.export_for_dashboard() [snapshot+json_log+vector_mercados S20 v2.1]
                             ├── /trades              → orc_dashboard.get_trade_history()
                             └── /plugins             → stub estatico (MCP nao expoe)
   Aba Pre-Analise           ├── /vector/markets      → orc_mercado.normalize_markets()    [snapshot F0]
                             ├── /vector/strength      → orc_mercado.strength_rank           [snapshot F0] (S25)
                             ├── /vector/indicators    → orc_mercado (ATR/RSI scaffold)      [snapshot F0] (S25)
                             ├── /vector/globals       → snapshot F0 + sentiment_orc_analise [DXY sem historico]
                             ├── /vector/correlation   ✅ orc_indices.correlate_markets_m1() [m1 parquet, 5x5 real]
                             ├── /vector/overview      ✅ REWIRE S25 — orc_mercado + orc_metricas
                             ├── /vector/symbol/{sym}  ✅ S28 — VBT + OHLCV + Multi-TF por mercado
                             ├── /vector/symbol/{sym}/history/{days} ✅ S2.5 — historico 2a YoY
                             ├── /vector/symbol/{sym}/quality    ✅ S29 — F1 score + backtest
                             ├── /vector/symbol/{sym}/patterns   ✅ S30 — pattern matching
                             └── /vector/symbol/{sym}/score      ✅ S32 — orc_score (proxy)
   Aba Validacao             ├── /validate/score75     → utils.orc_ranking.rank_signals()
                             └── /validate/normalize   → utils.orc_ranking.rank_signals()    [S25: migrado de _vector_db]
   Aba Ordens                └── /order/trail-log     → json_log_orc_metricas + entry_params_orc_ordens
   |   Aba Harness                ├── /harness             → subprocess pytest tests/ (via venv Python — 129 tests, 48.9s)
                             └── /health/fases        ✅ S33 — orc_health_fases.check_fases() (sub-aba Saude, todas as abas)
   Barra global (topo)        ├── /mcp/login           → mcp_client.set_session_token() [so RAM, nunca disco]
                             ├── /mcp/logout          → idem
                             ├── /mcp/session         → mcp_client.has_session_token()
                             ├── /f0/status            → f0_supervisor.f0_status() [status/f0.pid]
                             ├── /f0/start             → f0_supervisor.f0_start() [pre-flight A9]
                             ├── /f0/stop              → f0_supervisor.f0_stop()
                             ├── /f0/restart           → f0_supervisor.f0_restart()
                             ├── /backfill/status      ✅ S31-PROG — backfill_supervisor (progress+pid+coverage)
                             ├── /backfill/start       ✅ S31-PROG — spawn subprocesso (gaps|full)
                             └── /backfill/stop        ✅ S31-PROG — terminate via psutil
```

**Gaps conhecidos (atualizado 2026-07-29):** `/vector/overview`, `/vector/consolidated` e
`/validate/normalize` foram migrados de `vector._vector_db` (99_archive) para
`orc_mercado`/`orc_ranking`/`orc_metricas` — spec S25.
`/vector/panda` aguarda 14+ candles M_1 para pandas-ta indicators.
~~`/vector/correlation` sem historico~~ — RESOLVIDO (S2.5 warmup): matriz 5x5 real
via `orc_indices.correlate_markets_m1()` sobre m1_*.parquet (200 velas/boot).
`/vector/globals` (DXY score) segue sem janela historica no snapshot — usa
refs fixas; evolucao futura: derivar do m1 parquet tambem.

---

## 6. LEGADO

| Pasta | Por que |
|-------|--------|
| `legacy/` | vectorbt_calibrator, _archive_*.py, blueprint, prompts, references, manifest |
| `99_archive/` | dashboard.py, _vector_db.py, 25 specs antigos |

---

## 7. AUDITORIAS VIVAS

Movidas de `99_archive/` para `specs/` — nao sao specs de fase (nao tem numero S),
sao relatorios de auditoria mantidos atualizados junto do rewire S25.

| Arquivo | O que audita |
|---------|--------------|
| specs/vectorbt_gap_analysis.md | 21 features vectorbt 0.26.0 — prioridades 1-5 |
| status/vectorbt_gap_analysis_S27.md | 8 gaps S27 + gate VBT + 3 SATs |
---

<!-- G11: spec_files mapping (machine-readable) -->
<!-- G8: spec catalog (plain text, para regex parsing) -->
```python
spec_files = {
    "S0": "00_visao_geral.md",
    "S1.1": "mcp_endpoints.md",
    "S2.5": "orc_coleta.md",
    "S3": "orc_analise.md",
    "S4": "orc_fusao.md",
    "S5": "orc_validacao.md",
    "S5.1": "strategy_3scalps_5markets.md",
    "S6": "orc_execucao.md",
    "S7": "orc_mar.md",
    "S17": "orc_analise.md",
    "S18": "vectorbt_ecosystem.md",
    "S19": "fluxo_logs.md",
    "S20": "orc_metricas.md",
    "S21": "orc_dashboard.md",
    "S22": "orc_dashboard_abas.md",
    "S25": "orc_vector_rewire.md",
    "S26": "orc_datasource.md",
    "S27": "orc_vectorbt_overview.md",
    "S28": "orc_estrategia.md",
    "S29": "orc_quality.md",
    "S30": "orc_pattern.md",
    "DG01": "domain_gates.md",
    "G24": "g24_orchestrator_wire.md",
    "S31": "orc_consolidacao.md",
    "S32": "orc_score.md",
    "S33": "orc_health.md",
    "S34": "orc_pattern_engine.md",
    "S35": "orc_ranking.md",
    "S36": "orc_calibracao.md",
    "S39": "vista_mercado.md",
    "B01": "boot_unificado.md",
}
```
