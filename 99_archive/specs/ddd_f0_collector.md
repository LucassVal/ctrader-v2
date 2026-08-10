> **STATUS: CONSOLIDADO_EM `orc_coleta.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S2.1: DDD — F0 COLETOR (REVISADO 2026-07-23)
>**Versao:** 1.1.0
>**Wire:** `f0_collector/orc_coleta.py`
>**Status:** DONE
>**R21:** validado 2026-07-23 — DOM removido, poll_tick abolido, poll_cycle unificado
>**R-USE:** RULES.md §CAT1-Cognicao

---

## ARQUITETURA

```
f0_collector/
├── __init__.py          # Reexporta Collector, run — interface publica
├── orc_coleta.py           # Orquestrador: take_snapshot(), get_snapshot() — hub F0
├── poller_orc_coleta.py           # poll_cycle() OHLCV+spot 5 ativos, backfill_symbol()
└── storage_orc_coleta.py          # save_parquet, load_parquet, append_rows, validate_resample
```

## CONTRATO DE INTERFACE (imutavel)

```python
# f0_collector/__init__.py
from f0_collector.orc_coleta import Collector, main

__all__ = ["Collector", "main"]
```

Chamada externa **nao muda**: `python -m f0_collector --dry-run`

## RESPONSABILIDADES POR ARQUIVO

### `orc_coleta.py` — Orquestrador (hub F0)
- `take_snapshot()` — coleta poll_cycle + balance + positions → `status/snapshot.json`
- `get_snapshot()` — leitura do snapshot (consumido pelo orchestrator, F1, F4, F5, dashboard)
- **UNICO pull point MCP** (G12 allowlist)
- **NAO contem**: chamadas MCP dispersas em outras fases

### `poller_orc_coleta.py` — Chamadas MCP (satelite puro)
- `poll_cycle()` — coleta unificada: OHLCV (M_1, count=15) + spot (bid/ask/spread) para 5 ativos
- `backfill_symbol()` — chain 30d windows, throttle <=5 req/s, parquet por simbolo
- **ABOLIDO:** `poll_tick()` — DOM nao existe no MCP v0.4.0. Substituido por poll_cycle()
- **Granularidade:** M_1 unico coletado. M_5/M_15 por pandas.resample().
- **Ticks:** nao existem no MCP. Barra M_1 formando tem close = spot vivo.
- tickVolume = contagem de atividade por minuto (proxy de liquidez)

### `storage_orc_coleta.py` — Persistencia
- `save_parquet(df, data_dir) → Path` — snapshot para disco
- `load_parquet(path) → DataFrame` — leitura
- `save_backfill_parquet(df, symbol) → Path` — backfill particionado
- `append_rows(df, rows) → DataFrame` — append em lote
- `validate_resample(symbol, window_hours) → dict` — M_5 server vs resample(M_1)

## DEPENDENCIAS

```
orc_coleta.py  → poller_orc_coleta, utils/mcp_client, utils/_artifacts
poller_orc_coleta.py  → utils/mcp_client
storage_orc_coleta.py → pandas
```

## FLOW

```
MCP (remoto)
  ↓ get_trendbars + get_spot_prices + get_balance + get_positions
_orc_f0.take_snapshot()
  ↓
status/snapshot.json  ← hub unico
  ↓
orchestrator.py + F1 + F4 + F5 + dashboard
```

## VALIDACAO (GATES)

| Gate | Arquivos | Threshold |
|------|----------|-----------|
| G0 (ruff) | Todos | 0 erros |
| G6 (harness) | test_f0_min_candles, test_f0_backfill, test_f0_snapshot, test_f0_pivots, test_f0_gateway_throttle | 5/5 harnesses |

## NOTA

DOM removido do MCP v0.4.0. `poll_tick()` abolido. O `f0_collector.py` original foi splitado em `orc_coleta.py` (hub) + `poller_orc_coleta.py` (satelite) + `storage_orc_coleta.py` (persistencia).
