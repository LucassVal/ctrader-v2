# SPEC S22: Dashboard — Hierarquia DDD de Abas (v5.0)

> **Versao:** 5.0.0 | **Status:** active | **Atualizado:** 2026-08-05
> **Wire:** `CtraderTab.tsx` (orquestrador) → componentes em sub-tabs/
> **Mudanca v5.0**: +aba Simulacao (PRE-BETA XAUUSD Demo Live)
> **Mudanca v4.0**: Unificacao 6→5 abas. R-USE: zero componentes novos.

## REGRAS

1. **DASHBOARD e o pai** — abas de nivel 1 (Overview, Analise, Trading, Qualidade, Laboratorio, Simulacao)
2. **CTRADER e filho de DASHBOARD** — aba de nivel 1
3. **Sub-tabs sao netos** — dentro de CTRADER, cada sub-tab e um componente isolado
4. **Proibido GOD object** — cada sub-tab em arquivo proprio, max 200L
5. **Shared e KISS** — helpers (Card, MetricRow, useApi) compartilhados em shared/
6. **A13 (anti-drift)**: componente novo → classificar ORQ vs SAT antes de criar

## ABAS MESTRAS — v5.0 (6 abas)

### 1. Overview (`overview-main`)
| Sub-tab | Componente | Endpoints |
|---------|-----------|----------|
| Saude & Telemetria | OverviewHealth | /status, /health/fases |
| Banca & Mercado | OverviewBank | /banca |

### 2. Analise (`analise`)
| Sub-tab | Componente | Endpoints | Spec |
|---------|-----------|----------|------|
| [F0/F1] {sym} (x5) | MarketTab | /vector/symbol/{sym} | S28 |
| [F2] Globais & Contexto | GlobalsView | /vector/globals | S25 |
| [F2] Correlacao | CorrelationView | /vector/correlation | S25.10 |
| [F3] Live Tracker | LiveLogView | /validate/live-logs | — |
| [F3] Ranking & Decisao | RankingView | /validate/ranking | S35 |
| [F3] Score & Calibracao | ScoreCalibrationView | /metrics | S36 |
| Normalizacao | NormalizeView | /validate/normalize | — |

### 3. Trading (`trading`)
| Sub-tab | Componente | Endpoints | Spec |
|---------|-----------|----------|------|
| Ordens Ativas | OverviewBank | /banca (snapshot F0) | S21 |
| Historico | TrailLogView | /order/trail-log | — |
| Estrategia (Equity) | StrategyTab | /performance | S28 |
| Parametros | (inline Card) | — | — |

### 4. Qualidade (`qualidade`)
| Sub-tab | Componente | Endpoints | Spec |
|---------|-----------|----------|------|
| G6 Testes | HarnessView | /harness | G6 |
| Pipeline | PipelineView | pipeline F0-F5 | — |
| Health Fases | OverviewHealth | /health/fases | S33 |
| Conformance | STUB (Card placeholder) | G11-G14 (pendente) | DG01 |

### 5. Laboratorio (`laboratorio`)
| Sub-tab | Componente | Endpoints | Spec |
|---------|-----------|----------|------|
| Bloco 1 — Combo MAE/MFE | LabBloco1View | /lab/bloco1 | S41 |
| Bloco 2 — Camadas | LabBloco2View | /lab/bloco2 | S42 |
| Walkforward | LabWalkforwardView | /lab/walkforward | S43 |
| Padroes | LabPatternsView | /lab/patterns | S44 |

### 6. Simulacao (`simulacao`) ← NOVA v5.0 (PRE-BETA)
| Sub-tab | Componente | Endpoints | Spec |
|---------|-----------|----------|------|
| Circuit Breaker | **SimulacaoBreakerView** 🆕 | /simulacao/breaker | S42 |
| Sinais Live | **SimulacaoSinaisView** 🆕 | /simulacao/sinais | S41+S42 |
| Ordens Demo | **SimulacaoOrdensView** 🆕 | /simulacao/ordens | F4 |
| PnL & Metricas | **SimulacaoPnLView** 🆕 | /simulacao/pnl | PRE-BETA |
| Log Simulacao | **SimulacaoLogView** 🆕 | /simulacao/log | PRE-BETA |

## COMPONENTES NOVOS (v5.0)

| Componente | Tipo | R-USE |
|-----------|------|-------|
| `SimulacaoBreakerView.tsx` | Card 3 estados | Novo (~60L) |
| `SimulacaoSinaisView.tsx` | Tabela de sinais | Reusa LiveLogView adaptado (~80L) |
| `SimulacaoOrdensView.tsx` | Lista de ordens | Reusa TrailLogView adaptado (~70L) |
| `SimulacaoPnLView.tsx` | Equity curve + metricas | Reusa StrategyTab adaptado (~100L) |
| `SimulacaoLogView.tsx` | Log de trades | Reusa PipelineView adaptado (~60L) |

**Total: 5 componentes. ~370L. 4/5 com R-USE de componentes existentes.**

## ENDPOINTS NOVOS (/simulacao/*)

| Endpoint | Backend | Frontend |
|----------|---------|----------|
| `GET /simulacao/breaker` | `orc_bloco2` circuit_breaker state | SimulacaoBreakerView |
| `GET /simulacao/sinais` | Bloco1 + Bloco2 ultimos N sinais | SimulacaoSinaisView |
| `GET /simulacao/ordens` | F4 ultimas ordens enviadas | SimulacaoOrdensView |
| `GET /simulacao/pnl` | Equity curve + Sharpe + DD | SimulacaoPnLView |
| `GET /simulacao/log` | Trades executados + rejeicoes | SimulacaoLogView |

## PRE-FLIGHT SIMPLIFICADO (.bat)

```
Boot (.ps1):
  ├── Deps (check_deps.py)
  ├── Parquet 7 simbolos (5 ativos + 2 indices)
  ├── Backfill (ausentes) + GAPS (diario)
  ├── Backtest DB
  ├── Oxlint (React/ctrader)   ← cTrader + React apenas
  ├── Ruff (Python/ctrader)    ← cTrader apenas
  ├── Harness (pytest tests/)  ← cTrader apenas
  └── ORQ smoke (imports)      ← cTrader apenas
```

**Removidos do pre-flight geral:** checks genericos do Neocortex que nao sao cTrader.

## CHANGELOG

| Versao | Data | Mudanca |
|--------|------|---------|
| 5.0 | 2026-08-05 | +aba Simulacao (PRE-BETA), +5 sub-tabs, +5 endpoints /simulacao/*, pre-flight simplificado |
| 4.0 | 2026-08-01 | Unificacao 6→5 abas, R-USE 11 mudancas 0 componentes novos |
