# AUDITORIA: FONTES DE DADOS — UNIFICAÇÃO (ref SPEC S0 — documento passivo, sem ID proprio)
>**Versao:** 1.0.0  
>**Wire:** `orchestrator.py → specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## FONTES DE DADOS ATUAIS

```
┌─────────────────────────────────────────────────────────┐
│                    DASHBOARD (React)                     │
│                 CtraderTab.tsx :5173                     │
└──────────┬──────────┬──────────┬──────────┬─────────────┘
           │          │          │          │
     ┌─────┘    ┌─────┘    ┌─────┘    ┌─────┘
     ▼          ▼          ▼          ▼
  /metrics   /health   /account   /market    ← 4 endpoints
     │          │          │          │
     ▼          ▼          ▼          ▼
┌─────────────────────────────────────────────┐
│           routers/ctrader.py :7744          │
│   (Faz chamadas DIRETAS a 4 fontes)         │
└──┬───────┬──────┬───────┬──────┬────────────┘
   │       │      │       │      │
   ▼       ▼      ▼       ▼      ▼
┌──────┐ ┌────┐ ┌────┐ ┌────┐ ┌──────────┐
│trades│ │MCP │ │cfg │ │logs│ │harness   │
│.db   │ │    │ │.yaml│ │.jsonl│ │runner.py │
└──────┘ └────┘ └────┘ └────┘ └──────────┘
  9️⃣       1️⃣4️⃣     9️⃣      2️⃣        1️⃣
leitores  leitores leitores leitores   leitor
```

## PROBLEMA

Cada módulo acessa fontes diretamente:
- `dashboard.py` → trades.db + MCP + config.yaml (3 fontes)
- `utils/metrics.py` → trades.db + status/*.json (2 fontes)
- `utils/orchestrator.py` → trades.db + MCP + logs + config (4 fontes)
- `f4_executor/safety_orc_execucao.py` → trades.db + MCP (2 fontes)
- `f5_mar/rules_orc_mar.py` → trades.db + custom_rules.json (2 fontes)

**Resultado:** Mudar schema do SQLite quebra 9 arquivos. Mudar config.yaml quebra 9 arquivos.

## SOLUÇÃO: ORCHESTRATOR COMO CAMADA ÚNICA

```
┌─────────────────────────────────────────────────────────┐
│                    DASHBOARD (React)                     │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │   ORCHESTRATOR  │  ← ÚNICO ponto de acesso
              │ orchestrator.py │
              └───┬───┬───┬─────┘
                  │   │   │
         ┌────────┘   │   └────────┐
         ▼            ▼            ▼
    ┌─────────┐ ┌──────────┐ ┌──────────┐
    │ metrics │ │  health  │ │ harness  │
    │   .py   │ │   .py    │ │ _runner  │
    └────┬────┘ └────┬─────┘ └──────────┘
         │           │
    ┌────┴────┐ ┌────┴─────┐
    ▼         ▼ ▼          ▼
┌──────┐ ┌──────┐ ┌──────────┐
│trades│ │status│ │   MCP    │
│.db   │ │.json │ │ (remoto) │
└──────┘ └──────┘ └──────────┘
```

## STATUS ATUAL

| Fonte | Leitores | Unificada via orchestrator? |
|-------|----------|----------------------------|
| trades.db | 9 | ✅ `orchestrator.get_trade_history()` |
| MCP | 14 | ✅ `orchestrator.get_mcp_balance/positions/spot()` |
| config.yaml | 9 | ✅ config_loader.py |
| logs/*.jsonl | 2 | ✅ logger.py |
| status/*.json | 2 | ✅ `orchestrator.get/save_status_json()` |
| fusion_output.json | 4 | ⬜ (f2, f3, contracts leem direto) |

## PLANO (futuro)

1. `orchestrator.py` → ÚNICO import para dashboard + fases
2. `metrics.py` → chamado APENAS pelo orchestrator
3. `health.py` → chamado APENAS pelo orchestrator
4. Fases F0-F5 → usam orchestrator para persistência (não SQLite direto)
5. Dashboard → chama APENAS endpoints (não SQLite direto)
