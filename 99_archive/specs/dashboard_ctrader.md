> **STATUS: CONSOLIDADO_EM `orc_dashboard.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S20.1: SPEC S8.2: DASHBOARD CTRADER — 4 ABAS + 15 SUB-ABAS (v3.0)

>**Versao:** 1.0.0  
>**Wire:** `CtraderTab.tsx → routers/ctrader_v2.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


**TICKET:** NC-CTRADER-012 | **TRACE:** 660e8400-e29b-41d4-a716-446655440001

## Wire
```
CtraderTab.tsx (:5173) → routers/ctrader_v2.py (:7744) → orchestrator.py + _orc_*.py
```

## Estrutura (v3.0)

### Aba 1: Pré-Análise (6 sub-abas)
| Sub-aba | Endpoint | Fonte |
|---------|----------|-------|
| Overview Vector | `/vector/overview` | `_vector_db.get_stats()` + `/health` |
| Consolidação | `/vector/consolidated` | `_vector_db.get_recent_signals()` top 10 |
| Panda/VBT | `/vector/panda` | VectorBT métricas por símbolo |
| Globais | `/vector/globals` | DXY score + sentimento + volatilidade |
| Mercados | `/vector/markets` | 5 ativos bid/ask/spread |
| Correlação | `/vector/correlation` | Matriz 5×5 via `_micro.calculate_correlation_matrix()` |

### Aba 2: Validação (2 sub-abas)
| Sub-aba | Endpoint | Fonte |
|---------|----------|-------|
| Score 75%+ | `/validate/score75` | `orc_ranking.py` → DeepSeek revalida |
| Normalização | `/validate/normalize` | Prompt enxuto ~40 tokens/sinal |

### Aba 3: Ordens (2 sub-abas)
| Sub-aba | Endpoint | Fonte |
|---------|----------|-------|
| Trail Log | `/order/trail-log` | `_orc_orders.get_trail_log()` |
| Parâmetros | `/order/trail-log` | BE, D40, D60, D80, trail, 80/60, scalp timeout |

### Aba 4: Harness (3 sub-abas)
| Sub-aba | Endpoint | Fonte |
|---------|----------|-------|
| Health | `/health` | `orchestrator.health_check_full()` |
| G6 Testes | `/harness` | pytest 20/20 via `harness_runner` |
| Pipeline | `/metrics` | `orchestrator.export_for_dashboard()` |

## Orquestradores wireados ao `/metrics`
- `utils/orchestrator.py` — unifica trades.db + MCP + status JSON
- `utils/orc_ranking.py` — valida sinais ≥75% via DeepSeek
- `f4_executor/orc_ordens.py` — OCO + trail + BE + 80/60 + scalp timeout
- `f0_collector/orc_coleta.py` — coleta 5 ativos (M5/M15)
- `f4_executor/orc_execucao.py` — executor de ordens
- `f5_mar/orc_mar.py` — pesos adaptativos

## BOOT: PYTHONPATH fix
- `.ps1`: `$env:PYTHONPATH = $null`
- `run_api.py`: remove paths Hermes do `sys.path`
- Motivo: `pydantic_core` 3.11 (Hermes) quebra Python 3.12 (Neocortex)
