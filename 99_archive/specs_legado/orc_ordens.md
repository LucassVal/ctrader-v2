# SPEC S6 | Versao: 2.0 | Wire: f4_executor/orc_ordens.py | Status: active

## PROPOSITO
F4-sub — Orquestrador de ordens: MARKET/OCO + trail + scalp timeout.
Re-exporta satelites de entry params, OCO e timeout. E chamado por orc_execucao.

## FLUXO
```
orc_execucao ──→ orc_ordens (re-exporta)
                    │
                    ├── entry_params_orc_ordens: ORDER_PARAMS, calculate_entry_params()
                    ├── oco_orc_ordens: validate_signal_for_entry(), execute_oco_order()
                    └── scalp_timeout_orc_ordens: check_scalp_timeout()
```

## ORQUESTRADOR — `f4_executor/orc_ordens.py` (38L)

| Function | Descricao |
|----------|----------|
| `ORDER_PARAMS` | Dict com parametros por estrategia (S1/S2) |
| `get_params(strategy)` | Retorna params para estrategia |
| Re-exporta | Todos os satelites |

## FILHOS

### `entry_params_orc_ordens.py` (82L)
- **Deve**: Calcular lot_size, SL, TP, entry_price por estrategia
- **Deve**: Respeitar ATR como multiplicador de distancia
- **Deve**: Validar spread contra ATR antes de permitir entrada
- **Entrada**: signal dict (symbol, strategy, score)
- **Saida**: ORDER_PARAMS dict (lot, sl_pips, tp_pips, entry_offset)

### `oco_orc_ordens.py` (71L)
- **Deve**: validate_signal_for_entry() — confirma se sinal ainda e valido
- **Deve**: execute_oco_order() — envia MARKET + SL/TP via F0
- **Deve**: Verificar margem disponivel antes de enviar
- **Deve**: Registrar ordem no json_log

### `scalp_timeout_orc_ordens.py` (44L)
- **Deve**: check_scalp_timeout() — timeout S1=5min, S2=15min
- **Deve**: Se timeout → BE ou fecha posicao
- **Deve**: Registrar timeout no json_log
