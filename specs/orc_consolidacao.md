# SPEC S31 — Consolidacao Parquet (G23): merge + gap scan + gap fill

> **Versao:** 1.3.0 | **Wire:** gates/run_consolidate_parquet.py + f0_collector/backfill_orc_coleta.py (--gaps) + utils/backfill_supervisor_orc_dashboard.py | **Status:** active
> **R-USE:** storage_orc_coleta.py (append_rows, COLUMNS), mcp_client.get_trendbars (so via F0)
> **v1.2.0 (2026-07-30):** gap scan ANCORADO na janela 730d + guarda anti-lixo (ts<1999) + paginacao reversa medida (1000 barras/req)
> **v1.3.0 (2026-07-30):** merge le CONSOLIDADO existente (bug 5) + fechamento DIARIO por simbolo DAILY_CLOSE_UTC (bug 6) + anti-loop edge-bar + fallback S31-VBT (storage_orc_consolidated.py)

## Proposito

Responder: "o banco M_1 de 2 anos esta completo? Se nao, o que falta exatamente?"

Hoje existem 2 bancos OHLCV separados e nada os consolida:

```
data/backfill/{SYM}_M1.parquet   ← backfill historico (2 anos)
data/m1_{SYM}_{ANO}.parquet      ← F0 live (append a cada 60s)
```

Problemas sem consolidacao:
- Janela que falha no backfill retorna [] e vira LACUNA PERMANENTE
  (resume so continua a partir do ultimo timestamp).
- Leitores (S29/S30/VBT) nao sabem qual fonte e canonica.

## Pipeline

```
G23 (gates/run_consolidate_parquet.py) — SEM MCP (R-NO-MCP-BYPASS)
  1. MERGE: le data/backfill/{SYM}_M1.parquet + data/m1_{SYM}_*.parquet
  2. NORMALIZA timestamps → ms epoch (backfill=ms int, live=ISO string;
     NaT mascara p/ NaN e cai no dropna — antes virava int64-min e ficava)
  3. DEDUP por timestamp (preferencia: live > backfill), sort
  3b. GUARDA ANTI-LIXO: descarta linhas com ts < 1999-01-01 (epoch 0 de
      runs antigos) — SEMPRE com [WARN] e contagem (R-NO-SILENT-FAIL)
  4. SALVA canonico → data/consolidated/{SYM}_M1.parquet
  5. GAP SCAN ANCORADO (scan_gaps_anchored): janela alvo [now-730d .. now]
     - sem dados → a janela INTEIRA e lacuna
     - prefixo [window_start .. primeiro ts) e sufixo (ultimo ts .. now]
       tambem contam como lacuna (scan antigo so olhava ENTRE barras —
       banco vazio virava "sem lacunas" e o fill saia em 4ms sem baixar nada)
     - desconta fim de semana (sex ~21:00 UTC → dom ~21:00 UTC)
  6. GAP REPORT → status/gap_report.json + resumo no stdout
     Lacuna = > GAP_MIN_MINUTES (default 5) minutos ausentes em horario de mercado
     coverage_pct = 100 × (1 − total_missing / expected_open_minutes) — honesto,
     ancorado na janela (antes era span first→last / 730d)

FILL (f0_collector/backfill_orc_coleta.py --gaps) — UNICO que toca MCP
  7. Le status/gap_report.json
  8. Para cada lacuna, pagina PARA TRAS via _iter_pages():
     o servidor devolve as N barras MAIS RECENTES da janela [from,to] (S1.1),
     count max 1000 → cada pagina = ate 1000 barras M_1, span ~3000min
     (margem fds), cursor retrocede p/ (barra mais antiga − 1min);
     anti-loop: aborta se pagina nao retrocede ou 5 paginas vazias seguidas
  9. Append + dedup no consolidado; roda G23 de novo → converge
```

## Contrato do gap report (status/gap_report.json)

```json
{
  "generated_at": "2026-07-30T17:00:00+00:00",
  "gap_min_minutes": 5,
  "window_days": 730,
  "expected_open_minutes": 751680,
  "symbols": {
    "XAUUSD": {
      "rows": 700000,
      "first": "2024-07-29", "last": "2026-07-30",
      "coverage_days": 730.0, "coverage_pct": 93.3,
      "gaps": [{"start_ms": 1722000000000, "end_ms": 1722086400000, "missing_minutes": 1440}],
      "total_gaps": 1, "total_missing_minutes": 1440
    }
  }
}
```

`coverage_pct` e ancorado: 100 × (1 − total_missing_minutes / expected_open_minutes).
Banco vazio → 1 lacuna de ~750k min (a janela inteira) → coverage ~0%.

## Regras

- G23 NAO toca MCP — gate puro de dados (le parquet, escreve parquet/json)
- Fill so via f0_collector/ (R-NO-MCP-BYPASS)
- Fim de semana NUNCA conta como lacuna
- G23 e WARN (nao bloqueia boot) — igual G21/G22
- Saida ASCII puro (R-ASCII-OUT): [OK]/[WARN]/[ERR]

## Modos

```bash
python gates/run_consolidate_parquet.py           # merge + scan + report
python gates/run_consolidate_parquet.py --check   # so valida consolidado existente
python f0_collector/backfill_orc_coleta.py --gaps # preenche so as lacunas
```

## Confianca progressiva (trabalha com o que tem)

O vector NAO espera os 2 anos completos: S29/S30/score operam sobre qualquer
historico disponivel enquanto o fill avanca em background.

```
G23 reporta por simbolo: rows, coverage_days, coverage_pct (0-100 de 730d)
  ↓
pre-flight le quantas velas OHLCV existem → sabe o que falta
  ↓
backfill --gaps vai baixando so as lacunas (runs curtos e convergentes)
  ↓
orc_score: adjusted_confidence = combined x min(1, data_days/730)
  → indice de confianca SOBE conforme a cobertura aumenta
```

| coverage_pct | Significado |
|---|---|
| < 10% | Score exploratorio — so snapshot/recente |
| 10-50% | Score parcial — padroes de curto prazo confiaveis |
| 50-90% | Score robusto — sazonalidade anual coberta |
| > 90% | Score cheio — 2 anos, confianca maxima |

## Limitacoes

- Horario de mercado fixo (dom 21:00 → sex 21:00 UTC); feriados contam como lacuna
  (aceitavel: volume de feriado e baixo e o fill e barato)
- Rebuild de vbt_{SYM}.parquet a partir do consolidado: pendencia S31-VBT

## S31-PROG — Progresso wireado (2026-07-30)

O backfill publica progresso em tempo real; NENHUM consumidor toca MCP ou o
processo — todos leem artefatos em status/:

```
backfill_orc_coleta.py (gaps|full) — UNICO ponto MCP
  → status/backfill_progress.json  (a cada janela: pct, barras, ETA)
  → status/backfill.pid            (vida do processo)
      ↓ leitura barata
utils/backfill_supervisor_orc_dashboard.py (SAT de orc_dashboard)
  → /backfill/status|start|stop (router — proxy puro)
  → orc_metricas.backfill_metrics() → secao "backfill" no /metrics
  → orc_health_fases._s31_backfill() → check "fill em andamento" (S33)
  → BackfillCard.tsx — barras de progresso por simbolo + geral + botoes
```

### Contrato do progresso (status/backfill_progress.json)

| Campo | Tipo | Descricao |
|-------|------|-----------|
| state | running/done/error | estado do run atual/ultimo |
| mode | gaps/full | lacunas do gap_report ou 2 anos completos |
| current_symbol | str/null | mercado sendo baixado agora |
| symbols.{SYM} | dict | {windows_done, windows_total, bars, state} por mercado — "windows" = PAGINAS de ate 1000 barras (windows_total e ESTIMADO: ceil(missing_min/1000); done pode passar) |
| totals | dict | {windows_done, windows_total, bars, pct} agregado (pct capado em 100) |
| elapsed_s / eta_s | float | decorrido e estimativa (ETA = elapsed/done × restante, nunca negativo) |
| last_error | str/null | ultima falha por simbolo |
| started_at / updated_at | ISO | heartbeat do progresso |

## Contrato medido 2026-07-30 (4 bugs reais corrigidos)

Sessao de wire ao vivo (MCP online, primeiro fill real). Bugs que zeravam
o fill silenciosamente — todos cobertos pelos testes/gates existentes so
DEPOIS de medidos ao vivo:

1. **`_fetch_window` chamava `.get()` na LISTA** — mcp_client.get_trendbars
   ja devolve a lista de barras (S1.1); AttributeError era engolido pelo
   except e toda pagina retornava []. Backfill nunca baixou 1 barra.
2. **1 req por janela de 30d** — teto do servidor: count max 1000 (~16,7h
   de M_1) por req; janela de 30d tem ~30k barras → pegaria ~3% mesmo se
   (1) funcionasse. Corrigido com `_iter_pages()` (paginacao reversa).
3. **Gap scan nao ancorado** — so detectava lacunas ENTRE barras; banco
   vazio = "sem lacunas" → `--gaps` saia em 4ms com state=done. Corrigido
   com `scan_gaps_anchored()` (prefixo/sufixo/janela inteira).
4. **Linhas-lixo epoch 0** — consolidados stale com 1 linha ts=1970
   (artefato de run antigo) zeravam coverage e gap math. Corrigido com
   `_drop_garbage_ts()` (+ fix NaT em `_to_ms`).

Medido ao vivo pos-fix: ~1,35 paginas/s (~1,3k barras/s), XAUUSD 2 anos =
798 paginas / ~686k barras em ~10min; ETA visivel no dashboard desde a
primeira pagina.

## Contrato medido 2026-07-30 noite (bugs 5 e 6)

5. **G23 merge ignorava o consolidado existente** — o fill --gaps escreve
   DIRETO em data/consolidated/, mas o merge so lia backfill/ + live:
   re-consolidar APAGARIA o fill (quase destruiu 1,4M barras XAU/EUR).
   Fix: consolidado entra como fonte; dedup keep=last: live > consolidado
   > backfill.
6. **XAUUSD tem pausa DIARIA 21:00-22:00 UTC** (metais CME) — medido via
   MCP: 0 barras 21:00-21:59, reabre 22:00. O scan marcava ~521 "lacunas"
   de 60min/dia (~48k min fantasmas). Fix: DAILY_CLOSE_UTC por simbolo no
   _closed_ms_between (intervalos UNIDOS — sex 21-22h ja esta no
   fechamento semanal, sem uniao contava dobro). Cobertura XAU sai de
   93,6% para o valor real (~99%). EURUSD/GBP/USDJPY/AUDUSD: sem pausa
   diaria (FX 24h no broker).
   Fix complementar no fill: anti-loop do _iter_pages agora entrega a
   barra da borda (earliest==to) em vez de abortar (yield antes da
   guarda); veredito "0 barras novas" vira done (periodo sem pregao),
   nao erro.

## S31-VBT — Fallback do Vector ao consolidado (2026-07-30 noite)

O vbt_{SYM}.parquet so acumula snapshots do F0 vivo (~1 dia). Com o
consolidado de 2 anos pronto, o Vector (quality/patterns/score/history)
passa a ler via SAT utils/storage_orc_consolidated.py:
- computa os MESMOS indicadores (R-USE f1_analyzer.indicators_orc_analise)
  sobre o consolidado — RSI/MACD/BB/ATR/ADX/OBV identicos ao vivo;
- quem cobre mais span vence (consolidado 730d > vbt ~1d);
- cache em-processo TTL 300s + mtime (indicadores 2 anos ~1s/computacao);
- history_days REAL alimenta analysis_days → coverage do orc_score sai de
  0% para o coverage real do G23.
Pendencia documentada: scan de padroes em profundidade total (2 anos M_1
= 750k janelas) — O(n×20) exige redesign S29/S30 (multi-TF: M1 recente +
M15/H1 longo alcance).

### Regras S31-PROG

- Supervisor NUNCA fala MCP (R-NO-MCP-BYPASS) — so spawna processo e le status/
- Dashboard mostra estado honesto: "nunca rodou" != "rodando" != "concluido"
- Botao "Disparar" chama /backfill/start (mode=gaps default); stop termina via psutil
- Progresso sobrevive a restart da API (subprocesso independente, CREATE_NO_WINDOW)


---

## G23 v2.0 — Fixes (2026-08-07)

### ts_window filter
`scan_gaps_anchored` agora filtra `ts_sorted` para so incluir timestamps dentro
da janela `[window_start_ms, now_ms]`. Antes escaneava TODOS os timestamps do
consolidado (2 anos), gerando falsos positivos de gaps fora da janela.

### --auto_backfill fresh scan
Quando `--auto_backfill` esta ativo, `prev_report` e sempre None → fresh scan
garantido. O cache so e usado em modo `--check --fast` sem auto_backfill.

### TimeoutExpired catch
O `subprocess.run` com `timeout=1800` agora captura `TimeoutExpired` e invalida
o cache (`report_path.unlink()`). Antes a excecao propagava sem limpar o cache,
causando scans stale no proximo boot.

### Wire point
`Abrir_NeoCortex_NovaPulse.ps1` L184:
```
& $VENV_PY "$CTRADER\\gates\
un_consolidate_parquet.py" '--check' '--auto_backfill'
```

---

## G23 v2.1 — Gap Filter Hardening (2026-08-09)

### RCA: 3 bugs causando loop scan→backfill→scan eterno

**Bug #1 — `total_gaps` desatualizado:** `_update_gap_report_incremental()` remove gaps
da lista `gaps` e atualiza `gaps_count`, mas NUNCA recalcula `total_gaps`. O campo fica
stale (ex: XAUUSD `total_gaps=156` com apenas 6 gaps reais restantes).

**Bug #2 — `DAILY_CLOSE_UTC` incompleto:** Apenas XAUUSD tinha entrada `(21, 22)`.
EURUSD, GBPUSD, USDJPY, AUDUSD tem pausa de rollover diaria as 21:00-21:09 UTC,
gerando ~220 gaps fantasmas cada. O filtro `_is_weekend_or_daily_close` com threshold
80% nao captura gaps de 9 min em janela de 1h (sobreposicao ~15%).

**Bug #3 — Ciclo infinito:** `--auto_backfill` deletava `gap_report.json` apos backfill
(`report_path.unlink()`), forcando fresh scan no proximo boot que reencontrava os
mesmos gaps fantasmas → backfill → unlink → loop eterno.

### Correcoes

| # | O que | Onde |
|---|-------|------|
| C1 | `DAILY_CLOSE_UTC` expandido: +EURUSD, GBPUSD, USDJPY, AUDUSD `(21, 22)`, +DXYUSD `(21, 23)` | `run_consolidate_parquet.py` |
| C2 | `_update_gap_report_incremental()` recalcula `total_gaps = len(new_gaps)` | `backfill_orc_coleta.py` |
| C3 | Pos-backfill: re-scan em vez de `unlink()`. Se gaps estaveis → mantem cache | `run_consolidate_parquet.py` |

### Metrica de convergencia

```
Antes: XAUUSD 156 gaps → backfill → unlink → fresh scan → 156 gaps (loop)
Depois: XAUUSD 156 gaps → backfill → re-scan → <10 gaps (feriados residuais)
        EUR/GBP/JPY/AUD <5 gaps cada
        DXYUSD/VIXUSD cobertura <100% aceito (indices de pregao parcial)
```
