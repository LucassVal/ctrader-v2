# SPEC S91 — DomainGates (Anti-Corruption Layer Frontend)

> **Versao:** 1.0.0 | **Wire:** DomainGates.ts → useApi.ts | **Status:** active
> **TICKET:** NC-UI-030

## PROPOSITO

Camada de validacao de tipo (Circuit Breaker) entre API e componentes React.
Toda resposta da API e validada ANTES de chegar ao componente.

## ARQUITETURA

```
API :7744
  → useApi.fetch()
    → DomainGates.validate(endpoint, raw)
      → GateResult { ok, data?, error?, trace }
        → Componente recebe data tipada OU error com trace
```

## GATES IMPLEMENTADOS

| Endpoint | Gate | Valida |
|----------|------|--------|
| `/banca` | validateBanca | .online, .conta.balance, .posicoes[], .mercados{} |
| `/performance` | validatePerformance | .scatter[], .monthly[], .equity_curve[], .total_trades |
| `/health` | validateHealth | .mcp.ok, .mcp.error |
| `/health/fases` | validateHealthFases | .fases{} nao vazio |
| `/f0/status` | validateF0Status | .running: boolean |
| `/backfill/status` | validateBackfill | .running, .coverage_pct |
| `/metrics` | validateMetrics | objeto valido (campos opcionais) |
| `/vector/symbol/*` | validateSymbolData | .symbol: string, .vector_bt{} nao vazio, .price/.bid |
| Outros | fallback | objeto ou array valido |

## COMPORTAMENTO

- **OK**: data tipada entregue ao componente
- **REJECT**: data = null, error = mensagem, trace = endpoint + campo
- **OFFLINE**: API inacessivel → error = mensagem de rede
- **FALLBACK**: endpoint sem gate especifico → aceita qualquer objeto/array

## REGRAS

| Regra | Descricao |
|-------|-----------|
| R-ANTI-DECAY | Separar estritamente logica de negocio de I/O |
| R-SELF-REPAIR | Se o schema falhar, surfacar erro (nao silenciar) |
| R-NO-SILENT-FAIL | Proibido `return null` sem mensagem de erro |
| KISS | Type guards simples (isNumber, isString, isObject, isArray) |
| R-USE | Tipos compartilhados em DomainGates.ts (fonte unica) |

## HISTORICO

| Versao | Data | Mudanca |
|--------|------|---------|
| 1.0.0 | 2026-08-01 | Criacao: 8 gates + fallback, wire no useApi |
