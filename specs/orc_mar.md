# SPEC S7 | Versao: 2.0 | Wire: f5_mar/orc_mar.py | Status: active

## PROPOSITO
F5 — Monitoramento, Ajuste, Replay: calcula pesos por PnL real,
sincroniza historico MCP, alimenta vectorbt para recalibragem.

## FLUXO
```
trades.db ──→ orc_mar ──→ custom_rules.json ──→ F2 (orc_fusao)
                 │
     ┌───────────┼───────────┐
     ▼           ▼           ▼
  rules      trades_log   mcp_sync
 (pesos)     (schema)    (historico)
```

## ORQUESTRADOR — `f5_mar/orc_mar.py`
Entry points: `calibrate()`, `sync_history()`.

## FILHOS

### `rules_orc_mar.py`
- **Funcao**: calcula pesos por PnL real
- **Dados**: trades.db (get_trades_today)

### `trades_log_orc_mar.py`
- **Funcoes**: ensure_schema(), log_trade(), get_trades_today(), log_rotation()
- **DB**: trades.db (schema owner)

### `mcp_sync_orc_mar.py`
- **Funcao**: sincroniza historico MCP (get_trendbars, get_deals)
- **Uso**: vectorbt replay
