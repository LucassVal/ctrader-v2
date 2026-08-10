> **STATUS: CONSOLIDADO_EM `INDEX.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S8: CONTRACTS — JSON SCHEMAS IMUTAVEIS
> **Versao:** 1.0.0
> **Wire:** `contracts/__init__.py`
> **Status:** DONE
> **R21:** validado 2026-07-23
> **R-USE:** RULES.md §CAT1-Cognicao

---

## CRM (O que entrega)

Schemas JSON canonicos para todos os artefatos do pipeline cTrader V2.
Cada contrato define tipos, campos obrigatorios e valores padrao.
Imutaveis — mudanca requer nova versao e migracao dos artefatos existentes.

### Contratos definidos

| Contrato | Arquivo | Artefato |
|----------|---------|----------|
| `FusionOutput` | `fusion_output.py` | F2 → F3: score final + redutores |
| `ScoresRaw` | `fusion_output.py` | F1 → F2: scores por pilar |
| `VerdictContract` | `fusion_output.py` | F3: decisao final |
| `CustomRules` | `fusion_output.py` | F5: regras customizadas |
| `ExecutionLog` | `fusion_output.py` | F4: log de execucao |
| `MetaContract` | `fusion_output.py` | Metadados do ciclo |
| `ContextContract` | `fusion_output.py` | Contexto de mercado |

### Regras

- Campos obrigatorios NAO podem ser removidos (breaking change)
- Campos novos devem ter default
- Nomes em snake_case (Python) mapeiam para camelCase (JSON)

## FLUXO

```
contracts/__init__.py ──→ reexporta todos os tipos
         │
         ├── fusion_output.py: schemas principais
         └── consumido por: F2 (fusion), F3 (validator), F5 (MAR)
```
