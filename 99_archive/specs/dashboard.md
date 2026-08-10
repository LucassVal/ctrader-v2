> **STATUS: CONSOLIDADO_EM `orc_dashboard.md` (2026-07-28)** | Este spec foi substituido. Ver spec ativo.

# SPEC S20: SPEC: DASHBOARD
>**Versao:** 1.0.0  
>**Wire:** `dashboard.py (Streamlit, legado)`  
>**Status:** 🗑️ DEAD — substituido por `S20_dashboard.md`  
>**R21:** validado 2026-07-23  
>**R-USE:** RULES.md §CAT1-Cognicao  
>**KISS:** spec-driven, sem infra desnecessaria  


## CRM
Dashboard Streamlit com 5 abas. Leitura somente do SQLite.

## ABAS
1. **Overview:** PnL diário, drawdown, equity curve, slots usados
2. **Trades:** Tabela filtrável (símbolo, TF, exit_reason, pnl)
3. **Scores:** Distribuição dos 3 pilares, threshold atual
4. **MAR:** Pesos atuais (`custom_rules.json`), convergência
5. **Logs:** Erros recentes de `logs/system.log`

## EXECUÇÃO
```bash
streamlit run dashboard.py --server.port 8501
```

## FONTE DE DADOS
- `trades.db` (SQLite) — trades, slots
- `custom_rules.json` — pesos do MAR

## ATUALIZAÇÃO
Refresh a cada 5 segundos (configurável em `config.yaml`).

## DEPENDÊNCIAS
`streamlit`, `pandas` (opcional — usa sqlite3 se pandas indisponível)
