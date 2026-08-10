# SPEC S90 — Boot Unificado (Entry Point Unico)

> **Versao:** 1.1.0 | **Wire:** boot.ps1 + Abrir_NeoCortex_NovaPulse.bat | **Status:** active

## ARQUITETURA

```
Abrir_NeoCortex_NovaPulse.bat (wrapper)
  → solicita elevacao admin
  → chama boot.ps1

boot.ps1 (entry point unico, ~130 linhas)
  │
  ├── LOG IMEDIATO (Desktop\nc_boot.log — cada linha no disco)
  │
  ├── PRE-FLIGHT (em ordem):
  │   ├── Python + Node + Deps
  │   ├── Parquet 7 simbolos (5 ativos + 2 indices DXY/VIX)
  │   ├── BACKFILL COMPLETO: se parquet ausente (first run)
  │   ├── G23 GAP SCAN: run_consolidate_parquet.py
  │   ├── BACKFILL GAPS: preenche lacunas do dia anterior
  │   ├── Ruff + Oxlint
  │   └── Harness (pytest)
  │
  ├── FASE 0: PRE-FLIGHT
  │   ├── Python venv (--version)
  │   ├── Node (--version)
  │   ├── React node_modules
  │   ├── 4 arquivos criticos (router, API, main.tsx, config)
  │   └── 10 Parquet files (5 M1 + 5 VBT) + backtest_trades.db
  │
  ├── FASE 1: LIMPEZA
  │   └── Portas 7744, 5173
  │
  ├── FASE 2: BOOT
  │   ├── API :7744 (Python run_api.py, health check 15 tentativas)
  │   └── Vite :5173 (npx vite, health check)
  │
  └── FASE 3: FINALIZAR
      ├── Log salvo
      ├── Resumo na tela
      └── Read-Host (janela fica aberta)
```

## PRE-FLIGHT CHECKS

| Check | O que verifica |
|-------|---------------|
| Python | `.venv\Scripts\python.exe --version` |
| Node | `node --version` |
| React | `node_modules\` presente |
| 4 Criticos | `ctrader_v2.py`, `NC-10_dashboard_api.py`, `main.tsx`, `config.yaml` |
| 5 M1 Parquet | `consolidated/{SYM}_M1.parquet` tamanho |
| 5 VBT Parquet | `vbt_{SYM}.parquet` presente |
| Backtest DB | `backtest_trades.db` tamanho |

## LOG

- **Local**: `Desktop\nc_boot.log`
- **Encoding**: UTF-8
- **Gravação**: cada linha no disco (append imediato)
- **Sobrevive a crash**: se o script morrer, o log até o ponto da falha está salvo

## COMPORTAMENTO

| Cenário | Comportamento |
|---------|--------------|
| Boot OK | Resumo verde, janela aberta (ENTER para fechar) |
| Boot com erro | Mensagem no log + janela aberta |
| Crash | Log gravado até a linha da falha |

## HISTORICO

| Versao | Data | Mudanca |
|--------|------|---------|
| 1.1.0 | 2026-08-01 | Simplificado: sem Ollama/NovaPulse/F0, log imediato, 5 mercados |
| 1.0.0 | 2026-08-01 | Versao inicial (complexa, quebrada) |
