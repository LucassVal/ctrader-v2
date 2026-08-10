# SPEC S6 | Versao: 2.0 | Wire: f4_executor/orc_execucao.py | Status: active

## PROPOSITO
F4 — Execucao: ordens MARKET/OCO + trail (D0→D80) + BE + scalp timeout.
Loop M_1: monitora posicoes abertas, aplica degraus, detecta ATR spike.

## FLUXO
```
F3 APPROVE ──→ orc_execucao ──→ orc_ordens (OCO/MARKET)
                      │
                      ├── monitor_orc_execucao (trail D0→D80)
                      ├── safety_orc_execucao (ATR spike → BE)
                      ├── entry_orc_execucao (calculate_entry)
                      ├── gates_orc_execucao (margem/slots)
                      └── json_log_orc_metricas (persiste trade)
```

## ORQUESTRADOR — `f4_executor/orc_execucao.py` (150L)
Wireia satelites. Entry point: `execute(approved_signals)` → loop M_1.

## FILHOS

### `orc_ordens.py` (38L) — Sub-orquestrador OCO
Re-exporta satelites de ordens:
- `entry_params_orc_ordens.py` (82L): ORDER_PARAMS + calculate_entry_params()
- `oco_orc_ordens.py` (71L): validate_signal + execute_oco_order()
- `scalp_timeout_orc_ordens.py` (44L): check_scalp_timeout()
- `trail_viewer_orc_ordens.py` ⚫ DEL — movido p/ json_log_orc_metricas

### `monitor_orc_execucao.py`
- **Classe**: PositionMonitor
- **Degraus**: D0 (BE rapido) → D40 (registra) → D60 (SL sobe) → D80 (fecha 80%, trail ativa)

### `safety_orc_execucao.py`
- **Funcoes**: detect_atr_spike(), detect_ghost_order()
- **Acao**: ATR spike → forca BE imediato

### `entry_orc_execucao.py`
- **Funcao**: calculate_entry() — wireado ao orc_execucao

### `gates_orc_execucao.py`
- **Funcoes**: check_margin(), check_positions(), check_slots(), check_session()

### ⚫ DELETADOS
| Arquivo | Destino |
|---------|---------|
| `log_trade_orc_execucao.py` | → `utils/json_log_orc_metricas.py` |
| `trail_viewer_orc_ordens.py` | → `utils/json_log_orc_metricas.py` |
