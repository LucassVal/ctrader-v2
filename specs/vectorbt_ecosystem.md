# SPEC S18: VECTORBT + ECOSSISTEMA — INTEGRAÇÃO cTRADER V2
>**Versao:** 1.0.0  
>**Wire:** `specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## S12.0 — VISÃO GERAL DO ECOSSISTEMA

```
┌──────────────────────────────────────────────────────┐
│                  cTRADER V2                           │
│                                                      │
│  F0 (coleta)  ←── MCP cTrader (dados reais)          │
│  F1 (análise) ←── TA-Lib (150+ indicadores)          │
│  F5 (backtest)←── vectorbt + vectorbt-rust           │
│  Dashboard    ←── Plotly (via vectorbt)              │
│                                                      │
│  EXTRA (não usados no MVP):                          │
│  ccxt → dados multi-exchange (futuro)                │
│  yfinance → dados Yahoo Finance (futuro)             │
│  numba → JIT engine (usado pelo vectorbt)            │
└──────────────────────────────────────────────────────┘
```

---

## S12.1 — VECTORBT 1.1.0 (Core Backtesting)

**Pip:** `vectorbt==1.1.0`  
**Motor:** vectorbt-rust 1.1.0 (sem overhead JIT)  
**Local:** `.venv/Lib/site-packages/vectorbt/`

### O que faz (verificado na instalação)

| Módulo | Função | Uso no cTrader |
|--------|--------|---------------|
| `vectorbt.portfolio.base.Portfolio` | Simula portfólio com equity curve, custos, slippage | **F5:** Backtest offline diário |
| `vectorbt.indicators` | Indicadores customizados + integração TA-Lib | **F1:** Alternativa ao Pandas-TA |
| `vectorbt.signals` | Geração, ranking, mapeamento de sinais booleanos | **F1→F2:** Converter scores em entries/exits |
| `vectorbt.generic.drawdowns` | Análise de drawdown | **F5:** `max_drawdown()` |
| `vectorbt.base.reshape_fns` | Broadcasting multi-ativo | **F5:** Testar 5 símbolos simultâneos |
| `vectorbt.ohlcv_accessors` | `DataFrame.vbt.ohlcv` — accessor nativo | **Dashboard:** `.vbt.ohlcv.plot()` |

### API utilizada (target)

```python
import vectorbt as vbt
import pandas as pd

# 1. Sinais da F1 convertidos para booleanos
entries = scores_df["final_adjusted"] > 70  # threshold de entrada
exits = scores_df["tec"] < 20               # sinal técnico fraco

# 2. Portfolio vetorizado (sem loop Python)
portfolio = vbt.Portfolio.from_signals(
    close=df["close"],
    entries=entries,
    exits=exits,
    freq="1min",
    init_cash=1000,
    slippage=0.001,    # 0.1%
    fees=0.0005,        # 0.05%
)

# 3. Métricas
stats = portfolio.stats()  # 50+ métricas em DataFrame
sharpe = portfolio.sharpe_ratio()
max_dd = portfolio.max_drawdown()
win_rate = portfolio.win_rate()
profit_factor = portfolio.profit_factor()
```

---

## S12.2 — VECTORBT-RUST 1.1.0 (Engine)

**Pip:** `vectorbt-rust==1.1.0` (instalado automaticamente com vectorbt 1.1.0)  
**Local:** `.venv/Lib/site-packages/vectorbt_rust/`

### O que faz

Engine precompilado em Rust. Elimina o overhead de compilação JIT do Numba na primeira execução. Backtests que demoravam 5s (Numba JIT) agora rodam em < 1s.

### Uso no cTrader

Transparente — o vectorbt detecta automaticamente e usa. Nenhuma configuração necessária. Benefício: calibração diária (F5) roda mais rápido, permitindo backtests com mais dados.

---

## S12.3 — NUMBA 0.66.0 (JIT Compiler)

**Pip:** `numba==0.66.0`  
**Local:** `.venv/Lib/site-packages/numba/`

### O que faz

Compila funções Python em código de máquina via LLVM. Usado internamente pelo vectorbt para vetorização de loops que não podem ser expressos em NumPy puro.

### Uso no cTrader

Interno ao vectorbt. Não usamos diretamente. Com vectorbt-rust instalado, o Numba é fallback — só entra se o engine Rust falhar.

---

## S12.4 — PANDAS 3.0.5 (Upgrade)

**Versão anterior:** 2.2.2 → **Atual:** 3.0.5

### Mudanças relevantes

| Feature | Versão | Impacto |
|---------|--------|---------|
| `copy_on_write` | 3.0 (default) | Menos cópias acidentais de DataFrame — menos memória |
| Arrow-backed strings | 3.0 | Strings mais rápidas (timestamp_utc, symbol) |
| PyArrow nativo | 3.0 | Parquet mais rápido (F0 salva a cada 1h) |

### Uso no cTrader

Todas as fases usam pandas. O upgrade é transparente, mas **atenção**: `copy_on_write` pode quebrar código que modifica DataFrame in-place. Testar F0 e F1 com pandas 3.0.

---

## S12.5 — TA-LIB 0.7.1 (Indicadores Técnicos)

**Pip:** `TA-Lib==0.7.1`  
**Local:** `.venv/Lib/site-packages/talib/`

### O que faz

150+ indicadores técnicos implementados em C. Muito mais rápido que pandas-ta (Python puro).

### Indicadores relevantes para o cTrader

| Indicador | Função TA-Lib | Uso no Pilar |
|-----------|--------------|-------------|
| RSI | `talib.RSI(close, timeperiod=7)` | P3 — Técnico |
| ATR | `talib.ATR(high, low, close, timeperiod=14)` | P2 — Volatilidade |
| SMA | `talib.SMA(close, timeperiod=20)` | P1 — Macro (DXY) |
| Bollinger | `talib.BBANDS(close, timeperiod=20)` | P3 — Técnico |
| MACD | `talib.MACD(close)` | P3 — Técnico (momentum) |
| ADX | `talib.ADX(high, low, close, timeperiod=14)` | P2 — Força da tendência |
| CCI | `talib.CCI(high, low, close, timeperiod=14)` | P3 — Commodity Channel |

### Uso no cTrader (alternativa ao Pandas-TA)

```python
# Antes (pandas-ta, Python puro, ~50ms por 1000 candles)
import pandas_ta as ta
rsi = ta.rsi(df["close"], length=7)

# Depois (TA-Lib, C compilado, < 1ms por 1000 candles)
import talib
rsi = talib.RSI(df["close"].values, timeperiod=7)
```

**Recomendação:** Migrar `f1_analyzer.py` de pandas-ta para TA-Lib. Ganho de performance: 50x mais rápido.

---

## S12.6 — CCXT 4.5.68 (Exchange Unified API)

**Pip:** `ccxt==4.5.68`  
**Local:** `.venv/Lib/site-packages/ccxt/`

### O que faz

API unificada para 100+ exchanges (Binance, Bybit, Kraken, etc.). Acesso a OHLCV, orderbook, execução de ordens.

### Uso no cTrader

**NÃO USADO NO MVP.** O cTrader MCP já fornece todos os dados. Uso futuro:
- Backtest com dados de múltiplas exchanges para validação cruzada
- Fallback de dados se MCP cair
- Comparação de spreads entre brokers

### Status: ❌ Desligado para MVP.

---

## S12.7 — YFINANCE 1.5.1 (Yahoo Finance)

**Pip:** `yfinance==1.5.1`  
**Local:** `.venv/Lib/site-packages/yfinance/`

### O que faz

Download de dados históricos do Yahoo Finance (ações, ETFs, forex, crypto).

### Uso no cTrader

**NÃO USADO NO MVP.** Uso futuro:
- Dados históricos para backtest inicial (antes do SQLite ter 90 dias)
- DXY real (não sintético) para Pilar 1
- Sentimento de mercado via notícias do Yahoo Finance

### Status: ❌ Desligado para MVP.

---

## S12.8 — IMPACTO NO CRONOGRAMA

| Fase | Mudança | Impacto |
|------|---------|---------|
| **F1** | pandas-ta → TA-Lib | Performance 50x. Prioridade: pós-MVP |
| **F5** | pandas fallback → vectorbt Portfolio | Métricas reais (Sharpe, drawdown, win rate). Prioridade: agora |
| **F0** | pandas 3.0 copy_on_write | Verificar compatibilidade. Prioridade: agora |
| **F5** | vectorbt-rust engine | Backtest mais rápido. Transparente — sem código |
| **EXTRA** | ccxt + yfinance | Desligados para MVP |
