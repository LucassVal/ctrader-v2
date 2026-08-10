# FIX CONNECTION — cTRADER (fallback direto)
>
>**Fonte:** cTrader Web → Settings → Connection Details  
>**Conta:** demo.deriv.2291147 | **Ambiente:** Demo

---

## PRICE FEED (cotação)

```
Host:     demo-uk-eqx-01.p.c-trader.com
Port:     5211 (SSL) / 5201 (Plain)
SenderCompID:  demo.deriv.2291147
TargetCompID:  cServer
SenderSubID:   QUOTE
Password:      2291147
```

## TRADING (ordens)

```
Host:     demo-uk-eqx-01.p.c-trader.com
Port:     5212 (SSL) / 5202 (Plain)
SenderCompID:  demo.deriv.2291147
TargetCompID:  cServer
SenderSubID:   TRADE
Password:      2291147
```

## PROTOCOLO

FIX 4.4 sobre TCP/TLS. Dois canais separados (market data + ordens).

---

## STATUS

⚠️ DNS do Hermes não resolve `*.c-trader.com`. Executar localmente no PC do Lucas.
O MCP HTTP (opção 1) sofre do mesmo problema de DNS.
