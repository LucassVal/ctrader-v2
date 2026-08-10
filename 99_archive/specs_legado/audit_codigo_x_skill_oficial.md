# AUDITORIA: CÓDIGO × SKILL OFICIAL cTRADER MCP (ref SPEC S0 — documento passivo, sem ID proprio)
>**Versao:** 1.0.0  
>**Wire:** `gates.sh → specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## DIVERGÊNCIAS ENCONTRADAS (7 críticas)

### D1 — symbolId (integer) vs symbol (string) 🔴

| Arquivo | Nosso código | API real (Remote) |
|---------|-------------|-------------------|
| `f0_collector/poller_orc_coleta.py` | `get_spot_prices(symbol="EURUSD")` | `get_spot_prices(symbolId=[1])` |
| `f0_collector/poller_orc_coleta.py` | `get_trendbars(symbol="EURUSD", ...)` | `get_trendbars(symbolId=1, ...)` |
| `f4_executor/entry_orc_execucao.py` | `get_spot_prices(symbol=symbol)` | `get_spot_prices(symbolId=[symbolId])` |
| `f4_executor/safety_orc_execucao.py` | `get_trendbars(symbol=symbol, ...)` | `get_trendbars(symbolId=symbolId, ...)` |
| `f5_mar/mcp_sync_orc_mar.py` | `get_trendbars(symbol=sym, ...)` | `get_trendbars(symbolId=symbolId, ...)` |
| `dashboard.py` | `get_spot_prices(symbol)` | `get_spot_prices(symbolId=[symbolId])` |

**Skill oficial:** "Every symbol parameter is a numeric integer `symbolId` (not a string ticker). Resolve via `get_symbols`, cache for the session."

### D2 — Timeframe `m5` vs `M_5` 🔴

| Arquivo | Nosso código | API real |
|---------|-------------|----------|
| `config.yaml` | `m5, m10, m15` | `M_5, M_15` (apenas 9 valores) |
| `utils/slot_tracker.py` | `("m5", "m10", "m15")` | `("M_5", "M_15")` — `M_10` NÃO EXISTE |
| `f4_executor/safety_orc_execucao.py` | `timeframe="m5"` | `period="M_5"` |
| `f5_mar/mcp_sync_orc_mar.py` | `timeframe="m1"` | `period="M_1"` |
| `contracts/fusion_output.py` | `"m5" \| "m10" \| "m15"` | `"M_5" \| "M_15"` |

**Skill oficial:** "9 values: M_1, M_5, M_15, M_30, H_1, H_4, D_1, W_1, MN_1. `M_2`, `M_3`, `M_10`, `H_3` etc. return -32602."

### D3 — MARKET rejeita SL/TP absoluto 🔴

| Arquivo | Nosso código | API real |
|---------|-------------|----------|
| `f4_executor/entry_orc_execucao.py` | `create_order(stopLoss=..., takeProfit=...)` | `create_order(relativeStopLoss=300, relativeTakeProfit=600)` |

**Skill oficial (Q-R4):** "`create_order` with `orderType: MARKET` REJECTS absolute `stopLoss`/`takeProfit`. Use `relativeStopLoss`/`relativeTakeProfit` (positive integer offset in points)."

### D4 — Volume em lots vs cents 🔴

| Arquivo | Nosso código | API real |
|---------|-------------|----------|
| `f4_executor/entry_orc_execucao.py` | `volume=0.1` (lotes) | `volume=1000000` (cents) |
| `f4_executor/monitor_orc_execucao.py` | `volume=close_vol` (lotes?) | `volume=<cents>` |
| `config.yaml` | `lot_size: 0.1` | precisa converter: 1 lote = 10,000,000 cents |

**Skill oficial:** "Every `volume` field on the Remote server is an integer count of **cents** of the base asset. Forex 1 lot = 10,000,000 cents."

### D5 — `close_position` sem volume obrigatório 🔴

| Arquivo | Nosso código | API real |
|---------|-------------|----------|
| `f4_executor/monitor_orc_execucao.py` | `close_position(position_id=str(...))` (sem volume!) | `close_position(positionId=..., volume=<cents>)` |

**Skill oficial:** "`close_position` on the Remote server **requires** a `volume` parameter (integer cents). To fully close, pass the position's current open `volume`."

### D6 — `amend_position` omit = REMOVE 🔴

| Arquivo | Nosso código | API real |
|---------|-------------|----------|
| `f4_executor/monitor_orc_execucao.py` | `amend_position(position_id=..., stopLoss=novo_sl)` (sem TP!) | Deve enviar **AMBOS** SL e TP, senão o omitido é REMOVIDO |

**Skill oficial (Q-R10):** "OMITTING the `stopLoss` field REMOVES the SL (and omitting `takeProfit` removes the TP). Safe pattern: ALWAYS pass BOTH."

### D7 — Preços em pipettes vs display 🔴

| Arquivo | Nosso código | API real |
|---------|-------------|----------|
| Todos | Usa preços display (1.0850) | Remote retorna **pipettes** (108500 para 5-digit) |

**Skill oficial:** "Every price field is an integer in pipettes. Display = raw / 10^pipDigits."

---

## IMPACTO POR FASE

| Fase | Bugs afetando | Severidade |
|------|--------------|------------|
| **F0** | D1, D2 — símbolos não resolvem, timeframe inválido | 🔴 Não coleta dados |
| **F4** | D1, D2, D3, D4, D5, D6 — ordens REJEITADAS | 🔴 Não opera |
| **F5** | D1, D2 — histórico não sincroniza | 🟡 MAR sem dados |
| **Dashboard** | D7 — preços mostrados errados (100000× maior) | 🟡 UI quebrada |

---

## CORREÇÕES APLICADAS (2026-07-23)

| # | Divergência | Arquivo | Status |
|---|------------|---------|--------|
| D1 | `symbolId` (int) | `mcp_client.py` — cache + `resolve_symbol()` | ✅ Corrigido |
| D2 | `M_5` (period) | `mcp_client.py` — `_timeframe_to_period()` | ✅ Corrigido |
| D3 | `relativeStopLoss` | `mcp_client.py:create_order` — MARKET usa relative | ✅ Corrigido |
| D4 | Volume cents | `mcp_client.py` — `_lots_to_cents()` | ✅ Corrigido |
| D5 | `close_position` volume | `mcp_client.py:close_position` — cents obrigatório | ✅ Corrigido |
| D6 | `amend_position` ambos | `mcp_client.py:amend_position` — P-AMEND-SAFE | ✅ Corrigido |
| D7 | Pipettes → display | `mcp_client.py` — `_price_to_pipettes()` + `_pipettes_to_price()` | ✅ Corrigido |
| — | Timeframes config | `config.yaml` — `m5,m10,m15` → `M_5,M_15,M_30` | ✅ Corrigido |
| — | `monitor_orc_execucao.py` close sem volume | `monitor_orc_execucao.py:159` — adicionado `volume=self.volume` | ✅ Corrigido |
| — | `monitor_orc_execucao.py` volume 80% truncado | `monitor_orc_execucao.py:86` — `int()` removido, usa float | ✅ Corrigido |
| — | `monitor_orc_execucao.py` amend SL/TP pipettes | `amend_position()` — conversão automática display→pipettes | ✅ Corrigido |
