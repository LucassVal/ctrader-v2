# PROMPT HANDOFF — Neocortex V44 / cTrader V2 → Kimi Code

> **Data:** 2026-07-29 | **Sessao:** 8+ commits | **Estado:** codigo compila, servidores offline (precisa reiniciar)

---

## 1. ESCOPO DO PROJETO

Sistema autonomo de trading multi-mercado integrado ao Neocortex V44.

```
cTrader V2 (11.0_apps/ctrader/)
├── F0: Coletor MCP       → snapshot.json + Parquet OHLCV
├── F1: Analise           → indicadores Vector BT + ranking
├── F2: Fusao             → consolidacao de sinais
├── F3: Validacao         → gates de qualidade
├── F4: Execucao          → ordens OCO
├── F5: MAR               → metricas de risco/retorno
└── Dashboard React (:5173) + API FastAPI (:7744)
```

**5 mercados:** XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD
**Estrategias:** S1 Scalp Rapido (M_5), S2 Tendencia (M_15)
**Base de calculo VBT:** SEMPRE M_1 (demais TFs so para dashboard)

---

## 2. O QUE FOI FEITO NESTA SESSAO (8+ commits)

### Implementado
- **S28:** Abas por mercado (5 sub-tabs XAUUSD..AUDUSD) no React
- **S27:** Vector BT — 17 indicadores (RSI, MACD, ADX, BBANDS, Donchian, HMA, Keltner, CCI, PSAR, WPR, Aroon, ZLEMA, OBV, STOCH, SMA)
- **S29:** Qualidade de sinais — walk-forward backtest com F1/precision/recall
- **S30:** Pattern Matcher — sliding window + cosine similarity para encontrar setups similares no historico
- **S2.5:** Parquet persistente (OHLCV M_1 + VBT indicators)
- **G16:** Atualizado com novos sub-tab IDs (mkt-XAUUSD...)
- **G22:** Pre-flight com VBT Parquet + TF consolidation checks
- **Limpeza:** ichimoku, volume, news → 99_archive; yfinance removido
- **Harness:** 16/16 ORQs passando

### Pendente (PRECISA de ação)
- **Backfill 2 anos** → `python f0_collector/backfill_orc_coleta.py` (~60 min, 730 req/simbolo)
- **Reiniciar servidor** → API :7744 com `unset PYTHONPATH` (contaminacao do venv Hermes)
- **Reiniciar F0** → para `_persist_parquet()` comecar a gravar VBT
- **/vector/symbol/XAUUSD lento** → numba JIT 30s no primeiro request (normal)
- **G21+G22 wire no gates.sh** → bug de escape no patch tool

---

## 3. ONDE ESTAO OS ARQUIVOS

### Index & Specs (30 arquivos)
```
11.0_apps/ctrader/specs/
├── INDEX.md                  ← SSOT: mapeia specs → arquivos → endpoints
├── ROADMAP.md                ← v4.2: concluido + pendencias
├── QUALITY_GATES.md          ← G0-G22 catalogados
├── 00_visao_geral.md         ← overview do sistema
├── orc_coleta.md             ← S2.5: Parquet + backfill
├── orc_vectorbt_overview.md  ← S27: Vector BT (17 indicadores)
├── orc_estrategia.md         ← S28: Market tabs + charts
├── orc_quality.md            ← S29: F1 score + walk-forward
├── orc_pattern.md            ← S30: Pattern matching
├── orc_metricas.md           ← metrics orchestrator
├── orc_datasource.md         ← S26: DataSource layer
├── orc_vector_rewire.md      ← S25: Vector BT rewiring
├── strategy_3scalps_5markets.md ← estrategias S1/S2
└── ... (30 total, alguns obsoletos: orc_analise, vectorbt_ecosystem)
```

### Gates (13 arquivos)
```
11.0_apps/ctrader/gates/
├── gates.sh                  ← suite completa (G0-G22, mas G21-G22 nao wireados)
├── run_metrics_gate.py       ← G16: valida sub-tabs × endpoints
├── run_preflight_deps.py     ← G22: checklist ON/OFF (VBT Parquet, TF counts)
├── run_preflight_parquet.py  ← G21: integridade dos arquivos Parquet
├── run_conformance.py        ← lint/compile/import
└── ...
```

### React Dashboard
```
10.0_ui_dash/react-dashboard/src/domains/ctrader/
├── CtraderTab.tsx            ← main: tabs, sub-tabs, switch routing
├── MarketTab.tsx             ← S28: 1 aba por mercado (VBT + OHLCV + Multi-TF)
└── StrategyTab.tsx           ← S28: radar + heatmap + trend bars
```

### API Router
```
10.0_ui_dash/routers/ctrader_v2.py   ← 31 endpoints (FastAPI)
```

### Orquestradores (utils/)
```
11.0_apps/ctrader/utils/
├── orc_vectorbt.py           ← 17 indicadores (compute_indicators)
├── orc_quality.py            ← S29: generate_signals + backtest
├── orc_pattern.py            ← S30: sliding window + cosine similarity
├── storage_orc_vbt.py        ← save/load VBT Parquet
├── storage_orc_coleta.py     ← save/load OHLCV Parquet
├── data_source.py            ← S26: leitura unificada snapshot
├── orc_metricas.py           ← collect_all() → /metrics
├── orc_mercado.py            ← normalize_markets()
├── orc_ranking.py            ← rank_signals()
├── orc_indices.py            ← DXY sintetico + sentiment
└── mcp_client.py             ← wrapper MCP cTrader
```

---

## 4. COMO FUNCIONA

### Fluxo de dados
```
F0 MCP (1 min)
  ├── get_trendbars(sym, [m15, h1, h4])  ← batch multi-TF
  ├── snapshot.json                       ← cache rapido
  ├── data/m1_{SYM}_{ANO}.parquet         ← OHLCV historico (append)
  └── data/vbt_{SYM}.parquet              ← indicadores VBT (append)

Dashboard React (:5173)
  ├── Vite proxy /api → :7744
  ├── /api/ctrader/banca                  ← orc_mercado
  ├── /api/ctrader/vector/symbol/{sym}     ← VBT + OHLCV + Multi-TF
  ├── /api/ctrader/vector/symbol/{sym}/quality  ← S29
  ├── /api/ctrader/vector/symbol/{sym}/patterns ← S30
  └── /api/ctrader/vector/symbol/{sym}/score    ← S29+S30 combinado
```

### Pipeline de confianca
```
Parquet 2 anos
  ├── S29: regras deterministicas → F1 score baseline
  ├── S30: pattern matching → "setup X = 72% bullish"
  └── S30 /score: combined = quality_f1×0.33 + pattern_conf×0.67
```

### Abas do Dashboard
```
Overview
├── Health Check
└── Banca & Mercado

Pre-Analise
├── XAUUSD  ← MarketTab (VBT + OHLCV + Multi-TF)
├── EURUSD
├── GBPUSD
├── USDJPY
├── AUDUSD
├── Estrategia  ← StrategyTab (Radar + Heatmap + TrendBars)
├── Globais
└── Correlacao
```

---

## 5. O QUE QUEREMOS FAZER (proximos passos)

### Imediato (bloqueadores)
1. **Rodar backfill 2 anos** → `cd 11.0_apps/ctrader && ../../.venv/Scripts/python.exe f0_collector/backfill_orc_coleta.py`
2. **Reiniciar servidor API** → `unset PYTHONPATH && .venv/Scripts/python.exe 10.0_ui_dash/main.py` (porta 7744)
3. **Reiniciar F0** → script de boot com harness_boot passando
4. **Verificar Vite :5173** → `npx vite --host 0.0.0.0 --port 5173` (Oxlint 0 errors)

### Curto prazo
- **S30 no React** → criar aba "Padroes" ou card no MarketTab mostrando pattern matches
- **/performance com dados reais** → wire orc_vectorbt.compute_portfolio_stats() com trades.db
- **G3 YoY** → grafico de win/loss por mes (precisa trades.db)
- **G5 Sinais × Resultados** → scatter plot (precisa trades.db + scores F1)
- **Wire G21+G22 no gates.sh**

### Medio prazo
- **Limpar specs obsoletos** → orc_analise.md, vectorbt_ecosystem.md, orc_estrategia.md v1
- **Migrar para DTW** → Dynamic Time Warping no S30 (mais preciso que cosine)
- **Regime detection** → bull/bear/lateral classification
- **F1 wireado ao VBT** → gerar sinais reais do F1 usando indicadores VBT

---

## 6. REGRAS IMPORTANTES (RULES.md)

- **R-PYTHON-FIRST**: toda logica em .py
- **R-USE**: reusar antes de criar (storage_orc_vbt, orc_vectorbt, orc_quality)
- **R-SDD**: specs antes de codigo (INDEX.md e a verdade)
- **R21**: verificar disco antes de afirmar
- **R-NO-MCP-BYPASS**: so F0 fala com MCP
- **R-PORT-PATH-LOCK**: portas 7744/5173 fixas, nunca alterar
- **Oxlint no React**: `Array<T>` proibido → usar `T[]`; `any` proibido → usar `unknown`
- **Ruff no Python**: ambiguos `×` proibidos, f-string sem placeholder bloqueia
- **ASCII puro** em codigo, logs, commits
- **PT-BR** para nomes de dominio (dominio, versao, agente)
- **PYTHONPATH**: `unset` antes de rodar Python do Neocortex (contaminacao Hermes)

---

## 7. ARQUIVOS CHAVE PARA COMEÇAR

```
1. specs/INDEX.md                          ← SSOT: tudo mapeado aqui
2. specs/ROADMAP.md                        ← o que foi feito / pendente
3. routers/ctrader_v2.py                   ← 31 endpoints
4. utils/orc_vectorbt.py                   ← 17 indicadores
5. utils/orc_pattern.py                    ← S30 pattern matching
6. utils/storage_orc_vbt.py                ← Parquet persistence
7. react-dashboard/src/domains/ctrader/CtraderTab.tsx  ← main React
8. react-dashboard/src/domains/ctrader/MarketTab.tsx    ← per-market tab
9. gates/run_preflight_deps.py             ← G22 checklist
10. tests/harness_boot.py                  ← 16 ORQs
```
