# SPEC S2.6 — WORKER BACKFILL (Fresh-Session-per-Batch)

> **Versao:** 1.0.0 | **Wire:** `tests/worker_backfill_batch.py` + `tests/orchestrator_v2.py`
> **P0 — ANTES DE ALTERAR, LEIA:** specs/NC-BP_CTRADER_DEV.md
> **Status:** testing | **Fase:** Testes

## RCA — Por que a sessao MCP expira

cTrader MCP expira sessoes em ~8-10 min **independente de atividade** (server-side policy).
Nao e timeout por inatividade — e tempo de vida absoluto desde o handshake.

```
T=0     init_client() → handshake → session_id
T=1..9  requests ativos (throttle 5 req/s)
T=10    servidor invalida session → "Session not found"
```

`_ensure_session_fresh()` renova a cada 7 min entre SIMBOLOS, mas um simbolo com muitos
ranges (ex: VIXUSD 15 ranges × 70+ paginas) pode levar >7 min → sessao expira DENTRO
do processamento do simbolo.

## Solucao: Fresh-Session-per-Batch

Em vez de uma sessao longa processando todos os ranges, dividir em **batches independentes**.
Cada batch abre seu proprio handshake MCP, baixa N ranges (default: 5), salva e fecha.

```
Orquestrador (orchestrator_v2.py)
  │
  ├── 1. G23 scan → gap_report.json
  ├── 2. Para cada simbolo:
  │     └── Splita gaps em batches de 5 ranges
  │           ├── Worker batch 1: handshake fresco → 5 ranges → save → exit
  │           ├── Worker batch 2: handshake fresco → 5 ranges → save → exit
  │           └── Worker batch N: handshake fresco → N ranges → save → exit
  └── 3. Re-scan → verifica convergencia
```

## Vantagens

| Abordagem | Sessao unica (atual) | Fresh-Session-per-Batch (v2.6) |
|-----------|---------------------|-------------------------------|
| Duracao da sessao | ~10 min+ | ~30-60s por batch |
| Risco de expirar | ALTO (VIXUSD) | ZERO |
| Resiliência | Stall detection + retry | Batch falhou → proximo continua |
| Paralelismo | Impossivel | Futuro: N workers paralelos |
| Complexidade | Baixa | Media (orquestrador + workers) |

## Contrato do Worker

```python
# Uso: python tests/worker_backfill_batch.py XAUUSD --ranges 5 --candles 1000
# 1. Preflight MCP (handshake + ping)
# 2. Carrega gap_report.json
# 3. Baixa N ranges × ~1000 candles cada
# 4. Salva no consolidated (dedup)
# 5. Reporta: barras/s, tempo total
```

## Contrato do Orquestrador

```python
# Uso: python tests/orchestrator_v2.py --days 15 --ranges-per-batch 5
# 1. Preflight MCP
# 2. G23 scan → gap_report.json
# 3. Para cada simbolo com gaps:
#    Splita gaps em batches → spawna worker para cada batch
# 4. Re-scan → verifica convergencia
# 5. Reporta: total barras, gaps antes/depois, tempo total
```

## Anti-Padroes

1. **Sessao unica para muitos ranges** → expira no meio. Usar batches.
2. **Worker sem preflight proprio** → reusa sessao expirada do pai. Cada worker faz seu handshake.
3. **Batch muito grande** → risco de expirar. Max 5 ranges por batch (~30-60s).

## Wire Points (fase de testes)

- `tests/worker_backfill_batch.py` — worker individual
- `tests/orchestrator_v2.py` — orquestrador de workers (a criar)
- NAO wireado no .bat/.ps1 ainda (fase de testes)


---

## v1.1 (2026-08-07) — Padrão `force=True` + reset global

### RCA do bug `exit=1 / 0 barras`

O worker original chamava `init_client(str(config))` sem `force=True`. Se o estado
global `_mcp_initialized` estivesse True (residual de chamada anterior no mesmo
processo, ou bug de estado entre subprocessos), o handshake era pulado e a sessao
expirada era reusada → "Session not found" → download_range retornava 0 barras.

### Solucao

```python
def preflight_mcp():
    import utils.mcp_client as mcp
    # Reset estado global — garante handshake NOVO
    mcp._mcp_initialized = False
    mcp._mcp_session_id = ""
    mcp._mcp_url = ""
    init_client(str(config), force=True)
```

### Resultado validado

`test_fresh_session.py XAUUSD 5`: 5/5 chamadas, 5000 barras em 9s, 557 bars/s.
Handshake medio: 0.7s. Zero falhas de sessao.

### Wire points atualizados

- `tests/worker_backfill_batch.py`: `preflight_mcp()` com force+reset
- `tests/orchestrator_v2.py`: workers chamados como subprocess (isolamento natural)
- `tests/test_fresh_session.py`: teste direto do padrao


---

## v1.2 (2026-08-07) — Wire no boot .ps1

### Wire point

`Abrir_NeoCortex_NovaPulse.ps1` L162-175:
```
Write-Step 'MCP Preflight + Test Battery'
& $VENV_PY "$CTRADER\tests\orchestrator.py" '--skip-real'
```

Executado APOS a verificacao de parquet e ANTES do backfill.
Garante que MCP esta online e testes sinteticos passam antes de qualquer
operacao de dados.

### Testes wireados

- `test_consolidation_cache.py`: 9 testes (cache, gaps, merge, pipeline)
- `test_fresh_session.py`: 5 chamadas fresh-session (prova de conceito)
- `test_cache_robustness.py`: robustez do cache com delecao parcial
- `test_per_symbol.py`: preflight individual por simbolo com download 10K

### Gate pattern

O padrao e: preflight MCP → sinteticos → backfill → G23 scan.
Se preflight falhar, o boot continua (aviso, nao bloqueante).
Se sinteticos falharem, o boot continua com aviso.
