# SPEC S25: Vector Rewire — Substituicao do _vector_db.py arquivado

> **Versao:** 1.0.0 | **Wire:** specs/INDEX.md | **Status:** active
> **Criado:** 2026-07-28 | **R21:** validado contra disco
> **Gap documentado:** INDEX.md L352-354 + L368-373

## PROPOSITO

Substituir as 4 rotas `/vector/*` que importam `vector._vector_db` (arquivado em
`99_archive/`) por fontes de dados reais do pipeline F0-F5.

## CONTEXTO

`_vector_db.py` era um banco SQLite que armazenava sinais e ordens. Foi substituido
por `trades.db` (F4) + `status/snapshot.json` (F0) + `json_log_orc_metricas` (S19).
As rotas `/vector/overview`, `/vector/consolidated`, `/vector/panda` e
`/vector/globals` nunca foram atualizadas — import falha silenciosamente,
retornando dados vazios ao React.

## S25.1 — Mapeamento de fontes

| Endpoint | Fonte antiga (99_archive) | Fonte NOVA |
|----------|--------------------------|-----------|
| `/vector/overview` | `_vector_db.get_stats()` + `get_recent_signals()` | `orc_mercado.normalize_markets()` + `orc_metricas.collect_all()` |
| `/vector/consolidated` | `_vector_db.get_recent_signals(20)` + `get_stats()` | `orc_ranking.rank_signals(min_score=75)` (top 10) |
| `/vector/panda` | `_vector_db` queries | `orc_mercado` — pandas-ta indicators (ATR, RSI via M_1 OHLCV) |
| `/vector/globals` | `_vector_db` + DXY sintetico | `dxy_orc_analise` + `sentiment_orc_analise` + `pillars_orc_analise` |
| `/vector/correlation` | snapshot 1 close/ciclo | mantido (ja usa snapshot) — aguarda extensao F0 |
| `/validate/normalize` | `_vector_db.get_recent_signals(10)` | `orc_ranking.rank_signals(min_score=75)` |

## S25.2 — Pipeline de dados (Visual)

```
F0 snapshot.json ────→ orc_mercado.normalize_markets() ──→ /vector/overview (strength_rank)
                   ────→ orc_metricas.collect_all()     ──→ /vector/overview (fases F0-F5)

F1 scores_raw.json ──→ orc_fusao.fuse() ──→ fusion_output.json
                                          ──→ orc_ranking.rank_signals() ──→ /vector/consolidated
                                          ──→ /validate/normalize

F0 OHLCV (M_1)     ──→ pandas-ta (ATR, RSI, MACD)      ──→ /vector/panda
                   ──→ dxy_orc_analise                  ──→ /vector/globals

F5 vectorbt         ──→ legacy/vectorbt_calibrator.py    ──→ (futuro) /performance
```

## S25.3 — VectorBT (S18) — Planejado, NAO wireado ainda

VectorBT 1.1.0 + vectorbt-rust 1.1.0 estao INSTALADOS no venv. O codigo de
backtest existe em `legacy/vectorbt_calibrator.py` mas:
- Depende de `v_historical_candles` (tabela que nao existe no `trades.db`)
- Usa SMA crossover placeholder (nao os 3 pilares da F1)
- Nunca foi wireado no pipeline ao vivo

### Quando wirear

Quando `trades.db` tiver dados reais (F0→F1→F2→F4 pipeline completo):
1. Criar `utils/orc_vectorbt.py` como wrapper limpo
2. `vbt.Portfolio.from_signals(close, entries, exits)` com sinais da F2
3. Exportar: Sharpe, max_drawdown, win_rate, profit_factor → `/performance`

## S25.4 — Panda (pandas-ta) — Parcialmente wireado

`pandas-ta-classic 0.6.52` instalado. Uso:
- `f1_analyzer/pillars_orc_analise.py`: BBANDS, ATR, ADX, EMA (via pandas-ta)
- `/vector/panda`: pode usar `pandas_ta.rsi()`, `pandas_ta.atr()` sobre OHLCV do snapshot

TA-Lib 0.7.1 NAO esta instalado (recomendado pelo spec S12.5 mas nao wireado).
Migracao pendente: `pip install TA-Lib` → 50x mais rapido que pandas-ta.

## S25.5 — Implementacao

### Fase 1 — Imediato (dados ja disponiveis)

- [x] `/vector/overview` → `orc_mercado` + `orc_metricas` (ja wireado S25.0)
- [x] `/vector/consolidated` → `orc_ranking.rank_signals(min_score=75)`
- [x] `/vector/markets` → `orc_mercado.normalize_markets()`
- [x] `/vector/strength` → `orc_mercado.strength_rank`

### Fase 2 — Curto prazo (precisa de 14+ candles M_1)

- [ ] `/vector/panda` → pandas-ta indicators (ATR, RSI, MACD) sobre OHLCV
- [ ] `/vector/indicators` → ATR, volatilidade, momento, RSI

### Fase 3 — Futuro (precisa de trades.db populado)

- [ ] `/performance` → vectorbt Portfolio stats (Sharpe, DD, win rate)
- [ ] `/vector/globals` → DXY real + sentimento + volatilidade cross-market

## S25.6 — Verificacao

```bash
# Apos implementar:
curl http://127.0.0.1:7744/api/ctrader/vector/overview | python -m json.tool
curl http://127.0.0.1:7744/api/ctrader/vector/consolidated | python -m json.tool
curl http://127.0.0.1:7744/api/ctrader/vector/strength | python -m json.tool

# Gates:
bash gates.sh --fast  # G16 deve reportar 17 sub-tabs OK, 0 erros
```

## S25.7 — Harness Pre-flight (G6)

`orc_mercado.py` (NOVO, S25) nao estava no `harness_boot.py`. Sem pre-flight,
um import quebrado no `utils/orc_mercado` so seria detectado quando o dashboard
tentasse acessar `/vector/markets` ou `/vector/overview` — falha silenciosa.

### Wire no harness_boot

```python
# tests/harness_boot.py — adicionar:
"MERCADO": {
    "module": "utils.orc_mercado",
    "attrs": ["normalize_markets", "_read_snapshot"],
    "children": [],
    "contract": "status/snapshot.json",
},
```

Total sobe de 10 → 11 orquestradores validados no pre-flight (G6).
Se `orc_mercado` nao importar, `harness_boot` falha e ctrader nao sobe (A9).

## S25.8 — Banca & Mercado (endpoint `/banca` + React OverviewBank)

Endpoint agregador que substitui 3 chamadas separadas (`/account`, `/positions`,
`/vector/markets`) por 1 unica. Adiciona secao de Performance com filtros
(7d/30d/60d/90d/custom) para grafico BID/WIN/LOSS quando houver historico.

### Fontes de dados

| Secao | Fonte | Status |
|-------|-------|--------|
| Conta (saldo, equity, margin, drawdown) | `snapshot.json` → `_normalize_balance()` | ✅ |
| Posicoes | `snapshot.json` → `get_positions()` | ✅ |
| Mercados ao vivo | `orc_mercado.normalize_markets()` | ✅ |
| Forca Global | `orc_mercado.strength_rank` | ✅ |
| Performance (BID/WIN/LOSS) | `get_deals()` MCP → `get_trade_history()` | ⚠️ EM IMPLEMENTACAO |

### Wire

```
/banca → ctrader_banca() → snapshot F0 + orc_mercado + get_trade_history()
                                                                   ↑
                                                            get_deals() MCP
```

### React

## S25.11 — Multi-TF via get_trendbars (substitui candles_buffer)

> **Status:** IMPLEMENTADO (2026-07-28)
> **Substitui:** S25.9 original (candles_buffer.py → 99_archive/)

O MCP cTrader ja fornece `get_trendbars(symbol, period, count)` com suporte a
H_1, H_4, M_15. Nao precisa acumular 60 velas M_1 — puxa direto do MCP.

### Pipeline

```
F0 (take_snapshot):
  poll_cycle()                            → snapshot.symbols (M_1)
  get_trendbars(sym, "m15", count=4)      → snapshot.trendbars[sym]["m15"]
  get_trendbars(sym, "h1",  count=2)      → snapshot.trendbars[sym]["h1"]
  get_trendbars(sym, "h4",  count=2)      → snapshot.trendbars[sym]["h4"]

orc_mercado._enrich_multi_timeframe(markets, snapshot):
  trendbars.m15 → change_15m, range_15m
  trendbars.h1  → change_1h,  range_1h
  trendbars.h4  → change_6h,  range_6h (aproximado)

Router /banca:
  get_snapshot() → inclui trendbars → normalize_markets(snap)
```

### Arquivos

| # | Arquivo | Acao |
|---|---------|------|
| 1 | `f0_collector/orc_coleta.py` | + get_trendbars no take_snapshot(), - candles_buffer.push() |
| 2 | `utils/orc_mercado.py` | _enrich_multi_timeframe le snapshot["trendbars"] |
| 3 | `routers/ctrader_v2.py` | /banca: snap["trendbars"] = full_snap.get("trendbars") |
| 4 | `CtraderTab.tsx` | Seletor [1m|15m|1h|6h] no OverviewBank |
| 5 | `99_archive/candles_buffer.py` | ARQUIVADO |
