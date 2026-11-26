# Autonomous research agents — PR #4 engineering contract

**Status:** implemented and tested as an **offline, deterministic multi-agent research workflow**, not a generative AI/LLM system or a production-grade autonomous trading desk.

## Actual source audit (2026-11-26)

The existing source already provides:
- `analytics.py`: 300 specialist **registry profiles** and 12 deterministic specialist evaluations per market snapshot.
- `swarm.py`: a human-invoked parallel local research review using installed Ruflo and Kronos workers, with TradingAgents only by explicit provider opt-in for previously supported instruments.
- `desk.py`: bounded asynchronous job queue, pending-job deduplication, and automatic **risk-dislocation** triggers on original market watchers.

Those components **do not constitute** a persistent, evidence-verified, autonomous research hierarchy for the new international catalog. This PR adds the first constrained, reproducible agent mission.

## New implementation

### `autonomous_research.py` — planner → workers → verifier → report

Six allowlisted, local Python evidence workers read only a frozen, source-attributed OHLCV snapshot and its matching deterministic risk assessment:

| Agent | Source-constrained task | Failure/limitation |
|---|---|---|
| Source integrity | Provider/simulation, transport, UTC stamp and staleness | Hold on stale or unobserved source |
| Data continuity | Bar count, interval, gaps | Distinguish missing data from market closures |
| Trend observation | Last 20-bar observed return | Observation only; not a forecast |
| Capital-risk challenger | Current drawdown, modeled one-bar CVaR | Risk hold; no override of independent veto |
| Adversarial counter-thesis | Window return and peak drawdown | Disclose unobserved geopolitical/news/liquidity risk |
| Issuer evidence | Report whether independently supplied company statements exist | Explicit UNKNOWN when fundamentals are missing |

**Verifier:** input facts are derived from ordered, validated OHLCV; independent drawdown recomputation rejects mismatched risk values; unknown evidence references, duplicate agents, unknown signals and inconsistent timestamps fail closed. A SHA-256 digest records the canonical **input identity**. **SHA-256 here is not a signed, tamper-proof audit ledger**—cryptographic event-chain signing remains future work. Report output includes the plan, all six specialist signals, source provenance, evidence field names, reasons, missing source/entitlement flags and explicit **execution: DISABLED**.

**Terminal decisions:** `ABSTAIN` or `REVIEW ONLY`. Neither state gives a buy/sell recommendation, trading permission, investment-performance assurance or override of risk controls. In particular, missing company financials, synthetic/stale feeds, or an independent governance/risk veto cause abstention. Data rights, corporate actions and quote latency are not assumed verified.

### Autonomous trigger and user interface

When a user **selects** a catalog stock, the pre-existing bounded data fetch obtains an observation (or a visibly unavailable/stale state). Once a new selected snapshot is accepted, one local agent mission is queued automatically; repeat polling of the same source/time/stale identity does not generate duplicate agent jobs. A per-ticker 180-second refresh cooldown and two-concurrent-fetch limit remain in force. No background scraping of all 159 catalog listings and no hidden paid inference occurs.

**Research swarm → Autonomous research mission** displays the current `ABSTAIN` / `REVIEW ONLY` result, six agent findings, missing evidence, source timestamp/currency, snapshot digest and **execution disabled**. Users can also manually start a new local agent run and open the complete structured report. A brief, readable report is stored in the existing local audit ledger. Individual job results are currently session-scoped; permanent structured research-history storage remains a separate milestone.

**Optional installed workers:** a user may also request **Run swarm → Run locally** for global stocks, reusing installed Ruflo and Kronos when available. Remote TradingAgents / paid-provider mode is **not offered or accepted** for global stocks; no provider routing is permitted through the new `autonomous` job kind. Installed model output remains supplemental research and cannot override the deterministic risk/broker gate.

### Security and resource isolation

- Jobs run in the pre-existing four-thread bounded Python job pool; the autonomous pipeline itself uses six deterministic, in-process functions and no network or process-execution capability.
- No exchange API, cloud model, LLM, external browser, broker credential, portfolio write, order route or execution mode is available inside the six local workers.
- The authenticated localhost API accepts only allowed job kinds and symbols and rejects explicit model routing for autonomous jobs; the separate order API rejects catalog equities even if a model manufactures a ticket.
- No extra Python packages or paid subscriptions required for deterministic agents.
- Failures appear as errored jobs; they are never presented as validated recommendations.
- The current source/account audit table is **not** cryptographically tamper evident.

## Verification gates and limits

- `test_autonomous_research.py` verifies six-agent deterministic output, input hash stability, stale/synthetic abstention, tampered timestamps/OHLCV, independently forged risk evidence, unknown evidence references, bounded payloads, automatic deduplicated dispatch, local-only job API, and no broker/cloud calls.
- Existing safety suites remain mandatory, especially paper order idempotency, risk veto, and authenticated API checks.
- Hosted Windows Microsoft Edge test validates the actual UI with **synthetic, explicitly labeled foreign-stock fixture**, then checks the automatic mission, `ABSTAIN` and structured evidence panel. These screenshots **do not** demonstrate successful real-market research or the installed `E:\\MeridianDesk` WebView2 launcher.
- No integration is described as installed/usable on an end-user machine without verifying the actual E: runtime and bundled model weights.

## Still to build under the accepted 100-requirement program

This is a limited first autonomy milestone. A true model-driven institutional research platform still requires a permissioned local/model gateway, independent source and corporate-filings retrieval, point-in-time entity graphs, validated worldwide market-data licenses, sandboxed tools, prompt-injection protection, multi-model adversarial evaluation, persisted missions and checkpoints, benchmark calibration, cost controls, formal security review and Windows-device acceptance tests. **Do not infer that the entire 100-question specification is implemented by PR #4.**

**Founder authorization:** this PR is kept in draft. No automatic merge, deployment, unapproved spending, live trading, or risk-policy changes.
