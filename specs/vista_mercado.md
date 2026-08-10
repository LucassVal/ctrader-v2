# SPEC S39 — Vista de Mercado: drill-down MTF por simbolo (abas de mercado)

> **Versao:** 1.0.0 | **Wire:** utils/vista_orc_mercado.py (SAT de orc_mercado) → /vector/symbol/{sym}.vista | **Status:** active
> **R-USE:** S27/S28 (indicators_orc_vectorbt), S31 (consolidado G23), S34 (pattern_library), S36 (signals_log + score_live), S35 (correlacao multi-janela), S20 v2.2 (drill-down)

## Proposito

As abas de mercado (XAUUSD..AUDUSD) respondem: **o que o sistema esta
analisando neste mercado, agora, em cada timeframe** — regime, momentum,
volatilidade, qualidade medida, padroes ativos e correlacao — tudo com
interpretacao, nunca numero cru sem contexto (pedido do dono 2026-07-30:
"ampliar agressivamente o que esta sendo analisado").

## Decisoes (pesquisa 2026-07-30: vectorbt MTF + taxonomia TA)

- **MTF por RESAMPLE do consolidado M1** (nao trendbars do MCP): M5/M15/H1
  derivados do M1 G23 via pandas resample — mesma base cientifica unica
  (dono: "M1 e o TF cientifico"), zero custo MCP, zero lookahead (so barras
  fechadas < now). Padrao documentado vectorbt: resample -> indicador por TF.
- **Regime por TF** = ADX + slope EMA(20) sobre closes do TF:
  ADX >= 25 e slope > 0 → TREND_UP; ADX >= 25 e slope < 0 → TREND_DOWN;
  ADX < 20 → RANGE; entre 20-25 → TRANSICAO.
- **Concordancia multi-TF** = fracao de TFs apontando a mesma direcao do M1
  (a "ciencia correlata" da decisao S34 sec.4 — vira insumo visual; modulacao
  do score fica para S35/S37, NAO entra aqui).
- **Correlacao multi-janela** (achado S35: janela unica insuficiente):
  200 barras / 1 dia / 1 semana, sobre returns log do consolidado M1.
- **Taxonomia TA na UI** (pesquisa): Tendencia (ADX/SMA/HMA/Aroon/PSAR/ZLEMA),
  Momentum (RSI/MACD/Stoch/CCI/WPR), Volatilidade (ATR/BB/Keltner/Donchian),
  Volume (OBV) — cada chip com zona interpretada (RSI<30 sobrevendido etc).

## Fix estrutural acoplado — 16/16 no consolidado (R-USE)

`load_indicators.latest` vinha do consolidado (10 colunas) → health "5/16".
`consolidated_indicator_points(..., full_families=True)` computa as 6 familias
restantes (Stoch, SMA, Donchian, HMA, Keltner, CCI, PSAR, WPR, Aroon, ZLEMA)
**so na cauda** (max_points + 250 barras de warmup), R-USE dos helpers escalares
de `indicators_orc_vectorbt`. Caminho do scan (full_families=False) INALTERADO
(lean — 850k pontos). load_indicators passa a pedir full_families=True:
latest 16/16, span continua vindo do consolidado.

## Contrato — vista_orc_mercado.market_detail(symbol) -> dict

```
symbol, gerado_em, sessao_atual (tokyo/london/ny/rollover)
regime_mtf: { m1/m5/m15/h1: {rsi, adx, atr_pct, ema_slope_pct, regime} }
concordancia: { direcao_m1, tfs_de_acordo, total_tfs }
calibracao: { n, hit_5m/15m/60m, por_faixa }       # R-USE signals_log (S36)
padroes_top: [ {signal_15m, confidence, occurrences, avg_pips_net_15m} x3 ]  # S34
score_live: { sinal, score, quality_f1, pattern_conf, coverage_pct, age_s }  # S36
correlacao: { janelas: {b200/d1/sem1: {peer: r}}, peers_fortes: [...] }
```

Custo: so leituras baratas + resample da cauda (7d) — NUNCA roda scan/score
pesado (regra de custo S20). Sem dados → campos null honestos (A7).

## React (wire)

- MarketTab: strip regime MTF + concordancia, chips TA por familia com zonas,
  cards calibracao/padroes/score do simbolo.
- CorrelationView: seletor de janela (200b/1d/1sem) via /vector/correlation?window=.
- GlobalsView/CorrelationView NAO se fundem (papeis distintos: drivers x pares).

## Regras

- REGRA-MET: /metrics segue sendo o overview; vista = drill-down sancionado (S20 v2.2).
- R-NO-MCP-BYPASS: vista NUNCA toca MCP — consolidado + artefatos status/.
- G12: vista_orc_mercado <= 200L; engine numpy de regime em SAT se estourar.
