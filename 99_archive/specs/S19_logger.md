> **STATUS: CONSOLIDADO_EM `fluxo_logs.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S19: LOGGER — SISTEMA DE LOG ESTRUTURADO
> **Versao:** 1.0.0
> **Wire:** `utils/logger.py`
> **Status:** DONE
> **R21:** validado 2026-07-23
> **R-USE:** RULES.md §CAT1-Cognicao

---

## CRM (O que entrega)

Logger unificado para todos os modulos do cTrader V2.
Output em console (stderr) + arquivo JSON lines (`logs/system.jsonl`).

### Formatos

| Destino | Formato | Uso |
|---------|---------|-----|
| Console | `%(asctime)s [%(levelname)s] %(name)s: %(message)s` | Dev/local |
| Arquivo | JSON lines: `{"ts":"...","level":"INFO","module":"F0","msg":"..."}` | Producao/auditoria |

### Niveis

- `DEBUG`: internals (nao commitar em prod)
- `INFO`: fluxo normal (snapshot salvo, backfill progresso)
- `ERROR`: falhas recuperaveis (MCP timeout, retry)
- `CRITICAL`: falhas nao recuperaveis (config ausente, DB corrompido)

### R-ASCII-OUT

Nenhum log contem emoji ou caractere nao-ASCII. G14 audita.

## FLUXO

```
get_logger(__name__, "MODULO") ──→ logger.info/error/...
        │
        ├── console (stderr, formatado)
        └── logs/system.jsonl (JSON lines, rotativo)
```
