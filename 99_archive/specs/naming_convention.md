> **STATUS: CONSOLIDADO_EM `INDEX.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S0.1: SPEC: CONVENÇÃO DE NOMEAÇÃO — CTRADER V2
>**Versao:** 1.0.0  
>**Wire:** `specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## ARQUIVOS

```
🔵 _orc_f*.py  = Orquestrador (loop principal, dispatch)
🟢 _*.py       = Satélite (função pura, ≤500L)
📦 __init__.py = Re-exporta API pública da fase
```

## DIRETÓRIOS

```
f0_collector/   → F0 Coleta (DDD)
f1_analyzer/    → F1 Análise (DDD)
f2_fusion/      → F2 Fusão (DDD)  
f3_validator/   → F3 Validação IA (DDD)
f4_executor/    → F4 Execução (DDD)
f5_mar/         → F5 MAR (DDD)
utils/          → MCP client, health, metrics, schema
contracts/      → TypedDicts imutáveis
tests/          → Harness tests
specs/          → Documentação spec-driven
```

## TETOS (Neocortex V44)

| Tipo | Máximo |
|------|--------|
| Orquestrador | 350L |
| Satélite | 500L |
| Arquivo standalone | 200L |
| GOD file (>500L) | REJEITADO |

## ORDEM DE CRIAÇÃO

1. **Spec** → `specs/fase.md`
2. **Contrato** → `contracts/fusion_output.py` (se aplicável)
3. **Satélite** → `fase/_sat.py`
4. **Orquestrador** → `fase/_orc_fase.py`
5. **Init** → `fase/__init__.py`
6. **Harness** → `tests/test_fase.py`
7. **Wire** → atualizar `specs/INDEX.md` + `run.py`
