# SPEC S44 — Motor de Tempo Real (Live Execution Architecture)

> **Versão:** 2.0 | **Wire:** S41 Camada 2 (gatilho) + S41 Camada 1 (contexto) | **Status:** spec
> **Atualizado:** 2026-08-05 — Roadmap v3.0: Buffer Deslizante, VWAP Exaustão, TA-Lib Live
> **Dependência:** TA-Lib 0.7.1 ✅ INSTALADO no venv Neocortex (Python 3.12)
> **Evolução de:** S40 (orc_pattern_candles.md v1.1 — análise offline de patterns)

## PROPOSITO

Fornecer o motor de análise em tempo real para o Bloco 1 v3.0, substituindo
o processamento em lote (Pandas sobre 2 anos de dados) por um fluxo contínuo
milissegundo a milissegundo com buffer deslizante O(1).

Três camadas:
1. **Camada Meso (60 velas M1):** VWAP Intradiária + Filtro de Exaustão
2. **Camada Micro (5 velas M1):** Slope + TA-Lib Patterns + Gatilho
3. **Camada de Antecipação (3 velas):** Previsão de continuidade

## ARQUITETURA DO BUFFER — `collections.deque(maxlen=60)`

```python
from collections import deque
import numpy as np

class TickBuffer:
    """Buffer circular O(1) para velas M1 em tempo real.

    Garantias:
      - Memória: O(1) — nunca cresce além de 60 velas
      - Inserção: O(1) — deque.append() é atômico
      - Descarte: automático — maxlen=60 elimina a vela mais antiga
      - Thread-safe: deque.append() é atômico em CPython (GIL)
    """

    def __init__(self):
        self.velas: deque[dict] = deque(maxlen=60)
        self.vwap_acumulado: float = 0.0
        self.volume_acumulado: float = 0.0

    def push(self, vela: dict) -> None:
        """Adiciona nova vela M1. Descarta a 61ª automaticamente.

        Exemplo de vela (do F0 snapshot):
          {"t": 1732900000, "o": 2650.12, "h": 2651.80,
           "l": 2649.50, "c": 2651.20, "v": 142}
        """
        if len(self.velas) == 60:
            # Remove a vela mais antiga antes de adicionar a nova
            velha = self.velas[0]
            self.vwap_acumulado -= velha["c"] * velha["v"]
            self.volume_acumulado -= velha["v"]

        self.velas.append(vela)
        self.vwap_acumulado += vela["c"] * vela["v"]
        self.volume_acumulado += vela["v"]

    @property
    def vwap(self) -> float:
        """VWAP intradiária (últimas 60 velas M1 = ~1 hora)."""
        if self.volume_acumulado == 0:
            return 0.0
        return self.vwap_acumulado / self.volume_acumulado

    @property
    def last_5(self) -> list[dict]:
        """Últimas 5 velas para análise micro."""
        n = len(self.velas)
        if n < 5:
            return list(self.velas)
        return [self.velas[i] for i in range(n - 5, n)]

    @property
    def last_3(self) -> list[dict]:
        """Últimas 3 velas para antecipação."""
        n = len(self.velas)
        if n < 3:
            return list(self.velas)
        return [self.velas[i] for i in range(n - 3, n)]
```

## CAMADA MESO — VWAP Intradiária + Filtro de Exaustão

```
Preço atual = vela atual["close"]
VWAP_1h = buffer.vwap

distanciamento_pct = |preço - VWAP_1h| / VWAP_1h × 100

Regime:
  preço > VWAP_1h × 1.001 → ABOVE (+0.1%)
  preço < VWAP_1h × 0.999 → BELOW (-0.1%)
  caso contrário            → NEUTRAL

Filtro de Exaustão (borracha esticada):
  SE distanciamento_pct > 0.50% (XAUUSD) ou > 0.15% (forex):
    → regime = "EXHAUSTED"
    → NENHUM sinal gerado nesta barra
    → Aguarda retorno à VWAP ou próximo tick
```

**Thresholds por ativo:**

| Ativo | Exaustão (%) | Justificativa |
|-------|-------------|---------------|
| XAUUSD | 0.50% | Ouro tem ranges intraday maiores (~$13 @ 2650) |
| EURUSD | 0.15% | Forex major tem ranges menores (~15 pips) |
| GBPUSD | 0.18% | Cable ligeiramente mais volátil |
| AUDUSD | 0.18% | Commodity currency |
| USDJPY | 0.15% | Major, baixa volatilidade |

**Por que funciona:** Se o preço está 0.50% acima da VWAP em XAUUSD, significa
que esticou ~$13 em 1 hora. A probabilidade de reversão à média (mean reversion
intradiária) supera a probabilidade de continuação. O código não aposta na
continuação — espera o retorno.

## CAMADA MICRO — Slope 5 Velas + TA-Lib Patterns

```python
def analyze_micro(buffer: TickBuffer, symbol: str) -> dict:
    """Analisa as últimas 5 velas do buffer para gerar sinal.

    Returns:
        {"signal": "BUY"|"SELL"|None, "confidence": 0..1,
         "slope": float, "accel": float, "patterns": [str],
         "rejected": bool}
    """
    velas = buffer.last_5
    if len(velas) < 5:
        return {"signal": None, "confidence": 0.0}

    # 1. Slope — regressão linear dos fechos
    closes = np.array([v["c"] for v in velas], dtype=np.float64)
    x = np.arange(5, dtype=np.float64)
    slope, _ = np.polyfit(x, closes, 1)  # grau 1 = linear
    slope_pct = slope / closes.mean()      # normalizado

    # 2. Aceleração — corpos crescendo?
    bodies = np.abs(np.array([v["c"] - v["o"] for v in velas], dtype=np.float64))
    accel = bodies[-1] / max(bodies[-2], 1e-10)  # corpo atual / anterior

    # 3. Rejeição — pavios longos?
    velas_arr = np.array([[v["o"], v["h"], v["l"], v["c"]] for v in velas], dtype=np.float64)
    body = np.abs(velas_arr[:, 3] - velas_arr[:, 0])
    upper_wick = velas_arr[:, 1] - np.maximum(velas_arr[:, 0], velas_arr[:, 3])
    lower_wick = np.minimum(velas_arr[:, 0], velas_arr[:, 3]) - velas_arr[:, 2]
    wick_ratio_up = upper_wick[-1] / max(body[-1], 1e-10)
    wick_ratio_dn = lower_wick[-1] / max(body[-1], 1e-10)
    rejected = (wick_ratio_up > 2.0) or (wick_ratio_dn > 2.0)

    # 4. TA-Lib patterns
    patterns = detect_live_patterns(velas_arr)

    # 5. Score composto
    confidence = 0.5  # baseline neutro
    if slope_pct > 0.02:
        confidence += 0.2
    elif slope_pct < -0.02:
        confidence -= 0.2
    if accel > 1.5:
        confidence += 0.1 * min(accel, 3.0) / 1.5
    if patterns:
        confidence += 0.1 * len(patterns)
    if rejected:
        confidence = 0.0  # anula sinal

    signal = None
    if confidence > 0.65 and slope_pct > 0.02:
        signal = "BUY"
    elif confidence > 0.65 and slope_pct < -0.02:
        signal = "SELL"

    return {
        "signal": signal,
        "confidence": round(min(confidence, 1.0), 2),
        "slope_pct": round(slope_pct, 4),
        "accel": round(accel, 2),
        "patterns": patterns,
        "rejected": rejected,
    }
```

### TA-Lib Live Detection

```python
def detect_live_patterns(velas_5: np.ndarray) -> list[str]:
    """Detecta patterns TA-Lib nas últimas 5 velas (janela mínima).

    velas_5: array shape (5, 4) com colunas [open, high, low, close]

    Patterns de 1-3 velas funcionam com 5 velas de histórico.
    Patterns de 5 velas (CDL3WHITESOLDIERS, etc.) também funcionam.
    Patterns longos (CDLRISEFALL3METHODS, 8 velas) → ignorados.
    """
    import talib

    # Lista de patterns compatíveis com janela de 5 velas
    SHORT_PATTERNS = [
        "CDLDOJI", "CDLHAMMER", "CDLHANGINGMAN", "CDLENGULFING",
        "CDLHARAMI", "CDLMORNINGSTAR", "CDLEVENINGSTAR",
        "CDLPIERCING", "CDLDARKCLOUDCOVER", "CDLSHOOTINGSTAR",
        "CDLINVERTEDHAMMER", "CDL3WHITESOLDIERS", "CDL3BLACKCROWS",
        "CDL3INSIDE", "CDLSPINNINGTOP", "CDLGRAVESTONEDOJI",
    ]

    open_p  = velas_5[:, 0]
    high_p  = velas_5[:, 1]
    low_p   = velas_5[:, 2]
    close_p = velas_5[:, 3]

    detected = []
    for pattern_name in SHORT_PATTERNS:
        func = getattr(talib, pattern_name, None)
        if func is None:
            continue
        result = func(open_p, high_p, low_p, close_p)
        if result[-1] != 0:  # sinal na última vela
            direction = "BULLISH" if result[-1] > 0 else "BEARISH"
            detected.append(f"{pattern_name}[{direction}]")

    return detected
```

## CAMADA DE ANTECIPAÇÃO — 3 Velas

```python
def should_anticipate(buffer: TickBuffer) -> bool:
    """Decide se deve antecipar entrada (não esperar fecho da vela 5).

    Condições:
      1. Últimas 3 velas mostram topos ASCENDENTES (compra) ou
         topos DESCENDENTES (venda) — tendência clara
      2. Volume está acelerando (vela atual > média das 3 anteriores)

    Se True → entry intrabarra (bid/ask atual)
    Se False → entry em open[t+1] (padrão Pip 0)
    """
    velas = buffer.last_3
    if len(velas) < 3:
        return False

    highs = [v["h"] for v in velas]
    lows  = [v["l"] for v in velas]

    # Topos e fundos ascendentes?
    uptrend = highs[0] < highs[1] < highs[2] and lows[0] < lows[1] < lows[2]
    # Topos e fundos descendentes?
    dntrend = highs[0] > highs[1] > highs[2] and lows[0] > lows[1] > lows[2]

    # Volume acelerando?
    vols = [v["v"] for v in velas]
    vol_accel = vols[-1] > np.mean(vols[:-1])

    return (uptrend or dntrend) and vol_accel
```

## FLUXO COMPLETO — `emit_once()` ao Vivo

```python
def emit_once(buffer: TickBuffer, dxy_close: deque, vix_close: deque, symbol: str) -> dict | None:
    """Motor de tempo real: avalia todas as camadas e emite sinal se aprovado.

    Chamado a cada novo tick M1 (via F0 → callback).
    """
    import sys
    sys.path.insert(0, r'C:\Workspace\Neocortex v44\neocortex\11.0_apps\ctrader')
    from utils.dxy_filter_orc_bloco1 import get_dxy_roc, check_dxy_alignment, check_vix_filter

    # ── Camada Meso: VWAP + Exaustão ──
    preco = buffer.velas[-1]["c"]
    vwap = buffer.vwap
    pct = abs(preco - vwap) / vwap * 100  if vwap > 0 else 0

    threshold = 0.50 if symbol == "XAUUSD" else 0.15
    if pct > threshold:
        return {"signal": None, "reason": "EXHAUSTED"}

    regime = "ABOVE" if preco > vwap * 1.001 else ("BELOW" if preco < vwap * 0.999 else "NEUTRAL")

    # ── VIX Panic Override ──
    vix_val = vix_close[-1] if len(vix_close) > 0 else 0
    vix_ma20 = sum(list(vix_close)[-20:]) / min(len(vix_close), 20)
    vix_spike = vix_val > vix_ma20 * 2.0

    # ── DXY ROC ──
    dxy_roc = get_dxy_roc(np.array(dxy_close), lookback=5)

    # ── Camada Micro: Slope + TA-Lib ──
    micro = analyze_micro(buffer, symbol)

    # ── Decisão ──
    if micro["rejected"] or micro["signal"] is None:
        return {"signal": None, "reason": "MICRO_REJECTED"}

    if micro["signal"] == "BUY" and (regime == "BELOW" and not vix_spike):
        return {"signal": None, "reason": "REGIME_MISMATCH"}

    if micro["signal"] == "SELL" and (regime == "ABOVE" and not vix_spike):
        return {"signal": None, "reason": "REGIME_MISMATCH"}

    # ── Panic Override ──
    if vix_spike:
        if symbol == "XAUUSD" and micro["signal"] == "SELL":
            return {"signal": None, "reason": "PANIC_BLOCK_SELL_XAU"}
        if symbol in ("AUDUSD", "GBPUSD", "EURUSD", "USDJPY") and micro["signal"] == "BUY":
            return {"signal": None, "reason": "PANIC_BLOCK_BUY_RISK"}

    # ── DXY Alignment ──
    dxy_ok = check_dxy_alignment(symbol, "BULLISH" if micro["signal"] == "BUY" else "BEARISH", dxy_roc)
    if not dxy_ok and not vix_spike:
        return {"signal": None, "reason": "DXY_MISMATCH"}

    # ── Antecipação ──
    anticipate = should_anticipate(buffer)

    return {
        "signal": micro["signal"],
        "confidence": micro["confidence"],
        "entry_type": "intrabar" if anticipate else "next_open",
        "vwap": round(vwap, 2),
        "regime": regime,
        "vix_spike": vix_spike,
        "dxy_roc": round(dxy_roc, 4),
        "slope_pct": micro["slope_pct"],
        "patterns": micro["patterns"],
    }
```

## CONTROLE DE MEMÓRIA — Prevenção de Memory Leak

| Componente | Estrutura | Memória | Cresce? |
|---|---|---|---|
| Buffer Meso | `deque(maxlen=60)` | ~60 × 7 fields × 8 bytes = 3.4 KB | **Não** |
| VWAP acumulador | 2 floats | 16 bytes | **Não** |
| DXY/ViX close | `deque(maxlen=60)` | ~1 KB cada | **Não** |
| TA-Lib patterns | `list` recriado a cada tick | ~200 bytes | **Não** |
| **Total por símbolo** | — | **~6 KB** | **Constante** |

Para 5 símbolos: ~30 KB total. Cabe em L1 cache.

## CHANGELOG

| Versão | Data | Mudança |
|--------|------|---------|
| 2.0 | 2026-08-05 | Motor de Tempo Real: deque(60), VWAP exaustão, slope 5 velas, TA-Lib live, antecipação 3 velas, emit_once() |
| 1.2 | 2026-08-05 | Wire Bloco1: pattern_confidence_orc_bloco1.py |
| 1.1 | 2026-07-30 | 61 padrões TA-Lib + 10 numpy fallback. Endpoint /lab/patterns funcional. |
