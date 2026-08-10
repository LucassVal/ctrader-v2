> **STATUS: CONSOLIDADO_EM `orc_mar.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S7: SPEC: FASE 5 — LOG + MAR
>**Versao:** 1.0.0  
>**Wire:** `f5_mar/orc_mar.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


## CRM
- `trades.db` populado com toda entrada (aprovada ou rejeitada)
- `get_trade_history` para reconciliar trades locais vs cTrader

## MÉTODOS MCP (nomes REAIS — ver S1.1)

| Método | Uso | Rate limit |
|--------|-----|-----------|
| `get_order_history` / `get_deals` | Reconciliar trades locais vs cTrader | **5 req/s** ⚠️ |
| `get_trendbars` | VectorBT calibrator (replay) | **5 req/s** ⚠️ |

> ⚠️ Nomes antigos `trading.get_history` / `analysis.get_trendbars` **nao existem** no MCP.
> Tools reais nao tem namespace com ponto. Ver `specs/mcp_endpoints.md`.

### Contrato de `get_trendbars` (medido — ver S1.1)
`fromTimestamp`+`toTimestamp` obrigatorios (string), janela **<=30 dias**, `count` **<=1000**
(default 100 trunca em silencio). Para 2 anos de backtest: janelas de 30d encadeadas,
throttle 5 req/s (sleep ~200ms). NAO usar `count` sozinho — da HTTP 400.
- `custom_rules.json` atualizado diariamente (00:00 UTC)

## HP
`test_f5_mar.py`: pesos convergem em ≤ 4 dias com média móvel 0.7. ✅ PASS

## LOG (T21)
- Tabela `trades`: trace_id, timestamp, symbol, timeframe, scores_json, verdict_json, execution_json, decision, pnl_net, exit_reason
- Tabela `slots`: controle de slots com persistência
- Tabela `v_historical_candles`: candles para VectorBT

## MAR — CALIBRAGEM DIÁRIA (T22)
- Gatilho: `new_day = True` (00:00 UTC)
- Algoritmo: média móvel com peso 0.7
  ```
  novo_peso = atual × 0.3 + ideal_dia × 0.7
  ```
- Normalização: soma = 1.0
- Escrita atômica: tempfile + `os.rename`
- Mínimo 5 trades no dia para calibrar

## LOG ROTATION
- Semanal (domingo): `DELETE WHERE created_at < date('now', '-90 days')` + VACUUM

## INTERFACE
- `python f5_mar.py --init-db` — inicializa schema
- `python f5_mar.py --calibrate` — força calibração diária
- `python f5_mar.py --rotate` — log rotation

## FLUXO OBRIGATORIO DE IMPLEMENTACAO

1. **Entrada:** `trade_log.json` da F4 + MCP `get_deals`, `get_order_history`
2. **Processamento:** Calcula MAR ratio (retorno / max drawdown) + Sharpe + Win rate. Compara com benchmark (buy & hold). Ajusta parametros via `rules_orc_mar.py`.
3. **Saida:** `mar_report.json` + metricas no `db_orc_mar.py` SQLite + `rules_orc_mar.py` ajusta lote/alavancagem
4. **Validacao:** G6: `test_f5_mar.py` — verifica `MAR >= 0`, `Sharpe >= 0`, `win_rate ∈ [0,100]`
5. **Wire:** `orc_mar.py` → loop fecha (feedback para F1 `sentiment_orc_analise.py` e F3 `orc_ranking.py`)

