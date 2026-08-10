# SPEC S29 — Qualidade de Sinais (Walk-Forward Backtest)

> **Versao:** 1.0.0 | **Wire:** utils/orc_quality.py → /vector/symbol/{sym}/quality | **Status:** active
> **R-USE:** storage_orc_vbt.py, orc_vectorbt.py

## Proposito

Medir qualidade dos sinais gerados pelos indicadores VBT usando walk-forward backtest.
Responde: "este indicador gera sinais bons ou e so ruido?"

## Pipeline

```
vbt_{SYM}.parquet (historico)
  ↓ storage_orc_vbt.load_history()
  ↓
generate_signals() — regras deterministicas
  ├── BUY:  RSI < 35 AND ADX > 20
  └── SELL: RSI > 65 AND ADX > 20
  ↓
backtest_signals() — walk-forward 5 velas
  ├── Para cada sinal: preco moveu na direcao? (min 5 pips)
  ├── Precision: sinais corretos / total sinais emitidos
  ├── Recall: sinais corretos / todos os acertos possiveis
  ├── F1 score: 2 × P × R / (P + R)
  ├── Win rate: % sinais com PnL positivo
  └── Profit factor: ganho total / perda total
  ↓
/vector/symbol/XAUUSD/quality
```

## Metricas

| Metrica | Significado | Bom |
|---------|------------|-----|
| analysis_days | Quantos dias de historico disponivel | > 30 |
| signals_count | Quantos sinais gerados | > 50 |
| win_rate | % sinais com lucro | > 55% |
| precision | Sinais corretos / sinais emitidos | > 0.5 |
| recall | Sinais corretos / oportunidades reais | > 0.4 |
| f1_score | Media harmonica P+R | > 0.45 |
| avg_pnl_pct | Lucro medio por sinal (%) | > 0 |

## Regras de sinal (v1)

| Tipo | Condicao | Confianca |
|------|----------|-----------|
| BUY | RSI < 35 AND ADX > 20 | (35-RSI)/20 + (ADX-20)/30 |
| SELL | RSI > 65 AND ADX > 20 | (RSI-65)/20 + (ADX-20)/30 |

## Limitacoes

- Sem ML — regras deterministicas (v1)
- Lookahead fixo de 5 velas M_1
- Min 5 pips para considerar acerto
- Depende de backfill + F0 com _persist_parquet ativo
