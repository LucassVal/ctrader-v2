# BLUEPRINT: SISTEMA DE TRADING AUTÔNOMO — cTRADER V2
>
>**Versão:** 2.0.0  
>**Data:** 2026-07-22  
>**Escopo:** 5 ativos (XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD)  
>**Modo:** Demo → 30 dias validação → Real (lote 0.1 por +15 dias)  
>**Custo mensal estimado:** < $10 (apenas DeepSeek Pro)

---

## 1. VISÃO GERAL

Sistema modular de 5 fases que coleta dados do cTrader via MCP, analisa localmente com matemática (custo zero), cruza scores em um JSON único, submete à validação final de uma IA (DeepSeek Pro), executa ordens OCO com gestão mecânica de risco, e se auto-calibra a cada 50 trades.

```
[F0] MCP cTrader ──df_master──→ [F1] 3 Pilares ──scores_raw──→ [F2] Fusão
                                                                     │
                                                             final_adjusted >= 70?
                                                                  │        │
                                                                 SIM      NÃO → [F5] Log
                                                                  │
                                                                  ▼
                                                             [F3] DeepSeek Pro
                                                                  │
                                                   ┌──────────────┼──────────────┐
                                                   ▼              ▼              ▼
                                               APPROVE      REJECT+reason   TIMEOUT
                                                   │              │         (≥3s)
                                                   │              │              │
                                                   │              │      fallback mecânico
                                                   │              │      (score≥85=APPROVE)
                                                   │              │              │
                                                   ▼              ▼              ▼
                                             [F4] Execução   [F5] Log     [F4] Execução
                                             OCO + 80/20     (rejeitado)  (lote 0.5x)
                                             + Trail BE
                                                   │
                                                   ▼
                                             [F5] Log + MAR
```

---

## 2. ARQUITETURA DE FASES

### FASE 0 — COLETA

| Atributo | Valor |
|----------|-------|
| **Script** | `f0_collector.py` |
| **Fonte** | cTrader Desktop via MCP (navegador, conexão local) |
| **Custo** | Zero |
| **Persistência** | `df_master_1min` em memória + parquet a cada 1h (backup) |

**Polling (adaptativo):**

| Dado | Frequência | Chamada MCP |
|------|-----------|-------------|
| Spot prices (bid, ask, spread) | 3 segundos | `get_spot_prices(symbolId)` |
| DOM (depth of market) | 3 segundos | `get_dom(symbolId)` |
| Candles 1min (OHLCV) | 60 segundos | `get_trendbars(symbolId, "m1", count=100)` |
| Sentimento (long/short %) | 60 segundos | `get_account_statistics()` |
| Balanço / Margem | 60 segundos | `get_balance()` |
| DXY sintético | 60 segundos | `get_trendbars(dxy_proxy_id, "m1", count=1)` |

**Símbolos monitorados:** XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD (5 ativos)

**Estrutura do `df_master_1min`:**  
`timestamp, symbol, open, high, low, close, tick_volume, spread, bid, ask, dom_bid_wall, dom_ask_wall, sentiment_ratio, dxy_close`

**Validação:** `len(df_master) >= 2` e `spread > 0`. Se falhar 3x consecutivas → reconecta MCP.

---

### FASE 1 — ANÁLISE LOCAL (3 PILARES)

| Atributo | Valor |
|----------|-------|
| **Script** | `f1_analyzer.py` |
| **Ferramentas** | Pandas-TA, NumPy |
| **Custo** | Zero |

**Pré-condição — Filtro de calendário (offline):**  
Antes de analisar, cruza `datetime.utcnow()` com `blackout_times.json` (arquivo hardcoded com eventos de alto impacto: NFP, FOMC, CPI, ISM). Se evento nos próximos 15 min → flag `news_imminent = true`. Se `news_imminent`, todos os scores são mantidos mas o lote máximo é reduzido para 0.02 na F4. O DOM da F0 também serve como detector secundário de "parede institucional".

**3 Pilares (TFs fixos: M5, M10, M15):**

#### Pilar 1 — Macro / Contexto
```
score_macro = (dxy_trend_zscore * 0.40) 
            + (sentiment_contrarian * 0.35) 
            + (tick_volume_percentile * 0.25)
            
dxy_trend_zscore      = (dxy_close - sma_dxy_20) / std_dxy_20  // normalizado
sentiment_contrarian  = 100 - (long_ratio * 100)                 // 0=extremo long, 100=extremo short
tick_volume_percentile = percentile(tick_volume, window=100)     // 0-100
```
**TF:** M15  
**Lógica:** Se todo mundo está comprado (long_ratio > 80%), o score cai. Contrarian.

#### Pilar 2 — Volatilidade
```
score_vol = (atr_percentile * 0.50) 
          + (vol_contango * 0.30) 
          + (spread_percentile * 0.20)

atr_percentile    = percentile(ATR(14), window=100)
vol_contango      = ATR_M5 / ATR_M15  // >1 = curto prazo mais volátil (aceleração)
spread_percentile = percentile(spread, window=100) invertido  // spread alto = score baixo
```
**TFs:** M5 (curto), M15 (longo)  
**Lógica:** `vol_contango > 1` significa que o M5 está mais volátil que o M15 — mercado "esticando". Excelente preditor de rompimento.

#### Pilar 3 — Técnico
```
score_tec = (rca_signal * 0.45) 
          + (delta_imbalance * 0.35) 
          + (rsi_extreme * 0.20)

rca_signal       = RCA(close, volume, window=14)  // Relative Comparative Analysis
delta_imbalance  = |bid_volume - ask_volume| / (bid_volume + ask_volume) * 100
rsi_extreme      = |RSI(7) - 50| * 2  // distância do centro, 0-100
```
**TF:** M5  
**Lógica:** Combina momentum (RCA), fluxo de ordens (delta) e condição extrema (RSI).

**Saída — `scores_raw.json`:**
```json
{
  "trace_id": "T20260722-143000-001",
  "timestamp_utc": "2026-07-22T14:30:00Z",
  "symbol": "XAUUSD",
  "news_imminent": false,
  "scores": {
    "macro": 72,
    "volatilidade": 58,
    "tecnico": 81
  }
}
```

**Validação:** Cada score ∈ [0, 100]. Scores fora do range → recalcula.

---

### FASE 2 — FUSÃO

| Atributo | Valor |
|----------|-------|
| **Script** | `f2_fusion.py` |
| **Ferramentas** | Python stdlib |
| **Custo** | Zero |

**Processamento:**
```
1. Carregar scores_raw.json (F1)
2. Carregar pesos:
   - Se custom_rules.json existe (F5): usar pesos calibrados pelo MAR
   - Senão: pesos iniciais = {macro: 0.33, volatilidade: 0.33, tecnico: 0.34}
3. Score Final Bruto = (macro * w1) + (vol * w2) + (tec * w3)
4. Aplicar redutores:
   - Se news_imminent: -15
   - Se spread > 2 pips: -10
   - Se |dom_imbalance| > 0.7: -10 (parede institucional)
   - Se sessão Sydney (22:00-07:00 UTC): -20
   - Se rollover (21:55-22:05 UTC): REJECT automático
5. Score Final = Score Bruto - redutores
```

**Threshold de entrada:** Score Final >= 70 → encaminha para F3. Abaixo → descarta (log F5).

**Saída — `fusion_output.json`:**
```json
{
  "meta": {
    "trace_id": "T20260722-143000-001",
    "timestamp_utc": "2026-07-22T14:30:00Z",
    "symbol": "XAUUSD",
    "timeframe": "M15",
    "slot_used": 12,
    "slot_max": 30,
    "positions_open_symbol": 2
  },
  "scores": {
    "macro":          { "raw": 72, "weight": 0.33, "weighted": 23.76 },
    "volatilidade":   { "raw": 58, "weight": 0.33, "weighted": 19.14 },
    "tecnico":        { "raw": 81, "weight": 0.34, "weighted": 27.54 },
    "final_raw": 70.44,
    "reducers_applied": [],
    "final_adjusted": 70.44,
    "threshold": 70
  },
  "context": {
    "news_imminent": false,
    "spread_pips": 0.88,
    "session": "LONDON",
    "dxy_trend": "BULLISH",
    "atr_14_m5": 12.5,
    "atr_14_m15": 10.8,
    "sentiment_ratio": 0.62,
    "dom_imbalance": 0.15
  }
}
```

---

### FASE 3 — VALIDAÇÃO IA

| Atributo | Valor |
|----------|-------|
| **Script** | `f3_validator.py` |
| **Modelo** | DeepSeek Pro |
| **Custo por chamada** | ~$0.000084 (95% cacheado) |
| **Timeout** | 3 segundos |
| **Fallback** | Mecânico (score >= 85 = APPROVE) |

**Prompt (cacheado — system fixo):**
```
System: "Você é um validador de qualidade para trading algorítmico.
         Analise os scores cruzados e o contexto de mercado.
         Responda EXCLUSIVAMENTE com JSON válido, sem texto adicional.
         Campos obrigatórios: decision (APPROVE|REJECT).
         Se APPROVE: confidence (0-1), adjustments (lot_multiplier, timeout_min, be_trigger_pct).
         Se REJECT: reason (SENTIMENT_EXTREMO|SPREAD_ALTO|CONSOLIDACAO|BAIXA_VOLATILIDADE|FORA_SESSAO|SCORE_INSUFICIENTE),
                    reason_detail (string explicativa)."

User: "<fusion_output.json como string>"
```

**Regras de decisão da IA:**
- Só rejeita se identificar padrão de risco CRUZANDO os 3 pilares
- Exemplo de rejeição: `macro=20, vol=80, tec=90` → "Contexto macro contradiz técnico. Consolidação provável."
- Exemplo de rejeição: `news_imminent=true, sentiment=0.85` → "Arrastão pré-news. Não entrar."

**Saída — `verdict.json`:**
```json
{
  "decision": "APPROVE",
  "confidence": 0.82,
  "adjustments": {
    "lot_multiplier": 1.0,
    "timeout_min": 15,
    "be_trigger_pct": 80
  }
}
```

```json
{
  "decision": "REJECT",
  "reason": "CONSOLIDACAO",
  "reason_detail": "Scores conflitantes: macro baixo (20) com técnico alto (90). Sem convicção direcional."
}
```

**Fallback mecânico (IA timeout > 3s ou erro de parse):**
```
SE final_adjusted >= 85:
  → APPROVE com lot_multiplier=0.5, timeout_min=10, be_trigger_pct=70
SENÃO:
  → REJECT, reason: IA_TIMEOUT
```

**Custo real:** ~100 chamadas/dia (apenas trades com score >= 70). 20 dias = 2000 chamadas × $0.000084 = **$0.17/mês**.

#### 3.1 Regra de Coerência Timeout × Timeframe

**O `timeout_min` retornado pela IA DEVE ser coerente com o timeframe do trade.** Timeframe mais curto = timeout mais curto, senão o slot fica travado e a rotatividade morre.

| Timeframe | timeout_min (mín) | timeout_min (máx) | Lógica |
|-----------|-------------------|-------------------|--------|
| **M5** | 5 | 10 | Scalp rápido. Se não rompeu em 10 min, morreu. |
| **M10** | 8 | 15 | Meio termo. |
| **M15** | 10 | 20 | Tendência. Mais tempo para respirar. |

**Validação no `f3_validator.py`:**  
Após receber o verdict da IA (ou gerar fallback), o script DEVE truncar `timeout_min` ao máximo permitido pelo timeframe. Exemplo: se a IA retornar `timeout_min=20` para um trade M5, o script corrige para `timeout_min=10`.

```
# f3_validator.py — pós-parse do verdict
TIMEOUT_MAX = {"M5": 10, "M10": 15, "M15": 20}
tf = fusion_output["meta"]["timeframe"]
verdict["adjustments"]["timeout_min"] = min(
    verdict["adjustments"]["timeout_min"],
    TIMEOUT_MAX[tf]
)
```

**No fallback mecânico**, os valores padrão por TF são:
- M5: `timeout_min=8`
- M10: `timeout_min=12`
- M15: `timeout_min=15`

---

### FASE 4 — EXECUÇÃO + GESTÃO DE RISCO

| Atributo | Valor |
|----------|-------|
| **Script** | `f4_executor.py` |
| **Conexão** | cTrader MCP + OCO nativa do broker |
| **Custo** | Zero |

#### 4.1 Pré-Entrada (gates)

| # | Condição | Ação se falhar |
|---|----------|---------------|
| G1 | `freeMargin > marginRequired` (1% risco) | REJECT: margem insuficiente |
| G2 | Posições abertas no mesmo símbolo < 3 | REJECT: limite por símbolo |
| G3 | Slots usados no TF atual < 30 | REJECT: pool esgotado |
| G4 | Sessão ≠ Sydney (22:00-07:00 UTC) | REJECT: baixa liquidez |
| G5 | Fora do rollover (21:55-22:05 UTC) | PAUSE: reconectar após |
| G6 | `news_imminent = false` OU lote ajustado | Ajusta: lote_max = 0.02 |

#### 4.2 Entrada

```
1. lote = 0.1 * lot_multiplier (F3)
   Se news_imminent: lote = min(lote, 0.02)

2. Calcular SL e TP baseados em ATR:
   direction = BUY|SELL (definido pelo sinal do Pilar 3)
   SL = entry ± (ATR_M15 * 1.0)
   TP = entry ± (ATR_M15 * 2.0)   // RR 1:2

3. Enviar ordem OCO:
   MCP::place_market_order(
     symbolId   = <id>,
     direction  = BUY|SELL,
     volume     = <lote * lotSize> (UNITS, nunca lots),
     stopLoss   = <SL>,
     takeProfit = <TP>
   )
   → orderId, positionId
```

#### 4.3 Monitoramento (loop 1s) + Estratégia de Degraus + 80/20

```
ENTRADA ABERTA. Loop a cada 1 segundo:

┌──────────────────────────────────────────────────────────────────┐
│ DEGRAU 0 — BREAKEVEN RÁPIDO (5% do TP ou 1.5 pips):             │
│   Dispara assim que o preço anda o MÍNIMO a favor.               │
│   → Lê spread DIRETO do MCP (MCP::get_spot_prices), nunca do     │
│     df_master. Sem delay, sem acoplamento com F0.                │
│   → Move SL para entry + spread_atual                            │
│   → A partir daqui, o pior cenário é sair NO ZERO (BE).          │
│   → Essencial para a rotatividade: trade lateral não toma loss.  │
│                                                                  │
│ DEGRAU 40%: pnl >= 40% do TP                                     │
│   → Apenas anota. Não age.                                       │
│                                                                  │
│ DEGRAU 60%: pnl >= 60% do TP                                     │
│   → Move SL para entry + (30% do ganho acumulado)                │
│   → Ex: entry=$2000, TP=$2010, pnl=$6 (60%)                      │
│     SL sobe para $2000 + $1.80 = $2001.80                        │
│                                                                  │
│ DEGRAU 80%: pnl >= 80% do TP                                     │
│   → FECHA 80% DO LOTE (realiza lucro)                            │
│   → Reenvia OCO para a sobra (20%):                              │
│       MCP::amend_position(positionId, stopLoss=entry+spread,     │
│                          takeProfit=tp_original)                  │
│     // OCO no servidor garante proteção mesmo se script cair.    │
│   → 20% RESTANTE: ativa TRAILING STOP (loop local 1s)           │
│                                                                  │
│ TRAILING STOP NOS 20% RESTANTES:                                 │
│   highest = max(entry, current_price)                            │
│   trail_sl = highest - (ATR_M5 * 0.3)                            │
│                                                                  │
│   REGRA DE OURO — TRAVA NO BE:                                   │
│   SE trail_sl < (entry + spread_atual):                          │
│      trail_sl = entry + spread_atual                             │
│      // NUNCA, SOB NENHUMA HIPÓTESE, volta abaixo do BE          │
│                                                                  │
│   SE current_price <= trail_sl:                                  │
│      → FECHA posição (sai no lucro)                              │
│                                                                  │
│ TIMEOUT (valor da F3, truncado ao máx do TF):                    │
│   SE tempo desde último highest_price > timeout_min:             │
│      → FECHA posição (rotatividade — libera slot)                │
│                                                                  │
│ SL/TP ORIGINAIS:                                                 │
│   Se SL ou TP atingidos → ordem fechada pelo broker              │
│   (OCO nativa — independente do script)                          │
└──────────────────────────────────────────────────────────────────┘
```

**Por que o Degrau 0 é crítico:**

| Sem Degrau 0 | Com Degrau 0 |
|-------------|-------------|
| Preço anda +2 pips e reverte → loss de 1 ATR (~10 pips) | Preço anda +2 pips e reverte → sai no BE (0) |
| Mercado lateral (40% do tempo) destrói a conta | Mercado lateral = zero a zero, slot liberado |
| Rotatividade morre (slot preso em loss) | Rotatividade vive (slot liberado rapidamente) |

O custo do Degrau 0 é apenas o spread (já pago na entrada). O ganho é eliminar losses em trades que "quase foram".

#### 4.4 Pool de Slots

| Timeframe | Slots/dia | Lógica |
|-----------|-----------|--------|
| M5 | 30 | Scalp rápido |
| M10 | 30 | Médio prazo |
| M15 | 30 | Tendência |
| **Total** | **90** | Controlado por margem, não por contagem |

Um slot é "usado" quando uma entrada é executada. Ao fechar (lucro, prejuízo, timeout, BE), o slot é liberado. Se 30 slots do TF já foram usados no dia, o sistema para de entrar naquele TF.

#### 4.5 Regras de Segurança

| # | Regra | Tipo |
|---|-------|------|
| R1 | Nunca martingale (lote NUNCA dobra após perda) | Hard block |
| R2 | Máximo 3 posições simultâneas no mesmo símbolo | Hard block |
| R3 | Rollover (21:55-22:05 UTC): fecha tudo ou pausa | Hard block |
| R4 | drawdown diário > 3%: kill switch (fecha tudo, pausa 24h) | Circuit breaker |
| R5 | drawdown semanal > 5%: pausa até segunda | Circuit breaker |

**Saída — `execution_log.json`:**
```json
{
  "trace_id": "T20260722-143000-001",
  "symbol": "XAUUSD",
  "direction": "BUY",
  "entry_price": 2000.50,
  "volume": 1000,
  "sl_initial": 1990.00,
  "tp_initial": 2021.00,
  "exit_price": 2018.30,
  "exit_reason": "DEGRAU_80_TRAIL_BE",
  "pnl_gross": 17.80,
  "pnl_net": 17.80,
  "duration_seconds": 423,
  "trail_activated": true,
  "be_locked": true
}
```

---

### FASE 5 — LOG + MAR (MOTOR DE AJUSTE DE RANKING)

| Atributo | Valor |
|----------|-------|
| **Script** | `f5_mar.py` |
| **Persistência** | SQLite (`trades.db`) |
| **Custo** | Zero |

#### 5.1 Log (toda entrada, executada ou rejeitada)

**Tabela SQLite:**
```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trace_id TEXT UNIQUE,
    timestamp_utc TEXT,
    symbol TEXT,
    timeframe TEXT,
    scores_json TEXT,       -- JSON completo da F2
    verdict_json TEXT,       -- JSON da F3
    execution_json TEXT,     -- JSON da F4 (null se REJECT)
    decision TEXT,           -- APPROVE | REJECT
    rejection_reason TEXT,   -- null se APPROVE
    pnl_net REAL,            -- null se REJECT
    exit_reason TEXT,        -- null se REJECT
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
```

#### 5.2 MAR — Auto-Calibragem Diária com Média Móvel

**Gatilho:** Diário (00:00 UTC), não por contagem de trades. O flag `new_day` vem do `f4_executor.py`.

**Por que diário e não a cada 50 trades:** 50 trades podem ocorrer em 2 dias (alta volatilidade, overfitting rápido) ou em 15 dias (mercado lateral, sistema não se adapta). Âncora temporal fixa resolve ambos.

**Algoritmo (média móvel com peso 0.7):**

```python
# f5_mar.py — executa quando new_day = True
WEIGHT_UPDATE_RATE = 0.7  # 70% peso novo, 30% peso antigo (inércia)

# 1. Calcular pesos ideais do dia (baseado nos trades de hoje)
dia_ideal = calcular_pesos_do_dia()  # mesmo método original: agrupar por pilar, avaliar performance

# 2. Média móvel entre peso atual e peso ideal do dia
atuais = carregar_pesos_atuais()  # do custom_rules.json
novos_pesos = {
    'macro':         atuais['macro'] * 0.3 + dia_ideal['macro'] * 0.7,
    'volatilidade':  atuais['vol']  * 0.3 + dia_ideal['vol']  * 0.7,
    'tecnico':       atuais['tec']  * 0.3 + dia_ideal['tec']  * 0.7
}

# 3. Normalizar (soma = 1.0)
total = sum(novos_pesos.values())
novos_pesos = {k: v/total for k, v in novos_pesos.items()}

# 4. Escrita atômica (atomic rename — ver seção 8)
salvar_custom_rules(novos_pesos)
```

**Por que 0.7 funciona:**

| Propriedade | Efeito |
|-------------|--------|
| Um dia excepcional (ex: todas as entradas lucraram no P1) | Não domina os pesos — 70% do novo, mas 30% do antigo segura |
| Mudança de regime (ex: mercado entra em tendência forte) | Em 3-4 dias, os pesos convergem para o novo regime |
| Dia sem trades | Não recalibra. Mantém pesos atuais. Sem divisão por zero. |

**Análise diária:**
```
1. Agrupar trades do dia por decision e exit_reason
2. Calcular métricas:
   - Win rate dos APPROVE hoje
   - Win rate perdida: REJECT onde o trade TERIA sido lucrativo
     (simula: "se tivesse entrado, qual seria o PnL?")
3. Identificar qual pilar está "inflado" ou "sabotando":
   - Se P1 (macro) aprovou trades perdedores → peso_ideal menor
   - Se P2 (vol) bloqueou trades vencedores → peso_ideal maior
4. Ajustar threshold se necessário:
   - Muitos REJECT com score 68-70 que seriam lucrativos → threshold = 68
   - Muitos APPROVE com score 70-72 que dão prejuízo → threshold = 73
```

**O que NÃO fazer:**
- **Não** criar janela de esquecimento exponencial — o 0.7 fixo já é suficiente
- **Não** armazenar histórico de pesos diários — `custom_rules.json` só tem estado atual
- **Não** criar detector de regime de mercado — a média móvel diária já se adapta naturalmente

**Saída — `custom_rules.json`:**
```json
{
  "version": 3,
  "trades_analyzed": 150,
  "last_updated_utc": "2026-08-15T10:00:00Z",
  "weights": {
    "macro": 0.28,
    "volatilidade": 0.35,
    "tecnico": 0.37
  },
  "threshold": 72,
  "stats": {
    "win_rate_approved": 0.61,
    "avg_pnl_per_trade": 12.50,
    "total_trades": 150,
    "total_pnl": 1875.00,
    "max_drawdown_pct": 3.2
  }
}
```

Este arquivo é lido pela F2 antes de cada fusão e atualizado diariamente pela F5 (00:00 UTC). Se não existir, usa pesos iniciais (0.33/0.33/0.34).

---

## 3. JSON PADRÃO UBÍQUO — SCHEMA COMPLETO

```json
{
  "meta": {
    "trace_id": "string (uuid)",
    "timestamp_utc": "ISO 8601",
    "symbol": "XAUUSD | EURUSD | GBPUSD | USDJPY | AUDUSD",
    "timeframe": "M5 | M10 | M15",
    "slot_used": "int (0-30)",
    "slot_max": 30,
    "positions_open_symbol": "int (0-3)"
  },
  "scores": {
    "macro": {
      "raw": "float (0-100)",
      "weight": "float (0-1)",
      "weighted": "float (0-100)"
    },
    "volatilidade": {
      "raw": "float (0-100)",
      "weight": "float (0-1)",
      "weighted": "float (0-100)"
    },
    "tecnico": {
      "raw": "float (0-100)",
      "weight": "float (0-1)",
      "weighted": "float (0-100)"
    },
    "final_raw": "float (0-100)",
    "reducers_applied": ["string (nome do redutor)"],
    "final_adjusted": "float (0-100)",
    "threshold": "float (0-100)"
  },
  "context": {
    "news_imminent": "bool",
    "spread_pips": "float",
    "session": "SYDNEY | TOKYO | LONDON | NY | OVERLAP",
    "dxy_trend": "BULLISH | BEARISH | FLAT",
    "atr_14_m5": "float",
    "atr_14_m15": "float",
    "sentiment_ratio": "float (0-1)",
    "dom_imbalance": "float (-1 a 1, positivo=ask wall)"
  },
  "verdict": {
    "source": "deepseek_pro | mechanical_fallback",
    "decision": "APPROVE | REJECT",
    "confidence": "float (0-1, apenas se APPROVE)",
    "reason": "string (apenas se REJECT)",
    "reason_detail": "string (apenas se REJECT)",
    "adjustments": {
      "lot_multiplier": "float (0.1-1.0)",
      "timeout_min": "int (5-30)",
      "be_trigger_pct": "int (50-90)"
    }
  }
}
```

---

## 4. ESTRUTURA DE ARQUIVOS (ATUAL — DDD)

```
ctrader_v2/
├── run.py                         # Orquestrador mestre (subprocess)
├── config.yaml                    # MCP URL, token, thresholds
├── .env                           # DeepSeek API key
├── blackout_times.json            # Calendário econômico offline
├── custom_rules.json              # Gerado pelo MAR (F5)
├── trades.db                      # SQLite — log unificado
│
├── f0_collector/                  # DDD — 3 satélites + orq
│   ├── __init__.py
│   ├── orc_coleta.py                 # Orquestrador (loop de polling)
│   ├── poller_orc_coleta.py                 # Chamadas MCP (spot, candles)
│   └── storage_orc_coleta.py                # df_master + parquet
│
├── f1_analyzer.py                 # 3 pilares (170L, teto 200L)
├── f2_fusion.py                   # Normalização + redutores (156L)
├── f3_validator.py                # DeepSeek Pro + fallback + MCP pre-check
│
├── f4_executor/                   # DDD — 6 satélites + orq
│   ├── __init__.py
│   ├── orc_execucao.py                 # Orquestrador (loop principal)
│   ├── gates_orc_execucao.py                  # G1-G6 validação pré-entrada
│   ├── entry_orc_execucao.py                  # create_order + SL/TP
│   ├── monitor_orc_execucao.py                # PositionMonitor (degraus, trail)
│   ├── safety_orc_execucao.py                 # ATR spike + kill switch
│   └── log_trade_orc_execucao.py              # Persistência SQLite
│
├── f5_mar.py                      # Log + MAR + MCP sync (264L → split pendente)
│
├── dashboard.py                   # Streamlit 5 abas
├── vectorbt_calibrator.py         # Backtest offline diário
│
├── prompts/
│   └── validator_system.txt       # System prompt fixo (241 bytes, cacheado)
│
├── utils/
│   ├── mcp_client.py              # 17 tools MCP com SSE + handshake
│   ├── schema_validator.py        # Validação JSON contra schema
│   ├── session_manager.py         # Sessões Sydney/London/NY
│   └── slot_tracker.py            # 90 slots/dia com SQLite
│
├── tests/
│   ├── test_f1_scores.py          # ✅ Scores ∈ [0,100]
│   ├── test_f2_fusion.py          # ✅ Pesos somam 1.0
│   ├── test_f3_fallback.py        # ✅ Fallback mecânico
│   ├── test_f4_ghost_order.py     # 🔒 Precisa MCP
│   ├── test_f4_trail_be.py        # ✅ Trail trava BE
│   └── test_f5_mar.py             # ✅ Pesos convergem
│
├── specs/                         # 16 specs documentadas
│   └── INDEX.md                   # SSOT — wireia todas
│
├── blueprint/                     # Índice do blueprint
├── references/                    # Pesquisa MCP (3 agentes)
└── blueprint_ctrader_v2.md        # CANÔNICO (este arquivo, 1003L)
```

---

## 5. REGRAS DE OURO

| # | Regra | Fase |
|---|-------|------|
| **RG1** | IA entra UMA vez por trade, na última milha. Nunca antes. | F3 |
| **RG2** | Toda lógica possível é local (Python, Pandas, SQLite). IA só valida. | F1-F5 |
| **RG3** | JSON é contrato imutável entre fases. Quebrou schema = quebrou pipeline. | F2 |
| **RG4** | Fallback mecânico obrigatório. Sem IA não pode significar "sistema parado". | F3 |
| **RG5** | Degrau 0 (BE rápido) é obrigatório: assim que o preço anda 5% do TP, SL vai para entry + spread. Trade lateral = zero a zero. | F4 |
| **RG6** | Trailing stop NUNCA volta abaixo do BE. Travou no BE, morreu no BE. | F4 |
| **RG7** | Sem martingale. Lote nunca dobra após perda. | F4 |
| **RG8** | MAR ajusta pesos, não regras. O humano define as regras; o MAR calibra. | F5 |
| **RG9** | Drawdown > 3% diário = kill switch. Drawdown > 5% semanal = pausa. | F4 |

---

## 6. CRONOGRAMA DE IMPLEMENTAÇÃO (SPEC-DRIVEN)

| Ordem | Fase | Spec | Código | Harness | Métrica de aprovação |
|-------|------|------|--------|---------|----------------------|
| **1** | F0 | `specs/f0_collector.md` | `f0_collector.py` | `test_f0_dry_run.py` | 1h sem timeout, >50 candles, spread > 0 |
| **2** | F4 | `specs/f4_executor.md` | `f4_executor.py` | `test_f4_ghost_order.py`, `test_f4_trail_be.py` | 1 trade completo com todos os degraus, sem crash |
| **3** | F1 | `specs/f1_analyzer.md` | `f1_analyzer.py` | `test_f1_scores.py` | Scores ∈ [0,100], distribuição normal |
| **4** | F2 | `specs/f2_fusion.md` | `f2_fusion.py` | `test_f2_fusion.py` | Pesos somam 1.0, redutores aplicados |
| **5** | F3 | `specs/f3_validator.md` | `f3_validator.py` | `test_f3_fallback.py` | Cache hit > 90%, fallback < 5% chamadas |
| **6** | F5 | `specs/f5_mar.md` | `f5_mar.py` | `test_f5_mar.py` | Pesos convergem em ≤ 4 dias |
| **7** | Dash | `specs/dashboard.md` | `dashboard.py` (Streamlit) | Visual | Curva equity, trades, pesos visíveis |
| **8** | Run | `specs/run.md` | `run.py` | `test_run_heartbeat.py` | Todos os processos reiniciam sem intervenção |
| **9** | — | — | 30 dias demo | `test_30d_metrics.py` | Win rate > 50%, drawdown < 5%, custo IA < $10 |

---

## 7. GLOSSÁRIO

| Termo | Definição |
|-------|-----------|
| **MCP** | Model Context Protocol — interface HTTP local com o cTrader Desktop |
| **OCO** | One-Cancels-Other — ordem com SL e TP nativos do broker |
| **BE** | Breakeven — preço de entrada + spread. Zero a zero. |
| **Trailing Stop** | Stop loss que sobe junto com o preço, mantendo distância fixa |
| **Trava no BE** | Trail sobe até o BE e para. Nunca volta. |
| **80/20** | Fecha 80% do lote no lucro, deixa 20% correr com trailing |
| **Degrau** | Gatilho parcial de PnL (40%, 60%, 80% do TP) |
| **Slot** | Unidade de entrada por timeframe. 30 por TF, 90 por dia. |
| **MAR** | Motor de Ajuste de Ranking — recalibra pesos a cada 50 trades |
| **RCA** | Relative Comparative Analysis — indicador de momentum |
| **Delta** | Diferença entre volume bid e ask — fluxo de ordens |
| **Contango de Vol** | Volatilidade do TF curto > TF longo — sinal de aceleração |
| **Kill Switch** | Fecha todas as posições e pausa o sistema |
| **Ghost Order** | Ordem enviada mas não preenchida. Detectada em 5s, slot liberado. |
| **ATR Spike** | ATR atual > 2x média dos últimos 20 candles. Dispara bloqueio de entrada + força BE nas abertas. |

---

## 8. INFRAESTRUTURA DE EXECUÇÃO 24H

### 8.1 Orquestrador Mestre (`run.py`)

Scripts separados via `subprocess`. Isolamento total — se a F0 cair, a F4 continua protegendo posições.

```
run.py:
  1. Inicia f4_executor.py  (PRIORIDADE MÁXIMA — protege posições abertas)
  2. Inicia f0_collector.py (dados)
  3. Inicia f1_analyzer.py  (scores)
  4. Inicia f2_fusion.py    (fusão)
  5. Inicia f3_validator.py (IA, sob demanda da F2)
  6. Loop de heartbeat: verifica se processos estão vivos
  7. Se F0/F1/F2/F3 cair → reinicia e loga
  8. Se F4 cair → ALERTA (humano precisa intervir)
     // OCO no servidor segura as posições enquanto isso
```

**Por que subprocess e não threading:** se um thread de análise crasha (erro no pandas), ele derruba o processo inteiro. Com subprocess, cada fase é isolada. A F4 nunca morre por erro da F1.

### 8.2 Validação da F0 — Modo Dry-Run

Antes de ligar o sistema completo, validar o MCP por 24h:

```
python f0_collector.py --dry-run --hours=24
```

Gera `f0_test_20260722.parquet`. Analisar: falhas de coleta, coerência do spread, resposta do DOM. Sem acionar F1-F5.

### 8.3 Timeout Global MCP

Único timeout para todas as chamadas MCP. Sem timeout por chamada.

```python
# utils/mcp_client.py
MCP_TIMEOUT = 2.0  # segundos — suficiente para localhost

def call_mcp(method, params):
    try:
        return requests.post(url, json={...}, timeout=MCP_TIMEOUT)
    except requests.Timeout:
        raise MCPTimeoutError(f"Timeout: {method}")
```

**Por que 2s:** MCP é local (navegador → PC). Se demorar mais que 2s, o navegador está sobrecarregado ou a conexão caiu. A F4 trata `MCPTimeoutError` como erro transiente (3 retries).

### 8.4 Estrutura de Arquivos (atualizada)

```
ctrader_v2/
├── run.py                      # Orquestrador mestre (subprocess)
├── config.yaml
├── blackout_times.json
├── custom_rules.json
├── trades.db
│
├── f0_collector.py
├── f1_analyzer.py
├── f2_fusion.py
├── f3_validator.py
├── f4_executor.py
├── f5_mar.py
│
├── prompts/
│   └── validator_system.txt    # System prompt fixo (cache 95%)
│
├── utils/
│   ├── mcp_client.py           # Wrapper MCP + timeout global 2s
│   ├── session_manager.py
│   ├── slot_tracker.py
│   └── schema_validator.py
│
└── tests/
    ├── test_f0_dry_run.py
    ├── test_f1_scores.py
    ├── test_f2_fusion.py
    ├── test_f3_fallback.py
    ├── test_f4_ghost_order.py
    ├── test_f4_trail_be.py
    └── test_f5_mar.py
```

---

## 9. ROADMAP SPEC-DRIVEN — CRM, HARNESS E MÉTRICAS

### 9.1 Modelo CRM/HP/CP por Fase

Cada fase segue o modelo **CRM (Customer/Controller) → HP (Harness Point) → CP (Collection Point)**:

| Fase | CRM (o que entrega) | HP (como valida) | CP (métricas coletadas) |
|------|--------------------|--------------------|------------------------|
| **F0** | `df_master_1min` + parquet | `test_f0_dry_run.py`: 1h sem crash | `f0_uptime_pct`, `f0_timeout_rate`, `f0_reconnects`, `f0_data_gaps` |
| **F1** | `scores_raw.json` | `test_f1_scores.py`: scores ∈ [0,100] | `f1_signals_per_hour`, `f1_score_distribution`, `f1_news_trigger_rate` |
| **F2** | `fusion_output.json` | `test_f2_fusion.py`: pesos somam 1.0 | `f2_signals_above_threshold`, `f2_avg_reducers_applied`, `f2_threshold_hit_rate` |
| **F3** | `verdict.json` | `test_f3_fallback.py`: fallback < 5% | `f3_approve_rate`, `f3_cache_hit_pct`, `f3_latency_ms`, `f3_fallback_rate` |
| **F4** | `execution_log.json` + posição gerenciada | `test_f4_ghost_order.py`: ghost < 1% | `f4_win_rate`, `f4_avg_pnl`, `f4_ghost_rate`, `f4_mcp_latency_ms`, `f4_slot_utilization` |
| **F5** | `custom_rules.json` | `test_f5_mar.py`: pesos convergem ≤ 4 dias | `f5_weight_delta_daily`, `f5_threshold_drift`, `f5_calibration_count` |

### 9.2 Harness de Métricas — O que medir em Produção (30 dias demo)

#### F0 — Coleta
```
mcp_uptime_pct:        SUM(tempo_conectado) / tempo_total  (meta: > 99%)
mcp_timeout_rate:      timeouts / chamadas_totais           (meta: < 1%)
mcp_avg_latency_ms:    AVG(tempo_resposta)                  (meta: < 500ms)
data_gap_seconds:      MAX(intervalo sem tick)              (meta: < 10s)
reconnect_count:       COUNT(reconexões)                     (meta: < 5/dia)
```

#### F1-F2 — Análise
```
signals_per_hour:      COUNT(scores_raw) / hora              (meta: 5-20)
signals_above_threshold: COUNT(final_adjusted >= 70)         (meta: 10-30% dos sinais)
avg_score_macro:       AVG(score_macro)                      (referência: ~50)
avg_score_vol:         AVG(score_vol)                        (referência: ~50)
avg_score_tec:         AVG(score_tec)                        (referência: ~50)
reducer_hit_rate:      COUNT(reducers_applied) / total       (meta: < 20%)
```

#### F3 — IA
```
cache_hit_pct:         chamadas_com_cache / total            (meta: > 90%)
avg_latency_ms:        AVG(tempo DeepSeek Pro)               (meta: < 1500ms)
fallback_rate:         fallbacks / total                     (meta: < 5%)
approve_rate:          APPROVEs / total                      (referência: 50-70%)
daily_cost_usd:        SUM(custo_chamadas)                   (meta: < $0.30/dia)
```

#### F4 — Execução
```
win_rate:              trades_lucrativos / total             (meta: > 55%)
avg_pnl_per_trade:     AVG(pnl_net)                          (meta: > $2)
profit_factor:         lucro_bruto / perda_bruta             (meta: > 1.5)
ghost_order_rate:      ghost_orders / total_ordens           (meta: < 1%)
slot_utilization:      slots_usados / 90                     (meta: 40-80%)
avg_trade_duration_s:  AVG(duração)                          (referência: 300-900s)
be_saves:              trades que saíram BE via Degrau 0     (rastreio)
trail_activated_rate:  trades que ativaram trailing          (rastreio)
max_drawdown_pct:      MAX(drawdown_intradiário)              (alerta: > 3%)
```

#### F5 — MAR
```
weight_delta_daily:    SUM(|peso_novo - peso_antigo|)        (meta: < 0.15/dia)
threshold_drift:       threshold_atual - threshold_inicial   (meta: ±5)
days_since_calibration: dias desde último ajuste              (alerta: > 3)
```

### 9.3 Dashboard — Streamlit + Handler Legado

**Dashboard principal (Streamlit — `dashboard.py`):**

```python
# Abas:
# 1. OVERVIEW: PnL diário, drawdown, equity curve, slots usados
# 2. TRADES: Tabela filtrável (símbolo, TF, exit_reason, pnl)
# 3. SCORES: Distribuição dos 3 pilares, threshold atual
# 4. MAR: Pesos atuais, histórico de convergência
# 5. LOGS: Erros, reconnects, ghost orders (últimas 24h)
```

Fonte de dados: `trades.db` (SQLite). Atualização: a cada 5 segundos (`st.rerun()` ou auto-refresh).

**Dashboard legado do cTrader (aproveitamento):**

O cTrader Desktop já possui gráficos de PnL e histórico de trades nativos. Não há "dashboard Python" legado — mas os handlers `NC-11_HDL-CTRADER-WORKSPACE.py` e `NC-11_HDL-CTRADER-CHART.py` permitem **abrir charts e aplicar templates automaticamente** via MCP. Isso pode ser usado para:

- Abrir chart do símbolo com indicadores (Bollinger, RSI) via `open_chart` + `addChartIndicator`
- Aplicar template de visualização pré-configurado

Uso: complementar ao Streamlit, não substituto. Streamlit = métricas do sistema. cTrader = visualização de mercado.

### 9.4 VectorBT — Integração Offline

```
Fluxo diário (fora de mercado, ex: 21:00 UTC):

1. vectorbt_calibrator.py:
   a. Lê v_historical_candles do SQLite (candles 1min agregados)
   b. Roda backtest com os 3 pilares em todos os TFs
   c. Gera historical_weights.json:
      {
        "macro_weight": 0.31,
        "vol_weight": 0.34,
        "tec_weight": 0.35,
        "backtest_period": "2026-07-01:2026-07-22",
        "backtest_sharpe": 1.42,
        "backtest_max_dd": 4.1
      }

2. F2 (fusion) lê historical_weights.json como prior informativo.
   O MAR (F5) ainda é a fonte primária dos pesos. O VectorBT é
   referência secundária — exibida no dashboard, não vinculante.
```

### 9.5 Configuração Inicial (`config.yaml`)

```yaml
# ctrader_v2/config.yaml
mcp:
  base_url: "http://localhost:8765/mcp"
  timeout_seconds: 2.0

symbols:
  - XAUUSD
  - EURUSD
  - GBPUSD
  - USDJPY
  - AUDUSD

timeframes: [M5, M10, M15]

initial_weights:
  macro: 0.33
  volatilidade: 0.33
  tecnico: 0.34

thresholds:
  entry_score: 70
  fallback_score: 85
  dom_imbalance: 0.7
  spread_max_pips: 2.0
  atr_spike_multiplier: 2.0

risk:
  lot_size: 0.1
  max_positions_per_symbol: 3
  slots_per_tf: 30
  daily_drawdown_kill: 0.03
  weekly_drawdown_kill: 0.05
  margin_soft_limit_pct: 0.20
  rr_ratio: 2.0

ia:
  provider: "deepseek"
  model: "deepseek-pro"
  timeout_seconds: 3.0
  prompt_file: "prompts/validator_system.txt"

mar:
  update_rate: 0.7
  calibration_time_utc: "00:00"

dashboard:
  port: 8501
  refresh_seconds: 5
```

### 9.6 Persistência e Recuperação

| Artefato | Persistência | Recuperação pós-crash |
|----------|-------------|----------------------|
| `slot_tracker` | **Em memória + SQLite.** A cada mudança de slot, escreve na tabela `slots`. | Ao iniciar, lê `slots WHERE date = today()`. Recupera estado. |
| `df_master_1min` | Em memória + parquet a cada 1h. | Crash = perde dados da última hora. Aceitável (F0 reinicia). |
| `custom_rules.json` | Disco. Atomic rename. | Sempre disponível. Última versão válida. |
| `trades.db` | Disco. WAL mode. | Sempre disponível. |
| Posições abertas | Servidor cTrader (OCO). | **Sobrevivem ao crash.** F4 consulta `get_positions()` ao reiniciar. |

### 9.7 Log Rotation

`trades.db` não cresce indefinidamente. Rotina semanal (domingo 00:00):

```sql
DELETE FROM trades WHERE created_at < date('now', '-90 days');
VACUUM;
```

90 dias de histórico é suficiente para MAR e VectorBT. Dados brutos (parquet) seguem mesma política.

### 9.8 Health Check (`run.py`)

Cada processo responde a um heartbeat via arquivo de status:

```
Cada fase escreve a cada 5s: status/<fase>.heartbeat
  → conteúdo: timestamp UTC + "OK"

run.py verifica a cada 10s:
  SE timestamp > 15s atrás → processo travou → reinicia
  SE F4 travou → ALERTA (não reinicia sozinho)
```

---

## 10. GAPS RESOLVIDOS (checklist final)

| Gap | Resolução | Seção |
|-----|-----------|-------|
| CRM/HP/CP por fase | Modelo definido | 9.1 |
| Métricas de harness | 25+ métricas documentadas | 9.2 |
| Dashboard | Streamlit + handlers legados (chart/template) | 9.3 |
| VectorBT integração | Script offline diário, pesos não-vinculantes | 9.4 |
| `config.yaml` spec | Schema completo | 9.5 |
| Persistência slot_tracker | Em memória + SQLite | 9.6 |
| Log rotation | DELETE 90 dias, VACUUM semanal | 9.7 |
| Health check | Heartbeat via arquivo de status | 9.8 |
| Cronograma desatualizado | Corrigido com spec + harness + métricas | 6 |
