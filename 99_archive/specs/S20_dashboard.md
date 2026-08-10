> **STATUS: CONSOLIDADO_EM `orc_dashboard.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S20: DASHBOARD UNIFICADO — BACKEND + FRONTEND
> **Versao:** 1.0.0
> **Wire:** `dashboard.py` (backend) + `10.0_ui_dash/react-dashboard/` (frontend)
> **Status:** DONE
> **R21:** validado 2026-07-23
> **R-USE:** RULES.md §CAT1-Cognicao
> **Substitui:** `dashboard.md` (DEAD), `dashboard_ctrader.md`, `dashboard_react_ctrader.md`

---

## CRM (O que entrega)

Dashboard unificado do cTrader V2 com 4 abas + 15 sub-abas.
Backend FastAPI na porta 7744, frontend React/Vite na porta 5173.

### Abas

| Aba | Sub-abas | Fonte de dados |
|-----|----------|----------------|
| **Overview** | Balance, Equity, Margin, PnL | `orchestrator.py` → snapshot F0 |
| **Markets** | 5 ativos: spot, spread, OHLCV | `orchestrator.py` → snapshot F0 |
| **Signals** | Scores F1, Fusion F2, Verdict F3 | `orchestrator.py` → artefatos |
| **System** | Health, Gates, Rules V44 | `orchestrator.py` health_check_full() |

### Regras de implementacao

- **URL direta:** React usa `http://127.0.0.1:7744/api/ctrader` (proxy Vite quebrado)
- **CORS:** backend permite `localhost:5173`
- **Timeout:** axios 60s, poll 15s
- **R-ASCII-OUT:** zero emoji na UI de dados (exception: UI decorativa)
- **Zero mock:** se MCP offline → `{online: false, data: null}`, nunca mock

### FLUXO

```
F0 snapshot ──→ orchestrator.py ──→ /api/ctrader/* (FastAPI :7744)
                                         │
                                   React/Vite :5173 (fetch direto, sem proxy)
                                         │
                                   CtraderTab.tsx (4 abas)
```
