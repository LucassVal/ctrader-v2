# SPEC S5.1 | ESTRATÉGIA — 3 SCALPS × 5 MERCADOS
>**Versao:** 1.0.0  
>**Wire:** `f3_validator.py → orc_ranking.py`  
>**Status:** DONE  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


---

## OS TIPOS DE SCALP

> ⚠️ **REVISADO 2026-07-23 — escopo agora são 2 scalps, não 3.**
> **`M_10` NÃO EXISTE no MCP.** O enum real do servidor é
> `M_1 · M_5 · M_15 · M_30 · H_1 · H_4 · D_1 · W_1 · MN_1`.
> A "S2 M10" descrita abaixo **nunca rodou em M10**: `_timeframe_to_period()` tinha um
> `FALLBACK = {"M10": "M_15", ...}` que a convertia em M_15 silenciosamente.
> Esse fallback foi **removido** (R51 FAIL-FAST) — hoje timeframe inválido levanta `MCPError`.

### Escopo vigente (2 scalps)

| # | Nome | Holding | Slots/dia | Timeout | Barras M_1 de gestão | Perfil |
|---|------|:-------:|:---------:|:-------:|:---:|--------|
| S1 | **Scalp Rápido** | 5 min | 30 | **5 min** | **5** | Rompimento. Não rompeu → morto. |
| S2 | **Tendência** | 15 min | 30 | **15 min** | **15** | Respiração. Bollinger %B como confirmação. |

**Total:** 60 trades/dia (2 × 30 slots), 5 mercados.

> **Timeout = duração do scalp.** Objetivo é girar a fila rápido e liberar slot para
> entrada melhor, não deixar trade maturando. Valores antigos (10/20 min) descontinuados.

### RELÓGIO ÚNICO: M_1

**Tudo roda em M_1** — pré-análise, entrada e gestão de ordem. "5 e 15 min" são
**horizonte de holding**, não timeframe de indicador. Isso resolve a incoerência do desenho
anterior, em que um scalp de M_15 com timeout de 20 min morria em 1,33 barra do próprio
timeframe: agora o de 5 min tem **5 barras** de gestão e o de 15 min tem **15**.

Consequência: trail, BE e degraus D40/D60/D80 rodam em M_1, independentemente da estratégia.

**Coleta:** apenas **M_1** (2 anos). Agregados M_5/M_15 só por `pandas.resample()` se algum
indicador exigir — o relógio de decisão permanece M_1. Ver `ROADMAP.md` itens 1.3 e 1.3b.

⚠️ **`m10` ainda está vivo em 6 arquivos de código** (`fusion_output.py`, `dashboard.py`,
`f3_validator.py`, `orc_execucao.py`, `schema_validator.py`, `slot_tracker.py`) e altera a
alocação de slots de 90 → 60/dia. Expurgo = item **5.0** do ROADMAP, particionado por módulo.

### Histórico legado (S3 M15 / S2 M10 — não usar)

O desenho original previa 3 scalps (M5/M10/M15). Com M_10 inexistente, S2 e S3 colapsam
no mesmo timeframe real (M_15). Mantido aqui só como registro da decisão.

---

## OS 5 MERCADOS

| # | Ativo | Tipo | Correlação |
|---|-------|------|------------|
| 1 | **XAUUSD** | Ouro (commodity) | Primário. Correlação inversa com DXY. |
| 2 | **EURUSD** | Forex Major | DXY proxy (57.6% do índice). |
| 3 | **GBPUSD** | Forex Major | Correlacionado com EURUSD (~0.7). |
| 4 | **USDJPY** | Forex Major | Correlação inversa com yields US. |
| 5 | **AUDUSD** | Forex Commodity | Correlacionado com ouro e commodities. |

**DXY sintético:** EURUSD inverso (maior peso no DXY).

---

## JSON PADRÃO (só muda deltas)

Cada entrada gera um JSON idêntico em estrutura. Só mudam:
- `trace_id` (timestamp único)
- `symbol` (1 de 5)
- `timeframe` (M5/M10/M15)
- Scores dos 3 pilares (calculados pela F1)
- `verdict` (APPROVE/REJECT — da F3)

```json
{
  "trace_id": "T20260723-143000-001",
  "symbol": "XAUUSD",
  "timeframe": "M15",
  "slot_used": 12,
  "slot_max": 30,
  "scores": {
    "macro": 72.5,
    "volatilidade": 68.3,
    "tecnico": 81.2,
    "final_adjusted": 74.0,
    "threshold": 70
  },
  "verdict": {
    "decision": "APPROVE",
    "adjustments": {"timeout_min": 18, "lot_multiplier": 1.0},
    "reason": "TENDENCIA_CLARA",
    "source": "deepseek_pro"
  }
}
```

---

## REGRA DE TOKEN (DeepSeek)

- **System prompt:** fixo em arquivo, cache hit > 90%
- **User prompt:** JSON serializado com `sort_keys=True` → mesmo prompt para mesmo estado
- **Saída esperada:** 50-80 tokens (só o verdict + ajustes)
- **Custo por chamada:** ~$0.00002 com cache hit
- **Custo diário (90 trades):** ~$0.0018
- **Custo mensal:** ~$0.05
