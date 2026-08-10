# SPEC S45 — Gerenciador Global de Portfólio (Prevenção de Sobreposição USD)

> **Versão:** 1.0 | **Wire:** `utils/portfolio_manager_orc_risk.py` | **Status:** spec
> **Atualizado:** 2026-08-05 — Roadmap v3.0, Rodada 7: RCA Alavancagem Cruzada
> **Depende:** S41 (sinais), S42 (execução), S44 (emit_once)
> **Regra de ouro:** NUNCA abrir >1 trade com exposição direcional ao USD simultaneamente.

## PROPOSITO

Prevenir alavancagem cruzada acidental ao escalar de 1 ativo (XAUUSD) para 5 ativos.
O denominador comum de todos os pares é o USD. Sem uma trava global, dois sinais
de COMPRA simultâneos em EURUSD e GBPUSD dobram o risco em Dólar — o robô aposta
2× contra o USD sem saber.

## RCA — Por que robôs quebram ao escalar

```
Cenário sem Portfolio Manager:
  t=0: Sinal BUY EURUSD  (short USD, compra EUR)
  t=0: Sinal BUY GBPUSD  (short USD, compra GBP)
  t=0: Sinal BUY AUDUSD  (short USD, compra AUD)

Resultado: 3× exposição short USD.
Se o DXY subir 1%, o drawdown é 3× pior que o esperado.
O backtest por símbolo isolado NUNCA revela esse risco.
```

## ARQUITETURA — Dicionário de Exposição Ativa

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import time

class USDDirection(Enum):
    LONG_USD = "LONG"    # comprando USD (ex: BUY USDJPY, SELL EURUSD)
    SHORT_USD = "SHORT"  # vendendo USD (ex: BUY EURUSD, SELL USDJPY)

@dataclass
class ActiveTrade:
    symbol: str
    direction: str          # "BUY" or "SELL"
    usd_exposure: USDDirection
    entry_price: float
    confidence: float       # 0..1 do S41
    opened_at: float        # timestamp

@dataclass
class PortfolioManager:
    """Trava global: nunca >1 trade com mesma exposição USD simultânea.

    Invariante:
      len([t for t in active if t.usd_exposure == USDDirection.SHORT_USD]) <= 1
      len([t for t in active if t.usd_exposure == USDDirection.LONG_USD])  <= 1

    Máximo teórico: 2 trades simultâneos (1 LONG USD + 1 SHORT USD).
    Mínimo garantido: nunca 2 trades na mesma direção USD.
    """

    active_trades: dict[str, ActiveTrade] = field(default_factory=dict)
    blocked_signals: list[dict] = field(default_factory=list)

    def usd_exposure_for(self, symbol: str, signal: str) -> USDDirection:
        """Mapeia símbolo + sinal → exposição ao USD.

        Regra universal:
          BUY em XXXUSD  → SHORT_USD  (você vende USD para comprar XXX)
          SELL em XXXUSD → LONG_USD   (você compra USD ao vender XXX)
          BUY em USDXXX  → LONG_USD   (você compra USD para comprar XXX)
          SELL em USDXXX → SHORT_USD  (você vende USD ao vender XXX)
        """
        if symbol in ("XAUUSD", "EURUSD", "GBPUSD", "AUDUSD"):
            return USDDirection.SHORT_USD if signal == "BUY" else USDDirection.LONG_USD
        elif symbol == "USDJPY":
            return USDDirection.LONG_USD if signal == "BUY" else USDDirection.SHORT_USD
        return USDDirection.SHORT_USD  # fallback seguro

    def has_exposure(self, direction: USDDirection) -> bool:
        """Verifica se já existe trade ativo com essa exposição USD."""
        return any(t.usd_exposure == direction for t in self.active_trades.values())

    def get_competitor(self, direction: USDDirection) -> Optional[ActiveTrade]:
        """Retorna o trade ativo que compete pela mesma exposição USD."""
        for t in self.active_trades.values():
            if t.usd_exposure == direction:
                return t
        return None
```

## LÓGICA DE DECISÃO — Conflito no Mesmo Milissegundo

```
Cenário: DXY em queda (-0.3% ROC). Dois sinais disparam simultaneamente:

  EURUSD → BUY (SHORT_USD, confidence=0.78)
  GBPUSD → BUY (SHORT_USD, confidence=0.72)

Ambos querem vender USD. Só 1 pode.
```

### Algoritmo de Desempate

```python
def resolve_conflict(
    pm: PortfolioManager,
    candidates: list[dict],  # sinais que chegaram no mesmo tick
) -> dict:
    """Resolve conflito quando >1 sinal disputa a mesma exposição USD.

    Critérios de desempate (em ordem):
      1. Maior confidence (S41 score)
      2. Menor spread atual (ask - bid) — menor fricção
      3. Menor distanciamento da VWAP — menos exausto
      4. Símbolo com menor ATR relativo — menos volátil

    Returns:
      {"approved": signal_dict, "blocked": [signal_dict, ...], "reason": str}
    """
    if len(candidates) == 1:
        return {"approved": candidates[0], "blocked": [], "reason": "UNCONTESTED"}

    # Agrupa por exposição USD
    by_exposure: dict[USDDirection, list[dict]] = {}
    for c in candidates:
        exp = pm.usd_exposure_for(c["symbol"], c["signal"])
        by_exposure.setdefault(exp, []).append(c)

    approved = []
    blocked = []

    for exp, signals in by_exposure.items():
        if pm.has_exposure(exp):
            # Já tem trade ativo nessa direção → bloqueia todos
            for s in signals:
                blocked.append({**s, "reason": f"EXPOSURE_TAKEN:{exp.value}"})
            continue

        if len(signals) == 1:
            approved.append(signals[0])
        else:
            # Desempate por confidence → spread → VWAP → ATR
            ranked = sorted(signals, key=lambda s: (
                -s["confidence"],
                s.get("spread", 999),
                s.get("vwap_distance_pct", 999),
                s.get("atr_relative", 999),
            ))
            approved.append(ranked[0])
            for s in ranked[1:]:
                blocked.append({**s, "reason": f"CONFLICT_LOST:{ranked[0]['symbol']}"})

    return {
        "approved": approved,
        "blocked": blocked,
        "reason": "CONFLICT_RESOLVED" if blocked else "UNCONTESTED",
    }
```

### Exemplo Prático — EURUSD vs GBPUSD

```python
pm = PortfolioManager()  # portfolio vazio

# Tick 14:35:22.047 — dois sinais no mesmo milissegundo
candidates = [
    {
        "symbol": "EURUSD", "signal": "BUY", "confidence": 0.78,
        "spread": 0.00012, "vwap_distance_pct": 0.08, "atr_relative": 0.0015,
    },
    {
        "symbol": "GBPUSD", "signal": "BUY", "confidence": 0.72,
        "spread": 0.00018, "vwap_distance_pct": 0.12, "atr_relative": 0.0020,
    },
]

result = resolve_conflict(pm, candidates)
# result["approved"] = EURUSD  (maior confidence: 0.78 > 0.72)
# result["blocked"]  = GBPUSD  (reason: CONFLICT_LOST:EURUSD)

pm.active_trades["EURUSD_143522"] = ActiveTrade(
    symbol="EURUSD", direction="BUY",
    usd_exposure=USDDirection.SHORT_USD,
    entry_price=1.0850, confidence=0.78,
    opened_at=time.time(),
)

# 3 minutos depois...
# Tick 14:38:15.123 — AUDUSD sinal BUY

aud_signal = {"symbol": "AUDUSD", "signal": "BUY", "confidence": 0.81}
exp = pm.usd_exposure_for("AUDUSD", "BUY")  # SHORT_USD

if pm.has_exposure(exp):
    competitor = pm.get_competitor(exp)
    # competitor = EURUSD (BUY, SHORT_USD, aberto há 3 min)
    # → AUDUSD BLOQUEADO: "EXPOSURE_TAKEN:SHORT:EURUSD"
```

## MATRIZ COMPLETA — Todas as Combinações Possíveis

| Trade Ativo | Novo Sinal | Conflito? | Resultado |
|---|---|---|---|
| EURUSD BUY (SHORT USD) | GBPUSD BUY (SHORT USD) | **Sim** | Bloqueia GBPUSD |
| EURUSD BUY (SHORT USD) | XAUUSD BUY (SHORT USD) | **Sim** | Bloqueia XAUUSD |
| EURUSD BUY (SHORT USD) | USDJPY SELL (SHORT USD) | **Sim** | Bloqueia USDJPY |
| EURUSD BUY (SHORT USD) | AUDUSD SELL (LONG USD) | **Não** | Aprova AUDUSD |
| EURUSD BUY (SHORT USD) | USDJPY BUY (LONG USD) | **Não** | Aprova USDJPY |
| USDJPY BUY (LONG USD) | EURUSD SELL (LONG USD) | **Sim** | Bloqueia EURUSD |

**Máximo teórico:** 2 trades simultâneos — 1 SHORT USD + 1 LONG USD.
Isso representa uma posição neutra em USD (hedge natural), não alavancagem dobrada.

## WIRE NO EMIT_ONCE()

```python
# Em S44 emit_once() — antes de retornar o sinal:

pm = get_portfolio_manager()  # singleton global

exposure = pm.usd_exposure_for(symbol, signal["signal"])

if pm.has_exposure(exposure):
    competitor = pm.get_competitor(exposure)
    return {
        "signal": None,
        "reason": f"PORTFOLIO_BLOCKED:{exposure.value}:{competitor.symbol}",
    }

# Se aprovado, registra no portfolio
pm.active_trades[f"{symbol}_{int(time.time()*1000)}"] = ActiveTrade(
    symbol=symbol,
    direction=signal["signal"],
    usd_exposure=exposure,
    entry_price=entry_price,
    confidence=signal["confidence"],
    opened_at=time.time(),
)
```

## LIMPEZA DE TRADES FECHADOS

```python
def cleanup_closed_trades(pm: PortfolioManager, f0_snapshot: dict) -> None:
    """Remove trades que já foram fechados (SL/TP/timeout).

    O F0 snapshot contém open_positions. Se o trade não está mais
    na lista de posições abertas, ele foi fechado → remove do dict.
    """
    open_symbols = {p["symbol"] for p in f0_snapshot.get("positions", [])}

    closed = []
    for key, trade in pm.active_trades.items():
        if trade.symbol not in open_symbols:
            closed.append(key)

    for key in closed:
        del pm.active_trades[key]
```

## REGRAS

1. **NUNCA >1 trade SHORT USD simultâneo**
2. **NUNCA >1 trade LONG USD simultâneo**
3. **Desempate por confidence → spread → VWAP → ATR**
4. **Limpeza automática no próximo tick via F0 snapshot**
5. **Singleton global** — uma única instância do PortfolioManager para todos os símbolos
6. **XAUUSD não tem privilégio** — compete em igualdade com os outros na mesma direção USD

## CHANGELOG

| Versão | Data | Mudança |
|--------|------|---------|
| 1.0 | 2026-08-05 | Spec inicial: dicionário de exposição, resolve_conflict, wire no emit_once |
