# SPEC S43 — Grid de Parâmetros & Walk-Forward Validation

> **Versao:** 2.0 | **Wire:** utils/parameter_grid_orc_bloco1.py | **Status:** active (v1.0) → evolving (v2.0 spec)
> **Atualizado:** 2026-08-05 — Roadmap v3.0: grids alinhados com S41 v3.0, XAUUSD first
> **Depende:** S41 (Bloco 1), vectorbt splitters

## PROPOSITO

Automatizar a busca de parâmetros ótimos com walk-forward validation,
evitando overfitting e garantindo que os parâmetros funcionam em dados
que o modelo nunca viu (out-of-sample).

## FLUXO ATUAL (v1.0)

```
m1_{SYM}_{ANO}.parquet
  │
  ▼
RollingSplitter(window_len=365, set_lens=(90,))
  │
  ├── Janela 1: [train 365d] → [test 90d]
  ├── Janela 2: [train 365d] → [test 90d]
  └── Janela N: [train 365d] → [test 90d]
  │
  ▼
Para cada janela:
  ├── Grid search de parâmetros no TRAIN
  ├── Aplicar melhor combo no TEST (NUNCA re-otimizar)
  └── Próxima janela
  │
  ▼
Consolidado: métricas por janela + estabilidade dos parâmetros
```

## GRIDS ATUAIS (v1.0 — obsoletos, usam RSI/MACD/ATR/BBands)

```python
# OBSOLETO — substituído em S41 v2.1 mas ainda referenciado aqui
BUY_GRID = {
    "rsi_period": [5, 7, 10, 14, 21],    # v2.1: [8, 14, 21]
    "rsi_threshold": [25, 30, 35],         # v2.1: [25, 30]
    "macd_fast": [8, 12, 16],              # v2.1: [10, 14, 18]
    "macd_slow": [18, 24, 32],             # v2.1: REMOVIDO
    "adx_period": [10, 14, 20, 30],        # v2.1: [14, 20]
    "adx_threshold": [20, 25],             # mantido
}

SELL_GRID = {
    "atr_period": [5, 10, 14, 20],        # v2.1: REMOVIDO (substituído por RSI)
    "bbands_period": [14, 20],             # v2.1: REMOVIDO
    "keltner_mult": [1.5, 2.0],            # v2.1: REMOVIDO
    "psar_accel": [0.02, 0.04],            # v2.1: REMOVIDO
}
```

## GRIDS v2.0 — Alinhados com S41 v3.0 (EM ESPECIFICAÇÃO)

### Grid de Momentum (substitui BUY + SELL)

```python
MOMENTUM_GRID = {
    "slope_window": [5],                    # fixo: 5 velas M1
    "slope_threshold": [0.02, 0.05, 0.10], # inclinação mínima (%)
    "accel_min": [1.2, 1.5, 2.0],          # corpo atual / corpo anterior
    "wick_ratio": [2.0, 2.5, 3.0],          # pavio / corpo para rejeição
    "anticipate_bars": [3],                  # fixo: 3 velas
}
# Total: 1×3×3×3×1 = 27 combos
```

### Grid de Força (mantido, com VIX)

```python
FORCE_GRID = {
    "vwap_window": [60],                    # fixo: 60 velas M1 (~1 hora)
    "dxy_roc_lookback": [5],                # fixo: 5 períodos
    "vix_spike_factor": [2.0, 2.5, 3.0],   # multi da média para spike
    "vix_max_normal": [30, 35, 40],         # threshold VIX normal
}
# Total: 1×1×3×3 = 9 combos
```

## PLANO DE VALIDAÇÃO — XAUUSD PRIMEIRO

```
Fase 0: XAUUSD apenas. Walk-forward com:
  - 365d train, 90d test, 12 janelas
  - MOMENTUM_GRID (27 combos)
  - FORCE_GRID (9 combos)
  - Total: 36 combos/janela × 12 janelas = 432 avaliações

Métrica de estabilidade:
  - Parâmetro mais frequente entre janelas (moda)
  - Desvio padrão do MAE entre janelas < 20% da média
  - Overfit flag: train_mae < test_mae × 0.5 por >50% das janelas

Só após XAUUSD aprovado → expandir grid para os outros 4 pares.
```

## ORQUESTRADOR — `utils/lab_orc_grid.py` (planejado)

```python
def run_walkforward_grid(
    symbol: str,
    tf: str = "M1",           # v2.0: M1 (antes era M5)
    window_len: int = 365,
    test_len: int = 90,
    n_windows: int = 12,
) -> dict:
    """
    Returns:
        {
            "windows": [
                {
                    "train": ("2024-01-01", "2024-12-31"),
                    "test": ("2025-01-01", "2025-03-31"),
                    "best_params": {"slope_threshold": 0.05, "accel_min": 1.5},
                    "train_mae": 0.12,
                    "test_mae": 0.18,
                    "test_sharpe": 0.45,
                }
            ],
            "stability": {
                "slope_mode": 0.05,
                "slope_stability": 0.85,
                "overfit_flag": False,
            }
        }
    """
```

## CONTROLE DE EXPLOSÃO COMBINATÓRIA

1. **Pareto 80/20**: testar primeiro os 20% de combos que cobrem 80% do espaço
2. **Correlação**: eliminar combos com correlação > 0.9 entre si
3. **Early stopping**: se 10 combos consecutivos piorarem MAE, abortar
4. **Limite hard**: máximo 200 combos por sub-fase por janela
5. **XAUUSD primeiro**: grid completo só no ouro; demais pares usam melhor combo do ouro como ponto de partida

## R-USE

| Componente | Origem | Uso |
|-----------|--------|-----|
| `RollingSplitter` | `vectorbt.generic.splitters` | Divisão IS/OOS |
| `itertools.product` | stdlib | Grid cartesiano |
| `run_bloco1()` | S41 | Avaliar cada combo |

## CHANGELOG

| Versão | Data | Mudança |
|--------|------|---------|
| 2.0 | 2026-08-05 | Spec: MOMENTUM_GRID + FORCE_GRID alinhados com S41 v3.0. XAUUSD first. |
| 1.0 | 2026-07-30 | Versão inicial com grids RSI/MACD/ATR/BBands (obsoletos). |
