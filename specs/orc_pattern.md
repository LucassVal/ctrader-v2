# SPEC S30 — Pattern Matcher + Backtest Simulator

> **Versao:** 2.1.0 | **Wire:** backtest_simulator.py + orc_metricas.py | **Status:** active

## MODOS DE BACKTEST

| Modo | Engine | Performance | Metrica |
|------|--------|-------------|---------|
| `--fast` (default) | Manual numpy loop | 3.8s / 18K trades | Win rate, PnL, equity |
| `--vbt` (opt-in) | `vectorbt.Portfolio.from_signals()` | 45s+ (numba JIT) | + Sharpe, drawdown, trade records |

### VBT Portfolio (mode --vbt)

Usa `vectorbt.Portfolio.from_signals()` com:
- Slippage 0.1%
- Commission 0.01%
- Initial capital $10,000
- Direction: both (long + short)

**Ativacao**: `python backtest_simulator.py --vbt`

**Output extra** (vs modo manual):
```json
{
  "sharpe_ratio": 1.42,
  "max_drawdown_pct": -12.3,
  "profit_factor": 1.85,
  "expectancy": 8.4
}
```

**Motivo de ser opcional**: numba JIT compila 17 indicadores na primeira chamada (~30s). 
Custo-beneficio: modo manual da os mesmos resultados de equity/PnL em 3.8s.

## PER-SYMBOL BREAKDOWN (S30 v2.1)

`/performance?mode=backtest` agora retorna `symbol_stats`:

```json
{
  "symbol_stats": {
    "XAUUSD": {"trades": 3614, "wins": 2038, "losses": 1576, "win_rate": 56.4, "pnl": 24970},
    "EURUSD": {"trades": 3743, "wins": 2118, "losses": 1625, "win_rate": 56.6, "pnl": 26080},
    ...
  }
}
```

## UI — Sub-tabs limpas (S30 v2.1)

"Saúde" duplicada removida das sub-tabs. Só existe em Overview → Saúde (global).

```
Overview      → Saúde, Health Check, Banca & Mercado
Pré-Análise   → Score & Calibração, XAUUSD..AUDUSD, Estratégia, Globais, Correlação
Validação     → Score 75%+, Normalização
Ordens        → Trail Log, Parâmetros
Harness       → Health, G6 Testes, Pipeline
```
