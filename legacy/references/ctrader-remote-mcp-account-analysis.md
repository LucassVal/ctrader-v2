# cTrader Remote MCP Server — Consolidated Operations Spec

> Extracted from cTrader Help Centre docs (dated 2026-05-08 through 2026-06-17).
> Sources: Account, Analysis, and Use Cases (Daily Briefing, Risk Management, Scaling Positions, Performance Review, Symbol Screening).

---

## 1. ACCOUNT OPERATIONS

Monitor and manage your trading account through natural-language prompts.

### 1.1 Account Overview
- **Prompt:** `Give me a summary of my account including balance, equity, free margin, and the number of open positions and pending orders.`
- **Returns:** Balance, equity, free margin, open positions count, pending orders count.

### 1.2 Check Balance
- **Prompt:** `What is my current account balance?`
- **Returns:** Balance, equity, free margin.

### 1.3 List Available Symbols
- **Prompt:** `What trading symbols are available on my account?`
- **Prompt:** `Is XAUUSD available for trading?`
- **Returns:** Full symbol list or confirmation for a specific symbol.

### 1.4 View Assets / Deposit Currency
- **Prompt:** `What is my deposit currency?`
- **Returns:** Deposit currency of the account.

### 1.5 Margin Monitoring
- **Prompt:** `Check my free margin as a percentage of equity and warn me if it's below 20%.`
- **Returns:** Margin utilization percentage with conditional warning flag.

### 1.6 Account Health Check (Combined)
- **Prompt:** `Run an account health check: show my balance, equity, margin level, number of open positions, and total unrealised P&L. Flag anything concerning.`
- **Returns:** Consolidated dashboard with all key metrics + flagging.

### Account Data Points Extracted
| Data Point | Description |
|---|---|
| Balance | Current account balance |
| Equity | Balance + floating P&L |
| Free Margin | Equity minus margin used |
| Margin Level | Margin used as % of equity |
| Open Positions | Count and details |
| Pending Orders | Count and details |
| Unrealised P&L | Total floating profit/loss |
| Deposit Currency | Base currency of account |
| Available Symbols | List of tradable instruments |

---

## 2. ANALYSIS OPERATIONS

Retrieve market data, analyse trade history, and run portfolio analysis.

### 2.1 Market Data

#### 2.1.1 Current Prices (Spot)
- **Prompt:** `What are the current bid and ask prices for EURUSD?`
- **Prompt:** `Get live prices for EURUSD, GBPUSD and USDJPY.`
- **Returns:** Bid, ask for single or multiple symbols.

#### 2.1.2 Historical Data (Trendbars / Candles)
- **Available periods:** 1m, 2m, 3m, 4m, 5m, 10m, 15m, 30m, 1h, 2h, 3h, 4h, 6h, 8h, 12h, Daily, Weekly, Monthly.
- **Prompts:**
  - `Get the last 24 hours of hourly candles for EURUSD.`
  - `Show me the daily candles for GBPUSD over the past 30 days.`
  - `Get 100 five-minute candles for XAUUSD.`
- **Returns:** OHLC candle data for the specified timeframe and count.

#### 2.1.3 Price Analysis
- **Prompt:** `What is the current spread on EURUSD?`
- **Prompt:** `Compare the session high and low for EURUSD, GBPUSD and USDJPY.`
- **Returns:** Spread in pips; session high/low per symbol.

### 2.2 Trade History

#### 2.2.1 Deal History
- **Prompt:** `Show me all my deals from the last 7 days.`
- **Prompt:** `How many trades did I make last month?`
- **Returns:** List of deals with symbol, side, volume, execution price, status.

#### 2.2.2 Performance Analysis
- **Prompt:** `Analyse my trading performance over the last 30 days: total deals, total volume, and fill rate.`
- **Prompt:** `Show me my deal history for this week and calculate the total commission paid.`
- **Returns:** Aggregate statistics: deal count, volume, fill rate, commission totals.

#### 2.2.3 Order History
- **Prompt:** `Show me all orders that were filled, cancelled, or expired in the last 7 days.`
- **Returns:** Order history filtered by status.

### 2.3 Portfolio Analysis

#### 2.3.1 Position Analysis
- **Prompt:** `Show me all my open positions with their unrealised P&L, and calculate the total.`
- **Prompt:** `Which of my open positions has the largest unrealised loss?`
- **Prompt:** `What is my total exposure in EURUSD across all open positions?`
- **Returns:** Position list with symbol, entry price, current P&L, stop loss, take profit, exposure.

#### 2.3.2 Risk Assessment
- **Prompt:** `Check my current margin usage. What percentage of my equity is free margin?`
- **Prompt:** `If EURUSD drops 100 pips, estimate the impact on my open positions.`
- **Returns:** Margin usage metrics; scenario impact estimates.

### 2.4 Combining Prompts
- `Get my account balance, list all open positions with their P&L, and tell me which positions I should consider closing based on risk.`
- `Pull the last 24 hours of hourly candles for EURUSD, summarise the trend, and check if I have any open positions that might be affected.`

### Analysis Data Points Summary
| Category | Data Points |
|---|---|
| Spot Prices | Bid, Ask, Spread, Session High/Low |
| Trendbars | OHLC candles (18 timeframes), count/duration queries |
| Symbols | Available list, symbol-specific queries |
| Deals | History by date range, count, volume, fill rate |
| Orders | History by status (filled/cancelled/expired) |
| Positions | Open positions, P&L, exposure by symbol, entry/stop/take-profit |
| Performance | Win rate, profit factor, avg win/loss, commission, daily P&L |
| Risk | Margin usage %, free margin %, scenario impact estimates |

---

## 3. USE CASES (End-to-End Workflows)

### 3.1 Daily Briefing
**Goal:** Combine account and market data into a morning summary.

| Step | Action | Prompt |
|---|---|---|
| 1 | Check account status | `Give me a summary of my account: balance, equity, free margin, and the number of open positions.` |
| 2 | Review open positions | `Show me all open positions with their unrealised P&L, entry price, and current stop loss and take profit levels. Highlight any position losing more than $200.` |
| 3 | Get overnight price moves | `Get the last 12 hours of hourly candles for EURUSD, GBPUSD, and USDJPY. Summarise the direction and range for each.` |
| 4 | Check key price levels | `For EURUSD, GBPUSD and USDJPY, show me the current bid, ask, session high, and session low.` |
| 5 | **Combined briefing** | `Run my daily briefing: show my account balance and equity, list all open positions with P&L, get the last 12 hours of hourly candles for EURUSD, GBPUSD and USDJPY with a trend summary, and show the current bid, ask, session high and session low for each symbol.` |

### 3.2 Risk Management
**Goal:** Monitor margin levels, identify overexposed positions, add stops, and close losing trades.

| Step | Action | Prompt |
|---|---|---|
| 1 | Check margin level | `What percentage of my equity is currently used as margin? Show my balance, equity and free margin.` |
| 2 | Find unprotected positions | `List all open positions that do not have a stop loss set.` |
| 3a | Add stop loss (individual) | `Set a stop loss on position 456789 at 1.1100.` |
| 3b | Add stop losses (bulk) | `For every open position that has no stop loss, add a stop loss 50 pips below the entry price for buy positions and 50 pips above for sell positions.` |
| 4 | Identify losing positions | `Show me all open positions with an unrealised loss greater than $300. Include the symbol, entry price, current P&L and whether a stop loss is set.` |
| 5a | Close by threshold | `Close all positions that are losing more than $500.` |
| 5b | Close specific | `Close position 456789.` |
| 5c | Close by symbol | `Close all losing EURUSD positions.` |
| 6 | **Combined risk check** | `Run a risk check on my account: show my margin level as a percentage of equity, list any positions without a stop loss and flag any position losing more than $300. Suggest which positions I should consider closing.` |

### 3.3 Scaling Positions
**Goal:** Build a position in stages, take partial profits, move stop to breakeven, manage remaining exposure.

| Step | Action | Prompt |
|---|---|---|
| 1 | Plan entry levels | `Get the last 48 hours of hourly candles for EURUSD and identify the key support and resistance levels.` |
| 2 | Place scaled entry orders | `Place the following limit buy orders on EURUSD, each for 0.3 lots: (1) Limit buy at 1.1200 with stop loss at 1.1050 and take profit at 1.1400. (2) Limit buy at 1.1150 with stop loss at 1.1050 and take profit at 1.1400. (3) Limit buy at 1.1100 with stop loss at 1.1050 and take profit at 1.1400.` |
| 3 | Monitor pending orders | `Show me all my pending orders on EURUSD and all open EURUSD positions.` |
| 4 | Take partial profits | `Close 0.3 lots of my EURUSD position.` |
| 5a | Query average entry | `What is the average entry price of my open EURUSD position?` |
| 5b | Move stop to breakeven | `Move the stop loss on my EURUSD position to that entry price.` |
| 6a | Close remaining | `Close my remaining EURUSD position.` |
| 6b | Adjust TP and let run | `Move the take profit on my EURUSD position to 1.1500.` |
| 7 | Cancel unfilled orders | `Cancel all my pending limit orders on EURUSD.` |

### 3.4 Performance Review
**Goal:** Pull deal history, calculate key metrics, break down P&L by symbol, find best/worst days.

| Step | Action | Prompt |
|---|---|---|
| 1 | Pull deal history | `Show me all my deals from the last 30 days.` |
| 2 | Calculate key metrics | `Based on my deals from the last 30 days, calculate the following: total number of trades, number of winning trades, number of losing trades, win rate, average winning trade in dollars, average losing trade in dollars, and profit factor.` |
| 3 | Break down by symbol | `Break down my last 30 days of trading performance by symbol. For each symbol, show the number of trades, win rate and total P&L.` |
| 4 | Best and worst days | `Group my deals from the last 30 days by date and show the daily P&L. Highlight the best and worst days.` |
| 5 | Review commissions | `What is the total commission I paid on all trades in the last 30 days? Show the breakdown by symbol.` |
| 6 | **Combined report** | `Generate a trading performance report for the last 30 days. Include: total trades, win rate, average win and loss, profit factor, breakdown by symbol with P&L and win rate, total commissions paid and best and worst trading days. Present the results in a table where possible.` |

**Metrics computed:** Total trades, winning trades, losing trades, win rate, average win ($), average loss ($), profit factor (gross profits / gross losses), P&L by symbol, daily P&L, commission by symbol.

### 3.5 Symbol Screening
**Goal:** Build a watchlist, compare price action across symbols, find trading opportunities.

| Step | Action | Prompt |
|---|---|---|
| 1 | Discover symbols | `What trading symbols are available on my account?` / `Is XAUUSD available for trading on my account?` |
| 2 | Get watchlist prices | `Get the current bid and ask prices for EURUSD, GBPUSD, USDJPY, XAUUSD, and US500.` |
| 3 | Compare spreads | `For EURUSD, GBPUSD, USDJPY, XAUUSD and US500, calculate the current spread in pips for each symbol and rank them from tightest to widest.` |
| 4 | Analyse recent trends | `Get the last 24 hours of hourly candles for EURUSD, GBPUSD, USDJPY, and XAUUSD. For each symbol, tell me whether it is trending up, down, or ranging, and what the total move in pips has been.` |
| 5 | Identify strongest movers | `Based on the last 24 hours of hourly data, rank EURUSD, GBPUSD, USDJPY, and XAUUSD by the percentage change from the period open to the latest close. Show the result in a table.` |
| 6 | Drill into a symbol | `For GBPUSD, show me the daily candles for the last 30 days. Identify the overall trend, any notable support and resistance levels, and the average daily range in pips.` |
| 7 | Check existing exposure | `Do I have any open positions or pending orders on GBPUSD?` |

---

## 4. GENERAL NOTES

- **Session prefix:** Always begin prompts with `Using the cTrader remote MCP server...` to ensure the AI agent routes to MCP instead of web search.
- **Multi-symbol:** Most price/candle queries support multiple symbols in a single prompt.
- **Timeframes:** 18 available: 1m, 2m, 3m, 4m, 5m, 10m, 15m, 30m, 1h, 2h, 3h, 4h, 6h, 8h, 12h, Daily, Weekly, Monthly.
- **Combined prompts:** Multiple operations can be chained in one prompt for complex workflows.
- **Trading actions:** Stop loss, take profit, and close operations are destructive — review agent output before confirming.
- **Disclaimer:** The MCP server is AI-assisted trading only. No financial/investment/legal/tax advice. Users are responsible for verifying outputs and supervising strategies.
