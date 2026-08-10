# SPEC S32 — orc_score: Score Combinado S29+S30 (orquestrador)

> **Versao:** 1.0.0 | **Wire:** utils/orc_score.py → /vector/symbol/{sym}/score | **Status:** active
> **R-USE:** orc_quality.quality_metrics (S29), orc_pattern.pattern_analysis (S30)

## Proposito

Toda fase/dado passa obrigatoriamente por um orquestrador. Ate 2026-07-29 a
regra de combinacao do score vivia no router (ctrader_v2.py) — debito de wire.
S32 cria o orquestrador: router vira proxy puro.

## Pipeline

```
/vector/symbol/{sym}/score (router — proxy)
  ↓
orc_score.combined_score(symbol)
  ├── orc_quality.quality_metrics(symbol)   → f1_score (regras deterministicas)
  ├── orc_pattern.pattern_analysis(symbol)  → confidence (padroes historicos)
  ↓
combined = quality_f1 × 0.33 + pattern_conf × 0.67   (se pattern_conf > 0)
combined = quality_f1                                 (fallback sem padroes)
adjusted = combined × min(1, data_days / 730)         (confianca progressiva, S31)
```

Padroes tem 2x mais peso que regras porque capturam contexto (S30 spec).
O score ajustado escala com a cobertura real do historico: enquanto o fill
dos 2 anos avanca, o vector trabalha com o que tem e a confianca sobe junto.

## Contrato de saida

| Campo | Tipo | Origem |
|-------|------|--------|
| symbol | str | param |
| combined_confidence | float 0-1 | formula acima |
| adjusted_confidence | float 0-1 | combined x cobertura (S31) |
| data_days | float | dias de historico disponivel |
| coverage_pct | float 0-100 | data_days / 730 |
| signal | BULLISH/BEARISH/NEUTRAL | outcome S30 |
| quality_f1 | float | S29 backtest |
| pattern_confidence | float | S30 outcome |
| rule | str | formula aplicada (auditabilidade) |
| details.quality | dict | retorno integral S29 |
| details.patterns | dict | retorno integral S30 |

## Regras

- orc_score NAO toca MCP, NAO le parquet direto — so orquestra S29+S30
- Router nao pode conter logica de combinacao (G16 valida wire)
- Peso 0.33/0.67 documentado aqui — mudar peso = mudar spec primeiro (R-SDD)
