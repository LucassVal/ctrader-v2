<!-- .:. ZONE 1: UBL METADATA .:. -->
$    | NC-11
&    | 11_APPS/NC-11_CTRADER/NC-11_CTRADER_MANIFEST.md
@    | Antigravity
%    | ACTIVE
#    | NC-11_CTRADER_MANIFEST_md
=LCK | `=LCK_UNLOCKED`
^FNC | Arquivo sanitizado automaticamente.
+DO  | Respeitar a governanca UBL.
-NOT | Violar isolamento de dominio.
#DOM | `#DOM_11`
>HRZ | `>HRZ_11`
^VRT | `^VRT_11`
*CRS | `-`

<!-- .:. ZONE 2: EIXO 5 - LOCAL DICTIONARY (Mapeamento de Dominio) .:. -->
v Variavel    : None
c Classe      : None



m Modelo      : None
f Funcao      : None
h Helper      : None
k Constante   : None
r Referencia  : @BOOT, @UBL, @CODICE
x Regex       : None
n Matematica  : None
z Cache       : None

<!-- .:. ZONE 3: VECTOR-SIG & RULES .:. -->

<!-- .:. ZONE 4: WORKFLOWS APLICAVEIS .:. -->
| Workflow | Arquivo | Quando invocar |
|:---|:---|:---|
| `/boot` | NC-01_WORKFLOW_BOOT.md | Inicio de sessao |
| `/rca` | NC-01_WORKFLOW_RCA.md | Antes de modificar este arquivo |
| `/audit` | NC-01_WORKFLOW_AUDIT.md | Antes de commit/entregar |
| `/qa` | NC-01_WORKFLOW_QA.md | Validar ausencia de acentos (R125) |
| `/handoff` | NC-01_WORKFLOW_HANDOFF.md | Apos modificacao concluida |
| `/reuse` | NC-01_WORKFLOW_REUSE.md | Verificar se solucao ja existe no @CATALOG |
| `/decay` | NC-01_WORKFLOW_DECAY.md | Se este arquivo ficar obsoleto |

<!-- .:. ZONE 5: FLUXOS DE REGRAS APLICAVEIS .:. -->
| Regra | Descricao |
|:---|:---|
| RU-01 | Antes de modificar, ler o `@BOOT` e `@UBL` |
| RU-02 | Validar com `NC-09_HEADER_AUDITOR.py` apos edicao |
| RU-03 | NUNCA usar `rm`/`del` - mover para `99_ARCHIVE/` (R05) |
| RU-04 | Manter changelog atualizado na secao `## m CHANGELOG` |

<!-- .:. ZONE 6: FLUXOS DE EXPANSAO E REPLICACAO .:. -->
| Regra | Descricao | Ferramenta |
|:---|:---|:---|
| RE-01 | Usar `NC-04_TEMPLATE_FACTORY.py --type md` para criar novos .md | @CATALOG item 3.3 |
| RE-02 | Nomenclatura: `NC-11_NOME_FUNCAO.md` | @BOOT item 3 |
| RE-03 | Registrar no `@CODICE` (+ADD) e `@CATALOG` se for Rule/Workflow | `/handoff` |
| RE-04 | Tags Replication: `$ NC-{XX}`, `& {path}`, `#DOM_{XX}` | Script |

<!-- .:. ZONE 7: DIRETRIZES ANTI-ALUCINACAO (NAO REMOVER) .:. -->
1. **Proibicao Absoluta de Recriacao:** NAO crie arquivos do zero. Consulte @CATALOG e use o que ja existe (R50).
2. **Proibicao de Alucinacao Estrutural:** NAO invente headers, taxonomias ou templates. Use formatos oficiais (Parte G).
3. **Validacao do Catalogo:** Leia @CATALOG antes de criar. Busca agressiva obrigatoria (Anti-Falso-Negativo).
4. **Templates Oficiais:** Use NC-04_TEMPLATE_FACTORY.py. Nunca crie arquivos manualmente.
5. **R21:** Verifique ambiente real (Test-Path, py_compile). Duvida -> T0.
6. **R125:** Zero acentos em codigo, nomes, YAMLs, metadados.

Das 133 regras catalogadas no documento base 01_GOVERNANCE_RULES/POLICIES/NC-01_RULES_MULTILAYER.md (@RULES), o V43 Stateless abstraiu 90 (Focadas em nuvem/cloud) e ativou agressivamente 43 focadas em FileSystem e I/O. As regras se fundem a topologia:

[P0] SUPREME KERNEL: Onde nascem R21 (Zero Suposicoes), R125 (Zero Acentos) e R01 (Nomenclatura).
[P1] OPERATIONAL PIPELINE: Onde vive a R12 (Handoffs), R03 (Ticket Ref), R19 (Ciclo Kanban).
[P2] DOMAIN RULES: Onde reside R14 (Isolamento de Lobos), R73 (AI Alignment) e R49 (Idempotencia).
[P3] EPISODIC STATE: A Borda Fisica governada por R04 (Atomic Locks), R05 (Never Delete) e R08 (Git Ignore).

### 2. A LEI DO REAPROVEITAMENTO ABSOLUTO E CATALOGO (CACHE HIT MAXIMIZATION)
Como premissa base do NeoCortex V43, qualquer IA que opere na codebase eh regida pelo Principio de Reaproveitamento Absoluto e Cache. O objetivo eh duplo: (A) Mitigar Miss Tokens e a consequente alucinacao, (B) Aumentar o aproveitamento de Cache Tokens retendo o estado de arquivos conhecidos e ja testados.

1. Reaproveitamento Irrestrito (Tudo se Renova): Antes de gerar uma linha de codigo, template YAML, script Python ou Manifesto, a IA DEVE consultar o Catalogo Unificado (@CATALOG - 01_GOVERNANCE_RULES/UBL/NC-01_CATALOG_MASTER.md) e o Codice (NC-01_CODICE_REGISTRY.md) via workflow /reuse. Nao se inventa do zero o que a V42 ou Sprints passadas ja solidificaram. Se precisa de um parser, ache-o em 07_ADAPTERS_PARSERS; se precisa de prompt, use os .mdc em 04_APP_TOOLS.
2. Limites de Agrupamento Estritos (Isolamento DDD): O reaproveitamento nao pode ser desculpa para violar as camadas P0-P3.
Nao injete logicas e queries de base de dados (06_INFRA_REPO) dentro de servicos de negocios (05_DOMAIN_LOGIC).
Se precisa reaproveitar um componente inter-camadas, utilize Padroes de Inversao de Controle ou os Adaptadores de Fronteira (07_ADAPTERS_PARSERS).
3. Workflow Oficial (/reuse): A governanca exige que qualquer reaproveitamento ou agrupamento passe por uma extensao da logica do arquivo existente. Nunca crie "versao 2", adicione modularidade ao arquivo legado (Kaizen).

### 3. REGRAS PARA A FUNCAO DO ARQUIVO
| RF-01 | [Definir regra especifica para este arquivo] |
| RF-02 | [Definir comportamento esperado deste arquivo] |

### 4. PROTOCOLO DE EXECUCAO
| Step 0 / RCA | `/rca` — 5 Whys + 3W antes de qualquer acao |
| Boot | `/boot` — carregar @BOOT, @UBL, @VISION, @CODICE, @ROADMAP |
| Regression | `/audit` — ruff + pyright + HEADER_AUDITOR |
| KISS | `/kaizen` — eliminar complexidade prematura |
| R125 | `/qa` — validar Zero Acentos |
| Handoff | `/handoff` — @CODICE + @ROADMAP + HANDOFFS/ |

## / WORKFLOWS APLICAVEIS

| Workflow | Arquivo | Quando invocar |
|:---|:---|:---|
| `/boot` | NC-01_WORKFLOW_BOOT.md | Inicio de toda sessao |
| `/rca` | NC-01_WORKFLOW_RCA.md | Antes de qualquer codificacao |
| `/audit` | NC-01_WORKFLOW_AUDIT.md | Antes de commit/entregar |
| `/qa` | NC-01_WORKFLOW_QA.md | Validar R125 (Zero Acentos) |
| `/handoff` | NC-01_WORKFLOW_HANDOFF.md | Fechamento de ticket |
| `/reuse` | NC-01_WORKFLOW_REUSE.md | Antes de criar novo arquivo |
| `/decay` | NC-01_WORKFLOW_DECAY.md | Arquivamento (R05) |
| `/tool-create` | NC-01_WORKFLOW_TOOL_CREATION.md | Criacao estrutural via Copier/Hygen e Factory |

$ NC-11
& 11_APPS/NC-11_CTRADER/NC-11_CTRADER_MANIFEST.md
@ Antigravity
% ACTIVE
# MANIFESTO FILHO: CTRADER (11_APPS/NC-11_CTRADER)
=LCK `=LCK_UNLOCKED`
^FNC Manifesto Filho do cTrader
+DO Respeitar a governanca UBL.
-NOT Violar isolamento de dominio.
#DOM `#DOM_11`
>HRZ `>HRZ_11`
^VRT `^VRT_11`
*CRS `*CRS_ALL`
[ EIXO 5 - DICIONARIO LOCAL ]

## REGRAS OBRIGATORIAS (SUB-HEADER — NAO REMOVER)

### 1. REGRAS DE GOVERNANCA (P0 — Kernel Supremo)
| R01 | Nomenclatura NC-XX_NOME_FUNCAO.ext. Sem acentos. |
| R04 | Atomic Locks — respeitar =LCK_T0. |
| R05 | Never Delete — mover para 99_ARCHIVE/. |
| R14 | Lobe Isolation — nao cruzar dominios DDD. |
| R21 | Zero Suposicoes — verificar ambiente real. |
| R49 | Idempotencia — scripts reexecutaveis. |
| R50 | DRY — consultar @CATALOG antes de criar. |
| R51 | Fail-Fast — abortar se parametros invalidos. |
| R53 | KISS — eliminar complexidade prematura. |
| R117 | SSOT Headers — 13 tags obrigatorias. |
| R125 | Zero Acentos — abolir caracteres latinos. |
| R126 | Structural Bound — usar Adapters (07_ADAPTERS_PARSERS). |
| R127 | Universal Structure — ordem canonica definida na Parte G. |

### 2. REGRAS PARA A FUNCAO DO ARQUIVO
| RF-01 | Este arquivo define as regras de governanca do dominio. Modificacoes exigem ticket e aprovacao T0. |
| RF-02 | Consulte @CATALOG (NC-01_CATALOG_MASTER.md) antes de criar novos arquivos neste dominio. |

### 3. PROTOCOLO DE EXECUCAO (Step 0 → RCA → KISS → Pareto → R125 → Handoff)
| Step 0 / RCA | `/rca` — 5 Whys + 3W antes de qualquer acao |
| Regression QA | `/audit` — ruff + pyright + NC-09_HEADER_AUDITOR.py |
| KISS Check | `/kaizen` — eliminar complexidade |
| Pareto 80/20 | Classificar ESFORCO_CRITICO vs ESFORCO_BRACAL |
| Zero Acentos | `/qa` — NC-09_UBL_SYMBOL_AUDITOR.py |
| Handoff | `/handoff` — @CODICE + @ROADMAP + HANDOFFS/ |

Este é o ambiente isolado do projeto cTrader.

Aqui repousam:
- `01_GOVERNANCE_RULES/UBL` -> Dicionário UBL específico do cTrader.
- `03_INFRA_CORE` -> Configurações de conexão FIX e Launchers MCP cTrader.
- `04_APP_TOOLS/AGENT_LOBES` -> Lobos cognitivos focados na API cTrader.
- `07_ADAPTERS_PARSERS` -> Adaptadores (Engines e Handlers) do cTrader.
- `08_MEMORY_LEDGER/MOCK_DATA` -> Mocks de retorno para simulação offline.
- `11_APPS/NC-11_CTRADER/10_UI_DASH/ctrader-dashboard` -> O front-end isolado.

Todos os arquivos devem responder à mesma hierarquia matemática `NC-[NUM]_...` conforme a pasta espelhada.
## m CHANGELOG
| Data | Ticket | Autor | Mudanca |
|------|--------|-------|---------|
| 2026-06-05 | TQ453 | T0-Antigravity | Header sweep |


---
## > RETORNE AO PAI
**Instrucao:** Se este arquivo for um sub-modulo, retorne ao manifesto de dominio pai correspondente.

---
## > RETORNE AO BOOT
O Boot e o Norte absoluto do NeoCortex V43.
