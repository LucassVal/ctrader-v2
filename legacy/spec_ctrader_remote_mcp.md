# cTrader Remote MCP Server — Complete Specification

> **Sources:** `help.ctrader.com/ctrader-ai-agent-connect/remote-mcp/setup/` + all sub-pages, `github.com/spotware/ctrader-skills` SKILL.md + references + scripts  
> **As-of:** rest-proxy 1.0.18 (last re-verification 2026-05-14)  
> **Compiled:** 2026-07-22

---

## 1. Overview

The cTrader Remote MCP server connects AI agents to **cTrader Web** via the **Model Context Protocol (MCP)** over HTTP (REST proxy architecture, not WebSocket/SSE). It exposes trading, account, and market data as MCP tools. Requires an **active cTrader Web session** (cTID login).

| Property | Value |
|----------|-------|
| **Platform** | cTrader Web (browser) only — NOT cTrader Windows/Mac |
| **Protocol** | MCP over HTTP (REST proxy — `rest-proxy`) |
| **Minimum Build** | rest-proxy 1.0.18 |
| **Transport** | HTTP (JSON-RPC-style tool calls via MCP) |
| **Session requirement** | Active cTrader Web session (cTID authenticated) |
| **Cost** | Free (included with cTrader account) |
| **Skills repo** | `https://github.com/spotware/ctrader-skills` |
| **Skills package** | `npx skills add https://github.com/spotware/ctrader-skills --all --global` |

---

## 2. Configuration & URL Format

### 2.1 Configuration Acquisition

The MCP JSON configuration is **generated dynamically inside cTrader Web** and is not hardcoded in public documentation. Flow:

1. Log into cTrader Web with cTID
2. Open **Settings → Remote MCP**
3. Select the trading account (separate token per account)
4. **Copy the configuration** (contains the URL + token)
5. Paste into the AI agent's MCP configuration

### 2.2 Local MCP Config (for reference)

```json
{
  "mcpServers": {
    "ctrader": {
      "type": "http",
      "url": "http://127.0.0.1:9876/mcp/"
    }
  }
}
```

### 2.3 Remote MCP Config (inferred structure)

Based on the local config pattern and documentation references, the remote config embeds the per-account token, likely in one of these forms:

```json
{
  "mcpServers": {
    "ctrader-remote": {
      "type": "http",
      "url": "https://<remote-mcp-host>/mcp/<account-token>/"
    }
  }
}
```

Or with explicit headers:

```json
{
  "mcpServers": {
    "ctrader-remote": {
      "type": "http",
      "url": "https://<remote-mcp-host>/mcp/",
      "headers": {
        "Authorization": "Bearer <token>"
      }
    }
  }
}
```

The **exact URL is dynamically generated per account** and copied from the cTrader Web UI.

---

## 3. Authentication & Token Management

### 3.1 Token Generation

- **Where:** cTrader Web → Settings → Remote MCP
- **Granularity:** One token per trading account
- **Issuance:** Generated server-side; copied as part of the MCP JSON config snippet
- **Type:** Bearer token (inferred from FAQ: "per-account bearer token issued from cTrader Web")

### 3.2 Session Lifecycle

| Event | Behavior |
|-------|----------|
| **Token created** | Active immediately when cTrader Web session is active |
| **cTrader Web session expires** | Token becomes invalid; re-authenticate in cTrader Web |
| **Token expired** | Copy new token from Settings → Remote MCP; update AI config |
| **Token rotation** | Switch account in cTrader Web → copy new account's config |
| **Required for connection** | Active cTrader Web session MUST be running |

### 3.3 Account Switching

- Each trading account gets a **separate token**
- Select the desired account in cTrader Web's account selector
- Copy its configuration from Settings → Remote MCP
- Update the AI client's MCP configuration with the new token

---

## 4. Protocol Specification

### 4.1 Transport & Protocol Type

- **Transport:** HTTP (REST proxy)
- **Protocol:** MCP (Model Context Protocol) tool-calling over HTTP
- **NOT:** WebSocket, SSE, or gRPC
- **Content-Type:** JSON (standard MCP JSON-RPC envelope)

### 4.2 Profile Distinction

The Remote server exposes **two tool profiles**:

| Profile | Contents | Confirmation |
|---------|----------|-------------|
| **data** | All read-only tools: `get_version`, `get_balance`, `get_assets`, `get_symbols`, `get_spot_prices`, `get_trendbars`, `get_positions`, `get_position_details`, `get_pending_orders`, `get_order_history`, `get_deals` | None required |
| **trading** | Everything in `data` + mutations: `create_order`, `amend_order`, `cancel_order`, `amend_position`, `close_position` | Explicit user confirmation required for each mutation |

### 4.3 Tool Discovery

The agent identifies the Remote server family via `tools/list`:
- **Remote fingerprint:** `get_version`, `get_assets`, integer `symbolId`-keyed tools, `moneyDigits` in responses
- **Local fingerprint:** `ping`, `get_accounts_list`, `list_charts`, `listChartIndicators`, `listPlugins`, `show_notification`, `get_server_time`
- **Both bound:** Both fingerprints visible → route by capability

---

## 5. Error Codes & Classification Matrix

### 5.1 Error Envelope Formats (rest-proxy 1.0.18 split)

Two envelope formats exist depending on error origin:

**Format 1 — JSON envelope (legacy, rest-proxy ≤ 1.0.14):**
```json
HTTP 400
{
  "error": {
    "code": "INVALID_REQUEST",
    "message": "...",
    "httpStatus": 400
  }
}
```

**Format 2 — Plain string (rest-proxy 1.0.18+ pre-upstream validation):**
```
"create_order: Absolute stopLoss is not supported for MARKET orders (fill price is unknown at send time). Use relativeStopLoss..."
"Time range exceeds upstream cap of 720h (PT720H = 30 days). Requested 800h. Split into 720h-or-smaller windows..."
```

### 5.2 Error Classification Matrix

| Error Envelope | Class | Retry? | Action |
|---------------|-------|--------|--------|
| MCP `-32602: Input validation error` (Zod) | Caller schema mismatch | NO | Fix caller input |
| Remote `400` `{"error":{"code":"INVALID_REQUEST",...}}` (legacy) | Server rejection | NO | Surface to user with reason |
| Remote plain-text: tool name + actionable hint (1.0.18+) | Server rejection | NO | Surface hint verbatim to user |
| Remote `502` `{"error":{"code":"502 BAD_GATEWAY","message":"uProxy error: <CODE>"}}` | Upstream broker | NO (max 1 retry) | Suggest direct action |
| `{"available": false}` | Resource absent | N/A | Use fallback path |
| `hasMore: true` | Pagination | N/A | Continue with `hasMore` loop |

### 5.3 Decision Tree for Remote Envelope Shape

1. Try-parse response as JSON → if has `error` object with `code` + `httpStatus` → JSON envelope (INVALID_REQUEST 400 or uProxy 502)
2. Else → plain string (1.0.18+ pre-upstream validation)
3. Both formats are semantically equivalent — request was REJECTED before reaching broker

### 5.4 Server-Side Validations (return 400 Bad Request)

| Field/Endpoint | Constraint |
|---------------|------------|
| `volume` (all endpoints) | `@Positive` — integer > 0 |
| `slippageInPoints` (`amend_order`) | `@Positive` — integer > 0 |
| `comment` (`create_order`) | ≤ 256 characters |
| `label` (`create_order`) | ≤ 100 characters |
| `get_trendbars` window | `fromTimestamp < toTimestamp`, interval ≤ 720h, count ≤ server limit |
| LIMIT/STOP/STOP_LIMIT | `limitPrice`/`stopPrice` MUST be present |

---

## 6. Rate Limits

| Class | Limit | Tools |
|-------|-------|-------|
| **General** | 50 requests/second | Most reads + mutations |
| **Historical** | 5 requests/second | `get_trendbars`, `get_order_history`, `get_deals` |

Pacing guidance: insert ~250ms between successive `get_trendbars` calls for multi-window backfills.

---

## 7. Complete Tool Surface (Remote MCP)

### 7.1 Version & Diagnostics
| Tool | Description |
|------|-------------|
| `get_version` | Returns `version`, `buildTime` (ISO 8601 string or "N/A"), `service` |

### 7.2 Account State
| Tool | Returns |
|------|---------|
| `get_balance` | `traderId`, `balance`, `equity`, `freeMargin`, `moneyDigits`, `depositAssetId`, `balanceVersion` (monotonic counter) |
| `get_assets` | `assetId` → asset name mapping (stable, cache for session) |

### 7.3 Symbols & Static Metadata
| Tool | Returns |
|------|---------|
| `get_symbols` | `symbolId`, `symbolName`, `enabled`, `baseAssetId`, `quoteAssetId`, `symbolCategoryId`, `description` (cache for session) |

### 7.4 Live & Historical Market Data
| Tool | Parameters | Returns |
|------|-----------|---------|
| `get_spot_prices` | `symbolId: int[]` (batched) | `prices[]` with `symbolId`, `bid`, `ask`, `timestamp` (epoch ms) |
| `get_trendbars` | `symbolId: int`, `period: enum`, `fromTimestamp`, `toTimestamp`, `count` | OHLCV bars per `period` |

### 7.5 Positions, Orders, Deals (Read)
| Tool | Description |
|------|-------------|
| `get_positions` | Open positions + pending orders |
| `get_position_details` | Single position + related orders + deals |
| `get_pending_orders` | Working pending orders |
| `get_order_history` | Order history (paginated via `hasMore`) |
| `get_deals` | Deal history with `dealStatus` enum (paginated via `hasMore`, `maxRows` default 50) |

### 7.6 Trading Mutations (trading profile)
| Tool | Notes |
|------|-------|
| `create_order` | `orderType`: MARKET, LIMIT, STOP, MARKET_RANGE, STOP_LIMIT |
| `amend_order` | Modify pending order |
| `cancel_order` | Cancel pending order |
| `amend_position` | Modify SL/TP on open position (**CRITICAL:** omit-removes quirk) |
| `close_position` | **REQUIRES** `volume` parameter (cents); pass position's full volume to fully close |

---

## 8. Encoding Rules (Remote-Specific)

### 8.1 Volume
- **Wire encoding:** Integer **cents** of base asset
- **Forex:** 1 lot = **10,000,000 cents** (100× Local's units)
- **Validation:** `@Positive` — rejects non-positive values
- **Conversion:** `scripts/units_encoding.py lots-to-cents`

### 8.2 Price
- **Wire encoding:** Integer **pipettes** (display = `value / 10^pipDigits`)
- **`pipDigits`** from `get_symbols` per-symbol metadata — cache per session
- **Foot-gun (Q-K19):** 5+ digit integer in order-DTO = probable pipettes leak → silent wrong fills
- **Conversion:** `scripts/pip_math.py`

### 8.3 Money
- **Wire encoding:** Integer in `10^moneyDigits` units
- **`moneyDigits`** from `get_balance` response (typically 2)
- **Conversion:** `scripts/units_encoding.py display-money` / `parse-money`

### 8.4 Timestamps
| Field | Encoding |
|-------|----------|
| `fromTimestamp`/`toTimestamp` (history endpoints) | **Either** epoch ms (int) or ISO 8601 string |
| `expirationTimestamp` (`create_order`/`amend_order`) | **Integer epoch ms ONLY** (ISO 8601 rejected per Q-R2) |
| `prices[].timestamp` (response) | Epoch milliseconds |
| `trendbars[].timestamp` (response) | Epoch milliseconds |
| `deals[].executionTimestamp` (response) | Epoch milliseconds |
| `buildTime` (`get_version` response) | ISO 8601 string or "N/A" |

### 8.5 Symbol Identifiers
- **Numeric integer `symbolId`** (NOT string ticker)
- Resolve via `get_symbols` → cache mapping for session
- Unknown `symbolId` in `get_spot_prices` batch: returns **empty `prices[]` array silently** — validate against cache first (Q-R8)

---

## 9. Enums & Constants

### 9.1 `period` Enum (9 values — Q-R1)

```
M_1, M_5, M_15, M_30, H_1, H_4, D_1, W_1, MN_1
```

**NOT 26 values!** M_2, M_3, H_3, etc. return `-32602: Input validation error` (Zod enum mismatch).

### 9.2 `orderType` Enum (5 values)

| Value | Required Price Fields | Behavior |
|-------|----------------------|----------|
| `MARKET` | (none) | Fill immediately at bid/ask |
| `LIMIT` | `limitPrice` | Fill only at or better than limitPrice |
| `STOP` | `stopPrice` | Trigger as market when price crosses stopPrice |
| `MARKET_RANGE` | `slippageInPoints`, `baseSlippagePrice` | Fill within slippage band |
| `STOP_LIMIT` | `stopPrice` + `limitPrice` | Trigger at stopPrice, submit limit at limitPrice |

### 9.3 `tradeSide` Enum

**UPPERCASE:** `BUY`, `SELL` (input AND response). Lowercase handling is build-dependent — always send uppercase.

### 9.4 `timeInForce` Enum (3 values)

| Value | Requires |
|-------|----------|
| `GOOD_TILL_CANCEL` | (default) |
| `GOOD_TILL_DATE` | `expirationTimestamp` (integer epoch ms) |
| `IMMEDIATE_OR_CANCEL` | (may behave like pending LIMIT per Q-R5) |

### 9.5 `dealStatus` Enum (6 values)

| Status | Meaning |
|--------|---------|
| `FILLED` | Fully filled — proceed |
| `PARTIALLY_FILLED` | Partial fill — surface gap between `volume` and `filledVolume` |
| `REJECTED` | Broker rejected — read reason, do not retry blindly |
| `INTERNALLY_REJECTED` | Server-side rejection before broker — treat like REJECTED |
| `ERROR` | Execution error — read `get_position_details` before further action |
| `MISSED` | Opportunity missed (market gapped) — no fill |

---

## 10. SL/TP Rules (Critical)

### 10.1 Absolute Price Only on Remote

All SL/TP fields on Remote use **absolute price** — no pip-distance form exists on this server:
- `create_order.stopLoss`, `create_order.takeProfit`
- `amend_order.stopLoss`, `amend_order.takeProfit`
- `amend_position.stopLoss`, `amend_position.takeProfit`

### 10.2 MARKET Order SL/TP Rejection (Q-R4)

`create_order(orderType="MARKET")` with absolute `stopLoss`/`takeProfit` is **REJECTED**:
```
Error: "create_order: Absolute stopLoss is not supported for MARKET orders..."
```

**Preferred workaround (single call):** Use `relativeStopLoss`/`relativeTakeProfit` (positive integer points):
```json
{
  "orderType": "MARKET",
  "tradeSide": "BUY",
  "volume": 100000,
  "relativeStopLoss": 300,
  "relativeTakeProfit": 600
}
```
BUY → SL = fill − relativeStopLoss, TP = fill + relativeTakeProfit. Lands atomically at fill — no race window.

**Fallback (two-step):** Place MARKET without SL/TP, then `amend_position` with both legs.

### 10.3 `amend_position` Omit-Removes (Q-R10 — CRITICAL)

Omitting `stopLoss` or `takeProfit` from `amend_position` **REMOVES** that leg (does NOT preserve it). Passing `null` is REJECTED.

**Safe pattern (P-AMEND-SAFE):**
1. Read current SL/TP via `get_positions`
2. ALWAYS pass BOTH legs in every `amend_position` call
3. Post-flight: re-read and verify BOTH legs survived

### 10.4 Trailing Stop Loss (Q-R3)

- Only honored on `amend_position(positionId, trailingStopLoss: true)` — after position exists
- Silently IGNORED on `create_order` and `amend_order`
- Requires `stopLoss` value present (anchor level)
- Remote-only; no Local equivalent

### 10.5 `close_position` Requires Volume

`close_position` **requires** a `volume` parameter (integer cents). To fully close, pass the position's current open `volume`. To partially close, pass any positive cents ≤ current volume. No "close all without volume" on Remote.

---

## 11. Pagination

### 11.1 Pattern

List-returning tools use `hasMore: boolean`:
- `get_pending_orders`
- `get_order_history`
- `get_deals` (also accepts `maxRows`, default 50)

When `hasMore: true`, advance the window by last record's timestamp. No offset/cursor token. Dedupe by `dealId`/`orderId`.

### 11.2 720-Hour Window Cap (Q-R7)

History endpoints reject windows > 720 hours (30 days):
```
Error: "Time range exceeds upstream cap of 720h (PT720H = 30 days). Requested 800h. Split into 720h-or-smaller windows..."
```

**Pattern (P-REMOTE-HISTORY-CHUNK):** Chunk into ≤ 720h windows, loop with `hasMore`, dedupe. Per-window calls CAN run in parallel.

### 11.3 Propagation Lag (Q-R11)

`get_deals`/`get_order_history` are eventually consistent. Just-closed deals may not appear for seconds to minutes. For immediate post-mutation verification, use the mutation response's embedded deal/order objects.

---

## 12. Pre-Flight Gates (Self-Healing)

Every mutation must pass these gates BEFORE submission:

| Gate | Check | Failure Action |
|------|-------|---------------|
| 1.1 Quote sanity | Price within ±20% of last bid/ask | STOP; surface to user |
| 1.2 Side-direction | BUY-stop above ask, BUY-limit below bid, etc. | STOP; suggest symmetric tool |
| 1.3 SL/TP sidedness | LONG: `SL < entry < TP`; SHORT: `TP < entry < SL` | STOP; surface gap |
| 1.4 volumeStep | `volume % volumeStep == 0` (Local only) | Round to valid step |
| 1.5 Schema-fields-only | Strip unknown keys before submit | Drop + log warning |
| 1.6 Pipettes-vs-display | Flag 5+ digit integer in price DTO (Remote) | STOP; decode pipettes |
| 1.7 Required fields | Verify conditional-required fields present | STOP; surface missing fields |

---

## 13. Post-Flight Verification

After EVERY mutation:

1. **Re-read** the affected entity via `get_positions`/`get_pending_orders`/`get_position_details`
2. **Verify** volume, side, entry price, SL, TP, status match intent
3. **On amend_position specifically:** Verify BOTH SL and TP legs survived (Q-R10)
4. **Encoding errors:** Re-run conversion scripts with corrected inputs
5. **Broker rejection** (`REJECTED`/`INTERNALLY_REJECTED`/`ERROR`): Surface reason, stop

---

## 14. Named Recovery Patterns

| Pattern | Trigger | Action |
|---------|---------|--------|
| **P-AMEND-SAFE** | Every `amend_position` on Remote | Read current → pass BOTH legs → post-flight verify |
| **P-REMOTE-MARKET-RELATIVE** | MARKET + SL/TP (preferred) | Single call with `relativeStopLoss`/`relativeTakeProfit` |
| **P-REMOTE-MARKET-2STEP** | MARKET + absolute SL/TP (fallback) | Place without SL/TP → await fill → amend_position with both legs |
| **P-REMOTE-MARKET-RANGE** | Slippage-bounded entry (gated) | `MARKET_RANGE` with `slippageInPoints` (if Q-R4-RANGE probe passes) |
| **P-REMOTE-HISTORY-CHUNK** | History > 720h | Windowed loop with `hasMore` + dedupe |

---

## 15. Active Quirks (rest-proxy 1.0.18)

| ID | Description | Status |
|----|-------------|--------|
| Q-R1 | `period` enum is 9 values, NOT 26 | ACTIVE |
| Q-R2 | `expirationTimestamp` integer epoch ms ONLY | ACTIVE |
| Q-R3 | `trailingStopLoss` silently dropped by `create_order`/`amend_order` | ACTIVE |
| Q-R4 | MARKET rejects absolute SL/TP (use `relativeStopLoss`/`relativeTakeProfit`) | ACTIVE |
| Q-R4-RANGE | `MARKET_RANGE` SL/TP acceptance UNVERIFIED (gated) | UNVERIFIED |
| Q-R5 | IOC behaves like pending LIMIT | ACTIVE |
| Q-R7 | 720h window cap on history endpoints | ACTIVE |
| Q-R8 | Unknown `symbolId` in `get_spot_prices` batch returns empty silently | ACTIVE |
| Q-R10 | `amend_position` OMIT-removes the omitted SL/TP leg (CRITICAL) | ACTIVE |
| Q-R11 | `get_deals`/`get_order_history` propagation lag | LIKELY FIXED (1/5 sessions) |
| Q-K19 | Pipettes vs display foot-gun (silent market fills) | ACTIVE |

---

## 16. Connection Setup & Verification

### 16.1 Setup Flow

1. Log into **cTrader Web** with cTID
2. Open **Settings → Remote MCP**
3. Select the **trading account**
4. **Copy** the configuration (contains URL + token)
5. Paste into AI agent with prompt: *"Set up the cTrader remote MCP server for me. Add the following to my MCP configuration, then verify the connection."*
6. AI agent updates MCP config and connects

### 16.2 Verification

1. Restart AI client session/application
2. Check remote MCP server appears in connected servers list
3. Run **W0 session bootstrap**:
   - Call `get_version()` to identify build
   - Call `get_balance()` to verify account connectivity
   - Cache `get_symbols()` and `get_assets()` for session

### 16.3 Requirements

- **Active cTrader Web session** — if session expires, re-authenticate and update token
- **Token is per-account** — switch account → copy new config
- **Trading confirmation** — configure AI client to request confirmation for trading operations

---

## 17. Prompt Best Practices

- Begin sessions with: *"Using the cTrader remote MCP server..."* — prevents agent from routing to web search
- Install skills: `npx skills add https://github.com/spotware/ctrader-skills --all --global`
- Update skills: `npx skills update -g -y`

---

## 18. Security Model

| Aspect | Detail |
|--------|--------|
| **Authentication** | Per-account bearer token from cTrader Web |
| **Session** | Requires active cTrader Web session |
| **Real trades** | AI agent CAN place/modify/close real orders |
| **Confirmation** | Configure per-tool confirmation in AI client |
| **Liability** | User responsible for verifying outputs, supervising strategies |
| **No financial advice** | Tool for AI-assisted interaction, NOT investment advice |

---

## 19. Demo vs Live

- Same tools work against both environments
- `environment` field in slug encodes demo/live
- Live accounts may require additional explicit user acknowledgment before first mutation
- Agent must surface "this is a LIVE account" warning before first trade in session

---

## 20. Key Integration Points for Python Client

For implementing `mcp_client.py`:

```python
# Session state (W0 bootstrap)
session = {
    "family": "remote",               # or "local", "both"
    "version": "1.0.18",              # from get_version()
    "server_time_offset_ms": 0,       # agent_epoch - server_epoch
    "symbols": {},                    # symbolId -> symbol metadata (cached)
    "assets": {},                     # assetId -> asset name (cached)
    "trader_id": None,                # from get_balance()
    "money_digits": 2,                # from get_balance()
    "deposit_asset_id": None,         # from get_balance()
    "account_currency": None,         # resolved from get_assets()
    "account_type": None,             # "Hedged" or netting
    "quirks_active": {                # per quirk: ACTIVE / REMOVED / SKIP
        "Q-R1": "ACTIVE", "Q-R2": "ACTIVE", "Q-R3": "ACTIVE",
        "Q-R4": "ACTIVE", "Q-R5": "ACTIVE", "Q-R7": "ACTIVE",
        "Q-R8": "ACTIVE", "Q-R10": "ACTIVE", "Q-R11": "LIKELY_FIXED"
    },
    "q_r4_range_probe": "not-run",    # "pass" / "fail" / "not-run"
    "idempotency_prefix": "sess-xxxxxxxx",
}

# Encoding conversions (critical)
# volume:  1 lot forex = 10,000,000 cents
# price:   display = pipettes / 10^pipDigits
# money:   display = raw / 10^moneyDigits
# time:    expirationTimestamp = epoch ms integer ONLY
# symbols: numeric symbolId, NOT string ticker
# side:    ALWAYS uppercase "BUY"/"SELL"

# Rate limits
# general:    50 req/s
# historical:  5 req/s (get_trendbars, get_order_history, get_deals)

# Critical pitfall: amend_position OMIT-removes SL/TP (Q-R10)
# Always: read current -> pass BOTH legs -> verify post-flight
```
