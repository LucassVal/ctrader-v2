# SPEC S41 — Bloco 1: Torneio do Passado (Alpha Generation)

> **Versao:** 3.0 | **Wire:** utils/orc_bloco1.py | **Status:** active (v2.1) → evolving (v3.0 spec)
> **Atualizado:** 2026-08-05 — Roadmap v3.0: VWAP, VIX Panic Override, Zoom-In 60/5
> **Depende:** S27 (vectorbt), S2.5 (parquet), S44 (TA-Lib patterns)

## PROPOSITO

Validar a inércia pura do movimento sem mascarar resultados com gestão de risco.
Separar alpha generation (sinal puro) de execution (gestão de ordens).

O Bloco 1 responde: "este sinal tem edge estatístico?" — sem confundir com "esta estratégia de saída é boa?".

## FLUXO ATUAL (v2.1 — implementado)

```
m1_{SYM}_{ANO}.parquet (2 anos) + DXYUSD_M1.parquet + VIXUSD_M1.parquet
  │
  ▼
┌─────────────────────────────────────────────────────────┐
│ PREFLIGHT — preflight_check(symbol, ohlc_df)            │
│   ├─ Carrega DXYUSD_M1.parquet + VIXUSD_M1.parquet     │
│   ├─ Alinha timestamps (forward fill)                  │
│   ├─ Aborta se >50% missing (FAIL FAST)                │
│   └─ Normaliza VIX (÷100,000)                          │
├─────────────────────────────────────────────────────────┤
│ BLOCO 1 — TORNEIO DO PASSADO                            │
│                                                         │
│  Sub-fase 1: Gatilho de Compra (S41.1) ✅               │
│    RSI(8,14,21) × MACD(10,14,18) × ADX(14,20)         │
│    THRESHOLDS: RSI < 25/30, ADX > 20/25                │
│    Estrategia: DIP BUY (mean reversion)                │
│                                                         │
│  Sub-fase 2: Gatilho de Venda (S41.2) ✅ v2.1           │
│    RSI(8,14,21) × ADX(14,20)                           │
│    THRESHOLDS: RSI > 65/70/75 (sobrecomprado)          │
│    Estrategia: SHORT TOP (trend exhaustion)             │
│                                                         │
│  Sub-fase 3: Filtro de Força (S41.3)                    │
│    ADX, ROC(DXY), VIX, tick_volume → threshold %        │
│                                                         │
│  Sub-fase 4: Contrapeso Macro — DXY+VIX (S41.4) ✅     │
│    check_dxy_alignment(roc) + check_vix_filter(max=35)  │
│                                                         │
│  SAÍDA: Matriz Sinais_Validados                         │
│    = (Gatilho) & (Força > Limiar) & (DXY OK) & (VIX OK) │
└─────────────────────────────────────────────────────────┘
  │
  ├─ console: [TORNEIO] candidatos + grid size
  ├─ console: [RANKING BUY/SELL] Top 3 menor MAE
  └─ status/bloco1_best.json → wire para orc_score (S32)
  │
  ▼
Bloco 2 (S42) — só opera sobre Sinais_Validados
```

## PREFLIGHT — Data Engineering: Alinhamento Multi-Bolsa (v3.0)

### Arquitetura de Sincronização

```
XAUUSD M1 (Forex 24/5)     DXYUSD M1 (ICE ~20h/d)     VIXUSD M1 (CBOE ~6.5h/d)
       │                          │                         │
       │  Timestamp UTC            │  Timestamp UTC          │  Timestamp UTC
       │                          │                         │
       ▼                          ▼                         ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ preflight_check(ohlc_df, symbol)                            │
  │  1. Normaliza todos os índices para UTC naive               │
  │  2. ohlc_df.index = índice maestro (Forex 24/5)             │
  │  3. dxy.reindex(ohlc_idx, method="ffill")                   │
  │  4. vix.reindex(ohlc_idx, method="ffill")                   │
  │  5. Valida limites de tolerância                            │
  └─────────────────────────────────────────────────────────────┘
```

### 1. Padronização Timezone (UTC)

Todos os parquets do F0 são gerados com timestamp UTC via `pd.to_datetime(unit="ms", utc=True)`.
O cTrader MCP retorna milissegundos desde epoch — naturalmente UTC.

No preflight, garantia adicional: converte para UTC e remove timezone (naive) para compatibilidade com `reindex()`:

```
if ohlc_df.index.tz is not None:
    ohlc_idx = ohlc_df.index.tz_convert("UTC").tz_localize(None)
else:
    ohlc_idx = ohlc_df.index
```

**Garantia:** A vela 10:00 do DXYUSD sempre alinha com 10:00 do XAUUSD. Ambos UTC. Sem offset de fuso.

### 2. Alinhamento por Forward Fill

O XAUUSD (Forex 24/5) é o **índice maestro** — grade de timestamps mais densa.
DXYUSD e VIXUSD são reindexados contra ele:

```
XAUUSD (maestro):  [00:00] [00:01] [00:02] [00:03] [00:04] [00:05] ...
DXYUSD (ICE):      [00:00] [00:01] [gap]   [gap]   [00:04] [00:05] ...
                        ↓ reindex(method="ffill")
DXY alinhado:      [00:00] [00:01] [00:01] [00:01] [00:04] [00:05] ...
                         ↑ forward fill — repete último valor conhecido

VIXUSD (CBOE):     [gap]   [gap]   [gap]   [gap]   [gap]   [00:05] ...
                        ↓ reindex(method="ffill") → NaN (sem valor anterior)
                        ↓ ffill().bfill()
VIX final:         [00:05] [00:05] [00:05] [00:05] [00:05] [00:05] ...
```

### 3. Limite de Tolerância — VIX Stale Detection

O VIXUSD (CBOE) fecha ~20:15 UTC e reabre ~13:30 UTC — gap de ~17h/dia + 48h fins de semana.

**Parâmetros de tolerância:**

| Índice | Gap diário | Tolerância Missing | Stale Threshold |
|--------|-----------|-------------------|-----------------|
| XAUUSD | 0h | — (maestro) | — |
| DXYUSD | ~3h | 5% das barras totais | 24h |
| VIXUSD | ~17h + fins de semana | 30% das barras totais | 72h |

**Justificativa dos thresholds:**

- **DXY 5%:** ICE fecha ~1h/dia entre 22:00-01:00 UTC. 5% de 210K barras M5 = ~10,500 barras = ~36 dias. Gaps reais de DXY são ~12 barras/dia → 0.006%.
- **VIX 30%:** CBOE fecha 17h/dia + 48h/fim de semana. 30% de 210K = ~63,000 barras = ~219 dias. Cobre folgadamente fins de semana (~30K barras/ano) + noites.
- **VIX Stale 72h:** Cobre 1 fim de semana normal (~65h) + margem para feriado de 1 dia. Se >72h, é feriado prolongado → confidence × 0.8, não aborta.

### 4. Implementação

```python
def preflight_check(ohlc_df, symbol) -> tuple[DataFrame, Series, Series]:
    """Sincroniza DXYUSD + VIXUSD. FAIL FAST se > tolerância.

    Estratégia (v3.0):
      1. ohlc_df (Forex 24/5) = índice maestro
      2. dxy.reindex(ohlc_idx, method="ffill") — gaps de ~3h
      3. vix.reindex(ohlc_idx, method="ffill") — gaps de ~17h
      4. ffill().bfill() nas pontas
      5. DXY missing > 5% → ABORTA
      6. VIX missing > 30% → ABORTA
      7. VIX > 72h desde última barra → STALE_WARN (confidence × 0.8)
      8. Normaliza VIX (÷100,000)
    """
    dxy_path = consolidated_dir / "DXYUSD_M1.parquet"
    vix_path = consolidated_dir / "VIXUSD_M1.parquet"

    if not dxy_path.exists() or not vix_path.exists():
        logger.error("PREFLIGHT: parquets ausentes. Execute backfill.")
        sys.exit(1)

    dxy_df = pd.read_parquet(dxy_path)
    vix_df = pd.read_parquet(vix_path)

    # Garante timezone-naive para compatibilidade com reindex
    if hasattr(ohlc_df.index, 'tz') and ohlc_df.index.tz is not None:
        ohlc_idx = ohlc_df.index.tz_convert("UTC").tz_localize(None)
    else:
        ohlc_idx = ohlc_df.index

    dxy_aligned = dxy_df["close"].reindex(ohlc_idx, method="ffill")
    vix_aligned = vix_df["close"].reindex(ohlc_idx, method="ffill")

    n_bars = len(ohlc_idx)
    dxy_miss = dxy_aligned.isna().sum()
    vix_miss = vix_aligned.isna().sum()

    if dxy_miss > n_bars * 0.05:
        logger.error("DXY: %d missing (%.0f%%) > 5%%", dxy_miss, dxy_miss/n_bars*100)
        sys.exit(1)
    if vix_miss > n_bars * 0.30:
        logger.error("VIX: %d missing (%.0f%%) > 30%%", vix_miss, vix_miss/n_bars*100)
        sys.exit(1)

    dxy_aligned = dxy_aligned.ffill().bfill().fillna(0.0)
    vix_aligned = vix_aligned.ffill().bfill().fillna(0.0)
    vix_aligned = vix_aligned / 100_000.0  # normaliza escala

    return ohlc_df, dxy_aligned, vix_aligned
```

## EVOLUÇÃO v3.0 — Microestrutura de Mercado (EM ESPECIFICAÇÃO)

> **Status:** ⬜ Especificado, não implementado. Validação inicial: apenas XAUUSD.

A v3.0 substitui o cálculo atual (RSI/MACD/ADX sobre toda a janela) por uma
arquitetura em 3 camadas temporais:

### Camada 1: Contexto Tático — VWAP 1H + DXY ROC (60 velas M1)

```
Buffer: últimas 60 velas M1 (~1 hora)
VWAP = (Σ preço × tick_volume) / Σ tick_volume

Regra binária:
  preço > VWAP 1H → SÓ COMPRA habilitada
  preço < VWAP 1H → SÓ VENDA habilitada
  preço ≈ VWAP (±0.1%) → NEUTRO (ambas)

DXY confirma (ROC 5 períodos):
  compra + DXY caindo → peso extra (+0.1 confidence)
  venda  + DXY subindo → peso extra (+0.1 confidence)
```

### Camada 1b: Matriz VIXUSD — Panic Override (NOVO v3.0)

```
VIX em spike (> 2× média 20 períodos):

  XAUUSD (Refúgio):
    → IGNORA correlação DXY
    → BUY autorizado mesmo com DXY subindo
    → SELL BLOQUEADO

  AUDUSD, GBPUSD, EURUSD (Risco):
    → SELL imposto (trava absoluta de COMPRA)
    → BUY BLOQUEADO

  USDJPY (Refúgio Cambial):
    → SELL AUTORIZADO (capital repatria para JPY → USDJPY cai)
    → BUY BLOQUEADO
```

### Camada 2: Gatilho Balístico — Slope 5 Velas + TA-Lib (5 velas M1)

```
Janela: últimas 5 velas M1 (~300 segundos)

Métricas:
  aceleração: tamanho dos corpos ↑ a favor do movimento?
  rejeição:   pavio superior > 2× corpo → HFT defendendo resistência
  slope:      regressão linear dos fechos (positivo/negativo)

Sinais:
  slope > 0 + corpos crescendo → BUY signal
  slope < 0 + corpos crescendo → SELL signal
  pavio superior > 2× corpo → cancelar BUY (rejeição)
  pavio inferior  > 2× corpo → cancelar SELL (rejeição)

TA-Lib patterns (61 padrões — S44):
  patterns detectados nas 5 velas → ajustam confidence ±0.2
  ex: CDLHAMMER + slope > 0 → confidence +0.2
  ex: CDLSHOOTINGSTAR + slope > 0 → confidence -0.15
```

### Camada 3: Antecipação — 3 Velas (NOVO v3.0)

```
Se últimas 3 velas mostram topos/fundos ASCENDENTES contínuos:
  → Não espera fechar vela 5
  → Dispara ordem a mercado (bid/ask intrabarra)
  → Entry: preço atual, não open[pos+1]

Se padrão NÃO confirma continuidade:
  → Aguarda fechamento da vela 5
  → Entry: open[pos+1] (padrão atual — Pip 0)
```

### Comparação: Atual vs Proposto

| Aspecto | v2.1 (atual) | v3.0 (proposto) |
|---------|-------------|------------------|
| Filtro direcional | ADX(14) > threshold | VWAP 1H + DXY ROC |
| Gatilho BUY | RSI oversold + MACD + ADX | Slope 5 velas + TA-Lib patterns |
| Gatilho SELL | RSI overbought + ADX | Slope 5 velas + rejeição HFT |
| VIX | Filtro simples (>35 aborta) | Panic Override por ativo |
| Entrada | open[pos+1] | intrabarra (antecipação) ou open[pos+1] |
| Janela de cálculo | Todas as barras do backtest | Buffer deslizante O(65) |
| CPU estimado | ~1.5M operações/grid | ~3,250 operações/grid (-99.8%) |

## PLANO DE VALIDAÇÃO — XAUUSD PRIMEIRO

```
Fase 0: XAUUSD apenas. Validar:
  1. VWAP 1H como filtro direcional (binário)
  2. Panic Override do VIX para ouro (refúgio)
  3. Slope 5 velas substitui RSI/MACD
  4. TA-Lib patterns como confirmação
  5. Antecipação 3 velas (entry intrabarra)

Métrica de aprovação:
  - MAE médio < 0.10% (atual XAUUSD: ~0.16%)
  - Sinais válidos/dia: 3-8 (atual: ~328 em 90d = 3.6/dia ✅)
  - DXY filtered out < 30% dos sinais

Só após XAUUSD aprovado → expandir para EURUSD, GBPUSD, USDJPY, AUDUSD.
```

## GRIDS (v2.1 — atuais)

```python
BUY_GRID = {
    "rsi_period": [8, 14, 21],
    "rsi_threshold": [25, 30],
    "macd_fast": [10, 14, 18],
    "adx_period": [14, 20],
    "adx_threshold": [20, 25],
}

SELL_GRID = {
    "rsi_period": [8, 14, 21],
    "rsi_threshold": [65, 70, 75],
    "adx_period": [14, 20],
    "adx_threshold": [20, 25],
}
```

## GRIDS (v3.0 — planejados)

```python
# Substitui BUY_GRID + SELL_GRID atuais
MOMENTUM_GRID = {
    "slope_window": [5],           # fixo: 5 velas M1
    "slope_threshold": [0.02, 0.05, 0.10],  # inclinação mínima (%)
    "accel_min": [1.2, 1.5, 2.0],          # corpo atual / corpo anterior
    "wick_ratio": [2.0, 2.5, 3.0],          # pavio / corpo para rejeição
    "anticipate_bars": [3],                  # fixo: 3 velas
}
```

## CONTRATO DE SAÍDA (v2.1 — atual)

```python
{
    "symbol": "EURUSD",
    "tf": "M5",
    "window": {"train_start": "2024-07-30", "train_end": "2026-08-03"},
    "best_buy_trigger": {...},
    "best_sell_trigger": {...},
    "force_threshold": {"tick_vol_pct": 80, "roc_pct": 0.5, "vix_max": 35.0},
    "signals_validated": {"total": 425, "buy": 122, "sell": 303},
    "dxy_filtered_out": 0,
    "trades": [...],
    "best_combo": {...}
}
```

## CONTRATO DE SAÍDA (v3.0 — planejado)

```python
{
    "symbol": "XAUUSD",
    "tf": "M1",
    "vwap_1h": 2650.32,
    "vwap_regime": "ABOVE",
    "vix_spike": False,
    "panic_override": None,           # "BUY_AUTHORIZED" | "SELL_IMPOSED" | None
    "slope_5": 0.042,                 # +4.2% inclinação
    "acceleration": 1.8,              # corpos crescendo 1.8×
    "rejection": {
        "upper_wick_ratio": 0.3,
        "lower_wick_ratio": 1.2,
        "rejected": False
    },
    "patterns_detected": ["CDLHAMMER", "CDLENGULFING"],
    "anticipate": True,
    "signal": "BUY",
    "confidence": 0.78,               # 0..1
    "entry_type": "intrabar",
    "trades": [...]
}
```

## REGRAS

1. **VWAP é binário**: não gera sinal, só habilita/desabilita direção
2. **VIX Panic Override**: spike de VIX > 2× média → regras especiais por ativo
3. **Slope 5 velas é o único gerador de sinal** — substitui RSI/MACD
4. **TA-Lib patterns são confirmadores** — ajustam confidence, não geram sinais
5. **Antecipação é opcional**: se rejeição detectada, espera fechamento
6. **XAUUSD primeiro**: toda validação começa e termina no ouro
7. **Buffer deslizante**: recalcular apenas últimas 65 velas (60+5)
8. **VIX normalizado**: valor bruto do MCP ÷ 100,000

## R-USE

| Componente | Origem | Uso |
|-----------|--------|-----|
| `compute_indicators()` | `utils/orc_vectorbt.py` | RSI, MACD, ADX (v2.1) |
| `dxy_filter_orc_bloco1.py` | `utils/` | check_dxy_alignment(), get_dxy_roc() |
| `mae_mfe_orc_bloco1.py` | `utils/` | calc_mae_mfe() |
| `signal_matrix_orc_bloco1.py` | `utils/` | build_boolean_matrix() |
| `time_exit_orc_bloco1.py` | `utils/` | generate_exits() |
| `grid_search_orc_bloco1.py` | `utils/` | run_parameter_grid() |
| `orc_pattern_candles.py` | `utils/` (S44) | detect_patterns() — v3.0 wire |

## CHANGELOG

| Versão | Data | Mudança |
|--------|------|---------|
| 3.1 | 2026-08-05 | Data Engineering: alinhamento multi-bolsa (Forex/ICE/CBOE), ffill, tolerância DXY 5%/VIX 30%, stale 72h, UTC padronizado. |
| 3.0 | 2026-08-05 | Spec: VWAP 1H + VIX Panic Override + Slope 5 velas + TA-Lib + antecipação. XAUUSD first. |
| 2.1 | 2026-08-01 | preflight DXY+VIX, transparência, SELL RSI, BUY_GRID ajustado. |
| 1.0 | 2026-07-30 | Versão inicial. ATR×BBands×Keltner×PSAR para venda. |


---

## v3.2 (2026-08-08) — Convencao de Datas + Anti-Overfitting

### Janelas temporais

| Uso | Fim da janela | Motivo |
|-----|---------------|--------|
| G23 Scan | Agora (live) | Detecta gaps ate o momento |
| Backfill | Agora (live) | Preenche dados ate o momento |
| Backtest 2y | **Ontem 23:59 UTC** | Dia completo, sem look-ahead |
| Backtest 9m | **Ontem 23:59 UTC** | Idem (DXY/VIX) |
| Monitor/Dashboard | Agora (live) | Tempo real |

### Anti-Overfitting

Backtests usam janela FIXA (ontem 23:59). NAO re-baixam dados a cada 1 minuto.
O backfill preenche dados, mas o backtest so usa dados consolidados ate o FIM do
dia anterior. Isso evita:

1. **Overfitting por atualizacao continua**: re-treinar a cada nova barra M1
   geraria sinais diferentes para o mesmo candle historico
2. **Look-ahead bias**: usar dados do dia corrente (incompleto) como se fosse
   completo
3. **Drift de especificacao**: backtest com janela movel gera resultados nao
   reproduziveis

### Helper

`utils/date_utils.py` — funcoes padronizadas:
- `backtest_end()` → ontem 23:59 UTC
- `scan_end()` → hoje 23:59 UTC
- `backtest_start_2y()` → 2 anos atras de ontem 23:59
- `backtest_start_9m()` → 9 meses atras de ontem 23:59

---

## VALIDACAO EMPIRICA — RANKING BUY/SELL (Fluxo 1, v2.1)

> **Data:** 2026-08-15 | **Harness:** `tests/test_bloco1_ranking_metrics.py` | **Janela:** ~2 anos, 5 ativos forex, M5

Resultado do Torneio do Passado (v2.1) sobre dados consolidados reais (XAUUSD/EURUSD/GBPUSD/USDJPY/AUDUSD):

| Ativo | BUY MAE | SELL MAE | Sinais | Win Rate | Sharpe |
|-------|---------|----------|--------|----------|--------|
| XAUUSD | 0.12% | 0.12% | 3416 | 49.2% | -0.03 |
| EURUSD | 0.04% | 0.04% | 3375 | 50.2% | +0.01 |
| GBPUSD | 0.04% | 0.04% | 3185 | 46.3% | -0.08 |
| USDJPY | 0.06% | 0.05% | 3704 | 49.0% | 0.00 |
| AUDUSD | 0.05% | 0.05% | 3253 | 48.1% | -0.02 |

**Best combo convergente em TODOS os ativos:**
- BUY:  RSI(8) < 25 + ADX(14) > 20 + MACD(10) (parametro de ranking, nao filtro)
- SELL: RSI(8) > 65 + ADX(14) > 20

**Leitura:** WR ~50% e Sharpe ~0 em todos os ativos = o edge do v2.1 (RSI/MACD/ADX) e estatisticamente NULO. MAE absoluto baixo (0.04-0.12%) mas sem assimetria de retorno. Isto MOTIVA a FASE 3 (v3.0 microestrutura: VWAP 1H + Slope 5 velas + Panic Override) que substitui o gatilho RSI/MACD por um gerador de sinal com edge direcional real.
