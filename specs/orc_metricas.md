# SPEC S20 | Versao: 2.2 | Wire: utils/orc_metricas.py | Status: active

## PROPOSITO
Orquestrador de metricas: 29 metricas em 5 fases + vector_mercados (v2.1) +
score_mercados + calibration (v2.2).
Collect_all() consolida tudo e expoe via /api/ctrader/metrics. json_log_orc_metricas e o satelite
de logs JSON estruturados.

## REGRA-MET (v2.2 — decretada pelo dono 2026-07-30)

**Tudo que o dashboard exibe passa por orc_metricas → /metrics.** Metricas e quem
alimenta o dashboard e conecta todas as pecas.

- Calculo pesado (S29 walk-forward, S30 patterns, S32 score, S36 calibracao)
  NUNCA roda dentro do collect_all (O(n x 20)) — roda em batch/emissor e grava
  artefato em status/. orc_metricas so LE artefato (barato) e expoe.
- Router nunca monta tela chamando orquestrador pesado direto.
- /vector/symbol/{sym}/score (e /quality, /patterns) continuam existindo para
  DRILL-DOWN sob demanda; o overview do dashboard vem de /metrics.
- G16 valida: toda sub-aba React consome endpoint alimentado por orc_metricas.

### Auditoria REGRA-MET (2026-07-30 — "o que escapa hoje")

| Endpoint (consumido pelo React) | Chama direto | Veredito |
|--------------------------------|--------------|----------|
| /vector/symbol/{s}/score, /quality, /patterns | orc_score/quality/pattern (pesado) | DRILL-DOWN permitido (documentado); overview via /metrics |
| /validate/score75 (ranking) | orc_ranking direto | ESCAPA — S35 wire: ranking grava status/ranking_live.json → secao `ranking` no /metrics |
| /vector/markets, /strength, /indicators, /globals, /correlation, /overview | orc_mercado/orc_indices (barato, snapshot F0) | EXCECAO documentada: leitura barata de snapshot pode ser servida direta; CIENCIA computada (score/padrao/calibracao/ranking) passa por orc_metricas |
| /health, /health/fases, /harness, /f0/*, /backfill/*, /mcp/* | hubs operacionais | FORA DE ESCOPO: controle/operacao, nao metrica de analise |
| /account, /positions, /risk, /performance, /banca, /order/trail-log | orc_dashboard (hub apresentacao) | OK: orc_dashboard e o hub de apresentacao operacional (trades/conta) |

## FLUXO
```
F0..F5 ──log_metrics_json()──→ status/metrics.json ──→ orc_metricas
                                                           │
                              ┌────────────────────────────┤
                              ▼                            ▼
                      collect_all()              validate_metrics()
                              │
                              ▼
                      /api/ctrader/metrics (dashboard)
```

## VECTOR_MERCADOS (v2.1 — S20 + S27 + S31)

Metricas e quem conecta as pecas: o vector passa a alimentar o /metrics.
Secao `vector_mercados` — overview POR MERCADO do que o vector calculou:

| Campo | Fonte | Significado |
|-------|-------|-------------|
| indicators_considered | storage_orc_vbt.load_indicators | nomes dos indicadores com valor valido |
| indicators_missing | idem | nomes sem valor (null/erro) |
| indicators_count | idem | "X/16 familias" |
| bars_used | idem | velas M_1 que alimentaram o calculo |
| vbt_source | idem | parquet / snapshot / offline |
| coverage_pct | status/gap_report.json (G23) | confianca dos DADOS (0-100 de 730d) |
| rsi / adx / atr | idem | glance rapido para o dashboard |

Regra de custo: /metrics so agrega leituras baratas (parquet + json).
Score pesado (S29+S30 walk-forward/pattern) fica on-demand em
/vector/symbol/{sym}/score — NUNCA dentro do collect_all (O(n x 20)).

## SCORE_MERCADOS (v2.2 — S20 + S32 + S36)

Secao `score_mercados` — le `status/score_live.json` (artefato gravado pelo
signal_emitter_orc_score a cada barra M1 fechada — S36 MODO PRESENTE):

| Campo (por simbolo) | Origem | Significado |
|---------------------|--------|-------------|
| sinal | score_live.json | BULLISH/BEARISH/NEUTRAL do ultimo ciclo |
| score | idem | adjusted_confidence × 100 (S32) |
| quality_f1 / pattern_conf | idem | componentes do score |
| regime_mult | idem | fator regime H1 (S34) |
| coverage_pct | gap_report (G23) | confianca dos dados |
| ts_emissao | idem | idade do ultimo sinal (staleness visivel) |

Se score_live.json ausente/velho (>10 min): secao volta `{online: false}` (A7).

## CALIBRATION (v2.2 — S20 + S36)

Secao `calibration` — le `status/calibration.json` (orc_calibracao, batch):

| Campo | Significado |
|-------|-------------|
| hit_rate_por_faixa | % acerto por faixa de score (min 30 amostras; senao "amostra insuficiente") |
| brier_5m/_15m/_60m | calibracao probabilistica por horizonte |
| drift | score medio acertos vs erros convergindo = alerta |
| replay_vs_live | metricas separadas por origem (modelo × sistema) |

## ORQUESTRADOR — `utils/orc_metricas.py` (227L)
Entry points: `collect_all()`, `validate_metrics()`, `f0_metrics()`..`f5_metrics()`, `vector_metrics()`.

## FILHOS

### `json_log_orc_metricas.py`
- **Funcoes**:
  - `log_metrics_json(phase, data)` — escreve metrics.json
  - `read_metrics_json()` — le metrics.json completo
  - `get_trail_log()` — trail viewer (dashboard) — migrado de trail_viewer_orc_ordens
  - `log_trade_json(log)` — persiste trade em trades.db + metrics.json — migrado de log_trade_orc_execucao
- **Saidas**: `status/metrics.json` + writes to `trades.db`


---

## Schema collect_all() — 29 Metricas (FASE 6 M3)

| Metrica | Tipo | Fonte | Fase |
|---------|------|-------|------|
| f0_mcp_uptime_pct | float | snapshot.json age | F0 |
| f0_data_gap_seconds | int | gap_report.json | F0 |
| f0_symbols_online | int | snapshot.json | F0 |
| f0_balance | float | snapshot.json | F0 |
| f0_equity | float | snapshot.json | F0 |
| f0_margin_free | float | snapshot.json | F0 |
| f1_signals_total | int | fusion_output.json | F1 |
| f1_signals_buy | int | fusion_output.json | F1 |
| f1_signals_sell | int | fusion_output.json | F1 |
| f2_score_avg | float | fusion_output.json | F2 |
| f2_score_max | float | fusion_output.json | F2 |
| f2_macro_weight | float | fusion_output.json | F2 |
| f3_rankings_count | int | ranking.json | F3 |
| f3_rank_top_symbol | str | ranking.json | F3 |
| f4_win_rate | float | trades.db | F4 |
| f4_profit_factor | float | trades.db | F4 |
| f4_max_drawdown_pct | float | trades.db | F4 |
| f4_total_trades | int | trades.db | F4 |
| f4_total_pnl | float | trades.db | F4 |
| f4_sharpe_ratio | float | trades.db (calc) | F4 |
| f5_mar_weight_delta | float | f5_mar/*.json | F5 |
| f5_mar_signals | int | f5_mar/*.json | F5 |
| coverage_2y_pct | float | gap_report.json | S31 |
| backfill_running | bool | backfill_progress.json | S31 |
| backfill_pct | float | backfill_progress.json | S31 |
| health_fases_ok | int | orc_health_fases | S33 |
| health_fases_total | int | orc_health_fases | S33 |
| cache_hit_rate | float | data_source.py | S26 |
| schema_validation_ok | bool | schema_validator.py | S32 |
