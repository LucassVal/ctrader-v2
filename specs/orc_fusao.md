# SPEC S4 | Versao: 2.0 | Wire: f2_fusao/orc_fusao.py | Status: active

## PROPOSITO
F2 — Fusao ponderada: score final = Sigma(componente × peso_F5).
Pesos calibrados pelo F5 (MAR) via vectorbt replay.
Saida: fusion_output.json (contrato imutavel).

## FLUXO
```
scores_raw.json ──→ orc_fusao ──→ fusion_output.json ──→ F3, F4, F5
                        ▲
                        │
                  custom_rules.json (pesos F5)
```

## ORQUESTRADOR — `f2_fusao/orc_fusao.py`
Entry point: `fuse(scores, rules)` → dict com score final + action.

## FILHOS
(Nenhum — orquestrador unico, logica concentrada)
