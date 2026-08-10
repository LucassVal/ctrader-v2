# SPEC S0 | Versao: 2.0 | Wire: tests/harness_boot.py | Status: active

## PROPOSITO
Harness — camada de validacao pre-flight. NAO e um orquestrador — e um gate de qualidade
(G6) que valida todos os orquestradores antes do ciclo de trade iniciar.

## FLUXO
```
harness_boot.py (Fase 0)
  │
  ├── Importa 10 orquestradores (F0-F5 + DASHBOARD + METRICS + RANKING + F4-sub)
  ├── Valida: attrs existem?
  ├── Valida: children importaveis?
  ├── Valida: contracts JSON validos?
  └── Reporta: 10/10 PASS ou FAIL

harness_runner.py (G6)
  │
  ├── 1. harness_boot.py (pre-flight)
  ├── 2. pytest (unit tests)
  └── Reporta: PASS/FAIL combinado
```

## ARQUITETURA DDD

```
HARNESS NAO E ORQUESTRADOR — e camada de validacao

tests/
├── harness_boot.py              Pre-flight de TODOS os orquestradores
├── test_f0_snapshot.py          Testes do snapshot F0
├── harness_runner.py            G6 (orquestra boot + pytest)
└── ...
```

## ISOLAMENTO DE RUNTIME (A11)

**Regra do app (A11):** Nenhum teste pode escrever em `status/`, `data/`, `logs/` ou
`trades.db` reais. Testes que exerciatam funcoes de escrita DEVEM redirecionar o path
via `monkeypatch` ou `tmp_path` do pytest.

### Funcoes de escrita sob vigilancia

| Funcao | Arquivo de producao | Path afetado |
|--------|--------------------|--------------|
| `take_snapshot()` | `f0_collector/orc_coleta.py` | `status/snapshot.json` |
| `save_parquet()` | `f1_analyzer/` | `data/` |
| `log_trade()` | `f4_executor/` | `trades.db` |
| `ensure_schema()` | `f4_executor/` | `trades.db` |
| `log_metrics_json()` | `utils/json_log/` | `logs/` |
| `append_to_df()` | fases 1-5 | arquivos de dados |

### Contrato

```
G19 (run_test_isolation.py) — AST scan de tests/*.py
  Se take_snapshot() chamado sem monkeypatch/tmp_path → [ERR]
  Se save_parquet() chamado sem monkeypatch/tmp_path → [ERR]
  Se log_trade() chamado sem tmp_path → [ERR]
```

### Correcao padrao

```python
# ANTES (ERR): escreve em status/snapshot.json de producao
def test_foo():
    snap = take_snapshot()  # [ERR] G19

# DEPOIS (OK): redireciona para tmp_path
def test_foo(tmp_path, monkeypatch):
    monkeypatch.setattr("f0_collector.orc_coleta._SNAPSHOT_PATH", tmp_path / "snap.json")
    snap = take_snapshot()  # [OK] G19
```
├── test_f1_*.py
└── ...

utils/
└── harness_runner.py            G6: orquestra boot + pytest
```

## REGRAS

| Regra | Descricao |
|-------|----------|
| Boot primeiro | harness_boot.py roda ANTES do F0 iniciar coleta |
| Falha = bloqueia | Se boot falhar, ctrader nao sobe |
| Offline = ok | Contracts runtime (snapshot.json) podem nao existir — warn, nao erro |
| ASCII only | Sem emoji/unicode em prints (G14) |

## EXPANSAO (planejado)

Cada fase tera seu proprio harness:
- `harness_f0_coleta.py` — valida poller + storage + snapshot
- `harness_f1_analise.py` — valida pillars + micro + sentiment
- `harness_f2_fusao.py` — valida fuse() + contract
- `harness_f3_validacao.py` — valida validate() + fallback
- `harness_f4_execucao.py` — valida OCO + trail + safety
- `harness_f5_mar.py` — valida calibrate() + sync
