# SPEC S3 | Versao: 3.0 | Wire: f1_analyzer/orc_analise.py | Status: active

## PROPOSITO
F1 — Analise tecnica: scores por ativo (BBANDS, ATR, ADX, EMA, DXY, sentiment, candlestick patterns).
Gera scores_raw.json para fusao no F2.

## FLUXO (ATUALIZADO v3.0)

```
snapshot.json ──→ orc_analise ──→ scores_raw.json ──→ F2 (orc_fusao)
                      │
        ┌─────────────┼─────────────┬──────────────┐
        ▼             ▼             ▼              ▼
    pillars      micro/sent     dxy/indicator   patterns (S40)
    (BBANDS,      (sentiment,    (DXY multi-    (candlestick
     ATR, ADX,    metadata)      par, indice)    detection)
     EMA, pivots)
```

## ORQUESTRADOR — `f1_analyzer/orc_analise.py`
Wireia todos os satelites. Entry point: `analyze(snapshot)`.

## FILHOS

### `pillars_orc_analise.py`
- **Funcoes**: calc_bbands(), calc_atr(), calc_adx(), calc_ema(), calc_pivots()
- **Dados**: snapshot OHLCV

### `micro_orc_analise.py`
- **Funcoes**: extract_symbol_metadata()
- **Dados**: snapshot + dxy_orc_analise

### `sentiment_orc_analise.py`
- **Funcoes**: calc_sentiment_ratio()
- **Dados**: snapshot F0 (positions) — nao chama MCP direto

### `dxy_orc_analise.py`
- **Funcoes**: DXY multi-par (5 ativos)
- **Uso**: micro_orc_analise + pillars

### `indicators_orc_analise.py`
- **Funcoes**: Indicadores compartilhados entre satelites

### `patterns_orc_analise.py` (NOVO — S40)
- **Funcoes**: detect_candle_patterns(df, patterns=None)
- **Dados**: m1_*.parquet (OHLCV historico)
- **Output**: dict[symbol, list[PatternDetected]]
- **Fallback**: 10 padrões numpy puro se TA-Lib não instalado
- **Wire**: alimenta `pattern_conf` no score S32

### ⚫ CORTADOS
| Arquivo | Motivo |
|---------|--------|
| `news_orc_analise.py` | MCP nao prove news |
| `ichimoku_orc_analise.py` | Cortado da v1 |
| `volume_orc_analise.py` | Zero importadores |
