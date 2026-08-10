# SPEC S2 | Versao: 2.0 | Wire: f0_collector/orc_coleta.py | Status: active

## PROPOSITO
F0 — PONTA DE LANCA: unico ponto de contato com o cTrader MCP.
Coleta OHLCV + spot de 5 ativos + 2 indices (DXYUSD, VIXUSD),
gera snapshot.json, e executa ordens (place_order, exit_position,
move_stops, kill_pending) via mcp_client.

Universo: SYMBOLS = [XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD]
Indices:  INDEX_SYMBOLS = [DXYUSD, VIXUSD] (dados, nao trading)

## FLUXO
```
MCP ──poll_cycle()──→ orc_coleta ──snapshot.json──→ F1..F5
                         │
                         ├── place_order() ←── F4 (orc_execucao)
                         ├── exit_position() ←── F4
                         ├── move_stops() ←── F4
                         └── kill_pending() ←── F4
```

## ORQUESTRADOR — `f0_collector/orc_coleta.py`
| Entry point | Chamado por | Descricao |
|------------|------------|-----------|
| `take_snapshot()` | Collector.run() | poll_cycle()+balance+positions+trendbars → snapshot.json |
| `get_snapshot()` | F1..F5, dashboard | Le snapshot (sem MCP) |
| `place_order()` | orc_execucao | Cria ordem MARKET + SL/TP |

## FILHOS

### `poller_orc_coleta.py`
- **Funcao**: poll_cycle(), SYMBOLS, INDEX_SYMBOLS, ALL_COLLECT_SYMBOLS
- **Fonte**: MCP via mcp_client
- **v2.1**: +INDEX_SYMBOLS (DXYUSD, VIXUSD) para coleta de indices macro

### `storage_orc_coleta.py`
- **Funcao**: save_backfill_parquet(), make_empty_df(), append_to_df()
- **Saida**: data/*.parquet (historico acumulativo)

---

## S2.5 — Banco M_1 Persistente (Parquet 2 anos)

> **Status:** IMPLEMENTADO (2026-07-28) | **v2.1 (2026-07-29):** warmup + fixes de persistencia
> **Wire:** F0 `take_snapshot()` → `_persist_m1_rows()` → `data/m1_*.parquet` + `data/vbt_*.parquet`

### Pipeline (v2.1 — corrigido e validado ao vivo)

```
BOOT do F0 (Collector.run):
  _warmup_m1()                          → 200 velas M_1/simbolo via get_trendbars
                                          (VBT sai no 1o ciclo; sem isso eram 50+ min)

A cada ciclo (~60s):
  poll_cycle()                          → 5 candles M_1
  _persist_parquet(cycle)
    └── _candle_to_row()                → schema COLUMNS (ts ms int)
    └── _persist_m1_rows(sym, [row])
          ├── append + dedup            → data/m1_{SYM}_{ANO}.parquet (+1 linha)
          └── se len(df) >= 50:
                compute_indicators(200 ultimas)  → data/vbt_{SYM}.parquet
  get_trendbars(sym, [m15, h1, h4])     → snapshot.trendbars (display)
  snapshot.json                         → sobrescrito (cache rapido)
```

### Bugs corrigidos em 2026-07-29 (v2.1)

| Bug | Efeito | Fix |
|-----|--------|-----|
| `_append(ohlcv_batch)` com 1 arg (assinatura exige df+rows) | M_1 live NUNCA persistia (TypeError engolido) | `_persist_m1_rows()` com assinatura correta |
| VBT sobre 1 vela do ciclo | `error: precisa >= 50 barras` — vbt_*.parquet nunca nascia | VBT sobre as 200 ultimas do parquet |
| `except: pass` silencioso | Falhas invisiveis | `logger.error` em todos os excepts |
| STOCH `.k/.d` inexistente no vbt 1.1.0 | compute_indicators 100% erro | `percent_k/percent_d` |
| Sem warmup | 50+ min sem VBT apos boot | `_warmup_m1()` (200 velas/simbolo) |

### Backfill (2 anos)

```
get_trendbars paginado: 30d/janela, 1000 barras/req, throttle 5 req/s
→ ~730 req/simbolo → ~12 min/simbolo → ~60 min total (5 simbolos)
```

### Calibracao Diaria (v2.1 — 2026-08-05)

Boot chama backfill em dois modos:
1. **Parquet AUSENTE** → `backfill_orc_coleta.py --symbol X` (2 anos completos)
2. **Parquet EXISTE** → `run_consolidate_parquet.py` (G23 gap scan) + `backfill_orc_coleta.py --gaps` (preenche so lacunas)

Fluxo: PRE-FLIGHT → G23 scan → backfill --gaps → F0 sobe com dados frescos.
Tempo tipico: G23 ~2s + gaps ~30s (vs ~60min do backfill completo).

### Arquivos

| # | Arquivo | Acao |
|---|---------|------|
| 1 | `f0_collector/storage_orc_coleta.py` | Ja existia — append/save/load Parquet |
| 2 | `f0_collector/orc_coleta.py` | Wire: storage.append_to_df() apos cada ciclo |
| 3 | `data/` | Diretorio de saida — m1_*.parquet |
| 4 | `tests/harness_boot.py` | +STORAGE orquestrador |

---

## SESSION LIFECYCLE (v2.2 — 2026-08-09)

> **Problema:** MCP expira sessoes em ~7-8 min server-side. O Collector.run()
> chamava `poll_cycle()` sem verificar idade da sessao — apos 7-8 min, todas as
> chamadas MCP falhavam com "Session not found" e o loop retentava a sessao morta.
> **Solução:** `mcp_client.ensure_session_fresh()` (SSOT) com SESSION_MAX_AGE=300s.
> Chamado no topo do loop principal e no error handler (force-reconnect).

```python
# orc_coleta.py Collector.run() — loop principal
while not shutdown_flag:
    ensure_session_fresh("config.yaml")  # renova a cada 5 min proativamente
    cycle = poll_cycle()
    # ...
    except (MCPConnectionError, MCPTimeoutError):
        init_client("config.yaml", force=True)  # force-reconnect no erro
```

### SSOT: `utils/mcp_client.py`

| Função | Descrição |
|--------|-----------|
| `ensure_session_fresh(config_path)` | Renova sessao se idade > 300s. Usado por F0 live + backfill. |
| `get_session_age()` | Idade da sessao em segundos (para health check). |
| `touch_handshake()` | Chamado automaticamente após `_initialize_mcp()` bem-sucedido. |
| `SESSION_MAX_AGE` | 300.0 (5 min — folga antes dos ~7-8 min do server). |
