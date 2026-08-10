# SPEC S19 | VERSION: 1.0 | WIRE: json_log_orc_metricas → orc_metricas | STATUS: active
Versao: 2.0
# Fluxo de Logs — cTrader V2

> **Resposta a**: "temos fluxos de logs? quem gera o JSON para metricas?"

## Logs no sistema (3 camadas)

```
┌────────────────────────────────────────────────────────────┐
│                     CAMADA 1: APLICACAO                    │
│                                                            │
│  logger.py ──→ logs/system.jsonl                           │
│    Categorias: ORDERS, MONITOR, SAFETY, MCP, FUSION, ...   │
│    Uso: debug, auditoria, troubleshooting                  │
│                                                            │
├────────────────────────────────────────────────────────────┤
│                     CAMADA 2: METRICAS                     │
│                                                            │
│  json_log_orc_metricas.py ──→ status/metrics.json          │
│    log_metrics_json("f0_coleta", data)                     │
│    log_metrics_json("f4_execucao", data)                   │
│    Estrutura: {"f0_coleta":{...}, "f4_execucao":{...}}     │
│    Uso: dashboard, vectorbt replay, analise                │
│                                                            │
├────────────────────────────────────────────────────────────┤
│                     CAMADA 3: TRADES                       │
│                                                            │
│  trades_log_orc_mar.py ──→ trades.db (SQLite)              │
│    log_trade_json() — trade concluido                      │
│    get_trades_today() — performance diaria                 │
│    Uso: MAR (pesos PnL), auditoria, replay                │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

## Quem gera o JSON para metricas?

```
CADA ORQUESTRADOR escreve sua fase:

  orc_coleta    ──log_metrics_json("f0_coleta")──┐
  orc_analise   ──log_metrics_json("f1_f2_analise")──┤
  orc_fusao     ──log_metrics_json("f1_f2_analise")──┤
  orc_validacao ──log_metrics_json("f3_ia")──────────┤
  orc_execucao  ──log_trade_json(trade)──────────────┤
  orc_mar       ──log_metrics_json("f5_mar")─────────┤
                                                    ▼
                                          status/metrics.json
                                                    │
                          ┌─────────────────────────┴──────────────┐
                          ▼                                        ▼
                  orc_metricas.collect_all()              vectorbt replay
                          │                                        │
                          ▼                                        ▼
                  /api/ctrader/metrics                   pesos → F2
```

## O vectorbt faz as analises de pre e execucao?

**SIM.** Fluxo:

```
1. PRE-EXECUCAO (calibracao):
   vectorbt ←── trades.db (historico)
   vectorbt ──→ custom_rules.json (pesos otimizados)
   custom_rules.json ──→ orc_fusao (F2)

2. POS-EXECUCAO (replay):
   vectorbt ←── trades.db + metrics.json
   vectorbt ──→ relatorio de performance
   Se detecta drift → recalibra pesos → realimenta F2
```

## Arquivos envolvidos

| Camada | Arquivo .py | Saida | Le por |
|--------|-----------|-------|--------|
| Log app | `utils/logger.py` | `logs/system.jsonl` | dev/humano |
| Metricas | `utils/json_log_orc_metricas.py` | `status/metrics.json` | dashboard, vectorbt |
| Trades | `f5_mar/trades_log_orc_mar.py` | `trades.db` | orc_mar, rules_orc_mar, vectorbt |
