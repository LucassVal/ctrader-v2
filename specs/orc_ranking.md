# SPEC S35 | Versao: 3.0 | Wire: utils/orc_ranking.py | Status: active

## PROPOSITO
Rank mecanico: spotter + sniper scores. IA removida (S26).
Score ≥ 85 → APPROVE. Fallback mecanico sem IA.

## FLUXO
```
fusion_output.json ──→ orc_ranking ──→ ranking.json
                           │
                           ├── rank_signals()
                           └── spotter + sniper (mecanicos)
```

## ORQUESTRADOR — `utils/orc_ranking.py`
Entry point: `rank_signals(fusion_output)` → dict com ranking.

## FILHOS
(Nenhum — logica concentrada)

---

## S35 — RANKING v2 (active 2026-08-01)

### Aba: Pré-Análise → "Ranking"

Componente: `sub-tabs/RankingView.tsx` → `/validate/ranking`

### 3 Camadas de Validação

| Camada | Fonte | Peso |
|--------|-------|------|
| REPLAY | backtest_trades.db (2 anos, 18K trades) | Calibração inicial (menor) |
| LIVE | signals_log.parquet (track record real) | Track record oficial (maior) |
| CORRELATION | Matriz de correlação cruzada | Filtro de exposição (penalidade) |

### Threshold: ≥ 85 → APPROVE para execução (F4)

Wireado as sub-abas de mercado: cada aba (XAUUSD..AUDUSD) expoe o ranking local
+ penalidade de correlacao cruzada + confluencia.

### Correlacao como filtro de exposicao (R21 — pesquisa web 2026-07-30)

Referencias externas (Investopedia, Mataf, TradingNX, literatura forex):

| Par | Literatura | Medido M1 (window=200, 2026-07-29) | Veredito |
|-----|-----------|-------------------------------------|----------|
| EURUSD × GBPUSD | +0.80 a +0.95 | +0.929 | CONSISTENTE |
| EURUSD × USDJPY | -0.44 a -0.50 | -0.725 | Mais forte que lit. (janela curta capta episodio de risco) |
| XAUUSD × USDJPY | Variavel (~-0.55, depende de risk sentiment) | +0.372 | REGIME-SENSIVEL — janela unica insuficiente |
| XAUUSD × EURUSD | ~+0.75 (USD fraco puxa ambos) | a medir | — |
| XAUUSD × AUDUSD | +0.60 a +0.80 (AU produtora de ouro) | a medir | — |
| XAUUSD × DXY | -0.6 a -0.8 | via proxy EUR (DXY sintetico) | — |

**Conclusao R21:** janela unica M1/200 (~3h20) NAO e suficiente. A literatura mostra
correlacao TF-dependente (+0.90 no diario vira ~+0.55 no horario) e regime-dependente
(quebra em NFP/FOMC/risco). Decorrelacao subita = sinal de mudanca de regime.

### Janelas multiplas de correlacao (obrigatorio)

| Janela | Barras M1 | Horizonte | Uso |
|--------|-----------|-----------|-----|
| Curta | 200 | ~3h20 | Scalping (decisao imediata) |
| Diaria | 1.440 | 1 dia | Filtro de exposicao |
| Semanal | 7.200 | 1 semana | Regime (quebra de correlacao) |

Implementacao: `orc_indices.correlate_markets_m1(window)` parametrizado (S25.10),
rolling, cache 5 min. EUR×GBP diaria < 0.60 = alerta de regime no dashboard.

### Regras de ranking v2

1. **Sobre-exposicao**: sinais em pares com |corr diaria| > 0.70 na MESMA direcao
   efetiva = mesma aposta (ex.: long EUR + long GBP ≈ 1 trade) → segundo sinal
   recebe -10 pts. (Literatura: 2% × 3 pares correlacionados = 6% numa aposta so.)
2. **Confluencia (nunca sinal primario)**: XAU bullish + EUR bullish (USD fraco nos
   dois) = +5 pts de confirmacao. Divergencia (XAU bullish + DXY proxy bullish) = alerta.
3. **Peso por qualidade historica**: S36 (calibracao) alimenta multiplicador por
   estrategia × simbolo — ranking aprende com o proprio track record.

## Regras

- Correlacao e CONFLUENCIA/FILTRO, nunca geradora de sinal (literatura + R21).
- Pesos (-10/+5) documentados aqui — mudar = spec primeiro (R-SDD).
- orc_ranking NAO toca MCP — le fusion_output + matriz de correlacao (snapshot/parquet).
