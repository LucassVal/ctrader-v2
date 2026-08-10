# SPEC S27-GAP — VectorBT Gap Analysis

> **Versao:** 1.0 | **Wire:** specs/INDEX.md seção 7 | **Status:** active
> **Fonte:** https://vectorbt.dev + repo polakowo/vectorbt
> **Data:** 2026-08-04
> **Auditoria cruzada:** `orc_vectorbt.py`, `orc_vbt_portfolio.py`, `legacy/vectorbt_calibrator.py`, specs S25/S27/S29/S30/S18

## Resumo do que JÁ usamos

| Categoria | O que usamos | Onde |
|-----------|-------------|------|
| Indicadores (vbt nativo) | RSI, MACD, ATR, BBANDS, OBV, STOCH | `orc_vectorbt.py:44` — `from vectorbt import` |
| Indicadores (numpy) | ADX, HMA, Donchian, Keltner, CCI, PSAR, WPR, Aroon, ZLEMA | `indicators_orc_vectorbt.py` |
| Portfolio | `vbt.Portfolio.from_signals()` | `orc_vbt_portfolio.py:80` |
| Portfolio | `vbt.Portfolio.from_orders()` | `orc_vectorbt.py:252` (fallback com >5 trades) |
| Métricas | stats(), sharpe_ratio(), max_drawdown(), calmar_ratio(), total_return() | Ambos os módulos |
| Engine | vectorbt-rust (instalado, detecção automática) | Transparente |

---

## Features NÃO Usadas — Ranqueadas por Prioridade para Scalping M5/M15

### PRIORIDADE 5 (Crítico — implementar IMEDIATAMENTE)

| # | Feature | Já usamos? | Prioridade | Justificativa |
|---|---------|-----------|:----------:|--------------|
| 1 | **Signal Stop Generators (SL, TSL, TP)** | ❌ Não | **5** | `vbt.RPROBNX` e o sistema de stops integrado ao `Portfolio.from_signals()` permitem simular stop-loss, trailing-stop e take-profit **nativamente** — sem precisar de lógica manual. Para scalp M5 com timeout de 5 min, saber o impacto de um SL de 3 pips vs 5 pips é ESSENCIAL. O `from_signals()` aceita `sl_stop`, `tp_stop`, `tsl_stop` como parâmetros diretos. |
| 2 | **Portfolio.from_order_func() (event-driven)** | ❌ Não | **5** | O `from_signals()` é vetorizado e sujeito a look-ahead bias. Para scalping M5, onde a ordem de execução importa muito (não pode "comprar" e "vender" no mesmo minuto sem dinheiro), o modo event-driven com callbacks Numba resolve isso. Permite também simular preenchimento parcial de ordens, rejeição por slippage, e ordens condicionais (ex: "só entra se ATR < 3"). |
| 3 | **Multi-asset grouping + cash sharing** | ❌ Não | **5** | `Portfolio.from_signals(group_by=..., cash_sharing=True)` permite testar os 5 pares forex como um portfólio ÚNICO com capital compartilhado. Hoje testamos cada símbolo isolado com $10k — irrealista. Com grouping, simulamos $10k divididos entre XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD com alocação dinâmica. |

### PRIORIDADE 4 (Muito importante — próximo sprint)

| # | Feature | Já usamos? | Prioridade | Justificativa |
|---|---------|-----------|:----------:|--------------|
| 4 | **Cross-validation splitters (rolling_split)** | ❌ Não | **4** | `vbt.rolling_split(window_len=..., set_lens=(train, valid, test))` divide os 2 anos de dados M_1 em janelas IS (in-sample) / OOS (out-of-sample). Para evitar overfitting: treinar parâmetros do RSI/ATR em 2024, validar em Jan-Jun 2026, testar em Jul 2026+. Hoje o backtest é estático (janela fixa), sem split. |
| 5 | **MA.run_combs (parameter combinations)** | ❌ Não | **4** | `vbt.MA.run_combs(price, window=np.arange(2, 101), r=2)` gera TODAS as combinações de 2 médias móveis (10.000 combos) e executa backtest em lote. Para M5 scalp: testar RSI(7..21) × ADX(10..30) × ATR(5..20) simultaneamente e achar a combinação ótima por símbolo. Hoje usamos períodos fixos (RSI=14, ADX=14, ATR=14). |
| 6 | **Labeling for ML (LEXLB)** | ❌ Não | **4** | `vbt.LEXLB.run(price, 0.02, 0.02)` detecta extremos locais (topos e fundos) para labeling supervisionado. Para M5: treinar um classificador que prevê "próximo candle sobe ou desce?" baseado nos indicadores VBT. Abre caminho para ML no pipeline sem depender de regras fixas RSI<35. |
| 7 | **QuantStats adapter** | ❌ Não | **4** | `pf.get_qs().plot_snapshot()` gera tearsheet profissional (curva de equity, drawdown subaquático, heatmap mensal, distribuição de retornos). Para validação visual rápida de estratégias M5/M15 antes de wirear no dashboard React. |

### PRIORIDADE 3 (Importante — planejar)

| # | Feature | Já usamos? | Prioridade | Justificativa |
|---|---------|-----------|:----------:|--------------|
| 8 | **IndicatorFactory (custom indicators)** | ❌ Não | **3** | `vbt.IndicatorFactory.from_apply_func()` permite criar indicadores proprietários com Numba. Ex: "M5 Volatility Squeeze" = BBANDS width < threshold AND Keltner width < threshold AND ATR < percentile. O factory gera toda a infra de broadcasting, parâmetros e plotting automaticamente. |
| 9 | **Drawdown analysis aprofundada** | ⚠️ Parcial | **3** | Já usamos `pf.max_drawdown()` mas NÃO usamos `pf.drawdowns.plot(top_n=3)` nem as métricas de duration, recovery time, underwater plot. Para scalping, drawdowns frequentes são normais — a análise de "quanto tempo até recuperar?" é mais relevante que o drawdown máximo absoluto. |
| 10 | **Portfolio logging (simulation trace)** | ❌ Não | **3** | `Portfolio.from_signals(..., log=True)` registra cada passo da simulação (cash, position, debt, free_cash, val_price a CADA barra). Para debugar por que uma estratégia M5 perdeu dinheiro num candle específico, o log é insubstituível. |
| 11 | **vbt.talib() wrapper** | ❌ Não | **3** | `vbt.talib('CDLDOJI').run(open, high, low, close)` integra 61 padrões de candlestick da TA-Lib com broadcasting do VectorBT. Para M5: detectar doji, engulfing, hammer em 1 linha, com suporte a hyperparameter sweeps. |

### PRIORIDADE 2 (Bom ter — backlog)

| # | Feature | Já usamos? | Prioridade | Justificativa |
|---|---------|-----------|:----------:|--------------|
| 12 | **Portfolio.from_random_signals() — Monte Carlo** | ❌ Não | **2** | Gera N portfólios com entradas aleatórias para estabelecer baseline estatístico. Ex: "minha estratégia M5 tem Sharpe 1.2 — isso é melhor que 10.000 estratégias aleatórias?" Essencial para validar se os resultados NÃO são sorte. |
| 13 | **SignalFactory (iterative signals)** | ❌ Não | **2** | `vbt.SignalFactory.from_choice_func()` gera sinais iterativos com callbacks Numba. Para estratégias onde a entrada depende do estado anterior (ex: "só entra de novo se última saída foi lucrativa"), essencial. |
| 14 | **Rust engine global** | ⚠️ Parcial | **2** | vectorbt-rust instalado mas NÃO configurado globalmente (`vbt.settings["engine"] = "rust"`). Para live trading a cada 1 min com 5 símbolos, cada ms conta. Habilitar Rust para todas as operações suportadas reduz latência do pipeline VBT. |
| 15 | **Data splitters (Scikit-Learn K-Folds)** | ❌ Não | **2** | `vbt.Splitter` + splitters do Scikit-Learn permitem K-Fold cross-validation temporal. Complementa o rolling_split com validação mais rigorosa. |

### PRIORIDADE 1 (Nice to have — futuro distante)

| # | Feature | Já usamos? | Prioridade | Justificativa |
|---|---------|-----------|:----------:|--------------|
| 16 | **Custom Plotly Heatmaps** | ❌ Não | **1** | `pf.total_return().vbt.heatmap()` visualiza grids de otimização. Útil para exploração manual de parâmetros, mas dashboard React já cobre visualização. |
| 17 | **Records & Mapped Arrays** | ❌ Não | **1** | Análise post-hoc de logs de simulação com `map_field()`, `top_n()`. Poderoso para pesquisa, mas overkill para pipeline live. |
| 18 | **Telegram Bot notifications** | ❌ Não | **1** | `vbt.TelegramBot` para alerts. Já temos webhook Discord via `orc_health.py`. |
| 19 | **Data acquisition (YFData, CCXTData, etc.)** | ❌ Não | **1** | Dados já vêm do MCP cTrader. Só útil se MCP cair e precisarmos de fallback. |
| 20 | **Pandas acceleration (.vbt accessor)** | ❌ Não | **1** | Rolling apply compilado, z-score, broadcasting. Ganho marginal para nosso volume de dados (máx 2 anos × M_1 × 5 símbolos = ~2.6M candles). |
| 21 | **Caching (cached_method/property)** | ❌ Não | **1** | Decorators de cache. Nossa pipeline reinicia a cada 1 min — cache teria pouca utilidade. |

---

## Features que NÃO se aplicam ao nosso caso

| Feature | Motivo |
|---------|--------|
| **Data generation (GBMData)** | Dados sintéticos para teste — já temos 2 anos de dados reais MCP |
| **Data updater** | Atualização periódica de dados externos — MCP cTrader já é live |
| **Persistence (save/load Dill)** | Salvamos em Parquet, não precisamos serializar objetos Python |
| **Scheduling utilities** | Nosso scheduler é o loop `poll_cycle()` do F0 |
| **Signal distribution analysis** | Já temos `orc_quality.py` + `orc_pattern.py` para análise de qualidade |

---

## Recomendações para o próximo sprint

### Sprint Atual (P5 — críticos)
1. **Stop-loss/take-profit no `orc_vbt_portfolio.py`**: adicionar `sl_stop` e `tp_stop` ao `from_signals()`. Para M5 scalp: SL=5 pips, TP=10 pips (ratio 1:2).
2. **Grouping multi-symbol**: testar os 5 pares como portfólio compartilhado com `cash_sharing=True` e `group_by`.
3. **Modo event-driven**: implementar `from_order_func()` com callbacks Numba para simulação realista de execução M5.

### Próximo Sprint (P4)
4. **Walk-forward com rolling_split**: dividir 2024 (train), Jan-Jun 2026 (valid), Jul+ 2026 (test).
5. **Parameter sweep**: `run_combs` para RSI(5..25) × ADX(10..30) — achar ótimo por símbolo.
6. **QuantStats tearsheet**: validação visual rápida antes de wirear no dashboard.

### Backlog (P3-P2)
7. **IndicatorFactory**: criar "M5 Scalp Squeeze" (BBANDS+Keltner+ATR combinados).
8. **LEXLB labeling**: preparar dados para ML supervisionado.
9. **Monte Carlo baseline**: `from_random_signals(n=1000)` para teste de significância.
10. **Habilitar Rust globalmente**: `vbt.settings["engine"] = "rust"`.
