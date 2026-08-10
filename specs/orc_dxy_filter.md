# SPEC S41.4 | Versao: 1.0 | Wire: utils/dxy_filter_orc_bloco1.py | Status: active

## PROPOSITO
Filtro DXY para Bloco1: confirma/nega sinais baseado na forca do dolar.
SAT filho de orc_bloco1.py. Determina se BUY/SELL em XAUUSD e
compativeis com a tendencia do DXY (DXY caindo favorece BUY ouro).

## FLUXO
```
dxy_filter_orc_bloco1.check(dxy_close, signal_direction) -> (allowed: bool, confidence_delta: float)
```

## REGRAS
- DXY caindo + BUY XAUUSD = +0.10 confidence
- DXY subindo + SELL XAUUSD = +0.10 confidence
- DXY caindo + SELL XAUUSD = -0.10 confidence (sinal contrario)
- DXY flat (ROC < 0.1%) = neutro
