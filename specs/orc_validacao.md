# SPEC S5 | Versao: 2.0 | Wire: f3_validacao/orc_validacao.py | Status: active

## PROPOSITO
F3 — Validacao: threshold ≥ 75 + action = APPROVE → libera para F4.
IA removida (S26). Apenas mecanico. _get_balance_safe() via snapshot F0.

## FLUXO
```
fusion_output.json ──→ orc_validacao ──→ APPROVE ──→ F4 (orc_execucao)
                              │
                              └── REJECT ──→ trades.db (F5 analisa)
```

## ORQUESTRADOR — `f3_validacao/orc_validacao.py` (196L)
Entry point: `validate(fusion_output)` → dict com valid + errors.

## FILHOS
(Nenhum)
