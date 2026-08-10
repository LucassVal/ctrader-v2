> **STATUS: CONSOLIDADO_EM `orc_fusao.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S4: SPEC S4: FASE 2 — FUSAO (MECANICA)
>**Versao:** 1.0.0  
>**Wire:** `f2_fusion.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


## RECEBE / ENTREGA
- **Recebe:** `scores_raw.json` (F1) + `custom_rules.json` (F5, pesos calibrados)
- **Entrega:** `fusion_output.json` — score normalizado + redutores + threshold

## CRM
Funde os componentes v1 (BBANDS %B/bandwidth, ATR, ADX + globais) em **um** score,
compara com o threshold. Regra de decisao pura, sem LLM.

## PROCESSAMENTO (deterministico)
1. Carrega `scores_raw.json` (F1)
2. Carrega pesos de `custom_rules.json` (F5) — pesos calibrados pelo MAR; default enquanto nao houver historico
3. Score = Σ(componente × peso). **Pesos somam 1.0** (harness trava isso)
4. Aplica redutores (regra fixa): news, spread/ATR alto, sessao Sydney, rollover (REJECT)
5. **Correlacao entra aqui como redutor MENOR** (nunca gatilho — ver S5.1)
6. Grava `fusion_output.json`

> ⚠️ **PENDENTE DE DECISAO (Fase 4.5):** os componentes exatos, seus pesos e a fusao
> so serao fixados apos a exploracao dos 2 anos. O desenho antigo (pilares macro/vol/tecnico
> 33/33/34) esta **superado** — nao usar. Ver ROADMAP 4.5.4.

## NORMALIZACAO ENTRE ATIVOS
Score em **percentil/z-score** sobre a historia do proprio ativo — nunca valor bruto.
Bruto enviesa o ranking para o ativo mais volatil (o ouro venceria sempre). Ver S5.1.

## INTERFACE
- Entrada: `scores_raw.json` + `custom_rules.json`
- Saida: `fusion_output.json`
- **Determinismo:** mesma entrada -> mesmo output (removido `sort_keys` p/ cache-LLM; S26)

## DEPENDENCIAS
- `utils/schema_validator.py` — valida fusion_output
- `utils/session_manager.py` — detecta Sydney/rollover
- `f1_analyzer/micro_orc_analise.py` — matriz de correlacao (redutor)

## FLUXO OBRIGATORIO DE IMPLEMENTACAO

1. **Entrada:** `scores_raw.json` da F1 + `fusion_output.json` (contrato imutavel)
2. **Processamento:** Media ponderada: macro×30% + vol×25% + tec×25% + spread×10% + sentiment×10% → score final 0-100. Correlation matrix (F1 pass-through) usada como redutor de concentracao: se 2 ativos tem corr >0.8, o de menor score perde 15%.
3. **Saida:** `fusion_output.json` com `final_score`, `confidence`, `breakdown` por pilar, `correlation_flag`
4. **Validacao:** G6: `test_f2_fusion.py` — JSON schema validation, `final_score ∈ [0,100]`, `sum(pesos) == 1.0`
5. **Wire:** `f2_fusion.py` → `f3_validator.py` (via fusion_output.json)

