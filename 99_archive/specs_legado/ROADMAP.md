# ROADMAP — cTrader V2 | SPEC S0

> **Versao:** 5.1 | **Wire:** specs/ROADMAP.md → specs/INDEX.md → G11 | **Status:** active
> **Atualizado:** 2026-07-31

## CONCLUIDO (sessao 2026-07-31 — Strategy & Macro Aggressive UX Revamp)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-31 | UI React: StrategyTab 100% reescrito — Radar multidimensional (Momentum, Força, Volatilidade, Tendência, Score) mapeado via /vector/symbol/{sym}, layout coeso R-USE. | S28 |
| 2026-07-31 | UI React: GlobalsView + CorrelationView expandidos — Alertas textuais baseados no DXY/VIX (Risk-on/off, direcao USD), Alerta de redundância direcional na matriz de correlação. | S28 / S35 |
| 2026-07-31 | S35 IMPLEMENTADA: orc_ranking v2 agora aplica penalidade severa (-10 pts) para trades na mesma direção de pares correlacionados (>0.70) usando janela de 1440m; aplica bônus (+5) se DXY proxy (EURUSD) confirmar direção. | S35 |
| 2026-07-31 | S38 IMPLEMENTADA: Paper F4 (simulador) wireado! orc_execucao e entry_orc_execucao rodam offline 100% desconectados do MCP, monitorando trades simulados via spot prices (get_spot_prices) e guardando no trades.db. | S38 |
| 2026-07-31 | UI React: CtraderTab.tsx e StrategyTab.tsx (Aba Ordens/Trail Log e Estratégia) marcados explicitamente com selos **PAPER TRADING (Simulação Real S38)** provando R21. | S38 |
| 2026-07-31 | Finalização do checkpoint de Harness/Gates (sem quebras de dependência, DDD mantido). | S0 |

## CONCLUIDO (sessao 2026-07-30 — noite 7: S39 Vista de Mercado + 3 bugs R21 de medicao)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | S39 IMPLEMENTADA: vista_orc_mercado + matrix_orc_vista (regime MTF por resample M1 — pesquisa vectorbt MTF, zero lookahead) + correlacao multi-janela (200b/1d/1sem, achado S35) + calibracao por simbolo + padroes top; wire /vector/symbol/{sym}.vista + MarketTab reescrito com interpretacao (zonas RSI/ADX, concordancia MTF) | S39 v1.0 |
| 2026-07-30 | Fix 16/16: families_orc_vectorbt (10 familias na cauda, R-USE helpers S28) via consolidated_indicator_points(full_families) — health de fases sai de 5/16 para 16/16 nos 5 mercados | S39 |
| 2026-07-30 | BUG R21 unidades: closes brutos cTrader sem price_divisor → pips 100.000x inflados; fix pip_raw em orc_scan + reconcile; re-scan 5/5 | S34 |
| 2026-07-30 | BUG R21 spread assimetrico: BEARISH nao pagava spread (hit inflado 60,9%); fix pips assinados por direcao; VERDADE MEDIDA: hit_5m 35,6%/15m 41,2%/60m 46,1% — regras atuais NAO vencem spread nos curtos | S34 |
| 2026-07-30 | BUG R21 ADX NaN (0/0 em barra flat) envenenava ultima barra; fix DX=0 sem DM | S39 |
| 2026-07-30 | Harness: 98 PASS · gates G7/G8/G11/G12/G16/G19/mockbuster PASS · 3 splits G12 (matrix_orc_quality, families_orc_vectorbt, matrix_orc_vista) | S0 |

## CONCLUIDO (sessao 2026-07-30 — noite 6: S34 v1.2 MEDIDA — hipotese quality REFUTADA)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | S34 v1.2: score replay composto (S32 parity) — quality trailing S29 em matrix_orc_quality (SAT novo, split G12), purge+replace do replay no re-scan (dedup keep=first manteria velhos), linha ganha quality_f1+coverage | S34 v1.2 |
| 2026-07-30 | Re-scan 730d x5 + reconcile MEDIDOS: REFUTADO — 99,97% dos sinais na faixa 0-50, hit_15m 51,4% (era 52,7%), Brier 0,271 (era 0,249), drift inalterado (~0,3 ponto); topo 70-85 (72,1%) desapareceu | S34 v1.2 |
| 2026-07-30 | Achado R21: pesos 0,33/0,67 do S32 sao chute nunca calibrado — proximo fio v1.3: mapa score→P(acerto) EMPIRICO (logistica/isotonica nos dados replay), corte de entrada sai da curva | S34 v1.3 |
| 2026-07-30 | Harness: 98 PASS (+5: trailing_quality ganhos/perdidos/zero-lookahead/amostra-min + purge); gates G7/G8/G11/G12/G16/G19 PASS; matrix_orc_scan 182L + matrix_orc_quality 57L | S0 |

## CONCLUIDO (sessao 2026-07-30 — noite 5: wire React S36 + emissor periodico no F0)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | Wire React S36: sub-aba "Score & Calibracao" em Pre-Analise — ScoreLiveCard (5 mercados: sinal/score/quality_f1/pattern_conf/coverage) + CalibrationCard (hit-rate por faixa com n, Brier 5/15/60, drift semanal); offline honesto (A7) com motivo real | S36 + S20 v2.2 |
| 2026-07-30 | Emissor S36 PERIODICO: F0 chama emit_once() a cada barra M1 fechada (branch CANDLE_INTERVAL do orc_coleta.run); falha nunca quebra o ciclo (padrao take_snapshot/S27); CLI --once mantido p/ manual | S36 v1.2 |
| 2026-07-30 | Bug React corrigido: StrategyTab lia data.matrix, API expoe data.correlation_matrix — heatmap de correlacao vivia em "Dados insuficientes" | S35 |
| 2026-07-30 | Validacao: oxlint 0 erros (CtraderTab + StrategyTab), tsc --noEmit limpo, gate G16 PASS | S0 |

## CONCLUIDO (sessao 2026-07-30 — noite 4: S34+S36 IMPLEMENTADAS + REGRA-MET wireada)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | S34 IMPLEMENTADA: orc_scan (ORQ CLI) + matrix_orc_scan (SAT) — cosine BLAS em chunks, outcomes 5/15/60 liquidos de spread, decay por recencia, sessao rollover excluida, min 30 amostras | S34 v1.1 |
| 2026-07-30 | Achado R21 (medido): media de janela 20b REJEITADA (593k matches/prototipo = zero discriminacao) — engine final: vetor por barra + thr 0.999 (~6,5k mediana) | S34 v1.1 |
| 2026-07-30 | Scan real 730d x5: ~150s/simbolo, 50 padroes/simbolo, 9.950 sinais replay → signals_log.parquet | S34 + S36 |
| 2026-07-30 | S36 IMPLEMENTADA: orc_calibracao (append dedup/reconcile/calibration.json) + signal_emitter_orc_score (score_live.json + anti-flood); reconcile validado (searchsorted right, off-by-one corrigido) | S36 v1.1 |
| 2026-07-30 | REGRA-MET wireada: secoes score_mercados + calibration em orc_metricas.collect_all + repassadas no export_for_dashboard (allowlist de chaves droppava as novas) | S20 v2.2 |
| 2026-07-30 | 1a calibracao real: hit_15m 52,8% (faixa 50-70, n=9.903) · 72,1% (70-85, n=43) · Brier ~0,25 = score replay AINDA NAO DISCRIMINA — proximo fio: componente quality no replay | S36 |
| 2026-07-30 | Harness: test_orc_scan (5) + test_orc_calibracao (4) + test_signal_emitter (3); suite 93 PASS; gates G7/G8/G11-14/G16/G19 PASS; G12 split DDD (orc_scan 232L ORQ + matrix 174L SAT) | S0 |

## CONCLUIDO (sessao 2026-07-30 — noite 3: fill completo + trilha S34-S38 especificada)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | Fill 2 anos COMPLETO: XAU 704.888 barras (96,6%) · EUR 739.286 (98,5%) · GBP 738.197 (98,4%) · JPY 739.552 (98,5%) · AUD 735.199 (98,4%) — restante = feriados/pausas reais modelados no G23 (DAILY_CLOSE_UTC) | S31 |
| 2026-07-30 | Pesquisa R21 correlacoes reais dos 5 mercados (web: Investopedia/Mataf/TradingNX): EURxGBP +0.80/+0.95, XAUxDXY -0.6/-0.8, XAUxJPY regime-sensivel — janela unica M1/200 INSUFICIENTE → janelas 200/1d/1sem | S35 |
| 2026-07-30 | Decisao do dono: M1 = TF cientifico unico (empirismo, scan, calibracao); M5/M15/H1 = graficos COM ciencia (regime H1 + concordancia multi-TF modulando o score) | S34 |
| 2026-07-30 | Trilha sinais→entradas especificada (debate aprovado): S34 Pattern Engine M1-puro · S35 Ranking v2 (correlacao como filtro) · S36 Calibracao (signals_log + reconciliador) · S37 Estrategia (impl S28) · S38 paper F4 | S34-S38 |
| 2026-07-30 | Schema signals_log.parquet aprovado pelo dono (data/): ts/symbol/strategy_id/sinal/score/coverage/close_entrada + outcomes 5/15/60 M1 | S36 |

## CONCLUIDO (sessao 2026-07-30 — noite 2: wire Vector↔consolidado + bugs 5/6)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | Bug 5: G23 merge ignorava consolidado existente — re-consolidar apagaria o fill (quase 1,4M barras); fix: consolidado como fonte, dedup live>consolidado>backfill | S31 v1.3.0 |
| 2026-07-30 | Bug 6: XAUUSD pausa diaria 21-22h UTC (medido MCP) gerava 521 lacunas fantasmas; fix: DAILY_CLOSE_UTC no G23 com uniao de intervalos + anti-loop edge-bar no _iter_pages + veredito "sem pregao"=done | S31 v1.3.0 |
| 2026-07-30 | S31-VBT: SAT storage_orc_consolidated.py — Vector (quality/patterns/score/history) le 730d REAIS do consolidado com indicadores identicos ao vivo (cache TTL 300s); score coverage sai de 0% p/ real | S31 + S27 |
| 2026-07-30 | /vector/globals: correlations wireado da mesma engine do /vector/correlation (era {} estrutural); ranking le fusion_output de status/ (era so raiz) | S25.10 |
| 2026-07-30 | Fill 2a onda: XAU 703k + EUR 738k salvos; GBP 736k, JPY/AUD em curso (restart matou GBP em memoria — escrita so ao fim do simbolo) | S31 |
| 2026-07-30 | Gates G7/G8/G10/G11-14/G16 + 81 testes PASS com 61 .py (novo SAT indexado + allowlist orbital justificada) | S0 |

## CONCLUIDO (sessao 2026-07-30 — noite: boot seguro + wire real do backfill)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | .bat/.ps1 PRE-BOOT seguro: nao mata mais TODOS os node (derrubava o Kimi IDE) nem dono de porta/cmdline sem checar — so processos do projeto (Test-NCProcess por path $NC_ROOT; externo = WARN, nunca kill) | S0 |
| 2026-07-30 | S31 FIX ao vivo (4 bugs que zeravam o fill): _fetch_window .get() em lista; 1 req/30d vs teto 1000 barras → _iter_pages() paginacao reversa; gap scan nao ancorado → scan_gaps_anchored (prefixo/sufixo/janela); linhas-lixo epoch 0 → _drop_garbage_ts + fix NaT | S31 v1.2.0 |
| 2026-07-30 | S31 MEDIDO: ~1,35 paginas/s (~1,3k barras/s); XAUUSD 2 anos = 798 paginas / ~686k barras em ~10min; coverage honesto ancorado (100×(1−missing/expected)) | S31 |
| 2026-07-30 | BackfillCard: badge MCP online/offline + "dados fluindo há Xs" (progress_age_s) + ETA h/min + "páginas" (era "janelas") | S31 |
| 2026-07-30 | router /market/risk: dxy_score wireado de orc_indices (era hardcoded 50.0 — flag G0 F841) | S25.10 |
| 2026-07-30 | Gates: G0/G1/G3/G6/G7/G8/G10/G16/G17/G18 PASS; G2 FAIL pre-existente — f0_collector/orc_coleta.py INFLATED (104+ linhas nao commitadas de sessao anterior, fora do escopo de hoje) | S0 |

## CONCLUIDO (sessao 2026-07-30 — S31-PROG: backfill wireado + revamp Overview)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | S31-PROG: backfill publica progresso (status/backfill_progress.json + .pid) — pct, barras, ETA por janela | S31 |
| 2026-07-30 | S31-PROG: backfill_supervisor_orc_dashboard (SAT) + endpoints /backfill/status\|start\|stop (proxy puro, nunca MCP) | S31 |
| 2026-07-30 | S31-PROG: wireado em orc_metricas (secao backfill no /metrics) + S33 (check "fill em andamento" com ETA) | S31 + S33 |
| 2026-07-30 | React: BackfillCard — barras de progresso por simbolo + geral, ETA, coverage, botoes Disparar/Parar | S31 |
| 2026-07-30 | React: REVAMP ov-health — card "Orquestradores (Fases)" velho (f0/f4/f5 processo-vivo) → grade S33 (mecanica por etapa) | S33 |
| 2026-07-30 | Harness S31-PROG: tests/test_backfill_progress.py (5 testes, G19-safe) | S31 |

## CONCLUIDO (sessao 2026-07-30 — tarde: revisao avaliacao mestra R21)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | run.py: F1-F3 apontavam p/ scripts MORTOS (f1_analyzer.py etc. inexistentes) → modulos reais -m f1_analyzer.orc_analise/f2_fusao.orc_fusao/f3_validacao.orc_validacao; streamlit legado fora | S0 |
| 2026-07-30 | gates.sh: wire G21+G22+G23 (suite agora G0-G23) — pendencia "bug de escape" resolvida | S0 |
| 2026-07-30 | Expurgo SSOT: audits S22/S23/S24 sem ID proprio (ref S0), S5.1 registrado no INDEX, vectorbt_ecosystem S17:S12→S18 | S0 |
| 2026-07-30 | avaliacao_mestre.md v2.0: revisada fato a fato (6 correcoes) + ampliada S27-S33, estado ao vivo, plano cirurgico | S0 |

## CONCLUIDO (sessao 2026-07-30)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-30 | S33 orc_health_fases: validador por fase sempre ativo — sub-aba "Saude" item 1 das 5 abas mestras + overview fases x harness | S33 |
| 2026-07-30 | S33 fix: timestamp M1 em ms (check f0) + f4 honesto (tabela trades ausente, sem fallback de zeros) | S33 |
| 2026-07-30 | G16: sub-aba "saude" mapeada → /health/fases | S0 |
| 2026-07-30 | Harness S33: tests/test_health_fases.py (5 testes, read-only G19) | S33 |
| 2026-07-30 | Auditoria gates: conformance G11-G14 FAIL→PASS — headers G11 (orc_pattern/quality/storage_vbt), mapa S2.5/S25.10 no INDEX, G14 ASCII backfill, ROADMAP SPEC S0 | S0 |
| 2026-07-30 | G12 split DDD: orc_vectorbt 456L→284L — helpers numpy p/ indicators_orc_vectorbt.py (satelite) | S25 |
| 2026-07-30 | G7 PASS: allowlist backfill CLI + storage_orc_vbt (naming debt) + utils→f1_analyzer justificado (S25.10) | S0 |
| 2026-07-30 | G8 PASS: orc_pattern/quality/storage_vbt indexados + allowlist backfill CLI/HANDOFF | S0 |
| 2026-07-30 | G21 PASS: fix numpy.int64→ns (ultima vela "56 anos") + tz naive/aware; removida linha-semente ts=0 dos 5 m1 parquets | S0 |
| 2026-07-30 | /health/fases AO VIVO na :7744 (7/9 fases OK — f4 sem trades ainda, s31 fill pendente: honesto) | S33 |

## CONCLUIDO (sessao 2026-07-29)

| Quando | O que | Spec |
|--------|-------|------|
| 2026-07-29 | S2.5 v2.1: fix persist M_1 (assinatura append_rows) + VBT sobre histórico 200 velas | S2.5 |
| 2026-07-29 | S2.5 warmup: 200 velas M_1/símbolo no boot — VBT sai no 1º ciclo | S2.5 |
| 2026-07-29 | S27 fix: STOCH percent_k/percent_d (vbt 1.1.0) — compute_indicators 100% erro antes | S27 |
| 2026-07-29 | S25.10: correlação 5×5 real via m1 parquet (orc_indices.correlate_markets_m1) | S25 |
| 2026-07-29 | G16 fix: wildcards {param} + mapa strategy stale (falha pré-existente no HEAD) | S0 |
| 2026-07-29 | S31 Consolidação Parquet: G23 merge backfill+m1, gap scan, gap fill | S31 |
| 2026-07-29 | S20 v2.1: vector_mercados no /metrics — overview por mercado (indicadores considerados, coverage, bars) | S20 |
| 2026-07-29 | S31-CONF: confiança progressiva — coverage no G23 + adjusted_confidence no score | S31 + S32 |
| 2026-07-29 | BOOT: sequência 9→6 passos (Frieren :5174, Elysian :5175, Benchmark :8989 removidos) | S0 |
| 2026-07-29 | S32 orc_score: score combinado sai do router → orquestrador | S32 |
| 2026-07-29 | S30-PIPS: fix pip size XAUUSD ($0.10) via PIP_SPECS.pip_size | S30 |
| 2026-07-29 | S30 Pattern Matcher: cosine similarity + combined S29+S30 score | S30 |
| 2026-07-29 | S29 Signal quality: walk-forward backtest + F1/precision/recall | S29 |
| 2026-07-29 | S28 Market Tabs: 5 abas por mercado (XAUUSD..AUDUSD) | S28 |
| 2026-07-29 | VBT Parquet persistence: save/load/history | S2.5 + S27 |
| 2026-07-29 | /vector/symbol/{sym} + /history/{days} | S28 |
| 2026-07-29 | G16+G22 fixed: dedup keys, VBT Parquet, TF consolidation | S0 |
| 2026-07-29 | 17 indicadores Vector BT (Donchian, HMA, Keltner, CCI, PSAR...) | S25 F2 |
| 2026-07-29 | S2.5 Banco M_1 persistente (Parquet append no F0) | S2.5 |
| 2026-07-29 | G21 Preflight Parquet + G22 Preflight Dependencies | S0 |
| 2026-07-29 | Limpeza F1: ichimoku, volume, news → 99_archive | S0 |
| 2026-07-29 | Harness 16/16 ORQs | S0 |
| 2026-07-29 | yfinance removido: DXY sintetico + sentiment via F1 | S25.10 |

---

## PENDENCIAS

### 🔴 Bloqueadores

| # | O que | Arquivo | Bloqueio |
|---|-------|---------|----------|
| S28-G3 | Precisão YoY (barras win/loss por mes) | `StrategyTab.tsx` | trades.db populado (F4 executor) — S38 |
| S28-G5 | Sinais × Resultados (scatter score×PnL) | `StrategyTab.tsx` | trades.db + scores F1 — S36 parcial, S38 full |
| RUN-BOOT | Validar boot central run.py F0-F5 engatando (apos fix scripts mortos) | `run.py` | Rodar e observar heartbeats |
| S25-F2 | Wire /performance com dados reais | `routers/ctrader_v2.py` | trades.db populado — S38 |
| FUS-STUB | fusion_output.json e stub {fusion_score:85} — F1→F2 nunca rodou real | `f2_fusao/orc_fusao.py` | wirear pipeline F1→F2→F3 (pre-S38) |
| RESTART | Score coverage G23 (orc_score editado) so vale apos restart da API | via .bat | dono reinicia |

### 🧭 Trilha sinais→entradas (aprovada pelo dono 2026-07-30 — spec-first R-SDD, implementar depois)

| # | O que | Spec | Depende de |
|---|-------|------|-----------|
| **S34** | Pattern Engine M1-puro: vetorizar extract_windows (sliding_window_view), scan batch offline 730d → pattern_library.json, densidade empirica de padrao, param sweep VectorBT (Sharpe por simbolo), ciencia multi-TF (regime H1 + concordancia) | orc_pattern_engine.md | S31 (feito) |
| **S35** | Ranking v2: janelas de correlacao 200/1d/1sem rolling, penalidade sobre-exposicao (-10 pts, corr>0.70 mesma direcao), confluencia +5 pts, wire sub-abas de mercado | orc_ranking.md v3.0 | S34 |
| **S20-WIRE** | REGRA-MET: tudo que o dashboard exibe passa por orc_metricas — secoes score_mercados (le status/score_live.json) + calibration (le status/calibration.json) no /metrics; React consome /metrics; /vector/*/score vira drill-down | orc_metricas.md v2.2 | S36 (artefatos) |
| **S36** | Calibracao v1.1: MODO PASSADO (replay walk-forward 730d — sinais sinteticos trailing sem lookahead, reconciliados na hora → calibracao imediata) + MODO PRESENTE (SAT signal_emitter_orc_score 1 sinal/simbolo/barra M1 + reconciliador horario fecha outcomes ts+60min<now) + hit-rate por faixa (min 30) + Brier + drift → aba 1 Geral | orc_calibracao.md | S35 |
| **S37** | Aba Estrategia impl: orc_estrategia.py + /vector/strategy (G1/G2 prontos, G3-G5 dependem trades.db) | orc_estrategia.md | S36 |
| **S38** | Paper F4: executor em modo paper → trades.db populado → desbloqueia G3/G5/S25-F2 | S6 + S5.1 | S36 + FUS-STUB |

### 🟡 Futuro (sem bloqueio)

| # | O que | Spec |
|---|-------|------|
| VBT-3 | /vector/symbol/{sym} com dados reais (reiniciar servidor) | S27 |
| S28-G1 | Radar chart interativo com hover/click (ja implementado) | S28 |
| S28-G2 | Heatmap clicavel (ja implementado) | S28 |
| SPEC-1 | Marcar specs obsoletos: orc_analise, vectorbt_ecosystem, orc_estrategia v1 | S0 |
| ~~S30-PERF~~ | Absorvido pela S34 (vetorizacao extract_windows) | S34 |

---

## CHANGELOG

| Data | Versao | Mudancas |
|------|--------|----------|
| 2026-07-30 | 4.7 | S34+S36 implementadas (orc_scan/matrix_orc_scan, orc_calibracao, signal_emitter); achado R21 media-janela rejeitada; 9.950 sinais replay; REGRA-MET wireada no /metrics; 93 testes + gates PASS |
| 2026-07-30 | 4.6 | Fill 2a completo (5 simbolos 96,6-98,5%); pesquisa R21 correlacoes; trilha S34-S38 especificada (M1-puro, ranking v2, calibracao signals_log); FUS-STUB bloqueador formalizado; S36 v1.1: replay walk-forward (PASSADO) + emissor live (PRESENTE) apos auditoria "prever→validar 100%" |
| 2026-07-30 | 4.5 | Revisao R21 avaliacao mestra v2.0: run.py F1-F3 reais, gates.sh G0-G23, expurgo SSOT (S22-S24/S5.1/S18), SPEC-2 debt |
| 2026-07-30 | 4.4 | S33 orc_health_fases: validador por fase (sub-aba Saude x5 + endpoint /health/fases + G16 + harness 5 testes); auditoria gates: modulos S27-S32 sem cobertura — S33 fecha lacuna em runtime |
| 2026-07-29 | 4.3 | S31 G23 consolidacao/gap-fill, S32 orc_score, fix pips XAUUSD, confianca progressiva (coverage), boot 9→6 passos (Frieren/Elysian/Benchmark fora) |
| 2026-07-29 | 4.2 | Market tabs, VBT persistence, /vector/symbol/history, G16+G22 fixes |
| 2026-07-28 | 4.0 | S26 DataSource, G20, ROADMAP cleanup |
