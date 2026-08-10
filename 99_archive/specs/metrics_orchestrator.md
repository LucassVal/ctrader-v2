> **STATUS: CONSOLIDADO_EM `orc_metricas.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S21: SPEC S21: METRICS ORCHESTRATOR + HEALTH CHECK REAL
>**Versao:** 1.0.0  
>**Wire:** `utils/orchestrator.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## 0. FRONTEIRA DDD (revisao 2026-07-23)

> Tres papeis distintos — **nao fundir** (R-ANTI-DECAY: aquisicao != apresentacao):
> - **Aquisicao** = `f0_collector` (unico a puxar MCP: candle/spot/balance/positions).
> - **Agregacao** = `utils/metrics.py` — le `trades.db` + `status/metrics.json`. **NAO toca MCP.** ✅
> - **Apresentacao** = `utils/orchestrator.py` — monta o payload do dashboard.
>
> ⚠️ **Hoje o orchestrator FURA o F0:** `_get_balance`/`_get_positions`/`_get_spot`/
> `health_check_full` chamam o MCP direto (linhas 180/194/205/233), competindo pelo rate
> compartilhado. **Alvo (ROADMAP 1.7):** orchestrator le o **snapshot do F0** (estado vivo) +
> `metrics.collect_all()` (agregacao) — nenhum dos dois chama MCP por conta propria.
> F0 **nao** absorve metrics; metrics ja esta correto e nao se mexe (R-AI-REUSE).

## 1. ORCHESTRATOR DE MÉTRICAS (`utils/orchestrator.py`)

Monta coleta + validação + exportação para o dashboard. **Agregacao** vem de `metrics.py`
(trades.db); **estado vivo** deve vir do snapshot do F0, nao de chamada MCP propria (ver §0).

### Funções:

| Função | Reuso | Entrada | Saída |
|--------|-------|---------|-------|
| `collect_all()` | `utils/metrics.py` | `trades.db` + `status/*.json` | Dict F0-F5 (25+ métricas) |
| `validate_against_specs()` | Specs S2-S7 thresholds | Dados de `collect_all()` | `{pass, failures[]}` |
| `export_for_dashboard()` | Formata p/ React | `collect_all()` | Dict plano (1 nível) |
| `health_check_full()` | `utils/health.py` + MCP + specs | — | `{mcp, phases, gates, alerts}` |

### Wire:
```
utils/orchestrator.py
  ├── importa utils/metrics.py (collect_all, validate_metrics)
  ├── importa utils/health.py (heartbeat, decay_detection)
  ├── importa utils/harness_runner.py (run_harness)
  ├── importa utils/mcp_client.py (get_version, get_balance)
  └── EXPORTADO para:
        routers/ctrader.py → /api/ctrader/metrics + /api/ctrader/health
        CtraderTab.tsx → sub-abas Pipeline + Conexão
```

---

## 2. HEALTH CHECK REAL

Não é só ping MCP. Valida o sistema inteiro contra as specs.

### Checks:

| Check | Spec | Função | Threshold |
|-------|------|--------|-----------|
| MCP vivo | S1.1 | `get_version()` | online + 16 tools |
| F0 coleta | S2 | `df_master` tem linhas recentes? | < 60s desde último tick |
| F1 scores | S3 | Scores ∈ [0,100] | macro+vol+tec > 0 |
| F2 fusão | S4 | Pesos somam 1.0 | ±0.01 |
| F3 IA | S5 | approve_rate | > 0 |
| F4 execução | S6 | drawdown < 3% | `max_drawdown_pct` < 3.0 |
| F5 MAR | S7 | weight_delta | < 0.1 |
| Gates | S0 | G6 harness | 15/15 PASS |
| DB | S1 §8 | trades.db existe | `os.path.exists` |
| Logger | S19 | logs/system.jsonl | < 10MB |

### Saída:
```json
{
  "mcp": {"online": true, "tools": 16},
  "phases": {
    "f0": {"ok": true, "last_tick_s": 3},
    "f1_f2": {"ok": true, "avg_score_macro": 72.5},
    "f3": {"ok": true, "approve_rate": 0.85},
    "f4": {"ok": true, "max_drawdown_pct": 1.2},
    "f5": {"ok": true, "weight_delta": 0.03}
  },
  "gates": {"g6": {"passed": true, "total": 15}},
  "alerts": []
}
```

---

## 3. CRUZAMENTO SPEC × FUNÇÕES

Cada check do health referencia explicitamente a spec que o define:

```
Check "F0 coleta" → spec S2 §3 ("df_master com timestamp < 60s")
Check "F4 drawdown" → spec S6 §4 ("daily_drawdown_kill = 3%")
Check "Gates" → spec S0 ("G6 HARNESS 15/15")
```

Se um check falhar, o alerta cita a spec violada.


## RATE LIMIT AWARENESS (D.10)
- Gateway throttle (1.5): 50 req/s live, 5 req/s historico, cache TTL 1s/30s
- `/health` faz UMA chamada agregada — o dashboard nao dispara N chamadas individuais
- `poll_cycle()` ja agrupa 5 ativos numa so chamada MCP
- Keep-alive: `init_client()` chamado 1x na inicializacao, sessao reusada
