> **STATUS: CONSOLIDADO_EM `orc_validacao.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S5: SPEC S5: FASE 3 — VALIDACAO (MECANICA)
>**Versao:** 1.0.0  
>**Wire:** `f3_validator.py → orc_ranking.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


## RECEBE / ENTREGA
- **Recebe:** `fusion_output.json` (F2)
- **Entrega:** `verdict.json` — `APPROVE` (com ajustes) ou `REJECT` (com motivo)

## CRM
Decisao de entrada **100% mecanica e deterministica**. Sem LLM no caminho (S26).

## PROCESSAMENTO (deterministico)
1. Le `fusion_output.json`
2. Se `final_adjusted < threshold`: **REJECT** automatico
3. Se `final_adjusted >= threshold`: **APPROVE**, com ajustes mecanicos por regra fixa:
   - `lot_multiplier` por faixa de score
   - `timeout_min` = duracao do scalp: **S1=5, S2=15** (relogio M_1 — ver S5.1)
4. `_apply_hard_cap()`: trava mecanica final sobre o veredito
5. Valida com `schema_validator.validate_verdict()`

> ⚠️ O `_mechanical_fallback()` de hoje **ja e** este processamento. Remover a IA
> (ROADMAP 4.1) e promover esse fallback a caminho unico — nao e codigo novo (R-AI-REUSE).

## INTERFACE
- Entrada: `fusion_output.json`
- Saida: `verdict.json`
- **Sem `DEEPSEEK_API_KEY`.** A secao `ia:` do `config.yaml` sai (S26).

## DETERMINISMO (substitui a antiga secao CACHE)
Mesma entrada -> mesmo veredito, sempre. E o que torna o replay da Fase 6 possivel:
sem determinismo aqui nao ha `previsto x realizado` (gap 5).

## HP
`test_f3_fallback.py`: APPROVE para score alto, REJECT para baixo, hard cap. ✅ PASS
(apos remocao da IA, renomear conceito de "fallback" para "caminho unico").

## DIVIDA
- ✅ `TIMEOUT_MAX`/`TIMEOUT_FALLBACK`: `m10` expurgado (2026-07-23). Valores corrigidos: M_5=5min, M_15=15min. Timeout = duracao do scalp (S5.1).

## FLUXO OBRIGATORIO DE IMPLEMENTACAO

1. **Entrada:** `fusion_output.json` da F2 + MCP `get_balance` (risk check) + DeepSeek Pro API (last mile, opcional)
2. **Processamento:** Gate validation: `final_score >= 85` → prossegue. DeepSeek rank (se score >=78): ordena 5 ativos por potencial. Fallback: ranking mecanico por score.
3. **Saida:** `ranking.json` com `[{symbol, score, confidence, reason}]` ordenado + `risk_ok: bool`
4. **Validacao:** G6: `test_f3_fallback.py` — verifica fallback mecanico funciona com DeepSeek offline
5. **Wire:** `f3_validator.py` + `orc_ranking.py` → `f4_executor/orc_execucao.py` (via ranking.json)

