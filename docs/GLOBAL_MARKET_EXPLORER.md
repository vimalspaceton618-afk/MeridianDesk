# Global Market Explorer V1 — execution and data boundaries

## Why this milestone

The original `market.SYMBOLS` list contains eight watched instruments and refreshes those symbols on startup. Turning this into a 150-symbol continuously polling list would increase rate-limit, memory and UI risks, so the full international catalog is separate from the legacy watchlist.

**Target requirement:** Q011–Q020 (worldwide multi-asset discovery, excluding Indian exchanges, provenance-first public/free data), Q030/Q040/Q061–Q064 (risk veto, broker isolation, documented provider failure), Q082/Q083 (working evidence-gated vertical slice). This is **not** completion of all 100 decisions.

## Implemented design

- `universe.py`: curated research-only equities spanning over 25 countries; fixed explicit issuer, listing, local currency and exchange metadata; no Indian listings. This is a starter discovery catalog, not a complete world-exchange security master.
- `GET /api/catalog`: authenticated localhost endpoint that returns catalog records without contacting a market provider.
- `market.fetch_bars` and `market.fetch_history`: permit the approved catalog tickers. Use the existing Yahoo chart public/indicative feed with source and timestamps; attempt daily bars when minute bars are unavailable. No synthetic fallback for real securities. Currency is extracted from provider metadata if supplied.
- `Desk.request_catalog`: limit on-demand quote fetches to two concurrent catalog tasks; keep a three-minute per-symbol request cooldown. Do not poll every catalog item. Unknown symbols remain invalid.
- UI: **Explore global stocks** (search issuer/ticker/country/exchange, filter by country) and select a symbol. Display researched exchange/currency, and explicitly label **research-only**, source and delayed/stale nature. Users can pin/unpin up to 16 international listings; these favorites persist in the local SQLite account and reappear after restart alongside the original eight symbols. Favorite quotes refresh on explicit selection (with cooldown), not through unlimited background polling.
- **Safety:** catalog instruments cannot submit to either local paper trading or Alpaca, even if future provider updates add bid/ask fields. They may run local deterministic research and backtesting only. No new integration-agent, filing-refresh, or broker execution authority is granted.

## Data semantics and costs

**Research-only is mandatory.** Yahoo publishes exchange-specific suffixes and delays, but the queried chart endpoint is not a guaranteed licensed real-time production API. A supported catalog ticker may return no data or an invalid chart. The UI reports unavailable/stale data rather than fabricating a quote. External data requires legal entitlements, provider terms review, market calendar normalization, historical corporate actions, and currency translation before institutional or commercial rollout.

For UK equities, some feeds quote in **GBp** (pence), not GBP pounds. Country metadata is only a hint: trust returned provider currency when present and display it. Chart risk values are in the instrument's native price units. **Never assume international marks are in USD** or perform local USD paper portfolio accounting from these observations.

Some exchanges have different holidays, auctions, settlement, symbol changes and country-specific restrictions. They have **not** been independently verified in this milestone. Provider mapping is not proof that live prices exist or that use/redistribution is licensed.

## Local favorites and recovery

The ledger creates a separate watchlist table using a non-destructive `CREATE TABLE IF NOT EXISTS` migration. Pin/unpin writes are transactional and limited to 16 international symbols. On startup, persisted snapshots of favorite instruments can be displayed only as **STALE** until refreshed; no background fetch of all saved symbols takes place. Account balances, paper order tables, broker routing and risk calculations are unchanged.

## Acceptance criteria

1. Authenticate catalog API; reject unauthenticated requests.
2. Catalog contains at least 150 unique ticker mappings across 25+ countries; reject unknown symbols and prohibited Indian exchange suffixes.
3. On first selection, fetch only the selected instrument and keep the original eight background watchers unchanged.
4. Limit concurrent catalog refreshes and apply per-symbol cooldown; surface source outages safely.
5. Preserve quote currency (e.g., JPY, GBp, CAD, BRL) and source/interval metadata.
6. Forbid international catalog symbols on both local paper-order and remote broker-order routes; preserve existing protections for the eight original instruments.
7. Search/filter UI works with existing modal, keyboard focus, no extra dependencies, no replacement of Windows launcher. Favorites must survive restart, cap at 16, reject invalid symbols, and leave cash/order tables unchanged.
8. Run existing Python safety tests, new catalog/backend tests and JavaScript offline UI regression in GitHub Actions.
9. **Follow-up on Windows:** run the full `E:\MeridianDesk` GUI acceptance and verify Yahoo international symbol availability and latency on the actual PC. Confirm no new provider requests occur until explicit selection.

## Proposed V2 follow-ups (not yet implemented)

- Pluggable licensed provider adapters with entitlements, source and delay contracts per exchange.
- Point-in-time symbol master with MIC/ISIN, listings/ADRs, issuer changes, market hours, corporate actions and adjustments.
- Paged security search with server-side caching, user watchlist persistence and batch subscriptions within provider quotas.
- Proper FX conversion, multi-currency risk engine, separated broker venue permissions, research evidence and ranking calibration.
- Cross-market instruments including options/futures, bonds and global macro, each with distinct validation, licensing and execution gates.

**Safety boundary:** no live broker orders, paid compute, PR merge or local installation changes in this milestone.
