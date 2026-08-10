> **STATUS: CONSOLIDADO_EM `orc_execucao.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S6.1: SPEC: DDD — F4 EXECUTOR SPLIT
>**Versao:** 1.0.0  
>**Wire:** `f4_executor/orc_execucao.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## ARQUITETURA

```
f4_executor/
├── __init__.py          # Reexporta run_executor() — interface pública
├── orc_execucao.py           # Orquestrador: loop principal, heartbeat, dispatcher
├── gates_orc_execucao.py            # Funções puras: G1-G6 (margem, posições, slots, sessão)
├── entry_orc_execucao.py            # Função pura: place_market_order + cálculo SL/TP
├── monitor_orc_execucao.py          # Classe PositionMonitor: degraus D0-D80, trail BE, ghost
├── safety_orc_execucao.py           # Funções puras: ATR spike detector, kill switch, drawdown
└── log_trade_orc_execucao.py        # Função pura: persistência no SQLite (trades.db)
```

## CONTRATO DE INTERFACE (imutável)

```python
# f4_executor/__init__.py
from f4_executor.orc_execucao import run_executor

__all__ = ["run_executor"]
```

Chamada externa **não muda**: `from f4_executor import run_executor`

## RESPONSABILIDADES POR ARQUIVO

### `orc_execucao.py` — Orquestrador (≤ 200L)
- Loop principal `run_executor(config_path)`
- Inicialização: resolve símbolos, conecta MCP
- Heartbeat: verifica morte de processos
- Dispatcher: chama `_gates`, `_entry`, `_monitor`, `_safety`, `_log_trade`
- Gerenciamento de `active_monitors: dict`
- **NÃO contém**: lógica de degraus, cálculo de ATR, SQL

### `gates_orc_execucao.py` — Validação pré-entrada (≤ 80L)
- `check_gates(symbol_id, timeframe, lot_multiplier, ...) → (bool, str, float)`
- G1: margem (`get_balance`)
- G2: posições mesmo símbolo (`get_positions`)
- G3: slots (`slot_tracker.is_full`)
- G4/G5: sessão (`session_manager.is_trading_allowed`)
- G6: news_imminent → reduz lote
- **Pura**: sem estado interno, sem MCP direto (recebe dados)

### `entry_orc_execucao.py` — Entrada OCO (≤ 100L)
- `calculate_entry(symbol_id, lot_multiplier) → dict`
- Obtém `symbol_details`, `spot_prices`, ATR
- Calcula volume em UNITS, SL, TP
- `_mcp_retry("place_market_order", ...)`
- Retorna `{order_id, position_id, entry_price, sl, tp, spread, atr, status}`
- **Pura**: sem estado interno

### `monitor_orc_execucao.py` — PositionMonitor (≤ 200L)
- Classe `PositionMonitor`
- `update(current_price, current_pnl) → str | None`
- Degraus: D0 (BE rápido), D40 (anota), D60 (sobe SL), D80 (fecha 80% + reenvia OCO)
- Trail BE: `highest - ATR * 0.3`, trava `entry + spread`
- Timeout: `tempo sem highest > timeout_min`
- Ghost detection: `PENDING_FILL > 5s`
- `close(exit_price, exit_reason) → dict` (log)
- **Único com estado**: mantém flags de degraus

### `safety_orc_execucao.py` — Segurança (≤ 80L)
- `check_atr_spike(symbol_id) → bool`
- `check_drawdown(db_path, equity) → (bool, str)`
- **Puras**: sem estado interno

### `log_trade_orc_execucao.py` — Persistência (≤ 40L)
- `log_trade_to_db(log: dict) → None`
- Cria tabela `trades` se não existir
- Insere registro
- **Pura**: sem estado

## DEPENDÊNCIAS (imports)

```
orc_execucao.py → gates_orc_execucao, entry_orc_execucao, monitor_orc_execucao, safety_orc_execucao, log_trade_orc_execucao
gates_orc_execucao.py → utils/slot_tracker, utils/session_manager, utils/mcp_client
entry_orc_execucao.py → utils/mcp_client
monitor_orc_execucao.py → utils/mcp_client
safety_orc_execucao.py → utils/mcp_client (para get_trendbars, get_balance)
log_trade_orc_execucao.py → sqlite3 (stdlib)
```

## VALIDAÇÃO (GATES)

| Gate | Arquivos | Threshold |
|------|----------|-----------|
| G0 (ruff) | Todos os 7 | 0 erros |
| G1 (compile) | Todos os 7 | 0 erros |
| G2 (slop) | Todos os 7 | deficit < 30 |
| G3 (mock) | Diretório `f4_executor/` | "No mocking" |
| G4 (stub) | Todos os 7 | 0 stubs |
| G5 (linter) | `orc_execucao.py`, `monitor_orc_execucao.py` | 0 ERR |
| G6 (harness) | `tests/test_f4_trail_be.py` | PASS |
