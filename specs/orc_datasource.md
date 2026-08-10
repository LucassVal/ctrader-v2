# SPEC S26: DataSource Layer — Single Source of Truth

>**Versao:** 1.0.0
>**Wire:** `utils/data_source.py` → ROUTER → ORQs puros
>**Status:** IMPLEMENTANDO

## PROBLEMA

Auditoria S25 revelou que 4+ orquestradores leem `status/snapshot.json` direto,
cada um com sua propria funcao `_read_snapshot()` duplicada. Se o schema do
snapshot mudar, todas as copias quebram. Nao ha contrato formal entre quem
produz (F0) e quem consome (F1-F5, DASH, MERCADO, METRICS).

```
ATUAL (fragil):
  F0 → snapshot.json
    ├── orc_mercado._read_snapshot()    ← duplicata #1
    ├── orc_dashboard._get_snapshot_safe() ← duplicata #2
    ├── orc_metricas._read_status()     ← duplicata #3
    └── Router → cada ORQ le disco proprio
```

## SOLUCAO

Uma unica camada `DataSource` que:
1. Le snapshot.json UMA vez por request (cache em memoria, TTL 5s)
2. Expoe metodos tipados: `get_balance()`, `get_markets()`, `get_positions()`
3. ORQs viram funcoes puras — recebem dados, retornam resultados

```
PROPOSTO (robusto):
  F0 → snapshot.json
         │
    ┌────▼────────────────────────────────┐
    │  DataSource (utils/data_source.py)  │  ← UNICO leitor
    │  - read()        le snapshot        │
    │  - get_balance() → dict normalizado │
    │  - get_markets() → dict 5 simbolos  │
    │  - get_positions() → list           │
    │  - cache 5s TTL                     │
    └────┬────────────────────────────────┘
         │
    ┌────▼────┐  ┌──────────┐  ┌───────────┐
    │ MERCADO │  │ METRICS  │  │ DASHBOARD │  ← ORQs puros
    │ (puro)  │  │ (puro)   │  │ (puro)    │
    └────┬────┘  └────┬─────┘  └─────┬─────┘
         └────────────┼──────────────┘
                      ▼
                   ROUTER (unico aggregator)
```

## INTERFACE

```python
# utils/data_source.py
class DataSource:
    def __init__(self): ...
    def refresh(self) -> None: ...           # força releitura
    def get_snapshot(self) -> dict: ...      # raw snapshot
    def get_balance(self) -> dict: ...       # normalizado USD
    def get_markets(self) -> dict: ...       # 5 simbolos raw
    def get_positions(self) -> list: ...     # posicoes abertas
    def is_online(self) -> bool: ...         # F0 ativo?
    def get_candles_buffer(self, sym, n) -> list: ...  # velas historicas
```

## MIGRACAO (fases, sem quebrar)

| Fase | O que | Impacto |
|------|-------|---------|
| 1 | Criar `data_source.py` com cache 5s | Zero — novo arquivo |
| 2 | Refatorar `orc_mercado.normalize_markets(snapshot=None)` | Backward compat |
| 3 | Router usa DataSource como fonte unica | 1 arquivo |
| 4 | Migrar `orc_dashboard._get_snapshot_safe()` → DataSource | Gradual |
| 5 | Remover `_read_snapshot()` duplicadas | Limpeza final |
