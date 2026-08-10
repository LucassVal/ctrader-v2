> **STATUS: CONSOLIDADO_EM `orc_vector_rewire.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S18: VECTOR DB — BANCO VETORIAL DE GOVERNANCA
> **Versao:** 1.0.0
> **Wire:** `vector/_vectordb_orc_mar.py`
> **Status:** DONE
> **R21:** validado 2026-07-23 — NAO confundir com vectorbt (backtest)
> **R-USE:** RULES.md §CAT1-Cognicao

---

## CRM (O que entrega)

SQLite de governanca do Neocortex V44. Armazena sinais, ordens e metricas
do ciclo de decisao para auditoria e replay.

**IMPORTANTE:** Este NAO e o vectorbt (biblioteca de backtest).
E o banco vetorial de governanca do sistema — registra o historico
de sinais gerados pelo pipeline F1→F2→F3.

### Tabelas

| Tabela | Proposito |
|--------|-----------|
| `signals` | Sinais gerados por ciclo (F1 scores, F2 fusion, F3 verdict) |
| `orders` | Ordens enviadas ao MCP (F4) |
| `metrics` | Metricas agregadas (win rate, PnL, drawdown) |

### Schemas

```sql
signals: id, timestamp_utc, symbol, timeframe, scores_json, fusion_score, verdict, meta_json
orders:  id, signal_id, order_type, volume, sl, tp, status, mcp_response_json, created_at
metrics: id, date, symbol, total_trades, wins, losses, win_rate, avg_pnl, sharpe
```

## FLUXO

```
F1→F2→F3 pipeline ──→ orc_ranking.py (consome fusion_output.json)
                              │
                        ranking.json (F3 artefact)
                              │
                        F4 executor (consome ranking)
                              │
                        _vector_db.save_order() ← auditoria
```
