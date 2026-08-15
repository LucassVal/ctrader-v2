# SPEC S42 — Bloco 2: Sobrevivência (Execution & Risk)

> **Versao:** 2.0 | **Wire:** utils/orc_bloco2.py | **Status:** implemented (v1.1 offline) → evolving (v2.0 spec)
> **Atualizado:** 2026-08-05 — Roadmap v3.0: defesa microestrutural, OCO dinâmico VIX, XAUUSD first
> **Depende:** S41 (Bloco 1), S27 (vectorbt stops)
> **Regra de ouro**: SÓ operar sobre Sinais_Validados do Bloco 1. NUNCA recalcular indicadores.

## PROPOSITO

Testar camadas de proteção (gestão de ordens) sobre uma matriz de sinais já validada.
Responder: "dado que o sinal tem edge, qual estratégia de saída maximiza Sharpe e minimiza Drawdown?"

O Bloco 2 NÃO gera sinais. Apenas simula execução.

## FLUXO ATUAL (v1.1 — implementado)

```
Sinais_Validados (Bloco 1)
  │
  ▼
┌─────────────────────────────────────────────────────┐
│ BLOCO 2 — SOBREVIVÊNCIA                             │
│                                                     │
│  Camada 0: Baseline (time exit M5/M15)              │
│    → Sharpe, MaxDD, Win Rate de referência           │
│                                                     │
│  Camada 1: Alvo 80% (S42.1)                         │
│    adjust_tp_func_nb: fecha 80% no TP1              │
│    → Comparar Sharpe vs baseline                     │
│                                                     │
│  Camada 2: Breakeven (S42.2)                         │
│    adjust_sl_func_nb: SL → entry+spread @ D% lucro  │
│    → Comparar MaxDD vs baseline                      │
│                                                     │
│  Camada 3: Trailing Stop (S42.3)                     │
│    from_signals(sl_trail=True)                       │
│    → Comparar Win Rate vs baseline                   │
│                                                     │
│  Camada 4: OCO Adaptativo ATR (S42.4)               │
│    OHLCSTX com SL/TP escalados por ATR               │
│    → Comparar todas as métricas                      │
│                                                     │
│  SAÍDA: Tabela comparativa                           │
│    Camada | Sharpe | MaxDD | WinRate | ProfitFactor  │
└─────────────────────────────────────────────────────┘
```

## EVOLUÇÃO v2.0 — Defesa Microestrutural + Fricção Real (EM ESPECIFICAÇÃO)

> **Status:** ⬜ Especificado, não implementado. Validação inicial: apenas XAUUSD.

### Camada 0: Gate de Spread (NOVO v2.0)

```
ANTES de qualquer execução, o Bloco 2 consulta o snapshot F0:

  ask = snapshot[simbolo]["ask"]          # preço de compra no mercado
  bid = snapshot[simbolo]["bid"]          # preço de venda no mercado
  spread = ask - bid                       # pedágio da corretora
  atr = talib.ATR(high, low, close, 14)[-1]  # volatilidade atual

  tp_distancia = atr × 2.0                # distância até o TP (OCO padrão)

  SE spread > tp_distancia × 0.20:
    → ABORTA (spread consumiria >20% do lucro projetado)
    → incrementa contador: aborted_trades++
    → NÃO entra na posição

  SE spread ≤ tp_distancia × 0.20:
    → Prossegue para Camada 1 (TP 80%)

Exemplo numérico (XAUUSD):
  ask = 2650.50, bid = 2650.10
  spread = 0.40 (4 pips)
  ATR(14) = 2.80
  tp_distancia = 2.80 × 2.0 = 5.60
  limite = 5.60 × 0.20 = 1.12
  0.40 < 1.12 → OK, prossegue
```

**Por que 20%:** Se o spread come >20% do TP, a operação já nasce com desvantagem
assimétrica. O risco de execução supera o edge estatístico do sinal.

### Camada 4b: OCO Dinâmico — VIX-Driven (NOVO v2.0)

```
O Bloco 2 recebe vix_spike do Bloco 1 (S41 § Camada 1b):

  vix_spike = VIX[t] / SMA(VIX, 20) > 2.0    ← calculado no S41, repassado ao S42

Em regime NORMAL (vix_spike = False):
  atr_multiplier = 1.5
  lote = lote_padrão                            # 1.0 (100%)
  SL = entry - (ATR × 1.5)
  TP = entry + (ATR × 1.5 × 2)                 # ratio 1:2

Em regime PANICO (vix_spike = True):
  atr_multiplier = 3.0                          # alarga 2× as bandas
  lote = lote_padrão × (1.5 / 3.0)             # = 0.5 (50% do lote normal)
  SL = entry - (ATR × 3.0)
  TP = entry + (ATR × 3.0 × 2)                 # mantém ratio 1:2

Risco Financeiro mantido constante:
  Risco_normal  = lote × (ATR × 1.5)           = 1.0 × 1.5 × ATR = 1.5 × ATR
  Risco_panico  = lote × (ATR × 3.0)           = 0.5 × 3.0 × ATR = 1.5 × ATR
  Risco_normal == Risco_panico ✓

Exemplo numérico (XAUUSD, ATR=2.80):
  Normal:  SL = entry - 4.20, TP = entry + 8.40,  lote = 1.0
  Pânico:  SL = entry - 8.40, TP = entry + 16.80, lote = 0.5
  Risco financeiro: 4.20 × 1.0 = 8.40 × 0.5 = 4.20 ✓
```

**Efeito:** Bandas mais largas evitam "violinadas" do stop em volatilidade extrema.
Lote reduzido mantém o risco financeiro constante — a operação não fica mais
arriscada, só mais tolerante a ruído.

### Validação XAUUSD Primeiro

```
Fase 0: XAUUSD apenas. Validar:
  1. Gate de spread com tick_volume real do MCP
  2. OCO dinâmico em spikes de VIX (backtest com dados históricos de pânico)
  3. Comparar Sharpe com/sem defesa microestrutural

Métrica de aprovação:
  - Trades abortados por spread < 15% do total
  - MaxDD com OCO dinâmico < MaxDD com OCO fixo
  - Win rate não degrada > 5% com defesas ativas

Só após XAUUSD aprovado → expandir para os outros 4 pares.
```

## ORQUESTRADOR — `utils/orc_bloco2.py` (312L, implementado)

Wireado em `routers/ctrader_v2.py:/lab/bloco2`. Validado via script direto:
- 709 trades EURUSD 90d, best_layer=oco_atr, 33.8s.
- Servidor atual nao carrega codigo novo (zombie PID).

```python
def run_bloco2(
    signals_validated: pd.DataFrame,
    ohlcv: pd.DataFrame,
    tf: str = "M5",
) -> dict:
    """
    Returns:
        {
            "comparison": pd.DataFrame,  # camada × métricas
            "best_layer": str,           # "oco_atr"
            "equity_curves": dict,       # {camada: [equity]}
            "trades_per_layer": dict,    # {camada: [trade dicts]}
        }
    """
```

## FILHOS (SATs)

### `partial_exit_orc_bloco2.py`
- `build_tp_callback(tp1_pct=0.8, tp1_target=0.02) → callable`
- R-USE: `adjust_tp_func_nb` do vectorbt

### `breakeven_orc_bloco2.py`
- `build_be_callback(trigger_pct=0.6, spread_pips=1.0) → callable`
- R-USE: `adjust_sl_func_nb` do vectorbt

### `oco_atr_orc_bloco2.py`
- `calc_oco_bands(atr_value, multiplier=1.5) → (sl_offset, tp_offset)`
- v2.0: `multiplier` dinâmico baseado em VIX spike
- R-USE: `OHLCSTX.run(sl_stop, tp_stop)`

### `spread_gate_orc_bloco2.py` (NOVO v2.0)
- `check_spread_gate(entry_price, ask, bid, atr) → bool`
- Aborta se spread > 20% TP projetado

### `layer_comparator_orc_bloco2.py`
- `compare_layers(results: dict) → pd.DataFrame`

## CONTRATO DE SAÍDA (v1.1 — atual)

```python
{
    "baseline": {"sharpe": 0.45, "max_dd": 12.3, "win_rate": 48.2, "profit_factor": 1.15},
    "comparison": [
        {"layer": "baseline", "sharpe": 0.45, "max_dd": 12.3, "win_rate": 48.2},
        {"layer": "tp_80",    "sharpe": 0.52, "max_dd": 10.1, "win_rate": 52.1},
        {"layer": "be",       "sharpe": 0.48, "max_dd": 8.7,  "win_rate": 48.2},
        {"layer": "trail",    "sharpe": 0.55, "max_dd": 11.2, "win_rate": 46.8},
        {"layer": "oco_atr",  "sharpe": 0.61, "max_dd": 7.3,  "win_rate": 54.5},
    ],
    "best_layer": "oco_atr",
}
```

## CONTRATO DE SAÍDA (v2.0 — planejado)

```python
{
    ...  # campos v1.1 mantidos
    "spread_gate": {
        "aborted_trades": 12,
        "abort_reasons": ["spread > 20% TP", "VIX spike + spread alargado"],
    },
    "oco_dynamic": {
        "vix_spike_events": 3,
        "atr_multiplier_used": [1.5, 1.5, 3.0],
        "lot_adjusted": [1.0, 1.0, 0.5],
    },
}
```

## REGRAS

1. **NUNCA recalcular indicadores** — os sinais vêm prontos do Bloco 1
2. **NUNCA alterar a matriz de sinais** — apenas simular execução
3. **Ordem de aplicação**: baseline → TP80 → BE → Trail → OCO (cumulativo)
4. **Métricas via ReturnsAccessor**: Sortino, VaR, Omega além de Sharpe
5. **Spread gate é pré-execução** — roda antes de qualquer camada
6. **OCO dinâmico é reativo ao VIX** — só altera em spikes confirmados
7. **XAUUSD primeiro**: toda validação começa no ouro

## R-USE

| Componente | Origem | Uso |
|-----------|--------|-----|
| `Portfolio.from_signals()` | vectorbt | Simulação base |
| `adjust_tp_func_nb` | vectorbt param | Alvo 80% |
| `adjust_sl_func_nb` | vectorbt param | Breakeven |
| `sl_trail=True` | vectorbt param | Trailing stop |
| `OHLCSTX` | vectorbt.signals | OCO adaptativo |
| `ReturnsAccessor` | vectorbt.returns | Sortino, VaR, Omega |

## VALIDACAO EMPIRICA — CORRELACAO DXY/VIX + CAMADAS OCO (Fluxo 2)

> **Data:** 2026-08-15 | **Harness:** `tests/test_bloco2_oco_layers.py` + `tests/test_bloco2_backtest_full.py` | **Janela:** ~9.8 meses XAUUSD M1

### Correlacao XAUUSD (M1, ~9.8 meses)

| Par | Correlacao |
|-----|-----------|
| XAUUSD x DXYUSD | -0.1245 (fraca negativa) |
| XAUUSD x VIXUSD | +0.4473 (moderada positiva) |

Amplitude media M1 (1440b) = 0.0236%.

**Leitura:** XAUUSD confirma comportamento refugio — sobe com VIX (panico) e contra dolar fraco. O Panic Override (S41 §Camada 1b) tem base empirica: a correlacao VIX positiva (+0.45) suporta BUY autorizado em spike. A correlacao DXY (-0.12) e fraca o suficiente para NAO justificar filtro rigido — valida o filtro "soft/neutro" (ROC < 0.1% = neutro) do S41 §Sub-fase 4.

### Camadas OCO (7 camadas)

`tests/test_bloco2_backtest_full.py` valida o fluxo completo: Baseline S1/S2 -> D80 -> BE -> Trail -> OCO ATR -> OCO dinamico VIX, com Spread Gate (S42 §Camada 0) e OCO dinamico (S42 §Camada 4b: ATR mult 3.0 + lote 0.5 em spike VIX).

## CHANGELOG

| Versão | Data | Mudança |
|--------|------|---------|
| 2.0 | 2026-08-05 | Spec: spread gate, OCO dinâmico VIX, XAUUSD first. |
| 1.1 | 2026-08-01 | Implementado (312L). Wireado router /lab/bloco2. Validado 33.8s. |
| 1.0 | 2026-07-30 | Versão inicial. |
