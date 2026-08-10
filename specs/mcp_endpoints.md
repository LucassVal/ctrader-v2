# SPEC S1.1: MCP CTRADER WEB — ENDPOINTS + SESSION LIFECYCLE

>**Versao:** 1.1.0 | **Wire:** `utils/mcp_client.py` | **Status:** active
>**P0 — ANTES DE ALTERAR, LEIA:** specs/NC-BP_CTRADER_DEV.md
>**R21:** validado 2026-07-23 | **v1.1 (2026-08-06):** sessao lifecycle + force-reconnect


---

## PROTOCOLO REAL (descoberto via teste)

```
1. POST initialize → responde SSE (event: message / data: {result})
2. Capturar mcp-session-id do header
3. POST notifications/initialized
4. POST tools/call {name: "get_balance", arguments: {}} → responde SSE
5. Extrair JSON do campo "text" dentro de content[0]
```

**Formato da resposta:**
```
HTTP 200
Content-Type: text/event-stream
mcp-session-id: 47df360c-...

event: message
data: {"result":{"content":[{"type":"text","text":"{\"balance\":...}"}]}}
```

---

## 16 TOOLS (nomes oficiais do servidor)

### Account (2)

| Tool | Params | Retorno |
|------|--------|---------|
| `get_balance` | `{}` | `{balance, equity, freeMargin, ...}` |
| `get_assets` | — | Lista de moedas da conta |
| *(sem `get_account_statistics`)* | — | ❌ Não exposto. Sentimento calculado via `get_positions()`. |

### Market Data (3)

| Tool | Params | Retorno |
|------|--------|---------|
| `get_symbols` | `{query?}` | `[{symbolId, symbol, description, pip, lotSize, ...}]` |
| `get_spot_prices` | `{symbol}` | `{bid, ask, spread, timestamp}` |
| `get_trendbars` | ⚠️ ver contrato real abaixo | `[{timestamp, open, high, low, close, tickVolume}]` |

#### ⚠️ `get_trendbars` — CONTRATO REAL (medido via `tools/list` + chamadas ao servidor)

O schema publicado diverge do comportamento do backend. Verificado em 2026-07-23:

```jsonc
{
  "symbolId":      41,                      // integer — OBRIGATORIO
  "period":        "M_5",                   // enum COM underscore
  "fromTimestamp": "2026-06-23T08:00:00Z",  // STRING (ISO-8601 ou epoch-ms)
  "toTimestamp":   "2026-07-23T08:00:00Z",  // STRING — exigido junto de from
  "count":         1000                     // integer, max 1000
}
```

| Regra | Valor | Evidencia (mensagem do servidor) |
|-------|-------|----------------------------------|
| `fromTimestamp` | **obrigatorio** — apesar de `required` listar so `symbolId`+`period` | `fromTimestamp: must not be null` |
| Janela `from`->`to` | **max 720h (30 dias)** | `Time range exceeds upstream cap of 720h (PT720H)` |
| `count` | **max 1000**, default **100** | `count must not exceed 1000` |
| `from`+`to`+`count` | **VALIDO** — a descricao do schema diz "invalid", mas funciona | testado: devolveu 500 barras |
| Tipo dos timestamps | **string**, nao integer | integer -> `-32602 Input validation error` |
| `period` valido | `M_1 M_5 M_15 M_30 H_1 H_4 D_1 W_1 MN_1` | enum do `inputSchema` |
| Retorno | as N barras **mais recentes** da janela | M_1 em janela de 30d devolveu 100 barras (1h40) |

> 🔴 **ARMADILHA:** `count` default 100 **trunca em silencio, sem erro**. Pedir 30 dias de M_1
> devolve 100 barras. Sempre passar `count` explicito.
>
> ✅ **RESOLVIDO 2026-07-23 (ROADMAP 1.0):** `get_trendbars()` agora envia
> `fromTimestamp`+`toTimestamp` (janela derivada de `count` x periodo x3, cap 720h),
> valida `count<=1000` e desembrulha `{"trendbars":[...]}` -> lista. Validado ao vivo
> (60 barras M_1). `get_order_history`/`get_deals` tinham o mesmo bug (`{"days":N}`) —
> corrigidos. Regressao bloqueada pelo **G10 MCP-CONTRACT** (`gates/run_mcp_contract.py`).

**Ticks brutos:** nao existem no MCP. Usar `tickVolume` da barra como proxy de atividade.

**Backfill 6 meses / 5 ativos** (teto 1000 barras/req, <=5 req/s historico):
M_5 = 38 req/ativo (~38s total) · M_15 = 13 · M_1 = 188 (~3min) · D_1 = 6 (janela manda).

### Positions / Orders / History (7)

| Tool | Params | Retorno |
|------|--------|---------|
| `get_positions` | `{symbol?}` | `[{positionId, symbolId, volume, entryPrice, sl, tp, pnl, ...}]` |
| `get_position_details` | `{positionId}` | `{position, orders[], deals[]}` |
| `get_pending_orders` | — | `[{orderId, type, symbol, volume, price, ...}]` |
| `get_order_history` | `{days?}` | `[{orderId, type, status, ...}]` cap 720h |
| `get_deals` | `{days?}` | `[{dealId, symbol, entryPrice, exitPrice, pnl, ...}]` cap 720h |

### Trading Mutations (4)

| Tool | Params | Retorno |
|------|--------|---------|
| `create_order` | `{symbol, side, volume, orderType?, stopLoss?, takeProfit?, limitPrice?, stopPrice?}` | `{orderId, positionId}` |
| `close_position` | `{positionId, volume?}` | `{status}` |
| `amend_position` | `{positionId, stopLoss?, takeProfit?}` | `{status}` |
| `cancel_order` | `{orderId}` | `{status}` |
| `amend_order` | `{orderId, price?, volume?, stopLoss?, takeProfit?}` | `{status}` |

### Util (1)

| Tool | Params | Retorno |
|------|--------|---------|
| `get_version` | — | `{name, version, build}` |

---

## QUIRKS CONFIRMADOS

| # | Quirk | Status |
|---|-------|--------|
| 1 | MARKET usa `stopLoss`/`takeProfit` (não `relativeStopLoss` como documentado) | ⚠️ A testar |
| 2 | `amend_position` — sempre enviar ambos SL+TP | ✅ Confirmado |
| 3 | `get_trendbars` / `get_order_history` / `get_deals`: cap 720h | ✅ Confirmado |
## BUGS CORRIGIDOS (2026-07-23 — testado com MCP real)

| # | Bug | Sintoma | Correção | Arquivo |
|---|-----|---------|----------|---------|
| B1 | `get_spot_prices` mandava string, MCP espera array | Erro -32602 "expected array" | `{"symbol": [symbol]}` | `mcp_client.py` |
| B2 | F0 sem retry na resolução de símbolos | Abortava na 1ª falha | Backoff 1s→2s→4s, 3 tentativas | `f0_collector/orc_coleta.py` |
| B3 | Logger quebrava com `KeyError: 'phase'` | Logs padrão (sem phase) crashavam | Removido `%(phase)s` do file handler | `utils/logger.py` |

---

### Reconexao Proativa (backfill v2.4-v2.6)

`_ensure_session_fresh()` no `backfill_orc_coleta.py`:
- Verifica idade da sessao (>420s = 7 min)
- Se proxima de expirar: `init_client(force=True)` → novo handshake
- Wireada no loop de ranges (v2.6), nao so entre simbolos
- Ver S2.6 para o padrao fresh-session-per-batch


## CLIENTE PYTHON

`utils/mcp_client.py` — reescrito com:
- Handshake automático (initialize → mcp-session-id → initialized)
- Parser SSE (`_parse_sse_body`)
- `call_tool(name, args)` — formato `tools/call`
- Extrai JSON do campo `content[0].text`
- 15 funções wrapper (1:1 com as tools do servidor)

### Throttle: HISTORIC_TOOLS (5 req/s) vs tools normais (50 req/s)

`HISTORIC_TOOLS` reduz o refill do token-bucket compartilhado para 5/s durante
a chamada — pensado para `get_trendbars`/`get_order_history`/`get_deals`/
`get_symbols` (janelas grandes ou catalogo completo, custam mais no
servidor). `get_positions` tambem estava nessa lista, mas e estado AO VIVO
da conta (poucas posicoes abertas tipicamente) — nada distingue seu custo
de `get_balance`, que corretamente usa o rate normal (50/s).

> **BUG 2026-07-28:** `take_snapshot()` (ROADMAP 1.7b) chama `get_positions()`
> a cada tick (~3s). Com `get_positions` no HISTORIC_TOOLS, cada tick paga o
> rate de 5/s do bucket COMPARTILHADO com `get_trendbars`/`get_symbols` —
> isoladamente nao explica espera de minutos (`wait = (1-tokens)/rate`
> maximo ~0.2s por chamada), mas e categorizacao incorreta que agrava
> qualquer disputa pelo bucket sob carga concorrente. `get_positions`
> movido para o rate normal (50/s); `get_trendbars`/`get_order_history`/
> `get_deals`/`get_symbols` continuam historicos (custo real maior,
> chamados com pouca frequencia).


---

## SESSAO MCP — Lifecycle & Reconnect (v1.1)

### RCA — Por que a sessao expira mesmo com requests ativos

O servidor cTrader MCP impoe **timeout fixo de sessao** (~10 min / 600s),
independente da atividade. Nao e inatividade — e tempo de vida absoluto da
sessao desde o handshake.

```
T=0     init_client() → handshake → session_id = "abc-123"
T=1..9  requests ativos a cada 0.2s (throttle 5 req/s)
T=10    servidor invalida session_id — todas as requests retornam
        "Session not found; re-initialize"
T=10+   init_client() chamado novamente, MAS _mcp_initialized=True
        → retorna imediatamente sem refazer handshake → loop infinito
```

### Solucao — `init_client(force=True)`

```python
def init_client(config_path: str = "config.yaml", force: bool = False) -> None:
    if _mcp_initialized and _mcp_url and not force:
        return  # keep-alive normal
    # force=True → reseta estado e refaz handshake completo
    _mcp_initialized = False
    _mcp_session_id = ""
    # ... carrega config, handshake, initialized ...
```

### Estados da Sessao

| Estado | _mcp_initialized | _mcp_session_id | Comportamento |
|--------|-----------------|-----------------|---------------|
| COLD | False | "" | init_client() → handshake completo |
| LIVE | True | "abc-123" | Requests funcionam |
| STALE | True | "abc-123" | Requests falham "Session not found" |
| RECONNECT | False → True | "" → "def-456" | init_client(force=True) → novo handshake |

### Health Check + Auto-Reconnect (backfill v2.3)

```
_health_check_mcp():
  1. Tenta get_balance()
  2. Se falhar → init_client(force=True)  ← NOVO: force reconecta
  3. Tenta get_balance() novamente
  4. Se falhar de novo → retorna False (MCP offline)
```

### Regras

- `force=True` SEMPRE refaz handshake — reseta `_mcp_initialized` e `_mcp_session_id`
- Backfill chama `_health_check_mcp()` antes de cada simbolo + a cada 60s
- Sessao expirada NAO e erro fatal — e condicao normal de operacao
- Max 3 tentativas de reconexao por ciclo de backfill
