> **STATUS: CONSOLIDADO_EM `orc_coleta.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S2: SPEC: FASE 0 — COLETA
>**Versao:** 1.0.0  
>**Wire:** `f0_collector/orc_coleta.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## CRM (O que entrega)

`poll_cycle()` unificado: 5 ativos (XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD).
Cada ciclo retorna OHLCV + bid/ask/spread por simbolo.
`take_snapshot()` persiste `status/snapshot.json` com simbolos + balance + positions.
`get_snapshot()` para F1/F4/F5/dashboard lerem sem MCP direto.

### ESTADO REAL (atualizado 2026-07-23 — FASE 1 1.2-1.7 DONE)

✅ **1.0:** `get_trendbars()` corrigido — `fromTimestamp`+`toTimestamp`, desembrulha `trendbars[]`.
✅ **1.1:** `poll_candles(count=15)` — era 2. Suficiente para Bollinger(20), ATR(14), ADX.
✅ **1.2:** `poll_cycle()` — coleta unificada OHLCV+spot 5 ativos. MCP real: EURUSD bid=113769 ask=113780.
✅ **1.5:** Gateway throttle+cache no `mcp_client.py` — token-bucket 50/s live, 5/s historico.
✅ **1.6:** Snapshot hub — F0 unico pull point. `take_snapshot()` + `get_snapshot()`.
✅ **1.7:** Orchestrator consome snapshot, nao chama MCP direto.
⬜ **1.3:** Backfill 2 anos M_1 pendente.
⬜ **1.3b:** Validacao resample pendente.
⬜ **1.4:** Pivots R1/R2/S1/S2 pendente.

### FLUXO F0

```
MCP (remoto) ──→ poller_orc_coleta.py (poll_cycle) ──→ orc_coleta.py (take_snapshot)
                                               │
                                    status/snapshot.json
                                               │
                          ┌────────────────────┼────────────────────┐
                          │                    │                    │
                    orchestrator.py       F1 analyzer          F4 executor
                    (dashboard 7744)     (metricas)           (ordens)
```

### GRANULARIDADE — M_1 unico, resto por resample

| Timeframe | Origem |
|-----------|--------|
| **M_1** | **coletado do MCP** (unica chamada de historico) |
| M_5 | `pandas.resample()` sobre M_1 |
| M_15 | `pandas.resample()` sobre M_1 |
| D_1 | coletado (pivots R1/R2/S1/S2 do dia anterior) |

Motivo: 3x menos requisicoes **e** fronteira de barra consistente entre timeframes —
series baixadas em separado podem desalinhar. **Validar antes de confiar** (ROADMAP 1.3b):
baixar M_5 do servidor, resamplear o M_1 do mesmo periodo, comparar barra a barra.

### CONTRATO DE COLETA HISTORICA (medido)

- `fromTimestamp` + `toTimestamp` **obrigatorios**, tipo **string** (ISO-8601 ou epoch-ms)
- Janela **<= 720h (30 dias)** por requisicao
- `count` **max 1000**, default **100** — o default **trunca em silencio, sem erro**
- Retencao disponivel: **>= 2 anos** (verificado ate 2024-07-17)
- Backfill alvo: **2 anos de M_1, 5 ativos ≈ 12,5 min** a 5 req/s (uma vez so)
- Particao: **ano mais antigo = out-of-sample intocado**

### TIMEFRAMES — sem fallback

`_timeframe_to_period()` agora usa mapa explicito e **levanta `MCPError`** em timeframe
desconhecido (R51 FAIL-FAST + R-NO-SILENT-FAIL). O fallback antigo mapeava
`M10 -> M_15` e qualquer entrada invalida -> `M_5` em silencio.
**Nao existe `M_10` no servidor** — enum real: `M_1 M_5 M_15 M_30 H_1 H_4 D_1 W_1 MN_1`.

**Ticks brutos nao existem no MCP.** Usar `tickVolume` da barra como proxy de atividade.

---

## HP (Como testar)

- `test_f0_dry_run.py`: dry-run 1h sem ordens reais. Verifica se parquet foi gerado.
- Rate limits respeitados: 2 req/s no pico (limite = 50 req/s geral)

---

## MÉTODOS MCP USADOS (wire S1.1)

| Método | Frequência | Rate limit |
|--------|-----------|------------|
| `get_spot_prices` | 3s (tick) | 50 req/s ✅ |
| `get_trendbars` | 60s (candle) | 5 req/s ⚠️ cap 720h |
| `get_symbols` | startup | 50 req/s ✅ |

### Quirks relevantes

| # | Quirk | Impacto na F0 |
|---|-------|--------------|
| 3 | `get_trendbars` janela 720h | Múltiplas chamadas com `from`/`to` para >30 dias |
| 4 | Apenas 10 timeframes (m1..MN) | Usar m1 para candles 1min |
| 11 | DOM indisponível em algumas contas | Fallback: `bid_wall = 0` |

---

## CP (Condições de produção)

- Conexão HTTPS com Bearer token (expira se browser fechar — #10)
- Reconexão automática com retry 3x
- Token renovado via cTrader Web → Settings → Remote MCP

## FLUXO OBRIGATORIO DE IMPLEMENTACAO

1. **Entrada:** MCP: `get_trendbars(M1, count=15)`, `get_spot_prices(symbol)` para 5 ativos
2. **Processamento:** `poller_orc_coleta.py` coleta >=15 candles M1 + ticks 3s → `storage_orc_coleta.py` append incremental → parquet diario
3. **Saida:** `data/f0_master.parquet` (5 simbolos x >=15 candles x OHLCV + spread)
4. **Validacao:** G6 harness: `test_f0_collector.py` — verifica `len(df) >= 15` e `df.columns == ['symbol','timestamp','open','high','low','close','volume','bid','ask','spread']`
5. **Wire:** `orc_coleta.py` → `f1_analyzer/orc_analise.py` (via parquet file)

