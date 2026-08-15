# SPEC S0-ROADMAP — cTrader V2 Progress Tracker v4.0

> **P0 — ANTES DE ALTERAR, LEIA:** specs/NC-BP_CTRADER_DEV.md (criação, manutenção, revisão, rollbacks)
> **Versao:** 4.0 | **Wire:** specs/INDEX.md §7 | **Status:** active
> **SSOT de progresso**: ordem de ataque. ✅ = CHANGELOG. ⬜ = pendente.
> **Atualizado**: 2026-08-06 — Tarefas SDD-DDD-TDD com rollbacks obrigatórios
> **Regra de ouro**: Validar pipeline EXCLUSIVAMENTE com XAUUSD primeiro.

---

## 🔴 PRIORIDADE 0 — Correções Anti-Drift (DDD + Infra) ✅ CONCLUÍDA

| # | Item | Detalhe |
|---|------|---------|
| D1 | Mover `orc_ranking.py` → `f3_validacao/` | ✅ |
| D2 | Mover `orc_score.py` → `f2_fusao/` | ✅ |
| D3 | `/api/ctrader/health` → `/status` | ✅ |
| D4 | Performance scatter timeout | ✅ |
| D5 | `routers/ctrader_v2.py` GOD split | ⬜ |
| D6 | Dashboard unificação 6→4 abas | ✅ |
| D7 | Lab components interface mismatch | ✅ |
| D8 | DXY+VIX indices no F0/backfill | ✅ |

---

## ⚙️ INFRAESTRUTURA ATIVA — Specs Implementadas (Produção)

> **Status:** ✅ Em produção. Estas specs sustentam o pipeline atual e NÃO fazem parte do roadmap futuro.

| SPEC | Arquivo | Função | Status |
|------|---------|--------|--------|
| S2 | orc_coleta.md | F0 — Coleta MCP (5 ativos + 2 índices) | ✅ |
| S2.5 | orc_coleta.md | Backfill 2 anos + gaps diários | ✅ |
| S3 | orc_analise.md | F1 — Análise técnica | ✅ |
| S4 | orc_fusao.md | F2 — Fusão ponderada | ✅ |
| S5 | orc_validacao.md | F3 — Validação (threshold) | ✅ |
| S6 | orc_execucao.md | F4 — Execução de ordens | ✅ |
| S7 | orc_mar.md | F5 — MAR (pesos + replay) | ✅ |
| S27 | vectorbt_ecosystem.md | Fundação matemática (vectorbt, TA-Lib) | ✅ |
| S31 | orc_consolidacao.md | G23 — Consolidação Parquet + gap scan | ✅ |
| S32 | orc_score.md | Score composto (fusão F2) | ✅ |
| S33 | orc_health.md | Health check por fase | ✅ |
| S35 | orc_ranking.md | Ranking mecânico (F3 last mile) | ✅ |
| S36 | orc_calibracao.md | Calibração — track record | ✅ |
| S39 | vista_mercado.md | Vista MTF por símbolo | ✅ |
| S90 | boot_unificado.md | Boot unificado (.ps1) | ✅ |

## 🥇 FASE 1 — Desbloquear Pipeline ✅ CONCLUÍDA

---

## 🥈 FASE 2 — Bloco 1: Torneio do Passado v2.1 ✅ CONCLUÍDA

Sub-fases 1-6 implementadas: BUY/SELL RSI + DXY+VIX preflight + transparência + wire.

---

## 🥉 FASE 3 — Bloco 1 v3.0: Microestrutura de Mercado ⬜

> **Spec:** S41 v3.0 (orc_bloco1.md)
> **Validação:** XAUUSD apenas. Só expandir após aprovação.
> **Métrica-alvo:** MAE BUY < 0.15% | MAE SELL < 0.15% | Sinais/dia: 3-15 | DXY filtered < 30%
> **DDD:** Todos SATs vão em `utils/`. ORQ principal já existe: `utils/orc_bloco1.py`.
> **Rollback Checkpoint:** /snapshot antes de cada sub-fase que modifica `orc_bloco1.py`.
> **Validação empírica v2.1 (2026-08-15):** edge RSI/MACD/ADX é NULO (WR~50%, Sharpe~0 nos 5 ativos) — ver S41 §VALIDAÇÃO EMPÍRICA. Motiva a migração para v3.0 (microestrutura).

### FASE 3.1 — VWAP 1H + DXY ROC (Contexto Tático) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **3.1.1** | S41 § Camada 1 | SAT: `vwap_orc_bloco1.py` | `test_vwap_orc_bloco1.py` | 1 novo SAT + 1 teste | /snapshot antes de criar SAT |
| → `VwapContext.compute(buffer=60 velas)` retorna `(vwap_price, regime: ABOVE/BELOW/NEUTRAL)` |
| → Regra binária: preço > VWAP → ABOVE (BUY enabled); preço < VWAP → BELOW (SELL enabled); ±0.1% → NEUTRAL |
| **3.1.2** | S41 § Camada 1 | SAT: `dxy_roc_orc_bloco1.py` | `test_dxy_roc_orc_bloco1.py` | 1 novo SAT + 1 teste | /snapshot antes de criar SAT |
| → `DxyConfirm.check(roc_5): +0.1 confidence se DXY caindo (BUY) ou subindo (SELL)` |
| **3.1.3** | S41 § Fluxo v3.0 | ORQ: ampliar `orc_bloco1.py` `_evaluate_combo()` | ampliar `test_orc_bloco1.py` | 1 ORQ (416L) + S32 + ranking | ⚠️ /snapshot OBRIGATÓRIO — modifica `_evaluate_combo()` |
| → Wire: `VwapContext.compute()` + `DxyConfirm.check()` substituem ADX(14) no `force_filter` |
| **3.1.4** | S41 § Validação | Backtest CLI | `test_backtest_bloco1.py` (ampliar) | 1 ORQ + parquets + status/*.json | — (read-only backtest) |
| → Backtest XAUUSD 2 anos. Comparar MAE com VWAP vs MAE com ADX. Salvar `status/bloco1_v3_vwap.json` |

> **Gate FASE 3.1:** bash gates.sh --fast → ruff F811 (sem redefinição) → pytest test_vwap* + test_dxy* → pytest test_orc_bloco1.py → curl /lab/bloco1?symbol=XAUUSD
> **Go FASE 3.2 se:** MAE VWAP ≤ MAE ADX + tolerância 10%

### FASE 3.2 — Matriz VIXUSD (Panic Override) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **3.2.1** | S41 § Camada 1b | SAT: `panic_override_orc_bloco1.py` | `test_panic_override_orc_bloco1.py` | 1 novo SAT + 1 teste | /snapshot antes de criar SAT |
| → `PanicOverride.check(vix_series, symbol) → (spike: bool, action: BUY_AUTHORIZED/SELL_IMPOSED/None)` |
| → Lógica: VIX[t] / SMA(VIX, 20) > 2.0 → ativa. XAUUSD=BUY_AUTHORIZED, EUR/GBP/AUD=SELL_IMPOSED, USDJPY=SELL_AUTHORIZED |
| **3.2.2** | S41 § Preflight | SAT: ampliar `preflight_check()` | ampliar `test_preflight.py` | preflight + bloco1 | /snapshot antes de modificar |
| → VIX stale detection: se última barra > 72h → confidence × 0.8. Se >168h → aborta |
| **3.2.3** | S41 § Validação | ORQ: wire no `_evaluate_combo()` | ampliar `test_orc_bloco1.py` | 1 ORQ + force_filter | ⚠️ /snapshot OBRIGATÓRIO |
| → `panic_action = panic.check()` bloqueia/libera BUY/SELL antes do force_filter |
| **3.2.4** | S41 § Validação | Backtest eventos reais | `test_panic_events.py` | parquets | — (read-only) |
| → Testar em mar/2020 (COVID), mar/2023 (SVB), ago/2024 (carry trade unwind). Validar que BUY ouro foi autorizado nos 3. |

> **Gate FASE 3.2:** bash gates.sh → pytest test_panic* → curl /lab/bloco1?symbol=XAUUSD&panic=true
> **Go FASE 3.3 se:** Panic Override acionou em eventos reais E MAE não degradou > 5%

### FASE 3.3 — Gatilho Balístico (Slope 5 Velas + TA-Lib) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **3.3.1** | S41 § Camada 2 + S44 § Camada Micro | SAT: `slope_orc_bloco1.py` | `test_slope_orc_bloco1.py` | 2 novos SATs + 2 testes | /snapshot antes de criar SATs |
| → `SlopeDetector.score(velas[0:5]) → (slope_pct, acceleration, signal: BUY/SELL/NONE)` |
| → Regressão linear dos fechos de 5 velas. Corpos crescendo + slope > 2% → sinal |
| **3.3.2** | S41 § Camada 2 | SAT: `rejection_orc_bloco1.py` | `test_rejection_orc_bloco1.py` | 1 SAT + 1 teste | /snapshot |
| → `RejectionFilter.check(velas[0:5]) → (rejected, reason)` |
| → Pavio superior > 2× corpo → cancela BUY. Pavio inferior > 2× corpo → cancela SELL |
| **3.3.3** | S44 § TA-Lib Patterns | SAT: `pattern_confidence_orc_bloco1.py` | `test_pattern_confidence.py` | 1 SAT + 1 teste | /snapshot |
| → `PatternConf.adjust(patterns_detected, slope_direction) → delta_confidence ∈ [-0.2, +0.2]` |
| → CDLHAMMER + slope > 0 → +0.20. CDLSHOOTINGSTAR → -0.15. Usa `talib.CDL*` (61 patterns) |
| **3.3.4** | S41 § Camada 2 | ORQ: `micro_momentum_orc_bloco1.score_signal()` | `test_micro_momentum.py` | 1 novo ORQ | /snapshot |
| → SAT orquestrador: `slope.score() + rejection.check() + pattern.adjust()` → `(signal, confidence)` |
| **3.3.5** | S41 § Fluxo v3.0 | ORQ: substituir `_detect_buy/sell_signals` por `micro_momentum.score_signal()` | ampliar `test_orc_bloco1.py` | ⚠️ BLAST RADIUS: substitui ~60% do `orc_bloco1.py` | ⚠️ /snapshot OBRIGATÓRIO — maior refactor da FASE 3 |
| → `orc_bloco1.py` perde RSI/MACD/ADX. Ganha VWAP+VIX+Slope+Rejection+Pattern. ~200 linhas substituídas |
| **3.3.6** | S43 v2.0 | SAT: ampliar `parameter_grid_orc_bloco1.py` com MOMENTUM_GRID | `test_parameter_grid.py` (ampliar) | 1 SAT + 1 teste | /snapshot |
| → Grid com 27 combos: slope_threshold [0.02, 0.05, 0.10] × accel_min [1.2, 1.5, 2.0] × wick_ratio [2.0, 2.5, 3.0] |
| **3.3.7** | S41 § Validação | Backtest XAUUSD 2 anos | `test_backtest_bloco1.py` (ampliar) | orc_bloco1 + parquets | — (read-only) |
| → MAE slope vs MAE RSI/MACD. Esperado: MAE slope < 0.15%. Salvar `status/bloco1_v3_slope.json` |

> **Gate FASE 3.3:** bash gates.sh → G7 ORBITAL (novos SATs wireados ao orc_bloco1) → pytest test_slope* + test_rejection* + test_pattern* + test_micro* + test_orc_bloco1.py → ruff → curl /lab/bloco1?symbol=XAUUSD&engine=v3
> **Go FASE 3.4 se:** MAE slope ≤ MAE RSI/MACD E sinais/dia entre 3-15

### FASE 3.4 — Antecipação Intrabarra ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **3.4.1** | S41 § Camada 3 + S44 § Camada Antecipação | SAT: `anticipation_orc_bloco1.py` | `test_anticipation_orc_bloco1.py` | 1 SAT + 1 teste | /snapshot |
| → `Anticipate.detect(velas[0:3]) → (anticipate: bool, entry_type: intrabar/open_next)` |
| → 3 velas com topos/fundos ascendentes contínuos → antecipa. Senão → aguarda fechamento |
| **3.4.2** | S41 § Camada 3 | ORQ: wire no `micro_momentum_orc_bloco1.py` | ampliar `test_micro_momentum.py` | 1 ORQ | /snapshot |
| → Se `anticipate=True`, usa bid/ask corrente como entry em vez de open[pos+1] |
| **3.4.3** | S41 § Validação | Backtest XAUUSD 2 anos com/sem antecipação | ampliar `test_backtest_bloco1.py` | — | — |
| → MAE com antecipação vs MAE sem. Esperado: redução de slippage em 30%+ |

> **Gate FASE 3.4:** pytest test_anticipation* + test_micro_momentum.py → curl /lab/bloco1?symbol=XAUUSD&anticipate=true
> **Go FASE 3.5 se:** MAE com antecipação < MAE sem E não aumentou falsos positivos > 20%

### FASE 3.5 — Expansão Multiclasse (pós-XAUUSD ✅) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **3.5.1** | S41 § Camada 1b | SAT: ampliar `panic_override_orc_bloco1.py` | ampliar `test_panic_override.py` | 1 SAT | /snapshot |
| → EURUSD, GBPUSD, AUDUSD: spike VIX → SELL_IMPOSED (trava compra em risco) |
| **3.5.2** | S41 § Camada 1b | SAT: ampliar `panic_override_orc_bloco1.py` | ampliar `test_panic_override.py` | 1 SAT | /snapshot |
| → USDJPY: spike VIX → SELL_AUTHORIZED (repasse JPY, refúgio cambial) |
| **3.5.3** | S41 § Validação | Backtest 5 símbolos | `test_backtest_bloco1.py` (ampliar) | orc_bloco1 + parquets | — |
| → Validar cada par com 2 anos de dados. MAE por símbolo < 0.15%. Panic Override ativou em eventos reais |

> **Gate FASE 3.5:** pytest test_panic_override.py → backtest completo 5 símbolos → G15 spec drift check
> **FASE 3 completa quando:** MAE < 0.15% em XAUUSD + Panic Override validado + Backtest 5 pares < 0.15%

---

## 🏅 FASE 4 — Bloco 2 v2.0: Defesa Microestrutural ⬜

> **Spec:** S42 v2.0 (orc_bloco2.md)
> **Validação:** XAUUSD apenas.
> **Métrica-alvo:** Sharpe (best_layer) > 0.50 | MaxDD < 15% | Monte Carlo p < 0.05 | Underwater < 60d | WF degrad < 50%
> **PRÉ-REQUISITOS BLOQUEANTES:** MonteCarlo + CircuitBreaker devem passar antes da PRE-BETA (Live).
> **DDD:** ORQ `utils/orc_bloco2.py` (312L). SATs em `utils/*_orc_bloco2.py`. Nunca recalcular indicadores.

### FASE 4.0 — Monte Carlo + Circuit Breaker (PRÉ-REQUISITOS) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **4.0.1** | S42 § Pré-requisitos + montecarlo-tdd-pattern | SAT: `montecarlo_orc_bloco2.py` | `test_montecarlo_orc_bloco2.py` (25 testes mín.) | 1 SAT + 1 teste | /snapshot |
| → `MonteCarlo.validate(trades, n=1000) → (p_value, sharpe_ci, go_nogo: bool)` |
| → Shuffle trades 1000×. Distribuição de Sharpe. p-value < 0.05 → edge real (não sorte) |
| **4.0.2** | S42 § Pré-requisitos | SAT: `equity_circuit_breaker_orc_bloco2.py` | `test_equity_circuit_breaker.py` (12+ testes) | 1 SAT + 1 teste | /snapshot |
| → Máquina de estados: `NORMAL → CAUTIOUS (daily DD > 3%) → SIMULATION (total DD > 15%)` |
| → Em CAUTIOUS: lote 50%. Em SIMULATION: sem ordens reais, só log |
| **4.0.3** | S42 § Saída v2.0 | ORQ: ampliar `orc_bloco2.py` → `bloco2_best.json` | ampliar `test_orc_bloco2.py` | ⚠️ 1 ORQ (312L) + F4 | ⚠️ /snapshot OBRIGATÓRIO |
| → `run_bloco2()` salva `status/bloco2_best.json`: best_layer, params, métricas. Formato compatível com F4. |
| **4.0.4** | S6 (orc_execucao.md) | SAT: `requote_handler_orc_execucao.py` | `test_requote_handler.py` | F4 + MCP | /snapshot |
| → `RequoteHandler.retry(entry, max_attempts=5, delay_ms=50) → fill_price` |
| → Exponencial backoff: 50ms, 100ms, 200ms, 400ms, 800ms. Desiste se 5 falhas |

> **Gate FASE 4.0:** pytest test_montecarlo* + test_equity* + test_orc_bloco2.py + test_requote*. Monte Carlo precisa p < 0.05. CircuitBreaker transições testadas.
> **Go FASE 4.1 se:** Monte Carlo p < 0.05 E CircuitBreaker 4 transições OK E bloco2_best.json válido

### FASE 4.1 — Gate de Spread ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **4.1.1** | S42 § Camada 0 | SAT: `spread_gate_orc_bloco2.py` | `test_spread_gate_orc_bloco2.py` | 1 SAT + 1 teste | /snapshot |
| → `SpreadGate.check(ask, bid, atr, tp_mult=2.0) → (pass: bool, spread_pct: float)` |
| → spread > 20% TP projetado → aborta trade. Loga `aborted_trades++` |
| **4.1.2** | S42 § Fluxo v2.0 | ORQ: wire no `run_bloco2()` | ampliar `test_orc_bloco2.py` | 1 ORQ (312L) | ⚠️ /snapshot OBRIGATÓRIO |
| → ANTES de qualquer camada de execução. Se gate.abort → pula todas as camadas, incrementa contador |

> **Gate FASE 4.1:** pytest test_spread* + test_orc_bloco2.py → curl /lab/bloco2?symbol=XAUUSD → verificar aborted_trades no JSON
> **Go FASE 4.2 se:** trades abortados < 15% do total em condições normais (VIX < 30)

### FASE 4.2 — OCO Dinâmico VIX ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **4.2.1** | S42 § Camada 4b | SAT: `oco_dynamic_orc_bloco2.py` | `test_oco_dynamic_orc_bloco2.py` | 1 SAT + 1 teste | /snapshot |
| → `OcoDynamic.compute(atr, vix_spike) → (sl_offset, tp_offset, lot_adjust)` |
| → Normal: atr×1.5 / atr×3.0, lote 100%. Pânico: atr×3.0 / atr×6.0, lote 50%. Risco financeiro constante |
| **4.2.2** | S42 § Fluxo v2.0 | ORQ: ampliar `oco_atr_orc_bloco2.py` | ampliar `test_oco_atr.py` | 1 SAT existente | /snapshot |
| → `calc_oco_bands(atr, vix_spike)` → multiplicador dinâmico. Lê `vix_spike` do Bloco1 via `bloco1_best.json` |
| **4.2.3** | S42 § Validação | Backtest XAUUSD com/sem OCO dinâmico | ampliar `test_orc_bloco2.py` | orc_bloco2 + parquets | — |
| → MaxDD com OCO dinâmico < MaxDD com OCO fixo. Em eventos VIX > 2× média, MaxDD reduz > 20% |

> **Gate FASE 4.2:** pytest test_oco* + test_orc_bloco2.py → backtest XAUUSD com VIX spike event → validar MaxDD
> **Go FASE 4.3 se:** MaxDD OCO dinâmico < MaxDD OCO fixo E WinRate não degradou > 5%

### FASE 4.3 — Expansão Multiclasse (pós-XAUUSD ✅) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) |
|------|-----------|-----|-------------|
| **4.3.1** | S42 § Saída v2.0 | Bloco2 para EURUSD, GBPUSD, AUDUSD, USDJPY | ampliar `test_orc_bloco2.py` (5 símbolos) |
| **4.3.2** | S42 § Saída v2.0 | Comparativo: best_layer por símbolo | `test_bloco2_5s.py` |

---

## 🥊 FASE PRE-BETA — XAUUSD Demo Live (cTrader) ⬜

> **Objetivo:** Pipeline completo: Bloco1 → Bloco2 → F4 → cTrader Demo → Banca.
> **Validação:** XAUUSD apenas. 30 dias em conta Demo.
> **Métrica-alvo:** Sharpe Demo ±20% do backtest | Drawdown < 15% | PnL > 0 após 30d | Zero violações do CircuitBreaker

### PRE-BETA.1 — Wire Bloco2 → Execução ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **PB.1.1** | S42 § Saída v2.0 + S6 | ORQ: `f4_executor/orc_simulacao.py` (F6) | `test_orc_simulacao.py` | 1 NOVO ORQ + F4 + S44 | ⚠️ /snapshot OBRIGATÓRIO — novo fluxo de execução |
| → `OrcSimulacao.run()`: lê `bloco1_best.json` + `bloco2_best.json` → monta ordem → chama F4 |
| **PB.1.2** | S6 (orc_execucao.md) | ORQ: ampliar `f4_executor/orc_execucao.py` | ampliar `test_orc_execucao.py` | F4 + MCP | ⚠️ /snapshot OBRIGATÓRIO |
| → F4 consome `bloco2_best.json` (entry_price, sl, tp, lot_size). Formato padronizado. |
| **PB.1.3** | S44 § Live | ORQ: ampliar `signal_emitter.py` → `emit_once()` lê bloco1+bloco2 .json | ampliar `test_signal_emitter.py` | signal_emitter + dashboard | ⚠️ /snapshot |
| → `emit_once()` → Bloco1 → Bloco2 → JSON → F6 → F4. Timeout 5s por ciclo. |

> **Gate PB.1:** curl /api/ctrader/emit (dry-run) → verificar JSON pipeline completo → pytest test_orc_simulacao.py + test_orc_execucao.py

### PRE-BETA.2 — Circuit Breaker + Gestão de Banca ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **PB.2.1** | S42 § Pré-requisitos | ORQ: wire `equity_circuit_breaker` no F6 | ampliar `test_equity_circuit_breaker.py` | orc_simulacao.py | /snapshot |
| → Máquina de estados no F6: NORMAL → CAUTIOUS → SIMULATION (automático por drawdown) |
| **PB.2.2** | S42 § Pré-requisitos | SAT: `calc_lot_size(lote_padrao, atr, risk_pct=0.01)` | `test_calc_lot_size.py` | — | /snapshot |
| → `lot = (capital × risk_pct) / (ATR × 1.5)`. Capital inicial: $10,000. Risco: 1% ($100) |
| **PB.2.3** | S6 | ORQ: ampliar `safety_orc_execucao.py` | ampliar `test_safety.py` | F4 + orc_simulacao | ⚠️ /snapshot |
| → `DAILY_DRAWDOWN_KILL = 0.03`. Drawdown diário > 3% → CircuitBreaker → CAUTIOUS |

> **Gate PB.2:** pytest test_equity* + test_calc* + test_safety.py → simulação com drawdown forçado → verificar transição para SIMULATION

### PRE-BETA.3 — Loop de Simulação (30 dias) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **PB.3.1** | S44 § Live | SAT: `simulation_loop.py` no F6 | `test_simulation_loop.py` | F6 + F0 + S44 + F4 | ⚠️ /snapshot — loop M1 consome MCP |
| → Loop: a cada tick M1 → Bloco1 → Bloco2 → F6 → F4. Timeout 5s/ciclo. Máx 5 falhas consecutivas |
| **PB.3.2** | S22 v5.0 | SAT: `log_simulation_trades(jsonl_path)` | `test_log_simulation.py` | — | /snapshot |
| → `logs/simulation_trades.jsonl`: timestamp, symbol, direction, entry, exit, pnl, sharpe_parcial |
| **PB.3.3** | S22 v5.0 | Frontend: ampliar aba Simulação | `DashboardView.test.tsx` (ampliar) | 10.0_ui_dash/ | /snapshot |
| → Aba Simulação: PnL acumulado (chart), Drawdown, Sharpe rolling 20d. Endpoint `/api/ctrader/simulacao/metrics` |
| **PB.3.4** | S22 v5.0 | SAT: `check_stop_criteria(f6_state)` | `test_stop_criteria.py` | F6 | /snapshot |
| → Critério de parada automático: 30 dias OU MaxDD > 15% OU CircuitBreaker = SIMULATION |

> **Gate PB.3:** bash gates.sh → pytest test_simulation* + test_log* + test_stop* → dashboard npm run build

### PRE-BETA.4 — Aprovação (Go/No-Go para FASE 5) ⬜

| # | Critério | Threshold |
|---|----------|-----------|
| PB.4a | Sharpe Demo 30d vs Sharpe Backtest | ±20% |
| PB.4b | Max Drawdown | < 15% |
| PB.4c | PnL acumulado | > 0 (positivo) |
| PB.4d | Trades executados | > 20 (significância mínima) |
| PB.4e | Violações CircuitBreaker | 0 (zero) |
| PB.4f | Requotes > 0.2% | 0 (zero) |

**Regra:** 6/6 → GO para FASE 5. < 6/6 → recalibra Bloco1/Bloco2.

---

## 🏆 FASE 5 — Portfolio Manager + Zoom-In Live ⬜

> **Spec:** S45 v1.0 (orc_portfolio_manager.md) + S44 (buffer deslizante)
> **Validação:** XAUUSD apenas.
> **Métrica-alvo:** Latência emit_once() < 5ms | RAM < 30KB por símbolo | 5 ativos simultâneos sem sobreposição USD

### FASE 5.1 — Buffer Deslizante O(1) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **5.1.1** | S44 § TickBuffer | SAT: `buffer_orc_bloco1.py` | `test_buffer_orc_bloco1.py` | S44 + S41 | /snapshot |
| → `TickBuffer(maxlen=65)` com `deque`. push() O(1), recompute() O(65). Thread-safe via GIL |
| **5.1.2** | S44 § Performance | Benchmark | `test_buffer_bench.py` | — | — |
| → 65 velas: VWAP + slope + rejection + TA-Lib < 5ms. RAM < 30KB por símbolo |
| **5.1.3** | S44 § Live | ORQ: substituir `compute_indicators_mtf()` por `TickBuffer` | ampliar `test_orc_vectorbt.py` | ⚠️ orc_vectorbt.py + S44 | ⚠️ /snapshot OBRIGATÓRIO |

### FASE 5.2 — Portfolio Manager (Sobreposição USD) ⬜

| Task | SDD (Spec) | DDD | TDD (Teste) | Blast Radius | Rollback |
|------|-----------|-----|-------------|-------------|----------|
| **5.2.1** | S45 § Arquitetura | SAT: `portfolio_manager_orc_risk.py` | `test_portfolio_manager.py` (12+ testes) | S44 + emit_once | /snapshot |
| → `ExposureTracker`: dicionário `{SHORT_USD, LONG_USD}`. register(), unregister(), has_exposure() |
| **5.2.2** | S45 § Resolução | SAT: resolver conflitos | ampliar `test_portfolio_manager.py` | — | /snapshot |
| → `resolve_conflict(signals[])`: desempate por confidence → spread → VWAP → ATR |
| **5.2.3** | S45 § Wire | ORQ: integrar no `emit_once()` (S44) | ampliar `test_signal_emitter.py` | ⚠️ emit_once + F4 | ⚠️ /snapshot |
| → Bloqueia sinal se exposição naquela direção USD já tomada |
| **5.2.4** | S45 § Cleanup | SAT: `cleanup_closed_trades()` | ampliar `test_portfolio_manager.py` | — | /snapshot |
| → Remove trades fechados via F0 snapshot. Roda a cada ciclo de emit_once() |
| **5.2.5** | S45 § Validação | Simulação 5 ativos simultâneos | `test_portfolio_5s.py` | F6 + todos os ORQs | — |
| → Máximo 2 trades simultâneos (1 LONG + 1 SHORT USD). Zero sobreposição. Hedge natural. |

> **Gate FASE 5:** pytest test_buffer* + test_portfolio* + test_signal_emitter.py → simulação 5 ativos → latência < 5ms
> **Go live se:** Portfolio Manager bloqueou sobreposição + Latência < 5ms + RAM < 30KB/símbolo

---

## 📋 Backlog

| # | Item |
|---|------|
| B1 | `gates/run_vbt_gap_gate.py` |
| B2 | ~~Monte Carlo baseline~~ → movido para FASE 4.0a |
| B3 | Log rotation, F0 auto-recovery |
| B4 | ccxt + yfinance (dados multi-exchange) |
| B5 | Notificações (Telegram/Discord) para sinais live |

---

## 📐 CONVENÇÕES SDD-DDD-TDD (v4.0)

### Ordem de Ataque por Task

```
1. Escrever/ampliar SPEC (SDD)     → especificação no arquivo .md relevante
2. Criar test_<modulo>.py (TDD)    → RED: teste falha (funcionalidade não existe)
3. Criar SAT/ORQ .py               → GREEN: teste passa
4. /snapshot (CHECKPOINT)          → git add + commit do SAT+teste isolado
5. Wire no ORQ pai                 → integrar SAT no fluxo
6. Rodar gates.sh                  → G7 ORBITAL + G11 SPEC + ruff + pytest
7. Backtest (se aplicável)         → validar métrica-alvo
8. Atualizar INDEX.md              → nova spec ou % progresso
9. Atualizar ROADMAP.md            → marcar task ✅ ou ajustar
10. Commit com --ship              → bash gates.sh --fast --ship="FASE X.Y: descrição"
```

### Checkpoints de Rollback

| Operação | Gatilho | Ação |
|----------|---------|------|
| `/snapshot` | Antes de criar SAT (novo arquivo) | `git add` do spec + test stub |
| ⚠️ `/snapshot` OBRIGATÓRIO | Antes de modificar ORQ existente (>200L) | `git stash` pronto. Declarar blast radius |
| `git checkout -- <file>` | Rollback de SAT com falha | Recupera original, sem afetar outros arquivos |
| `git revert <commit>` | Rollback de wire que quebrou pipeline | Reverte o commit de wire, SATs preservados |

### Blast Radius por Tipo de Arquivo

| Arquivo | Raio | Precaução |
|---------|------|-----------|
| Novo SAT (`utils/*_orc_*.py`) | 1-2 arquivos | Baixo risco. /snapshot recomendado |
| ORQ existente (`utils/orc_*.py`) | 3-8 arquivos (SATs filhos + router + testes + dashboard) | ⚠️ /snapshot obrigatório. Rollback explícito |
| Router (`routers/ctrader_v2.py`) | 5-10 arquivos (endpoints + DomainGates + React) | ⚠️ /snapshot obrigatório |
| F4/MCP (`f4_executor/`) | CONTA DEMO afetada | ⚠️⚠️ só testar em SIMULATION mode primeiro |
| Parquet (`data/`) | Read-only no pipeline | Backfill antes de deletar |

### Controle de Explosão Combinatória (Pareto)

- **FASE 3.3:** 27 combos grid × 2 direções = 54 → OK (< 200 limite)
- **FASE 3.4:** antecipação × grid = 54 × 2 = 108 → OK
- **FASE 3.5:** 5 símbolos × 108 = 540. ⚠️ APLICAR PARETO: testar XAUUSD completo (108), demais só top 5 combos (5 × 10 = 50). Total: 158.
- **FASE 4.2:** OCO × grid × 5 símbolos = 540. Mesma estratégia Pareto.
- **FASE 5.2:** Portfolio Manager é O(1) por sinal — sem grid.

---


---

## 🔧 FASE 6 — Infraestrutura de Métricas & Dashboard (2026-08-08)

> **Origem:** Revisao massiva do pipeline DDD de metricas.
> **RCA:** 7 achados — 3 precisam de acao, 4 estao OK.

| # | Task | Spec | DDD | Blast Radius | Status |
|---|------|------|-----|-------------|--------|
| M1 | DXY+VIX no snapshot F0 (ALL_COLLECT_SYMBOLS) | S2 | ORQ: f0_collector | snapshot.json + ranking | ✅ | — `orc_coleta.py` coleta indices alem dos 5 forex | S2 | ORQ: f0_collector | snapshot.json + ranking | ⬜ |
| M2 | `orc_health_fases.py`: adicionar checks G23 (ja 90% coberto) | S33 | SAT: orc_health_fases | router + dashboard | ✅ | (gap_report.json) e backfill (backfill_progress.json) | S33 | SAT: orc_health_fases | router + dashboard (2 endpoints) | ⬜ |
| M3 | Documentar schema de `collect_all()` (29 metricas em S21) | S21 | Spec-only | 0 | ✅ | no spec S21 — 29 metricas com tipos e fontes | S21 | Spec-only | 0 (documentacao) | ⬜ |
| M4 | Validacao de schema nos JSONs (utils/schema_validator.py) | S32 | SAT: utils/schema_validator | 3 arquivos JSON | ✅ | de status — `jsonschema` ou `pydantic` nos 3 principais (fusion_output, ranking, metrics) | S32 | SAT: utils/schema_validator | 3 arquivos JSON | ⬜ |
| M5 | `data_source.py`: cache TTL 15s + hit-rate tracking | S26 | SAT: data_source | 0 | ✅ | para 15s e adicionar metricas de hit-rate | S26 | SAT: data_source | 0 (isolado) | ⬜ |
| M6 | Dashboard: DXY/VIX (automatico via M1 — F0 ja coleta) | S22 | ORQ: orc_dashboard | router + React | ✅ | na aba Overview (cobertura, gaps) | S22 | ORQ: orc_dashboard | router + React (1 endpoint + 1 componente) | ⬜ |

### Justificativa por achado

| Achado | Task | Explicacao |
|--------|------|-----------|
| DXY/VIX ausentes do snapshot | M1 | F0 coleta so 5 forex. Ranking S35 precisa dos indices. Ampliar coleta. |
| G23/backfill nao cobertos pelo health | M2 | `orc_health_fases.py` valida F0-F5 mas nao o novo G23. Adicionar checks de gap_report e backfill_progress. |
| collect_all() sem docs | M3 | 29 metricas sem schema documentado. Spec S21 precisa de tabela com nome, tipo, fonte, fase. |
| JSONs sem validacao | M4 | fusion_output, ranking, metrics podem corromper silenciosamente. Validar schema no load. |
| Cache TTL curto | M5 | 5s e agressivo. 15s reduz leitura de disco. Hit-rate ajuda a detectar stale cache. |
| Dashboard nao mostra indices | M6 | Overview mostra 5 forex. Adicionar DXY/VIX com cobertura e gaps. |


## ✅ CONCLUÍDO

| Data | Item |
|------|------|
| 2026-08-04 | FASE 1 completa: pipeline, backtest OCO, resample M1→M15, TA-Lib, 129/131 tests |
| 2026-08-05 | Reestruturação Bloco 1/Bloco 2: separação alpha × risk |
| 2026-08-05 | Decisão Pip 0: Open da barra seguinte (sem look-ahead bias) |
| 2026-08-05 | DXYUSD+VIXUSD mapeados no MCP (381 símbolos, id 2626/2625). F0 ampliado. |
| 2026-08-05 | Bloco1 v2.1: preflight FAIL FAST, SELL RSI, transparência, ranking, wire |
| 2026-08-05 | Bloco2 v1.1: 312L implementado, 5 camadas, best_layer=oco_atr |
| 2026-08-05 | Backfill diário: G23 gap scan + --gaps no .bat |
| 2026-08-05 | Roadmap v3.0: Microestrutura, VIX Panic Override, XAUUSD first |
| 2026-08-06 | Roadmap v4.0: SDD-DDD-TDD com rollbacks, blast radius, Pareto, 39 tasks atômicas |
| 2026-08-08 | Revisao massiva dashboard metrics engine: 7 achados, 6 tasks (M1-M6) na FASE 6 |
| 2026-08-06 | BP00 — `specs/NC-BP_CTRADER_DEV.md`: boas práticas P0 (criação, manutenção, revisão). Wireado no INDEX+ROADMAP+7 specs ativos. |
| 2026-08-06 | S41 v3.1 + S35 v3.1: validação dupla (2 anos forex puro + 9 meses com DXY/VIX). Anti-overfitting: otimiza em 2 anos, valida filtro em 9 meses. |
| 2026-08-09 | **Session Lifecycle (SSOT):** `ensure_session_fresh()` extraído para `mcp_client.py`. Wire no F0 live (`orc_coleta.py`) + backfill + dashboard health (`session_age_s`, `session_ttl_s`) + `orc_health_fases.py`. MCP expira em ~7-8 min → renovação proativa a cada 5 min. |
| 2026-08-09 | **G23 Gap Filter Hardening:** C1: `DAILY_CLOSE_UTC` expandido (EUR/GBP/JPY/AUD + DXYUSD). C2: `_update_gap_report_incremental()` recalcula `total_gaps`. C3: pós-backfill re-scan em vez de `unlink()` cego. Bugs #1/#2/#3 resolvidos. |
