# SPEC S27 — Vector BT Integration Overview (v3.0)

> **Versao:** 3.0.0 | **Wire:** utils/orc_vectorbt.py → storage_orc_vbt.py → Portfolio | **Status:** active
> **R-USE:** vectorbt 0.26.0 — motor unico de indicadores + backtest + stops + patterns
> **Atualizado:** 2026-08-04 — stops nativos, walk-forward, candlestick patterns

## Fluxo completo (ATUALIZADO)

```
F0 MCP (1 minuto)
  └── poll_cycle() → 5 símbolos batch
       │
  ├─→ snapshot.json              → /vector/symbol/{sym} (cache rapido)
  ├─→ data/m1_{SYM}_{ANO}.parquet → OHLCV historico (S2.5)
  └─→ data/vbt_{SYM}.parquet     → Indicadores VBT (S27)

Fluxo de Backtest (NOVO):
  m1_{SYM}.parquet (2 anos)
       │
  ├─→ Portfolio.from_signals(entries, exits,
  │       sl_stop=0.01, tp_stop=0.02, sl_trail=True,    ← S40 OCO/Trail/80%
  │       fees=0.0001, slippage=0.001, freq='1min',
  │       group_by=symbol, cash_sharing=True)            ← Multi-asset
       │
  ├─→ Walk-Forward: RollingSplitter(window_len=365, set_lens=(90,))  ← S40
  ├─→ Monte Carlo: call_seq='random' × N simulações      ← S40
  └─→ Métricas: Sortino, VaR, Omega, DSR, stability      ← ReturnsAccessor

Fluxo de Padrões (NOVO):
  m1_{SYM}.parquet (OHLCV)
       │
  ├─→ TA-Lib: 61 candlestick patterns (se instalado)     ← S40
  └─→ Numpy: 10 patterns core (fallback sem TA-Lib)       ← S40
       │
  └─→ entries/exits → Portfolio.from_signals() → win_rate por padrão
```

## Bancos de dados (ATUALIZADO)

| Banco | Localizacao | Conteudo | Persistencia |
|-------|------------|----------|-------------|
| snapshot.json | status/snapshot.json | OHLCV M_1 atual + balance + posições | Sobrescrito a cada ciclo |
| m1 Parquet | data/m1_{SYM}_{ANO}.parquet | OHLCV M_1 historico (2 anos) | Append incremental |
| vbt Parquet | data/vbt_{SYM}.parquet | Indicadores VBT por timestamp | Append incremental |
| backtest_stats | data/backtest_{SYM}.parquet | Métricas walk-forward por janela | Append incremental |

## Indicadores (17 — mantidos)

### Implementados (orc_vectorbt.py)
| Categoria | Indicador | Lib |
|----------|----------|-----|
| Tendencia | ADX(14), SMA(14/20/50) | vbt + numpy |
| Momentum | RSI(14), MACD(12,26,9), STOCH(14,3,3) | vbt |
| Volatilidade | ATR(14), BBANDS(20,2) | vbt |
| Volume | OBV | vbt |
| — | HMA(14), Donchian(20), Keltner(20,2), CCI(14) | numpy |
| — | PSAR, WPR(14), Aroon(14), ZLEMA(14) | numpy |

## Novas capacidades (v3.0)

### Stops (nativos do Portfolio.from_signals)
| Parâmetro | Função | Uso cTrader |
|----------|--------|-------------|
| `sl_stop` | Stop-Loss fixo | M5 scalp: SL=5 pips |
| `tp_stop` | Take-Profit fixo | M5 scalp: TP=10 pips |
| `sl_trail` | Trailing Stop | M15 swing: trail ativo |
| `upon_stop_exit` | Comportamento ao disparar stop | Close parcial ou total |
| `adjust_sl_func_nb` | Callback Numba para SL dinâmico | D60: SL→BE |
| `adjust_tp_func_nb` | Callback Numba para TP dinâmico | D80: fecha 80% |

### Walk-Forward + Monte Carlo
| Técnica | API | Status |
|---------|-----|--------|
| Rolling Walk-Forward | `splitters.RollingSplitter` | ⬜ |
| Parameter Sweep | `run_combs` | ⬜ |
| Monte Carlo | `call_seq='random'` | ⬜ |
| Random Baseline | `RAND.run()` | ⬜ |
| Métricas Avançadas | `returns.accessors` (Sortino, VaR, Omega, DSR) | ⬜ |

### Candlestick Patterns (S40)
| Fonte | Padrões | Dependência |
|-------|---------|------------|
| TA-Lib | 61 | `pip install TA-Lib` (requer compilação C) |
| Numpy puro | 10 core | Zero dependências |

## Wire (ATUALIZADO)

| Endpoint | Fonte | O que retorna |
|----------|-------|--------------|
| `/vector/symbol/{sym}` | Parquet → snapshot fallback | OHLCV + VBT + Multi-TF |
| `/vector/symbol/{sym}/history/{days}` | Parquet | Serie temporal VBT (YoY) |
| `/vector/symbol/{sym}/patterns` | S40 | Padrões de candle detectados |
| `/vector/symbol/{sym}/walkforward` | RollingSplitter | Métricas por janela IS/OOS |
| `/performance` | Portfolio.from_signals | Sharpe, Sortino, DD, PnL, VaR |

## Gaps conhecidos (v3.0)

| Gap | Severidade | Ação |
|-----|-----------|------|
| Resample M1→M5/M15 não implementado | 🔴 | `pandas.resample('5T')` sobre m1_*.parquet |
| Walk-Forward não wireado | 🔴 | Novo SAT: splitter_orc_walkforward.py |
| Stops não usados no backtest | 🔴 | Ampliar orc_vbt_portfolio.py |
| TA-Lib não instalado | 🟡 | Começar com numpy puro (10 padrões) |
| Monte Carlo não implementado | 🟡 | Novo SAT: montecarlo_orc_vbt.py |
