# SPEC S36 — Calibracao: Quality Track Record (previsibilidade × acerto)

> **Versao:** 1.2.0 | **Wire:** utils/orc_calibracao.py (ORQ) + utils/signal_emitter_orc_score.py (SAT) + f0_collector/orc_coleta.py (gatilho M1) | **Status:** active
> **R-USE:** S32 (orc_score), S35 (ranking v2), S31 (consolidado 730d), S5.1 (S1/S2)

## Proposito

Conciliar o que o sistema PREVIU com o que ACONTECEU: todo sinal emitido e logado
com seu score; um reconciliador mede o outcome real em M1; o dashboard expoe
hit-rate por faixa de score — a prova empirica de que score alto = acerto alto
(overview de rankings historicos de qualidade, pedido 2.1.1 do dono).

## DOIS MODOS DE VALIDACAO (ampliado 2026-07-30 — auditoria "cobre 100%?")

### MODO PASSADO — replay walk-forward (calibracao IMEDIATA)

Sem replay, o signals_log so acumula de agora em diante: 30 amostras/faixa
levariam semanas. O replay resolve no dia 1:

```
para cada ts em grade do consolidado (a cada 15 min, 730d):
    janela = dados SOMENTE ate ts (trailing, zero lookahead bias)
    sinal_sintetico = orc_score.combined_score(janela)
    append signals_log (origem="replay")
    outcomes = barras [ts+1 .. ts+60] ja existem no parquet → reconcilia na hora
```

Resultado: signals_log nasce com milhares de sinais validados → hit-rate por
faixa + Brier + ranking de qualidade DISPONIVEIS imediatamente, antes do 1º
sinal live. Roda batch offline (padrao S31/S34), nunca em runtime.

### MODO PRESENTE — emissor live + reconciliador continuo

```
signal_emitter_orc_score.py (SAT do orc_score)
  → GATILHO (v1.2.0): wireado no ciclo F0 (orc_coleta.run, branch CANDLE_INTERVAL)
    — a cada barra M1 fechada o F0 chama emit_once(); CLI --once segue
    disponivel para emissao manual. Falha do emissor NUNCA quebra o ciclo F0
    (try/except, mesmo padrao take_snapshot/S27 VBT).
  → a cada barra M1 fechada: combined_score(symbol)
  → append signals_log (origem="live")
  → grava status/score_live.json (ultimo ciclo: sinal/score/componentes/regime)
  → anti-flood: max 1 sinal/simbolo/barra; dedup (symbol, sinal, faixa_score, ts_min)

orc_calibracao.reconcile() (batch horario ou sob demanda)
  → fecha outcomes de todo sinal com ts + 60 min < now e outcome NULL
  → grava status/calibration.json

orc_metricas (REGRA-MET, S20 v2.2)
  → le score_live.json + calibration.json (barato) → secoes score_mercados
    e calibration no /metrics → dashboard
```

Exemplo concreto: previu BULLISH XAUUSD as 18:10 (score 72) → as 18:15, 18:25
e 19:10 o reconciliador marca acerto_5m/_15m/_60m e pips — visivel na aba 1 Geral.

### origem: replay × live

| origem | Mede | Peso no S35 |
|--------|------|------------|
| replay | o MODELO (regras+padroes) em 2 anos | calibracao inicial, peso menor |
| live | o SISTEMA real (latencia, dados ao vivo) | track record oficial, peso maior |

## Pipeline

```
[PASSADO] replay walk-forward (batch offline, 730d consolidado)
[PRESENTE] signal_emitter_orc_score (SAT, a cada barra M1 fechada)
  → data/signals_log.parquet (append, coluna origem=replay|live)
       → orc_calibracao.reconcile() (batch, le consolidado M1)
            → status/calibration.json
                 → aba 1 Geral (overview qualidade) + S35 (peso por track record)
```

## Schema `data/signals_log.parquet` (aprovado pelo dono 2026-07-30; origem add v1.1)

| Coluna | Tipo | Origem |
|--------|------|--------|
| ts | datetime64[ns] UTC | emissao |
| symbol | str | 5 ativos (A5) |
| origem | str | `replay` (walk-forward historico) / `live` (emissor presente) |
| strategy_id | str | S1/S2 (S5.1) — nullable ate S28/S37 implementar |
| sinal | str | BULLISH / BEARISH |
| score | float 0-100 | S32 adjusted_confidence × 100 |
| coverage_pct | float | cobertura S31 no momento da emissao |
| close_entrada | float | close M1 da barra de emissao |
| outcome_5m_pips | float | reconciliador (lookahead 5 barras M1) |
| outcome_15m_pips | float | reconciliador (lookahead 15 barras M1) |
| outcome_60m_pips | float | reconciliador (lookahead 60 barras M1) |
| acerto_5m | bool | direcao bateu no horizonte 5 |
| acerto_15m | bool | idem 15 |
| acerto_60m | bool | idem 60 |

**Suficiencia (resposta ao dono):** este schema cobre S36 inteiro (hit-rate, Brier,
drift, ranking de qualidade). NAO duplicar com trades.db — trades.db so no S38
(paper F4), com PnL/gestao real. strategy_id e o unico campo que chega "adiantado"
(nullable), justamente para S37 nao precisar migracao de schema.

## Metricas de calibracao

- **Hit-rate por faixa de score** (0-50, 50-70, 70-85, 85-100), minimo 30 amostras
  por celula — abaixo disso, celula marcada "amostra insuficiente" (A7 honesto).
- **Brier score** por horizonte (5/15/60) — calibracao probabilistica real.
- **Drift detector**: score medio dos acertos vs dos erros por semana — se convergir,
  o score parou de discriminar (alerta).
- **Ranking historico de qualidade**: estrategia × simbolo × faixa — alimenta a
  aba 1 Geral e o peso de track record do S35.

## Regras

- Reconciliador BATCH (nunca no runtime de emissao) — le signals_log + consolidado M1.
- Lookahead em barras M1 (empirismo M1-puro, decisao do dono 2026-07-30).
- Sem lookahead bias: outcome usa APENAS barras posteriores a ts; sinais com menos
  de 60 barras futuras ficam com outcome NULL (aguardando).
- Min 30 amostras por celula antes de expor % (R21 — sem numero sem base).
- orc_calibracao NAO toca MCP — so le parquet (signals_log + consolidated).
- Outcomes LIQUIDOS de spread (R21, S34 §4b): outcome_Xm_pips desconta o
  spread medio do simbolo (PIP_SPECS.spread) antes de marcar acerto.
