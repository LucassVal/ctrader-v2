# SPEC S25: R-USE: ALTERNATIVAS — MCP LIMITAÇÕES × SOLUÇÕES NOSSO CÓDIGO
>**Versao:** 1.0.0  
>**Wire:** `specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## R1 — VIX (proxy: ATR)

**Problema:** cTrader MCP só expõe forex, sem índices (VIX não disponível).  
**Solução (R-USE):** ATR como proxy de volatilidade do mercado.

| Ativo | ATR proxy | Cálculo | Arquivo |
|-------|-----------|---------|---------|
| XAUUSD | ATR(14) em pips | `safety_orc_execucao.py:get_atr(symbol, "M_15")` | `f4_executor/safety_orc_execucao.py` |
| EURUSD | ATR(14) em pips | `safety_orc_execucao.py:get_atr(symbol, "M_15")` | `f4_executor/safety_orc_execucao.py` |
| Todos | ATR(14) × 2 = banda volatilidade | `pillars_orc_analise.py:calc_atr_band()` | `f1_analyzer/pillars_orc_analise.py` |

**Wire:** F4 `safety_orc_execucao.py` → `entry_orc_execucao.py` → SL/TP = ATR × RR_RATIO  
**Validação:** ATR > 0 e < 5% do preço (sanity gate F4).

---

## R2 — DOM/Order Book (proxy: spread + tick_volume)

**Problema:** DOM/Order book removido do MCP v0.4.0.  
**Solução (R-USE):** Spread (bid-ask) + tick_volume spike como proxy de liquidez/profundidade.

| Indicador | Proxy | Cálculo | Arquivo |
|-----------|-------|---------|---------|
| Profundidade | Spread = ask - bid | `micro_orc_analise.py:calculate_spread()` | `f1_analyzer/micro_orc_analise.py` |
| Pressão compra/venda | Volume spike ratio | `_volume.py:detect_volume_spike()` | `f1_analyzer/_volume.py` |
| Tendência volume | SMA_short / SMA_long | `_volume.py:calculate_volume_trend()` | `f1_analyzer/_volume.py` |

**Wire:** F1 `micro_orc_analise.py` + `_volume.py` → scores F1 → F2 fusion → F3 IA.  
**Heurística:** Spread < 0.1% = líquido; spike ratio > 2.0 = entrada institucional.

---

## R3 — Account Statistics (proxy: get_positions + get_balance)

**Problema:** `get_account_statistics()` não existe no MCP.  
**Solução (R-USE):** Calcular estatísticas via `get_positions()` + `get_balance()`.

| Estatística | Cálculo | Arquivo |
|------------|---------|---------|
| Win rate | trades vencedores / total | `f5_mar/rules_orc_mar.py` (via `trades.db`) |
| Drawdown | (equity_max - equity_min) / equity_max | `utils/metrics.py` |
| Long/short ratio | posições long / total | `f1_analyzer/sentiment_orc_analise.py` |
| Profit factor | gross_profit / gross_loss | `f5_mar/rules_orc_mar.py` |
| Sharpe | (retorno - risk_free) / std_dev | `f5_mar/rules_orc_mar.py` |
| Exposure % | margem_usada / equity | `f4_executor/gates_orc_execucao.py` |

**Wire:** `get_positions()` → `sentiment_orc_analise.py` → F1 score → F2 fusion.  
**Wire:** `get_balance()` → `gates_orc_execucao.py` → F4 pre-flight check.

---

## R4 — Correlação entre ativos

**Problema:** Sem dados de correlação no MCP.  
**Solução (R-USE):** Matriz de correlação calculada localmente via `df_master`.

| Métrica | Arquivo |
|---------|---------|
| Matriz 5×5 correlação | `f1_analyzer/micro_orc_analise.py:calculate_correlation_matrix()` |
| DXY score (força dólar) | `f1_analyzer/micro_orc_analise.py:calculate_global_dxy_score()` |

**Wire:** F1 `micro_orc_analise.py` → F2 fusion → score diversificação.

---

## BANCO DE DADOS DO VECTOR

**Problema:** Vector engine usa apenas arquivos JSON/Parquet, sem persistência transacional.  
**Solução:** SQLite como banco único do vector (mesmo schema do `trades.db`).

```
vector/
  NC-11_VECTOR-ENGINE.py    → loop principal (spotter/sniper)
  NC-11_VECTOR-GUARDRAILS.py → constraints de segurança
  NC-11_VECTOR-ORDERMGR.py  → gestão de ordens
  NC-11_VECTOR-SESSION.py   → sessão (trace_id, estado)
  NC-11_VECTOR-PAYLOADS.py  → templates DeepSeek
  _vectordb_orc_mar.py             → NOVO: camada SQLite (trades, sinais, logs)
```

### Schema `vector.db`:

```sql
CREATE TABLE IF NOT EXISTS vector_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timestamp REAL NOT NULL,
    spotter_score REAL,        -- 0-100 (spotter IA)
    sniper_score REAL,         -- 0-100 (sniper IA)
    fusion_score REAL,         -- 0-100 (spotter + sniper)
    signal TEXT,               -- BUY/SELL/NEUTRAL
    confidence REAL,           -- 0.0-1.0
    payload_json TEXT,         -- DeepSeek response raw
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vector_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT NOT NULL,
    signal_id INTEGER REFERENCES vector_signals(id),
    order_id TEXT,             -- MCP orderId
    position_id TEXT,          -- MCP positionId
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    volume REAL,               -- lots
    entry_price REAL,
    sl REAL,
    tp REAL,
    status TEXT,               -- PENDING/FILLED/CLOSED/CANCELLED
    pnl REAL,
    exit_reason TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Pandas no vector: ✅ Compatível

O `.venv` do Neocortex tem pandas 3.0.5 + numba 0.66.0. O vector pode usar pandas para:
- `pd.read_sql()` → carregar histórico de sinais
- `df.rolling()` → médias móveis para scores
- `df.corr()` → correlação entre sinais spotter/sniper

**Wire:** `_vectordb_orc_mar.py` → `NC-11_VECTOR-ENGINE.py` → `executar_loop()`.

---

## WIRE COMPLETO — ORQUESTRADORES × MÉTRICAS × DASHBOARD

```
┌──────────────────────────────────────────────────────────────┐
│                   DASHBOARD React (:5173)                    │
│  4 abas × 15 sub-abas  ←── 12 endpoints :7744               │
└──────────────────────────┬───────────────────────────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
         /metrics      /health      /validate/*   /order/*
              │            │            │            │
              ▼            ▼            ▼            ▼
┌─────────────────────────────────────────────────────────────┐
│              orchestrator.py (camada única)                  │
│                                                             │
│  export_for_dashboard():                                    │
│    ├── f0_coleta     ← F0 orc_coleta.py                        │
│    ├── f1_f2_analise ← F1 orc_analise.py                        │
│    ├── f3_ia         ← f3_validator.py + DeepSeek           │
│    ├── f4_execucao   ← F4 orc_execucao.py + orc_ordens.py       │
│    ├── f5_mar        ← F5 orc_mar.py                        │
│    ├── vector        ← _vectordb_orc_mar.py                        │
│    ├── ranking       ← orc_ranking.py (DeepSeek ≥75%)      │
│    └── orders        ← orc_ordens.py (OCO+trail+BE+80/60)  │
│                                                             │
│  health_check_full():                                       │
│    ├── mcp           ← MCP get_balance + get_version         │
│    ├── f0/f4/f5      ← SQLite + MCP checks                  │
│    ├── gates         ← pytest G6                             │
│    ├── logger        ← system.jsonl                          │
│    ├── vector        ← _vectordb_orc_mar stats                      │
│    ├── ranking       ← orc_ranking candidates               │
│    └── orders        ← orc_ordens active                    │
└─────────────────────────────────────────────────────────────┘
```

### R-USE documentado:
- R1: VIX → ATR proxy ✅
- R2: DOM → spread + tick_volume ✅
- R3: Account stats → get_positions + get_balance ✅
- R4: Correlação → matriz local pandas ✅
