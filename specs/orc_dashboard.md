# SPEC S21 | Versao: 2.0 | Wire: utils/orc_dashboard.py | Status: active

## PROPOSITO
Hub de apresentacao: agrega dados de F0→F5 e expoe via /api/ctrader/health
e /api/ctrader/metrics. Consumido pelo React dashboard (porta 5173).

## FLUXO
```
orc_dashboard ──→ /api/ctrader/health (status geral)
       │
       ├── health_check_full()
       │     ├── snapshot F0
       │     ├── metrics orc_metricas
       │     ├── trail orc_ordens → json_log
       │     ├── orders orc_ordens
       │     └── vector stats (legacy)
       │
       └── aggregate() → dict unificado
```

## ORQUESTRADOR — `utils/orc_dashboard.py` (406L)
Entry points: `health_check_full()`, `aggregate()`, `get_mcp_balance()`,
`get_mcp_positions()`, `get_mcp_spot()` (todos via snapshot F0 — R-NO-MCP-BYPASS).

## FILHOS
(Consome satelites de outros orquestradores: orc_metricas, orc_ordens, json_log)

### `f0_supervisor_orc_dashboard.py` (ROADMAP 1.8, novo 2026-07-28)
Supervisao do processo F0 (status/start/stop/restart) via `status/f0.pid`
(auto-registrado pelo proprio F0) + `psutil` (ja dependencia do projeto —
`10.0_ui_dash/routers/system.py` ja usa para Hardware Metrics).
F0 continua independente do dashboard (nao amarrado ao ciclo de vida da aba —
decisao explicita: coleta continua mesmo com o dashboard fechado). `f0_start()`
roda `harness_boot.py` como pre-flight (A9) antes de subir o processo.

| Entry point | Descricao |
|------------|-----------|
| `f0_status()` | running, pid, uptime_s, snapshot_age_s, snapshot_stale |
| `f0_start()` | pre-flight A9 + spawn subprocess (CREATE_NO_WINDOW) |
| `f0_stop()` | terminate() + wait, fallback kill() |
| `f0_restart()` | stop() + start() |

Endpoints (`routers/ctrader_v2.py`): `GET /f0/status`, `POST /f0/start`,
`POST /f0/stop`, `POST /f0/restart`. Tambem: `POST /mcp/login`, `POST /mcp/logout`,
`GET /mcp/session` — token manual de sessao (so em memoria do processo API,
nunca em disco; NAO afeta o F0, que sempre le `config.yaml`).
