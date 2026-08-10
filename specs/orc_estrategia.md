# SPEC S28 — Aba Estratégia: 5 Gráficos Multi-Filtro

> **Versao:** 1.1.0 | **Status:** IMPLEMENTADO (G1 a G5 no Dashboard)
> **Wire:** `orc_metricas.py` → /performance + /vector/correlation → React sub-tab "Estratégia"
> **Depende de:** S2.5 (backfill Parquet), S25 F2 (compute_indicators)

---

## FERRAMENTAS VECTOR BT — MAPA COMPLETO

### ✅ Usadas (8)

| Ferramenta | Tipo | Módulo | Uso |
|-----------|------|--------|-----|
| `vbt.MA` | Indicador | `basic.py` | SMA 14/20/50 |
| `vbt.BBANDS` | Indicador | `basic.py` | Bollinger (20,2) |
| `vbt.RSI` | Indicador | `basic.py` | RSI (14) |
| `vbt.MACD` | Indicador | `basic.py` | MACD (12,26,9) |
| `vbt.STOCH` | Indicador | `basic.py` | Stochastic (14,3,3) |
| `vbt.ATR` | Indicador | `basic.py` | ATR (14) |
| `vbt.OBV` | Indicador | `basic.py` | OBV |
| `vbt.Portfolio.from_signals` | Backtest | `portfolio` | Sharpe, DD, equity |

### ⬜ NÃO Usadas — Nativas Vector BT (2)

| Ferramenta | Motivo para wirear |
|-----------|-------------------|
| `vbt.MSTD` | Volatilidade rolling (substitui cálculo manual) |
| `vbt.IndicatorFactory` | Criar indicadores customizados (regime detection, etc) |

### ⬜ NÃO Usadas — Acesso `.vbt` / `.ta` (100+ indicadores)

Vector BT expõe pandas-ta via acessor `.ta` em Series/DataFrame. Disponíveis
mas não wireados:

| Categoria | Indicadores | Prioridade |
|-----------|------------|------------|
| **Tendência** | ADX (já manual), CCI, Aroon, DPO, KST, Ichimoku (cortado), PSAR, TRIX, Vortex | 🔴 ADX wireado manualmente |
| **Momentum** | RSI (✅), Stoch (✅), WPR, MFI, UltimateOscillator, ROC, TSI, UO | 🟡 WPR útil p/ sobrecomprado/vendido |
| **Volatilidade** | BBANDS (✅), ATR (✅), Donchian, Keltner, Ulcer Index | 🟡 Donchian p/ breakout |
| **Volume** | OBV (✅), AD, CMF, EOM, ForceIndex, KVO, MFI, NVI, PVI, PVT, VPT, VWAP | 🟡 AD p/ confirmação de tendência |
| **Ciclo** | DPO, EBSW, HT | ⚪ Baixa prioridade |
| **Sobreposição** | SMA (✅), EMA, WMA, HMA, DEMA, TEMA, KAMA, MAMA, VWAP, ZLEMA | 🟡 HMA p/ lag reduzido |
| **Estatístico** | Beta, Correlation, Kurtosis, MAD, Median, Quantile, Skew, StDev, Variance, ZScore | 🔴 Correlação cross-pair já existe |

---

## ABA ESTRATÉGIA — 5 Gráficos

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  ESTRATÉGIA   [Símbolo: ▼ XAUUSD]  [TF: ▼ H_1]  [Ano: ▼ 2026] │
├──────────────┬──────────────┬──────────────────────────────┤
│  G1: Força   │  G2: Cruzam. │  G3: Precisão                │
│  Relativa    │  Estratégias │  YoY                          │
│  (radar 5    │  (heatmap    │  (barras empilhadas           │
│   ativos)    │   5×5 cross) │   azul=acerto verm=erro)     │
├──────────────┴──────────────┼──────────────────────────────┤
│  G4: Equity Curve           │  G5: Sinais × Resultados     │
│  (linha cumulativa,         │  (scatter: score F1 × PnL,   │
│   5 ativos sobrepostos)     │   tamanho = volume)          │
└─────────────────────────────┴──────────────────────────────┘
```

### G1 — Força Relativa (Radar)

```
Dados: orc_mercado.strength_rank dos 5 ativos
Eixos: Vol%, Lat%, change_1h, ADX, RSI
Radar com 5 pontas (1 por ativo), normalizado 0-100
```

### G2 — Cruzamento de Estratégias (Heatmap 5×5)

```
Dados: correlação entre sinais dos pares
Eixo X/Y: 5 ativos
Célula: correl(RSI_XAUUSD, RSI_EURUSD) etc
Cor: verde=convergem, vermelho=divergem
Filtro: período (7d, 30d, 90d, 1a)
```

### G3 — Precisão YoY (Barras Empilhadas)

```
Dados: trades.db → agrupado por ano/mês
Eixo X: meses (Jan-Dez)
Eixo Y: % acertos
Barra azul = win, barra vermelha = loss
Filtro: símbolo, estratégia (S1/S2), ano
```

### G4 — Equity Curve (Linha)

```
Dados: orc_metricas ou Vector BT Portfolio
Eixo X: tempo (dias)
Eixo Y: PnL acumulado ($)
5 linhas sobrepostas (1 por ativo) + linha preta (total)
Filtro: período, estratégia
```

### G5 — Sinais × Resultados (Scatter)

```
Dados: score F1 × PnL do trade
Eixo X: score do sinal (0-100)
Eixo Y: PnL do trade ($)
Tamanho da bolha: volume/lote
Cor: verde=ganho, vermelho=perda
Filtro: símbolo, período
```

---

## PIPELINE DE DADOS

```
Backfill Parquet           F0 (ongoing)            F4 trades.db
    │                          │                       │
    └──────────┬───────────────┘                       │
               ▼                                       │
         DataSource                                    │
               │                                       │
    ┌──────────┼──────────┐                            │
    ▼          ▼          ▼                            │
  orc_       orc_       orc_                           │
  mercado    vectorbt   metricas                       │
  (força,    (RSI,      (PnL,                          │
   vol%)     MACD...)    win%)                         │
    │          │          │                            │
    └──────────┼──────────┼────────────────────────────┘
               ▼          ▼
     /vector/strategy (NOVO)
               │
         React sub-tab "Estratégia"
```

---

## CHECKLIST DE IMPLEMENTAÇÃO

| Fase | Item | Dependência | Status |
|------|------|-------------|--------|
| **0** | Backfill 2 anos executado | `backfill_orc_coleta.py` | ✅ |
| **0** | F0 restart (Parquet persistente ativo) | Reiniciar servidor | ✅ |
| **1** | `/vector/panda` → indicadores reais | compute_indicators() | ✅ |
| **1** | G1 — Radar força relativa | orc_mercado (já pronto) | ✅ |
| **2** | G2 — Heatmap correlação | micro_orc_analise (já pronto) | ✅ |
| **3** | G3 — Precisão YoY | trades.db populado (F4) | ✅ |
| **3** | G4 — Equity curve | Vector BT Portfolio / orc_metricas | ✅ |
| **3** | G5 — Sinais × Resultados | trades.db + scores F1 | ✅ |
| **4** | Wire `/vector/strategy` | Todos acima | ✅ |
| **4** | React sub-tab "Estratégia" | Endpoint pronto | ✅ |
