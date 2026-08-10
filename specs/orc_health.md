# SPEC S33 — orc_health_fases: Validador por Fase Sempre Ativo (orquestrador)

> **Versao:** 1.0.0 | **Wire:** utils/orc_health_fases.py → /api/ctrader/health/fases | **Status:** active
> **R-USE:** health.read_heartbeat (S21), orc_metricas.vector_metrics/_read_gap_coverage (S20), storage_orc_vbt (S27)

## Proposito

Cada aba mestra do dashboard ctrader ganha uma **sub-aba 1 "Saude"** que prova,
ao vivo, que as mecanicas e codigos daquela etapa estao OK. O overview principal
mostra **todas as fases x harness** numa grade unica.

Motivacao: gates e harness validavam o codigo ate S27, mas nada validava os
modulos novos (orc_score S32, vector_metrics S20 v2.1, correlate_markets_m1,
warmup, G23 gap-fill). Auditoria 2026-07-30: zero cobertura em tests/ e gates/
para esses modulos. S33 fecha essa lacuna com validacao **em runtime**, nao so
em CI: o proprio dashboard mostra o veredito.

## Pipeline

```
/api/ctrader/health/fases (router — proxy puro)
  ↓
orc_health_fases.check_fases()
  ├── f0_coleta    heartbeat f0 + snapshot fresco + m1 recente + pid vivo + sessao MCP fresca
  ├── f1_f2        status/scores_raw.json + status/fusion_output.json
  ├── f3_ia        status/verdict.json
  ├── f4_execucao  trades.db abre e responde SELECT
  ├── f5_mar       status/custom_rules.json
  ├── vector_s27   vector_metrics() → indicators_count por simbolo (R-USE)
  ├── s29_s30      pontos VBT >= 30 (minimo p/ quality/patterns sairem do sem_dados)
  ├── s31_backfill gap_report.json → coverage_pct por simbolo + idade do fill
  └── s32_score    orc_score.combined_score importa e campos do contrato presentes
  ↓
{fase: {ok: bool, checks: [{nome, ok, detalhe}], resumo: str}}
```

## Regras

- **Regra de custo (S20 v2.1):** so leituras baratas — stat de arquivo, head de
  parquet, SELECT COUNT, JSON pequeno. Score pesado (S29+S30 completo) NUNCA
  roda aqui; s29_s30 verifica apenas se ha pontos suficientes.
- **Nao toca MCP** (R-NO-MCP-BYPASS): saude do F0 vem de heartbeat/pid/snapshot,
  nunca de chamada MCP.
- **Honestidade:** fase em aquecimento (ex.: 29 pontos de 30) reporta
  `ok=false` com detalhe "aquecendo: 29/30" — nunca mascara como ok nem como erro.
- Router nao contem logica de check (G16 valida wire; proxy puro como S32).
- Sem escrita em disco: check_fases() e read-only (G19-compatible).

## Contrato de saida

| Campo | Tipo | Descricao |
|-------|------|-----------|
| fases | dict[str, FaseSaude] | chave = id da fase (tabela acima) |
| FaseSaude.ok | bool | todos os checks passaram |
| FaseSaude.checks | list | [{nome, ok, detalhe}] |
| FaseSaude.resumo | str | "3/3 checks OK" ou "1 falha" |
| gerado_em | str ISO | timestamp UTC da varredura |
| fases_ok | str | "9/9" — agregado p/ overview principal |

## Dashboard (S22)

- A sub-aba **Saúde** original foi unificada com o **Health Check** principal. O componente resultante (`OverviewHealth.tsx`) foi renomeado funcionalmente para **Saúde & Telemetria** e consolidado.
- Esse componente mestre (OverviewHealth) inclui as dependências macro (MCP, Base de Dados, F0 Control, etc) e a grade detalhada S33 ao final da tela.
- Sub-abas redundantes foram removidas das seções de overview, ordens, validação e pré-análise, mantendo apenas a aba mestre de Saúde concentrada onde for relevante ou na visão geral.
