# Meridian Desk

In the full Windows deployment folder, open **`E:\MeridianDesk\Open Meridian Desk.lnk`** to start the Windows market and risk workstation. The shortcut uses the bundled Python runtime and Microsoft Edge in a dedicated app window. Meridian starts a private loopback service, connects to public data, and opens a local paper account with **$100,000 in simulated cash** on first launch. Closing the window ends the local desk session. Broker orders already accepted by an exchange follow their own time-in-force.

## Git checkout

This repository contains the application source, tests, documentation, and selected licensed integration assets. The self-contained Windows deployment also has locally provisioned runtimes and dependencies, SDK/build outputs, browser profiles, caches, databases, and logs; those generated or machine-specific files are intentionally excluded from Git. A source checkout is not the complete runnable Windows deployment.

## First run

1. The normal window opens on **Market overview** with **BTC-USD** selected. Select **DEMO** in the watchlist to try the offline workflow. This simulated equity has prices and ten annual financial statements bundled on E:. It works offline.
2. Open **Research swarm**. Inspect the risk decision, valuation, and specialist evidence. **Run review** records a new snapshot. **Agent registry** shows all 300 cards. The desk runs a panel of 12 rule-based specialists from eight pods on each usable snapshot.
3. In **Research swarm**, choose **Run swarm** to run deterministic specialists, Kronos and Ruflo against one captured price snapshot. Select TradingAgents to include its provider. The result records unavailable or failed workers individually. The combined report respects the programmatic risk gate.
4. Run a **backtest** for DEMO to inspect a historical value strategy over synthetic data. The result includes the test period, fill count, transaction costs, drawdown, and a same-asset buy-and-hold comparison.
5. In **Portfolio**, use the local paper order ticket. For a first simulated fill, choose DEMO, buy one share, and set a limit just above the displayed price and below its 30% margin-of-safety ceiling. A successful order updates cash, holdings, and the activity log. A blocked order explains which check failed.
6. Open **Connections** and run **Ruflo** or **Kronos** for the selected instrument. Reports appear in the research runs for that symbol. **TradingAgents** uses a configured provider or compatible local server.

## Market coverage

| Instrument | Source and behavior |
| --- | --- |
| BTC-USD, ETH-USD | Coinbase Exchange ticker WebSocket with bids, asks, heartbeat, and five-minute price history. If Coinbase history is unavailable, Kraken supplies five-minute OHLC data where available. |
| SPY, AAPL, MSFT, EUR/USD, gold futures | Public Yahoo Finance chart data with five-minute quotes and extended-hours observations where published. Prices can be delayed, and exchanges have closed sessions. |
| DEMO | Repeatable synthetic five-minute OHLCV and a fictional operating company. All DEMO orders stay in the local paper ledger. |

The watchlist distinguishes **LIVE** ticker observations, **PUBLIC** indicative bars, **SIM** data, **STALE** cached observations, and **WAIT** while awaiting a provider. Check the source, time and session shown with the instrument. A public bar is suitable for research. Local paper fills on a real-market symbol require a two-sided quote aged two seconds or less and a spread within 1%. A chart can continue displaying data while its execution checks block orders. DEMO remains available during an outage.

## Risk, valuation and backtests

- The risk panel uses observed closing-price drawdowns, per-bar realized volatility, a variance-targeted GARCH(1,1) scenario and 10,000 seeded one-bar shocks for modeled 99% expected shortfall. The scenario assumes normal shocks. Outputs describe the selected bar interval. Quarter-Kelly uses observed gains and losses when the series has enough variation; the displayed estimate is capped at 15%.
- The programmatic entry gate checks observation depth, severe current drawdown and modeled tail loss. For covered equities it also checks earnings history, margin of safety and governance evidence. A risk or governance veto blocks a new position. Add-on research reports have no order authority.
- AAPL and MSFT can load annual SEC Company Facts and recent filing references under **Connections**. Estimates use reported net income, D&A, total capital expenditure as a maintenance proxy and working-capital changes. The two-stage DCF uses a 10% hurdle and 2.5% terminal growth. Gaps and valuation assumptions are visible in the research result. Public filing data alone leaves governance review incomplete and blocks new issuer entries. DEMO uses an explicitly synthetic governance review.
- When two successive fresh market snapshots cross the 30% margin-of-safety, 20% drawdown or 8% one-bar expected-shortfall threshold, Meridian records an alert and queues local swarm research. A 15-minute cooldown applies per instrument. These alerts run without a hosted provider and carry no order authority.
- The DEMO replay trades after dated statements become available, enters at a 30% discount with a 15% allocation and exits on full value. For market symbols, the backtest requests up to five years of daily market prices. An expanding history selects a long/cash momentum lookback. Trades use the following open, with 10 basis points charged on each transition. The comparison is the same asset held over the test period. Public price backtests exclude dividend reinvestment. DEMO results come from a simulated price process.

## Accounts and order handling

**Local paper** uses the SQLite ledger on E:. Its instant-fill model applies 2 basis points of adverse slippage and a 1-basis-point fee, rounded to cents with a one-cent minimum. Orders must meet their limit immediately. Buys need available cash and a resulting position at or below 15% of account equity. Sells require an existing long position. Trade IDs make an identical retry idempotent.

**Alpaca paper or live** uses a separate broker account. The adapter supports BTC/USD, ETH/USD, AAPL, MSFT and SPY subject to provider availability and account permissions. Equity limit orders require whole shares and the open regular session. Crypto orders use good-till-canceled limits. Select the intended account mode before launch. The ticket requires an exact typed confirmation matching the displayed mode, side and symbol. Live mode submits real orders.

Broker preflight verifies cash, existing positions and pending reservations, a fresh broker bid/ask and price agreement. A ticket marked **dispatch pending** can mean the broker received it before a connection interruption. Use **Reconcile** to retrieve its status by client ID. **Halt** persists across restarts and blocks new submissions for both account modes. Open orders already resting at the broker must be managed in the broker account.

## Configuration

| Setting | Use |
| --- | --- |
| `MERIDIAN_BROKER` | `off` by default. Use `paper` for the Alpaca paper endpoint or `live` for its live endpoint. |
| `APCA_API_KEY_ID`, `APCA_API_SECRET_KEY` | Credentials for the selected Alpaca account. Supply through the launch environment. |
| `MERIDIAN_SEC_CONTACT` | A descriptive SEC request user agent including your contact address, for issuer refreshes. |
| `TRADINGAGENTS_MODEL`, `TRADINGAGENTS_BASE_URL` | Model ID and API base URL for a compatible local model server with streaming chat completions and tool support. |
| TradingAgents provider credentials | The adapter recognizes `TAURIC_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `DEEPSEEK_API_KEY`, `OPENAI_API_KEY` and `OPENROUTER_API_KEY`. Set one for the chosen provider. |

The program reads the process environment at startup. In PowerShell, a session-only broker mode can be selected with `$env:MERIDIAN_BROKER = 'paper'`. Open the shortcut from that same session with `Invoke-Item -LiteralPath 'E:\MeridianDesk\Open Meridian Desk.lnk'`. Use the standard paper simulation without any credentials.

**Kronos** runs bundled CPU inference offline and produces a next-interval forecast from the last 32–256 OHLC bars. **Ruflo** uses its local task orchestrator for drawdown, volatility and historical tail loss, then runs a dependent risk review. **TradingAgents** submits a price summary when you run the worker. Its provider may charge for tokens, and the agent can consult outside sources. Provider readiness reflects installed configuration; a completed request confirms connectivity. Details, source pins, installed weights and licenses are documented in the [integration guide](integrations/README.md).

## MetaTrader 5

The supplied EA binary, source and four include files are preserved under `E:\MeridianDesk\mt5\MQL5`. **Connections** imports the latest complete **APEX-FX SIGNAL REPORT** from an Experts log or report text export. Choose a UTF-8 or UTF-16 file up to 4 MB. For a larger log, export the complete relevant report to a small text file. The importer looks for the report header, pair, direction, timestamp, confluence score, risk flags and final disclaimer. Import records the report in the local activity log. The desktop does not install or launch the EA or submit MT5 trades.

## Files, lifetime and verification

| E-drive path | Contents |
| --- | --- |
| `E:\MeridianDesk\data\desk.sqlite3` | Local paper account, positions, fills, broker ticket references, recent snapshots, halt state and audit events. |
| `E:\MeridianDesk\data\sec` | Cached issuer statements and filing references. |
| `E:\MeridianDesk\data\tradingagents` | TradingAgents project-local configuration and sessions, when used. |
| `E:\MeridianDesk\cache`, `integrations\cache` | Dedicated desktop browser profile, temporary files and integration caches. |
| `E:\MeridianDesk\logs\desktop.log` | Startup and service errors. |
| `E:\MeridianDesk\runtime`, `integrations` | Bundled Python, JavaScript runtime, source checkouts, model weights and dependencies. |

Keep the full installation together on E:. The primary launcher uses the installed Microsoft Edge browser. Windows Application Control on this machine blocks the unsigned native executable. The optional WinForms/WebView2 source is in `native` for organizations that build and sign their own binaries. Meridian places its project files, databases, browser profile, temporary directories and model caches on E:. Windows controls system-level runtime behavior. For a consistent database backup, close the desk before copying its data directory. Completed jobs appear in the activity log. The on-screen job queue is scoped to the open session.

The paths below describe the full local E: deployment, not a source-only Git checkout. Run its verification suites from PowerShell; these commands use the bundled Python with bytecode generation disabled.

```powershell
Set-Location 'E:\MeridianDesk'
$env:TEMP = 'E:\MeridianDesk\cache\temp'
$env:TMP = $env:TEMP
.\runtime\python\python.exe -B -m unittest -v test_analytics test_market test_orders test_swarm test_desk
.\runtime\python\python.exe -B tests\test_integrations.py -v
```

The desktop API suite creates isolated temporary accounts under `E:\MeridianDesk\tests`. It exercises the authenticated loopback service, synthetic paper orders, restart and halt persistence, registry and research jobs, a real combined local Ruflo/Kronos run, and report import. The integration suite exercises the local model workers and a loopback provider fixture. The local service tests use a separate SQLite database and leave the normal paper account available for the next desktop session.
