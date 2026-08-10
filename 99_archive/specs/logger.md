> **STATUS: CONSOLIDADO_EM `fluxo_logs.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S19: SPEC S19: LOGGER JSON CATEGORIZADO
>**Versao:** 1.0.0  
>**Wire:** `utils/logger.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## CATEGORIAS

| Categoria | Descrição | Exemplo |
|-----------|-----------|---------|
| `OPERATION` | Loop principal, heartbeats | `F0 iniciado`, `F4 loop tick` |
| `MCP_CALL` | Chamada MCP bem-sucedida | `get_balance OK (234ms)` |
| `MCP_ERROR` | Erro MCP (timeout, sessão, etc.) | `Timeout ao chamar get_spot_prices` |
| `PHASE_ERROR` | Erro em fase (F0-F5) | `F3: DeepSeek timeout` |
| `TRADE` | Evento de trade | `ENTRADA BUY XAUUSD @ 2000.0` |
| `HARNESS` | Testes | `G8 INDEX-SYNC: PASS` |
| `HEALTH` | Health check | `Heartbeat: MCP online, 16 tools` |
| `METRICS` | Coleta de métricas | `collect_all() → 5 fases` |

## FORMATO

```json
{"ts": "2026-07-23T14:30:00Z", "cat": "TRADE", "phase": "F4", "msg": "ENTRADA BUY", "data": {...}}
```

## SAÍDA

| Arquivo | Formato | Uso |
|---------|---------|-----|
| `logs/system.log` | Texto legível | Debug rápido |
| `logs/system.jsonl` | JSON Lines | Métricas, dashboard, auditoria |

## USO

```python
from utils.logger import get_logger
logger = get_logger(__name__, "F4")
logger.info(f"ENTRADA {side} {symbol} @ {price}")
# → {"ts":"...","cat":"TRADE","phase":"F4","msg":"ENTRADA BUY XAUUSD @ 2000.0"}
```
