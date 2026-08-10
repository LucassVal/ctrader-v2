# SPEC S0 | VERSION: 2.0 | WIRE: todos os orquestradores | STATUS: active

Versao: 2.0

# 00 — Visao Geral do cTrader V2

> **"Arquivo 0"** — ponto de entrada da documentacao.
> Toda decisao de arquitetura, fluxo e contrato parte daqui.

## Arquitetura

```
┌─────────────────────────────────────────────────────────┐
│                    CTRADER V2                           │
│                                                         │
│  F0 (orc_coleta)  ←── PONTA DE LANCA MCP ──→ cTrader   │
│  F1 (orc_analise) ←── scores tecnicos                  │
│  F2 (f2_fusao/orc_fusao)   ←── fusao ponderada (F5 pesos)       │
│  F3 (f3_validacao/orc_validacao)←── threshold + gatekeeper           │
│  F4 (orc_execucao)←── ordens + trail + BE              │
│  F5 (orc_mar)     ←── Monitoramento Ajuste Replay      │
│                                                         │
│  UTILS:                                                │
│    mcp_client     ←── Gateway throttle+cache            │
│    orc_metricas   ←── 29 metricas + collect_all         │
│    orc_dashboard  ←── Hub apresentacao                  │
│    orc_ranking    ←── rank mecanico (IA removida)       │
└─────────────────────────────────────────────────────────┘
```

## Fluxo Ponta-a-Ponta

```
MCP ──→ F0 (orc_coleta) ──snapshot.json──→ F1 (orc_analise)
                                                  │
                                                  ▼ scores_raw.json
                                            F2 (f2_fusao/orc_fusao)
                                                  │
                                                  ▼ fusion_output.json
                                            F3 (orc_validacao)
                                                  │
                                          ┌── APPROVE? ──┐
                                          ▼ SIM           ▼ NAO
                                    F4 (orc_execucao)    REJECT → F5
                                          │
                                    ┌─────┴─────┐
                                    │  OCO/MKT   │
                                    │  Trail/BE  │
                                    │  Scalp     │
                                    └─────┬─────┘
                                          ▼
                                    trades.db + metrics.json
                                          │
                                          ▼
                                    F5 (orc_mar) ──→ pesos → F2
```

## Como ler os specs

Cada orquestrador tem seu spec no formato:

```
specs/orc_<nome>.md
  ├── PROPOSITO
  ├── FLUXO (ASCII)
  ├── ORQUESTRADOR (arquivo .py, entry points)
  └── FILHOS (satelites, funcoes)
```

## Convencoes

| Elemento     | Nomenclatura                            |
| ------------ | --------------------------------------- |
| Orquestrador | `orc_<funcao>.py`                     |
| Satelite     | `<nome>_orc_<pai>.py`                 |
| Wrapper      | `<fase>.py` (re-exporta orquestrador) |
| Gateway      | `mcp_client.py` (infra, nao satelite) |

## Fluxos de Dados

| Fluxo    | Origem | Destino      | Formato                |
| -------- | ------ | ------------ | ---------------------- |
| Coleta   | MCP    | F0           | OHLCV + spot           |
| Snapshot | F0     | F1..F5       | `snapshot.json`      |
| Scores   | F1     | F2           | `scores_raw.json`    |
| Fusao    | F2     | F3,F4,F5     | `fusion_output.json` |
| Ordem    | F4     | MCP          | HTTP (via mcp_client)  |
| Trade    | F4     | trades.db    | SQLite                 |
| Metricas | F0..F5 | orc_metricas | `metrics.json`       |
| Pesos    | F5     | F2           | `custom_rules.json`  |

## Specs relacionados

| Spec                             | Descreve                       |
| -------------------------------- | ------------------------------ |
| `orc_coleta.md`                | F0 — coleta MCP               |
| `orc_analise.md`               | F1 — scores tecnicos          |
| `orc_fusao.md`                 | F2 — fusao ponderada          |
| `orc_validacao.md`             | F3 — threshold + gatekeeper   |
| `orc_execucao.md`              | F4 — ordens + trail + BE      |
| `orc_ordens.md`                | F4-sub — OCO + scalp + params |
| `orc_mar.md`                   | F5 — pesos + replay           |
| `orc_dashboard.md`             | Hub apresentacao               |
| `orc_metricas.md`              | 29 metricas + JSON log         |
| `orc_ranking.md`               | Rank mecanico                  |
| `fluxo_logs.md`                | Fluxo de logs                  |
| `ROADMAP.md`                   | Roadmap completo               |
| `QUALITY_GATES.md`             | Gates G0-G18                   |
| `mcp_endpoints.md`             | Contrato MCP                   |
| `ruse_alternatives.md`         | R-USE alternatives             |
| `strategy_3scalps_5markets.md` | Estrategia                     |
| `vectorbt_ecosystem.md`        | VectorBT                       |

---

## Regra Anti-Drift — ORQ vs SAT (A13)

**Todo novo .py DEVE ser classificado ANTES de ser criado:**

| Tipo | Onde | Regra |
|------|------|-------|
| **ORQ** (orquestrador) | `f{n}_<fase>/orc_<nome>.py` | Decide, coordena, importa outros utils. Contém lógica de negócio. |
| **SAT** (satélite) | `utils/<nome>_orc_<pai>.py` | Função pura. Sem decisão de negócio. Sem import de outros utils. |

**Check rápido**: se o arquivo importa outros `utils/*.py` ou contém condicionais de negócio (`if score >= threshold → APPROVE`) → é **ORQ**, não SAT.

**Exemplos de violação (drift identificado 2026-08-01):**
- `utils/orc_ranking.py` → deveria ser `f3_validacao/orc_ranking.py` (decide APPROVE/REJECT)
- `utils/orc_score.py` → deveria ser `f2_fusao/orc_score.py` (combina F1+F2 com pesos)

**Satélites corretos em `utils/`**: `orc_pattern.py`, `orc_quality.py`, `orc_indices.py`, `orc_mercado.py`, `orc_calibracao.py`, `orc_grid.py`, `orc_scan.py` — funções puras, sem decisão.
