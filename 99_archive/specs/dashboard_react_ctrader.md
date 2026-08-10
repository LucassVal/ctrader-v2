> **STATUS: CONSOLIDADO_EM `orc_dashboard.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S8.1: DASHBOARD REACT — ABA CTRADER + SUB-ABAS
>
>**Versão:** 2.0.0  
>**Pai:** S8 (`specs/dashboard.md`)  
>**Wire:** `routers/ctrader.py` → `CtraderTab.tsx` → `specs/INDEX.md`  
>**Status:** ✅ Implementado (8 sub-abas, zero mock)

---

## 1. BACKEND — `routers/ctrader.py`

### Endpoints REAIS (substituíram mock)

| Endpoint | Fonte | Offline |
|----------|-------|---------|
| `GET /api/ctrader/health` | MCP `get_version()` | `{online:false}` |
| `GET /api/ctrader/account` | MCP `get_balance()` | `{online:false, data:null}` |
| `GET /api/ctrader/market` | MCP `get_spot_prices()` + `get_trendbars()` | `{online:false}` |
| `GET /api/ctrader/positions` | MCP `get_positions()` + `get_deals()` | `{online:false}` |
| `GET /api/ctrader/risk` | MCP `get_balance()` (drawdown) | `{online:false}` |
| `GET /api/ctrader/plugins` | Honesto (MCP não expõe) | `{online:false}` |
| `GET /api/ctrader/metrics` | `utils/metrics.py::collect_all()` | Tolerante a DB vazio |
| `GET /api/ctrader/harness` | `utils/harness_runner.py::run_harness()` | Cache 60s |

### Envelope padrão
```json
{"status": "ok", "ts": "2026-07-23T...", "data": {...}, "error": null}
```

---

## 2. FRONTEND — `CtraderTab.tsx` (8 SUB-ABAS)

### Sub-abas implementadas:

| Aba | Ícone | Conteúdo | Endpoint |
|-----|-------|----------|----------|
| **Overview** | Activity | Saldo, Equity, Win Rate, Profit Factor, MCP status | account + metrics |
| **Pipeline** | Layers | F0 Coleta, F1-F2 Análise, F3 IA, F4 Execução, F5 MAR | metrics |
| **Conexão** | Wifi | MCP vivo, servidor, 16 tools, modo, latência | health |
| **Mercados** | BarChart3 | Bid/Ask/Spread 5 ativos + candles M5 | market |
| **Ordens** | Target | Posições abertas, pendentes, deals (7d) | positions |
| **Harness** | TestTube | 15/15 testes, output pytest | harness |
| **Estratégia** | Crosshair | S1 M5, S2 M10, S3 M15 com slots/timeouts | estático |

### Padrão UI:
- `API_URL = 'http://127.0.0.1:7744'` + `axios` + `setInterval(5s)`
- Tokens: `--nc-cyan/emerald/amber/red`, `glass-card`, `tab-active-glow`
- Ícones: `lucide-react`. Badge DEMO/OFFLINE.

### Regras:
- MCP online → dado REAL. MCP offline → `{online:false}` (NUNCA mock).
- Frontend faz polling 5s. Toggle auto-refresh.
- `npm run lint` limpo + `npm run build` ok.
