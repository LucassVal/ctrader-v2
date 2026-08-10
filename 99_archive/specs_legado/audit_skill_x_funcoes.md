# AUDITORIA: SKILL OFICIAL cTRADER × FUNÇÕES NOSSO SISTEMA (ref SPEC S0 — documento passivo, sem ID proprio)
>**Versao:** 1.0.0  
>**Wire:** `specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## 1. WORKFLOWS OFICIAIS × NOSSO CÓDIGO

### W0 — Session Bootstrap

| Passo oficial | Nosso código | Status |
|--------------|-------------|--------|
| Identificar server family (Remote/Local) | `init_client()` — detecta Remote via `get_version` | ✅ |
| Probe build identification | `get_version()` — sem comparação com baseline | ⬜ |
| Comparar build vs frontmatter min-build | Não implementado | 🔴 |
| Load symbol precision baseline (`symbol_precision_table.json`) | Não carregado (usamos fallback pipDigits=5) | 🔴 |
| Verify symbol at first use (pipDigits, lotSize, volumeStep) | `get_symbols()` cache — sem verificação de minVolume/volumeStep | 🟡 |
| Resolve active account (traderId, moneyDigits, depositAssetId) | `get_balance()` — sem cache de moneyDigits/assetId | 🟡 |
| Q-R4-RANGE probe (OPT-IN) | Não implementado | 🔴 |
| Idempotency-key prefix | Não implementado | 🔴 |

### W1 — Entry Orders

| Passo oficial | Nosso código | Status |
|--------------|-------------|--------|
| Tier selection (LIMIT→MARKET_RANGE→MARKET) | `entry_orc_execucao.py` — só MARKET, sem tier selection | 🟡 |
| TIER 3 (MARKET) → relativeStopLoss/relativeTakeProfit | `create_order(MARKET, sl=..., tp=...)` → `relativeStopLoss` ✅ | ✅ |
| Pre-flight gates (quote sanity, side sanity, SL/TP sidedness) | Não implementado | 🔴 |
| Pre-flight: volumeStep compliance | Não implementado | 🔴 |
| Pre-flight: pipettes-vs-display detection (Q-K19) | `_price_to_pipettes()` — sem detecção de erro de unidade | 🟡 |
| Post-flight verification (re-read position) | `monitor_orc_execucao.py` faz poll mas não verifica volume/SL/TP | 🟡 |
| Idempotency label | Não usado | 🔴 |

### W2 — Modify Position

| Passo oficial | Nosso código | Status |
|--------------|-------------|--------|
| P-AMEND-SAFE (sempre enviar ambos SL+TP) | `amend_position()` — Q-R10 ✅ | ✅ |
| Trailing SL via amend_position (não create_order) | `_amend_sl()` — usa amend_position ✅ | ✅ |
| Re-read after amend | `monitor_orc_execucao.py` — sim, via poll | ✅ |
| Omit = REMOVE awareness | Documentado no amend_position | ✅ |

### W3 — Close Position

| Passo oficial | Nosso código | Status |
|--------------|-------------|--------|
| Volume obrigatório em cents | `close_position(id, volume)` ✅ | ✅ |
| Ler get_positions antes para volume | `monitor_orc_execucao.py` — usa `self.volume` da entry | 🟡 |
| Partial close (80%) | `monitor_orc_execucao.py:86` — `self.volume * 0.8` ✅ | ✅ |

### W5 — Risk Sizing

| Passo oficial | Nosso código | Status |
|--------------|-------------|--------|
| `scripts/position_sizing.py` — % risco → volume | Não usado | 🔴 |
| `scripts/tiered_margin.py` — margem dinâmica | Não usado | 🔴 |
| `scripts/conversion_rate.py` — conversão moedas | Não usado | 🔴 |
| VolumeStep compliance | Não implementado | 🔴 |

---

## 2. FUNÇÕES NOSSO CÓDIGO × SKILL OFICIAL

| Nossa função | Equivalente oficial | Conformidade |
|-------------|-------------------|-------------|
| `init_client()` | W0 §1-2 | 🟡 parcial (sem build comparison) |
| `get_balance()` | W0 §6 | ✅ |
| `get_symbols()` + cache | W0 §4-5 | 🟡 (sem precision baseline) |
| `resolve_symbol()` | W0 §5 (per-symbol verify) | ✅ |
| `get_spot_prices()` | W0 (não especificado, mas usado) | ✅ |
| `get_trendbars()` | W0 (não especificado, mas usado) | ✅ |
| `create_order(MARKET)` | W1 TIER 3 (P-REMOTE-MARKET-RELATIVE) | ✅ |
| `create_order(LIMIT/STOP)` | W1 TIER 1 | ✅ |
| `close_position()` | W3 | ✅ |
| `amend_position()` | W2 (P-AMEND-SAFE) | ✅ |
| `entry_orc_execucao.py` | W1 (TIER 3 only) | 🟡 (sem gates, sem tiers) |
| `monitor_orc_execucao.py` | W2 + W3 | 🟡 (sem idempotency) |
| `safety_orc_execucao.py` (ATR) | W1 pre-flight (quote sanity parcial) | 🟡 |
| `gates_orc_execucao.py` | W1 pre-flight (balance check) | 🟡 (sem volumeStep) |
| `micro_orc_analise.py` (spread, swap, corr) | — (nosso extra) | ✅ |
| `orchestrator.py` | — (nosso extra) | ✅ |

---

## 3. INDICADORES MICRO POR MERCADO

### Cross-reference: O que cada ativo precisa

| Ativo | Característica | Indicador macro | Indicador micro | Fonte MCP |
|-------|---------------|----------------|-----------------|-----------|
| **XAUUSD** | Ouro — trend, volatilidade alta | DXY (EURUSD proxy), VIX via ATR | ATR(14), Bollinger(20,2), tick_volume ratio | `get_trendbars` |
| **EURUSD** | Mean-reversion, range | DXY score, sentimento EUR | RSI(14), Bollinger %B, spread médio | `get_trendbars` + `get_spot_prices` |
| **GBPUSD** | Volátil, news-sensitive | DXY, sentimento GBP | ATR(10) curto, tick_volume spike detect | `get_trendbars` |
| **USDJPY** | Carry trade, risk sentiment | DXY, risk-on/off (AUDJPY proxy) | Ichimoku (cloud espessura), swap acumulado | `get_trendbars` + `get_positions` |
| **AUDUSD** | Commodity proxy, China | DXY, iron ore/copper (indireto) | RSI(14), Bollinger %B, correlação c/ XAUUSD | `get_trendbars` + `_micro.correlation` |

### Indicadores implementados vs faltando

| Indicador | F1 implementa? | MCP fonte | Prioridade |
|-----------|---------------|-----------|------------|
| ATR | ✅ `pillars_orc_analise.py` | `get_trendbars` | ALTA (SL/TP sizing) |
| RSI(14) | ✅ `pillars_orc_analise.py` | `get_trendbars` | ALTA (sobrecompra/venda) |
| Bollinger %B | ✅ `pillars_orc_analise.py` | `get_trendbars` | ALTA (squeeze/expansão) |
| Ichimoku | ✅ `_ichimoku.py` | `get_trendbars` | MÉDIA (tendência + cloud) |
| Spread médio | ✅ `micro_orc_analise.py` | `get_spot_prices` | MÉDIA (custo entrada) |
| Swap acumulado | ✅ `micro_orc_analise.py` | `get_positions` | BAIXA (custo carrego) |
| Tick volume ratio | ⬜ | `get_trendbars.tickVolume` | MÉDIA (confirmação) |
| Tick volume spike | ⬜ | `get_trendbars.tickVolume` | ALTA (detectar entrada/saída) |
| Correlação 5×5 | ✅ `micro_orc_analise.py` | df_master local | MÉDIA (diversificação) |
| DXY score | ✅ `micro_orc_analise.py` | EURUSD trendbars | ALTA (macro) |
| VolumeStep check | ⬜ | `get_symbols` | ALTA (ordem não rejeitada) |
| MoneyDigits | ⬜ | `get_balance` | MÉDIA (display correto) |
| Idempotency label | ⬜ | — (UUID nosso) | ALTA (não duplicar ordens) |

### Recomendações — próximos indicadores a implementar:

1. **Tick volume spike detector** (`f1_analyzer/_volume.py`)
   - Detecta anomalias no tick_volume vs média móvel
   - Confirma breakout/entrada de institucionais
   - Prioridade: ALTA (melhora timing de entrada F4)

2. **VolumeStep compliance** (`f4_executor/gates_orc_execucao.py`)
   - Lê `get_symbols.volumeStep` e arredonda volume
   - Evita rejeição `@Positive` do Remote
   - Prioridade: ALTA (F4 não funciona sem)

3. **Idempotency label** (`mcp_client.py`)
   - Prefixo UUID por sessão em `label`/`comment` de cada ordem
   - Evita ordens duplicadas em retry
   - Prioridade: ALTA

4. **MoneyDigits cache** (`mcp_client.py`)
   - Lê `get_balance.moneyDigits` e usa para display
   - Prioridade: MÉDIA
