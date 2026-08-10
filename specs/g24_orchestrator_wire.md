# SPEC S24 — Orchestrator Wire Gate

> **Versao:** 1.1.0 | **Wire:** gates/run_orchestrator_wire.py | **Status:** active
> **TICKET:** NC-GATE-024

## PROPOSITO

Garantir que toda funcao publica em `utils/` tem um orquestrador declarado E um teste.
Quem define as funcoes sao os orquestradores — nao o contrario.
G24 detecta drift: funcao sem teste = alerta no pre-flight.

## CLASSIFICACAO

| Sigla | Significado | Quem chama | Exemplo |
|-------|------------|-----------|---------|
| **ORQ** | Orquestrador | Router (endpoint) | `orc_metricas.collect_all()` |
| **SAT** | Satelite | Apenas ORQs | `storage_orc_vbt.load_history()` |
| **UTIL** | Infraestrutura | Qualquer um | `mcp_client.get_client()` |

## REGRA

```
Router → APENAS ORQ
ORQ    → SAT + UTIL
SAT    → UTIL (nunca outro SAT diretamente)
UTIL   → stdlib + deps externas

TODO ORQ → pelo menos 1 teste unitario (test_*.py)
```

## EXECUCAO

```bash
python gates/run_orchestrator_wire.py
# G24 — 160/160 (100%) cobertura, 0 orfas, 0 ORQs uncovered → PASS
```

## TEST COVERAGE (v1.1)

| ORQ | Teste | Status |
|-----|-------|--------|
| orc_ranking | test_orc_ranking.py | ✅ |
| orc_pattern | test_orc_pattern.py | ✅ |
| orc_mercado | test_orc_mercado.py | ✅ |
| orc_indices | test_orc_indices.py | ✅ |
| orc_vectorbt | test_orc_vectorbt.py | ✅ |
| orc_vbt_portfolio | test_orc_vbt_portfolio.py | ✅ |
| vista_orc_mercado | test_vista_orc_mercado.py | ✅ |
| f0_supervisor_orc_dashboard | test_f0_supervisor.py | ✅ |

## VIOLACOES

| Tipo | Severidade | Acao |
|------|-----------|------|
| Funcao sem mapeamento | WARN | Registrar no mapa |
| Router importa SAT | ERR | Mover logica para ORQ |
| ORQ sem teste | WARN | Criar test_*.py |

## HISTORICO

| Versao | Data | Mudanca |
|--------|------|---------|
| 1.1.0 | 2026-08-01 | Test coverage gate: 8/8 ORQs cobertos, 129 tests |
| 1.0.0 | 2026-08-01 | Criacao: 160/160 mapeadas, FUS-STUB extinto |
