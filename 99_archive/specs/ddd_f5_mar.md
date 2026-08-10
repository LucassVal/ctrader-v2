> **STATUS: CONSOLIDADO_EM `orc_mar.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S7.1: SPEC: DDD — F5 MAR SPLIT
>**Versao:** 1.0.0  
>**Wire:** `f5_mar/orc_mar.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## SPLIT

| Arquivo | Responsabilidade | Estimado |
|---------|-----------------|----------|
| `f5_mar/orc_mar.py` | Orquestrador: CLI, dispatch, calibrate_daily | ~80L |
| `f5_mar/db_orc_mar.py` | SQLite: schema, log_trade, ensure_schema | ~60L |
| `f5_mar/rules_orc_mar.py` | MAR: load/save rules, calcular_pesos, media movel | ~60L |
| `f5_mar/mcp_sync_orc_mar.py` | MCP: sync_trades, sync_candles | ~90L |
| `f5_mar/__init__.py` | Re-exporta funções públicas | ~10L |

## CONTRATO (não muda)

```python
from f5_mar import ensure_schema, log_trade, calibrate_daily, sync_trades_from_mcp, sync_candles_from_mcp
```

## INTERFACE EXTERNA

Nenhuma mudança nos callers:
- `f4_executor/orc_execucao.py` → `from f5_mar import log_trade` (mantido)
- `run.py` → `"script": "-m f5_mar.orc_mar"` (atualizar path)
- CLI: `python -m f5_mar.orc_mar --calibrate`
