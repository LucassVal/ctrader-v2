> **STATUS: CONSOLIDADO_EM `orc_execucao.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S6: SPEC: FASE 4 — EXECUÇÃO + GESTÃO DE RISCO
>**Versao:** 1.0.0  
>**Wire:** `f4_executor/orc_execucao.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## CRM (O que entrega)

Execução OCO com 5 degraus (D0/D40/D60/D80/Trail), monitoramento 1s, kill switch 3%/5%.

---

## MÉTODOS MCP USADOS (wire S1.1)

| Método | Uso | Quirks |
|--------|-----|--------|
| `create_order` | Entrada OCO | MARKET usa stopLoss/takeProfit |
| `close_position` | Fechar total/parcial | Volume em cents |
| `amend_position` | Mover SL (degraus) | **#2**: sempre enviar AMBOS SL+TP |
| `get_positions` | Monitorar ativas | `positionId` string |
| `get_balance` | Kill switch | `freeMargin` |
| `get_spot_prices` | Preço atual (1s) | bid/ask direto |

---

## QUIRKS CRÍTICOS (fonte: spotware/ctrader-skills)

### #1 — MARKET rejeita SL/TP absolutos
```python
# ❌ ERRADO (rejeitado pelo MCP)
params = {"stopLoss": 1990.50, "takeProfit": 2010.50}

# ✅ CORRETO (relativo em pipettes)
entry = 2000.00
relative_sl = int(abs(entry - 1990.50) * 100_000)  # = 950000
relative_tp = int(abs(2010.50 - entry) * 100_000)  # = 1050000
params = {"relativeStopLoss": relative_sl, "relativeTakeProfit": relative_tp}
```
**Já implementado** em `utils/mcp_client.py:place_market_order()`.

### #2 — amend_position OMITE = REMOVE
```python
# ❌ ERRADO (se enviar só SL, o TP é removido)
amend_position(pos_id, sl=1995.00)

# ✅ CORRETO (sempre enviar ambos)
amend_position(pos_id, sl=1995.00, tp=2010.50)
```
**Já implementado** em `utils/mcp_client.py:amend_position()` — busca valores atuais se não informados.

### #5 — Pipettes foot-gun
Preço negociado × 100.000 = valor no MCP.
Ex: EURUSD 1.10500 → enviar `110500`.
**Já documentado** no client.

### #9 — Silent error (errorCode sem exception)
Após `place_market_order`, checar `ExecutionEvent.errorCode`.
**A implementar** no `entry_orc_execucao.py`.

---

## ENCODING (volume e preço)

| Campo | Unidade | Exemplo |
|-------|---------|---------|
| `volume` | cents | 1 lote XAUUSD = 100 units × 100 = **10000 cents** |
| `entry_price` | preço real (double) | bid/ask do `get_spot_prices` já vem correto |
| `relativeStopLoss` | pipettes (int64) | distância × 100.000 |

---

## RECOVERY PATTERNS

| Erro | Padrão |
|------|--------|
| 401 "No valid session" | Token expirado → alertar renovar |
| 429 Rate limit | Backoff 1s→2s→4s |
| 502 BAD_GATEWAY | Retry 3x |
| ExecutionEvent.errorCode ≠ 0 | Log + rejeitar entrada |

---

## SCALP TIMEOUT (v2.1 — 2 estratégias: M5 + M15)

| Estratégia | Timeframe | Timeout | Regra |
|-----------|-----------|---------|-------|
| Scalp 5 | M_5 | 5 min | Fecha se D60 não atingido |
| Scalp 15 | M_15 | 15 min | Fecha se D60 não atingido |

> M_10 não existe no Remote MCP (Q-R1). M_15 usado como proxy.

**Lógica:** `check_scalp_timeout()` em `f4_executor/orc_ordens.py`
- PnL ≥ 15% do TP → fecha com ganho parcial
- PnL < 15% do TP → corta perda (capital não fica parado)

## BE RULE
```
BE = entry_price + (spread_ask - spread_bid) × 2
```
- Spread conta na entrada E na saída
- Via MCP `get_spot_prices` (bid/ask)

**Wire:** `orc_ordens.py` → `monitor_orc_execucao.py` → polling loop F4

## FLUXO OBRIGATORIO DE IMPLEMENTACAO

1. **Entrada:** `ranking.json` da F3 + MCP `get_balance`, `get_positions`, `get_symbols`
2. **Processamento:** Top-2 ativos do ranking → calcula lote (2% risco) → OCO (entry+SL+TP) → trail stop → BE em +10 pips. Gates: margem, max posicoes, slots, sessao, news.
3. **Saida:** `trade_log.json` + ordens OCO ativas no MCP + `log_trade_orc_execucao.py` registro local
4. **Validacao:** G6: `test_f4_ghost_order.py` + `test_f4_trail_be.py` — verifica OCO pricing, SL/TP relativos, trail, BE
5. **Wire:** `orc_execucao.py` → `f5_mar/orc_mar.py` (via trade_log.json + MCP `get_deals`)

