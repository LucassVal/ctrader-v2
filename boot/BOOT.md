---
description: Inicializador logico do Neocortex V44 — lema, boot sequence, ponteiros para docs
always_on: true
---

# BOOT — Neocortex V44

> **Papel deste arquivo**: inicializador logico (lema do sistema, sequencia de boot, ponteiros).
> NAO e fonte de estado operacional — o estado real esta em `6.0_banco/neocortex.db` (SQL).
> Para estado atual: `make db-status` | `make roadmap-status` | `make boot`

## LEMA DO SISTEMA

> **"Automatize localmente o maximo possivel sem IA. Use a IA apenas para ajustar ferramentas, criar processos e integrar o que ja existe — de forma proporcional a necessidade real, nao ao hype."**

## SEQUENCIA DE BOOT (ordem obrigatoria para cold-start)

```
1. RULES.md              → 68+ regras canonicas (T0, fonte de verdade absoluta)
2. NC-BP_GLOBALMAP.md    → mapa arquitetural: fases, gaps, make targets, SQL tables
3. ARQUITETURA_BASE.md   → schema SQL, convencoes de codigo, paths
4. UBL.md                → lexico 48 termos canonicos (R-LANG)
5. make db-status        → PENDING/DONE/DEAD (estado real dos tickets no SQL)
6. make boot             → health check 130 modulos + wiring (R-BOOT-SQL)
```

**NOTA**: CLAUDE.md/GEMINI.md/AGENTS.md sao espelhos de RULES.md para suas respectivas IDEs.
Nao sao fontes de verdade — apenas relays. Ler RULES.md diretamente.

## ARQUITETURA CLOUD-ONLY (2026-06-15)

| Camada | Componente | Papel |
|--------|-----------|-------|
| Executores Cloud | Claude, Gemini, DeepSeek | Executam E revisam tickets via `make agent-run` |
| Gates Automaticos | `NC-04_ticket_linter.py` + ruff + pytest | Validacao deterministica — 0 tokens cloud |
| Orquestracao | `NC-08_agent_runner_daemon.py` | Despacha tickets para executores cloud |
| Alfandega | `NC-04_ticket_linter.py` + `NC-05_circuit_breaker.py` | Gates de entrada e runtime |
| SSOT | `6.0_banco/neocortex.db` | 19 tabelas: tickets, roadmap, modulos, changelog... |

> **Qwen/Ollama** = agente local FUTURO (SillyTavern + tarefas pre-agendadas).
> Status: PLANEJADO. Ver ticket NC-UI-003 (HUD Qwen tab) + NC-ORQ-006 (ciclo cloud).

## DOCUMENTACAO (ponteiros, nao duplicar aqui)

- **Mapa Global:** `3.0_ssot/blueprints/governanca/NC-BP_GLOBALMAP.md`
- **Governanca 68 regras:** `RULES.md` (fonte) / mirrors: CLAUDE.md, GEMINI.md, AGENTS.md
- **Schema SQL:** `0.0_devdocs/NC-DOC-007_ARQUITETURA_BASE.md`
- **Lexico:** `3.0_ssot/UBL.md`

> LEGADO V43 ARQUIVADO: maker-cli.py, fila priorizada Markdown, handoffs por arquivo.
> Tudo agora gerido pelas tabelas do `6.0_banco/neocortex.db` via `make help`.

## ESTADO ATUAL (2026-06-16)

```
Tickets:     120 SQL (91 DONE, 6 PENDING, 23 DEAD) + 28 filesystem
Modulos:     24 fases wireadas, 832 filhos (R-PARENT-WIRE)
Orbitais:    19 implementados (100% extensoes cobertas)
Testes:      48 arquivos, 286 tests coletados
DevDocs:     47 tecnologias no fonte_catalog, 11 baixadas
CI:          L1 pre-commit (8 steps), L2 commit-msg, L3 pre-push, L4 GitHub Actions
Apps:        4 wireados (novapulse, elysian-bonds, game-asset-mcp, MoneyPrinterTurbo)
Auditoria:   maker audit perf/analyze/suggest + .audit.md orbital
DB:          Blind anti-reset + DB→FS writeback + ticket-sync-fs wireado no flow-boot/ship
```

## WIRE ATUAL (FLUXOS)

```
flow-create  → generate → backbone → triad → lint → test → ubl → git
flow-update  → validate → backbone → triad → lint → test → ubl → git
flow-boot    → lock-db → ticket-sync → boot → backbone → triad → lint
flow-ship    → ubl → lint → test → backbone → triad → devdocs → ticket-sync → seed → blueprints → ui → git → audit
```

## PRE-COMMIT (8 steps)

```
1. Block .db .env .pyc
2. Ruff .py staged
3. L1+ backbone_validator (.py 7-layer)
4. Backbone formatos (18 extensoes)
5. Qwen review (advisory)
6. Triad parity (Makefile↔nc.ps1↔maker-cli)
7. DevDocs coverage (advisory)
8. Resultado final
```
