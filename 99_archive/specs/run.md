> **STATUS: CONSOLIDADO_EM `INDEX.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S0.2: SPEC: RUN — ORQUESTRADOR MESTRE
>**Versao:** 1.0.0  
>**Wire:** `run.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


## CRM
Orquestrador que gerencia todos os processos via `subprocess`. Isolamento total.

## PROCESSOS

| Nome | Módulo | Prioridade | Reinicia? |
|------|--------|-----------|-----------|
| f4 | `f4_executor._orc_f4` | CRITICAL | ❌ (humano intervém) |
| f0 | `f0_collector._orc_f0` | normal | ✅ |
| f1 | `f1_analyzer` | normal | ✅ |
| f2 | `f2_fusion` | normal | ✅ |
| f3 | `f3_validator` | normal | ✅ |
| f5 | `f5_mar` | normal | ✅ |
| dashboard | `dashboard.py` (streamlit) | low | ✅ |

## HEARTBEAT
- Cada processo escreve `status/<fase>.heartbeat` a cada 5s
- `run.py` verifica a cada 10s
- Se heartbeat > 15s atrasado → processo travou
- F4 travou → ALERTA (não reinicia)

## INICIALIZAÇÃO
1. F4 primeiro (crítico)
2. F0, F1, F2, F3, F5 em paralelo
3. Dashboard por último

## ENCERRAMENTO
SIGINT/SIGTERM → `proc.terminate()` com timeout 5s → `proc.kill()`
