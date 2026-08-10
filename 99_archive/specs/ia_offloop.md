> **STATUS: CONSOLIDADO_EM `orc_validacao.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S26: SPEC S26: IA OFF-LOOP — IA FORA DA MALHA DE DECISAO
>**Versao:** 1.0.0  
>**Wire:** `specs/INDEX.md`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## DECISAO CANONICA

> **Nenhuma IA (DeepSeek, Claude, qualquer LLM) participa do caminho de decisao de trade.**
> Sinal, fusao, validacao, ranking, entrada e gestao de ordem sao **100% mecanicos e deterministicos.**

A IA existe **fora da malha** (off-loop): o owner abre um assistente (ex.: `claude.exe`),
aponta para as metricas que o sistema mecanico gerou, e pede analise/sugestao de ajuste.
O ajuste vira mudanca de **parametro em `config.yaml`** — nunca codigo que a IA decide em runtime.

```
DENTRO da malha (PROIBIDO):
    sinal -> [IA decide] -> ordem          nao-deterministico, nao-backtestavel, nao-replicavel

FORA da malha (CORRETO):
    sistema roda mecanico -> gera metricas -> owner abre claude.exe -> "avalie e proponha"
    -> owner ajusta config.yaml -> re-roda backtest                 deterministico, falsificavel
```

## POR QUE (nao e preferencia — e requisito)

1. **Falsificabilidade.** Uma chamada LLM nao replica bit-a-bit. Com IA na malha, o replay
   (Fase 6, gap 5) e **impossivel por construcao**: nao da para reproduzir a decisao passada,
   logo nao da para provar que um ajuste melhorou algo. Tirar a IA da malha e **pre-requisito
   do empirismo**, nao economia de custo.
2. **Atribuicao de PnL.** So decisao deterministica permite dizer "este parametro causou este
   resultado". LLM injeta variavel oculta nao-atribuivel.
3. **Custo e latencia.** Zero chamada por trade. Zero timeout de 3s no caminho critico.
4. **R-AI-LEMA.** "Automatize local sem IA. IA so para ajustar ferramentas." Off-loop e
   exatamente isso: a IA ajuda a **calibrar a ferramenta**, nao a **operar**.

## O QUE ISSO SIGNIFICA NO CODIGO (tarefas no ROADMAP)

| Onde | Estado hoje | Acao |
|------|-------------|------|
| `f3_validator.py` | `_call_deepseek()` + `_mechanical_fallback()` coexistem | promover fallback a unico; **apagar** DeepSeek |
| `utils/orc_ranking.py` | `_call_deepseek_ranking()` + `_fallback_ranking()` | idem — mecanico vira primario |
| `f4_executor/orc_ordens.py` | so comentario "≥75% + DeepSeek OK" (linha 11) | limpar comentario; codigo ja e mecanico |
| `contracts/fusion_output.py` | `sort_keys=True` era para **cache do LLM** | proposito removido (nao quebra; simplificar) |
| `config.yaml` | secao `ia:` (provider/model/timeout) | **remover a secao inteira** |
| `prompts/validator_system.txt` | system prompt do validador LLM | arquivar (R05) |

> **Nota de reuso (R-AI-REUSE):** remover a IA **nao constroi nada** — o caminho mecanico
> ja existe e ja roda hoje quando a DeepSeek da timeout. E promocao de fallback a primario,
> nao implementacao nova.

## PROIBICAO PERMANENTE (documentar a ausencia)

Esta secao existe para impedir que um agente futuro "reinstale" a IA achando que faltava:

- ❌ **NAO** adicionar chamada LLM em F1/F2/F3/F4/F5.
- ❌ **NAO** reintroduzir `provider`/`model`/`api_key` em `config.yaml` na secao de decisao.
- ❌ **NAO** criar "validador IA", "ranking IA", "spotter/sniper IA" (o VECTOR-ENGINE que fazia
  isso ja foi arquivado em `99_archive/ctrader_legado_v1/`).
- ✅ IA entra **apenas** como ferramenta externa off-loop operada pelo owner, sobre dados ja gerados.

Relacionado: [[ruse_alternatives]] (S25), [[strategy_3scalps_5markets]] (S5.1), `ROADMAP.md` Fase 4 + 4.5.
