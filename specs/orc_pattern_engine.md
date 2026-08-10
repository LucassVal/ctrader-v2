# SPEC S34 — Pattern Engine M1-puro: VectorBT exploration + performance + ciencia multi-TF

> **Versao:** 1.2.0 | **Wire:** utils/orc_scan.py (ORQ) + utils/matrix_orc_scan.py (SAT) → status/pattern_library.json | **Status:** active
> **R-USE:** S29 (walk-forward), S30 (cosine similarity), S31-VBT (storage_orc_consolidated 730d), S32 (pesos/coverage), R21

## Engine v1.2 — score composto no replay (paridade S32)

### Resultado MEDIDO do re-scan v1.2 (2026-07-30 22:55 — hipotese REFUTADA)

A paridade live×replay foi implementada corretamente, mas a medicao REFUTOU a
hipotese "quality compoe e discrimina":

- Distribuicao comprimiu: 9.997/10.000 sinais cairam na faixa 0-50 (quality
  trailing e baixo e quase constante → funciona como escala para baixo, nao
  como discriminador); a faixa 70-85 (que na v1.1 tinha 72,1% de hit com n=43)
  DESAPARECEU — o composto nao alcanca mais 70+
- hit_15m faixa 0-50: 51,4% (era 52,7% na 50-70) — sem ganho de acerto
- Brier PIOROU mecanicamente: 0,271 (era 0,249) — scores ~0,35 vs outcomes
  ~51%: a formula afastou o score da taxa real de acerto
- Drift inalterado: acertos 35,9 vs erros 35,6 (separacao ~0,3 ponto)

CONCLUSAO R21: pesos fixos 0,33/0,67 herdados do S32 sao CHUTE — nunca foram
calibrados contra outcome real. O sinal de edge mora na conf do padrao PURA
(v1.1: 72,1% no topo). PROXIMO FIO (v1.3): calibracao EMPIRICA do score —
ajustar mapa score→P(acerto) nos proprios dados replay (regressao logistica
acerto ~ quality + conf, ou isotonica), substituindo a formula heuristica;
a faixa de corte para entrada sai da curva ajustada, nao de peso inventado.

### Formula implementada (v1.2 — paridade S32, mantida como baseline)

Problema medido na 1ª calibracao (abaixo): score do replay = SO conf do padrao
→ Brier ~0,25 + drift acertos≈erros (nao discrimina). A v1.2 compoe o score do
replay com a MESMA formula do score live (S32), fechando a paridade
passado×presente exigida pelo dono:

```
score_replay(t) = ( quality_f1_trailing(t) x 0.33 + conf_padrao x 0.67 ) x coverage_G23(simbolo)
```

- **quality_f1_trailing(t)** — nova funcao SAT `matrix_orc_scan.trailing_quality_f1()`:
  mesmas regras do S29 (BUY RSI<35 & ADX>20; SELL RSI>65 & ADX>20; lookahead
  5 barras; acerto = move direcional > 0,05%), computada em janela TRAILING de
  90 dias terminando em t (cumsum vetorizado, O(n), zero lookahead: f1[t] usa
  apenas barras <= t). Minimo 30 sinais na janela (A7); abaixo disso = NaN e o
  score cai no fallback S32 ("apenas patterns", conf x coverage).
  NOTA R21: no S29, F1 == win-rate (tp=wins, fp=fn=losses) — paridade mantida
  de proposito; refino da formula F1 e debito separado do S29.
- **coverage_G23(simbolo)** — mesma fonte do S32 (`orc_metricas._read_gap_coverage`),
  constante por simbolo; a linha replay passa a gravar `coverage_pct` (era None)
  e `quality_f1` (rastreabilidade da composicao).
- **Re-scan SUBSTITUI replay** (nao append): dedup do S36 e (symbol,origem,ts)
  keep=first, entao re-scan sem purge manteria scores velhos. `run_scan` chama
  `orc_calibracao.purge_signals(origem="replay", symbols=...)` antes do append.
  Linhas live NUNCA sao purgadas.
- Custo adicional medido: desprezivel (vetorizado) — scan segue ~150s/simbolo.
- Juiz do fix: Brier < 0,25 e drift (acertos−erros) separando > 1 ponto —
  medidos pelo reconcile apos re-scan. Se nao separar, o proximo fio e a
  selecao de padroes (faixa 70-85 ja mostrou 72,1% com n=43).

## Achados R21 da sessao S39 (2026-07-30 — bugs de UNIDADE e SPREAD, medidos)

1. **Closes em unidades brutas cTrader**: consolidado G23 guarda close bruto
   (XAUUSD 337.110.000 = $3.371,10 com price_divisor 100.000; USDJPY divisor
   1.000). Scan e reconcile faziam `diff/pip_size` SEM o divisor → outcome
   pips inflados 100.000x (avg_pips_net -85.013 absurdo). Fix: `pip_raw =
   pip_size x price_divisor` em orc_scan e orc_calibracao.
2. **Spread ASSIMETRICO**: `r = raw - spread` para todo sinal fazia BEARISH
   ganhar ate em alta leve (short tambem paga spread!). Inflou o hit_15m para
   60,9%. Fix: pips assinados na direcao (`direction x raw - spread`) em
   build_replay_row e reconcile. Verdade honesta medida apos os 2 fixes:
   **hit_5m 35,6% / hit_15m 41,2% / hit_60m 46,1%** (n=9.465) — as regras
   atuais NAO vencem o spread nos horizontes curtos. 52,7% e 60,9% anteriores
   eram artefatos de medicao.
3. **ADX NaN por divisao 0/0** (plus_di+minus_di==0 em barra flat) envenenava
   a media movel → ultima barra None (health 15/16). Fix: DX=0 sem DM.

## Achado R21 (medido 2026-07-30 — engine v1.1)

A **media de janela de 20 barras foi TESTADA e REJEITADA**: destrói a
discriminacao — em thr 0.92, 100% dos prototipos qualificavam com mediana de
~593k matches cada (tudo e similar a tudo). Engine final: **vetor de estado
POR BARRA** (mesmas 5 features do S30) + **thr 0.999** (mediana ~6,5k matches
— base estatistica forte) + amostra de stats limitada (5k/prototipo).
Custo medido: ~150s/simbolo (~12 min os 5 — acima do alvo <10 min, aceito).
Match space sem janela; `window` vira apenas exclusao de vizinhanca (+-5 barras).

### Resultado do 1º scan real (730d × 5 simbolos, 9.950 sinais replay)

- 50 padroes/simbolo; maioria NEUTRAL — edge FRACO (honesto, A7)
- hit_rate_15m replay: 52,8% (faixa 50-70, n=9.903); faixa 70-85: 72,1% (n=43, amostra pequena)
- Brier ~0,25 = score replay NAO discrimina ainda (equivale a chutar 50%)
- Drift: score medio de acertos ≈ erros — confirma: proximo fio e melhorar o
  SCORE do replay (hoje = conf do padrao; falta componente quality S29 por janela)

## Decisao de arquitetura (fechada pelo dono 2026-07-30)

- **M1 e o timeframe cientifico unico.** Todo empirismo (scan, calibracao, hit-rate) roda em M1.
- M5/M15/H1 sao camada visual (graficos) — mas DEVEM carregar ciencia correlata (secao 4).
- Scan profundo M1 730d tem custo O(n×20) (~750k janelas) — exige vetorizacao, NAO troca de TF.

## 1. Problema

| Item | Estado hoje |
|------|------------|
| extract_windows (S30) | loop Python O(n×20): 700k velas × 20 indicadores ≈ 14M iteracoes — inviavel p/ scan full 730d |
| conf sem matches | 0.5 flat — sem densidade empirica de padrao |
| VectorBT | usamos so RSI/MACD/STOCH basicos; vbt expoe IndicatorFactory, Portfolio.from_signals, param sweeps e resample nativo — inexplorado |

## 2. Pattern Engine v2 (M1-puro)

1. **Vetorizacao numpy**: extract_windows vira `np.lib.stride_tricks.sliding_window_view` — mesmo resultado, ~100x mais rapido.
2. **Scan batch offline**: `python -m utils.orc_pattern --scan SYMBOLS --days 730` → grava `status/pattern_library.json` (top-N padroes com outcome medio por lookahead). NUNCA em runtime (padrao S31 backfill).
3. **Densidade de padrao**: conf deixa de ser 0.5 flat → frequencia historica do padrao × outcome medio (empirico, medido no consolidado).
4. **Exploracao VectorBT**: param sweep de indicadores (RSI 7/14/21, BB 20×2.0 vs 20×2.5, janelas EMA) via `Portfolio.from_signals` sobre o consolidado — acha os parametros com melhor Sharpe/hit-rate POR SIMBOLO. Resultado alimenta orc_quality (S29) como "regime de parametros".

## 3. Lookaheads de calibracao (M1)

| Horizonte | Barras M1 | Uso |
|-----------|-----------|-----|
| Curto | 5 | scalp S1 (timeout 5 min, S5.1) |
| Medio | 15 | scalp S2 (timeout 15 min, S5.1) |
| Longo | 60 | contexto/regime 1h |

Validacao empirica obrigatoria (R21): medir hit-rate por lookahead no scan 730d — se o de 60 nao agregar poder preditivo, cortar (KISS). O dono pediu teste dessa validacao antes de fixar.

## 4. Ciencia dos graficos multi-TF ("grafico bonito COM correlato")

Os TFs M5/M15/H1 do grafico nao alimentam sinal diretamente, mas carregam 2 camadas cientificas, ambas por `resample()` do M1 consolidado (A2 — zero coleta extra):

a) **Regime H1 como contexto**: tendencia H1 (EMA50 vs EMA200 + ADX H1) classifica regime
   (trend-up / trend-down / range). Sinal M1 a favor do regime H1 → bonus de confianca;
   contra → penalidade. Entra no score (S32) como fator `regime_mult`.
b) **Concordancia multi-TF**: direcao do sinal em M1 × M15 × H1 (3 votos). 3/3 = confianca
   alta; 1/3 = alerta de ruido. Exibido no grafico como badge `M1✓ M15✓ H1✗` — o grafico
   vira evidencia visual da concordancia, nao so decoracao.

## 4b. Refinos R21 (registrados 2026-07-30, debate simulacao)

- **Decaimento temporal dos matches**: padrao de 2024 vale menos que de 2026
  (regime muda). Peso por recencia: matches dos ultimos 90 dias × 2,0;
  91-365d × 1,0; > 365d × 0,5. Aplicado no outcome medio do scan.
- **Sessao/horario**: cada ocorrencia de padrao e taggeada por sessao UTC —
  Tokyo (0-7h), London (7-12h), NY (12-21h), rollover (21-24h, baixa liquidez).
  Outcomes do rollover NAO entram na media (distorcem); ficam em contagem separada.
- **Outcome LIQUIDO de spread**: pips do outcome descontam o spread medio do
  simbolo — padrao +0,8 pips com spread 0,35 e marginal. Sem custo, hit-rate e
  ilusorio (R21). Tabela inicial (estimativa conservadora, refinar com spread
  medio MEDIDO do snapshot quando o F0 acumular historico):
  `SPREAD_PIPS = {XAUUSD: 3.5, EURUSD: 1.0, GBPUSD: 1.2, USDJPY: 1.0, AUDUSD: 1.2}`
- **PIP_SPECS por simbolo**: outcomes sempre em pips normalizados
  (XAUUSD $0,10 / JPY 0,01 / demais 0,0001) — comparavel entre mercados.
- **Amostra minima**: padrao com < 30 ocorrencias marcado
  "amostra_insuficiente" — nunca entra na library com % bonito sem base (A7).
- **Ranking nao gera sinal**: ranking (S35) so ordena/filtra; sinal nasce no
  S32; correlacao nunca cria sinal, so modula.

## 5. Performance (absorve S30-PERF)

| Etapa | Hoje | Alvo S34 |
|-------|------|----------|
| extract_windows | loop Python O(n×20) | sliding_window_view numpy |
| scan 730d × 5 simbolos | inviavel (~14M iter) | batch offline < 10 min |
| runtime live | nao roda scan | so le pattern_library.json |

## Regras

- Scan profundo NUNCA em runtime — batch offline, progresso em status/ (padrao S31).
- M1 e o unico TF de calculo (decisao do dono 2026-07-30).
- `regime_mult` documentado aqui — mudar peso = spec primeiro (R-SDD).
- orc_pattern/orc_quality NAO tocam MCP nem router — so orquestram leitura do consolidado.
