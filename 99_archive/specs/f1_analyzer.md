> **STATUS: CONSOLIDADO_EM `orc_analise.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S3: SPEC S3: F1 — ANALYZER (PILARES + INDICADORES)
>**Versao:** 1.0.0  
>**Wire:** `f1_analyzer/orc_analise.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## RECEBE / ENTREGA
- **Recebe:** `snapshot.json` (F0, via `get_snapshot()` — nao chama MCP direto)
- **Entrega:** `scores_raw.json` — 5 scores: macro, vol, tec, spread, sentiment
- **CORTADO v1:** `_ichimoku` (Senkou B=52p > holding 5min), `_volume` (zero importadores)
- **FLOW:** snapshot F0 → F1 calcula 5 metricas → F2 fusion → F3 ranking

## INDICADORES v1 (revisao 2026-07-23)

> **Relogio unico M_1.** Todos os indicadores calculados em M_1 (ver S5.1). Agregados M_5/M_15
> so por `pandas.resample()` se um indicador exigir; o relogio de decisao permanece M_1.
> Calculo via **vectorbt** (nativos) + `vbt.talib()` para os 161 do TA-Lib. Ver S17.

### Micro por ativo — NUCLEO v1

| Grupo | Indicador | Papel | Fonte |
|-------|-----------|-------|-------|
| Volatilidade | **BBANDS(20,2) + %B + bandwidth** | posicao no canal / squeeze->expansao | `vbt.BBANDS` |
| Escala | **ATR(14)** | dimensiona SL/TP; normaliza entre ativos | `vbt.ATR` |
| Regime | **ADX** | porteiro: `<20` = lateral, mata rompimento | `vbt.talib("ADX")` |
| Direcao | EMA 9/21 | vies | `vbt.MA` |
| Estrutura | Pivots R1/R2/S1/S2 (D_1 anterior) | alvo de TP / filtro sniper (NAO score) | aritmetica pura |

**%B:** `(close - lower) / (upper - lower)`. Lido em **direcoes opostas** por estrategia:
S1 (rompimento) quer %B perto de 1,0 = ENTRA; S2 (respiracao) quer %B extremo = ESPERA continuacao.

### Confirmador da S2 — A DECIDIR (varredura, Fase 4.5)
RSI(14) **ou** STOCH — nao os dois. Escolhido por varredura no out-of-sample. Ver ROADMAP 4.5.

### CORTADOS da v1 (registro da decisao)
- **MACD** — em M_1 o sinal chega depois do trade de 5min morrer.
- **Ichimoku** — Senkou B = 52 periodos e nuvem projetada 26min a frente, alem do horizonte de
  holding. `_ichimoku.py` permanece no disco mas **nao entra no fluxo v1**; reavaliar so se
  provar ganho out-of-sample. NAO wirear em `_orc_f1` agora.

## GLOBAIS (1x por ciclo, contexto para os 5 ativos)
| Indicador | Papel |
|-----------|-------|
| DXY sintetico **multi-par** | EURUSD 0,693 / USDJPY 0,164 **invertido** / GBPUSD 0,143 (ver 2.5) |
| Correlacao rolling 5x5 | redutor de concentracao no ranking (F2) |
| Regime de volatilidade | ATR medio normalizado dos 5 |
| Sentimento | contrarian via `get_positions()` |

---

## 📁 ARQUIVOS (DDD)

| Arquivo | Tipo | Função |
|---------|------|--------|
| `orc_analise.py` | 🔵 ORQ | CLI, `analyze()`, scores_raw.json. **HOJE so importa `_pillars`+`_news`** — wirear `_micro`/`_sentiment` (ROADMAP 2.1) |
| `pillars_orc_analise.py` | 🟢 SAT | componentes de score + Bollinger %B |
| `micro_orc_analise.py` | 🟢 SAT | spread, pipDigits, ATR, correlacao, DXY. **Zero importadores no F1 hoje** (so no dashboard) |
| `sentiment_orc_analise.py` | 🟢 SAT | Sentimento via `get_positions()`. Expõe `calc_sentiment_ratio` + alias `get_sentiment_ratio` |
| `_ichimoku.py` | ⚪ SAT | **fora da v1** (cortado); permanece no disco, nao wireado |
| `_volume.py` | ⚪ SAT | **zero importadores** — wirear ou arquivar (ROADMAP 2.4) |
| `_news.py` | 🟢 SAT | `blackout_times.json` (opcional) |
| `__init__.py` | 📦 PKG | Re-exporta API |
| `f1_analyzer.py` | ❌ MORTO | Sombreado pelo pacote homonimo — `import f1_analyzer` resolve o `__init__.py`, nunca o `.py`. Arquivar (ROADMAP D.4) |

## HP
`test_f1_scores.py`: scores ∈ [0,100], distribuição normal.

## TIMEFRAMES
Relogio de decisao: **M_1**. Enum real do MCP (medido, ver S1.1):
`M_1 M_5 M_15 M_30 H_1 H_4 D_1 W_1 MN_1` — **com underscore, sem M_10, sem H_12**.
Fallback silencioso de conversao ja removido (`_timeframe_to_period` levanta `MCPError`).

## FLUXO OBRIGATORIO DE IMPLEMENTACAO

1. **Entrada:** `data/f0_master.parquet` da F0 + MCP `get_positions` (sentiment)
2. **Processamento:** NUCLEO v1: `_pillars` (macro=Bollinger %B, vol=ATR+bandwidth, tec=ADX+EMA cross) + `_micro` (spread, correlation 5x5 pass-through para F2) + `_sentiment` (long/short ratio). **CORTADOS:** `_ichimoku` (Senkou B 52p > holding), `_volume` (zero importadores).
3. **Saida:** `scores_raw.json` com 5 scores (macro/vol/tec/spread/sentiment) + correlation_matrix 5x5 (pass-through para F2)
4. **Validacao:** G6: `test_f1_scores.py` — verifica `all(0 <= s <= 100 for s in [macro,vol,tec,sentiment])` e `correlation_matrix.shape == (5,5)`
5. **Wire:** `orc_analise.py` → `f2_fusion.py` (via scores_raw.json)

