# MeridianDesk — Founder Requirements Traceability (Q001–Q100)

**Status:** accepted requirements, NOT a production-readiness claim. **Baseline:** source on `main`, inspected 2026-11-26. This map lists candidate implementation locations, not proof that a capability has shipped.

## Non-negotiable execution boundaries

- All broker-connected live orders require specific human confirmation; agents never receive live dispatch authority.
- Risk and regulatory vetoes remain independent; uncertain broker status requires reconciliation, never automatic resubmission.
- Public release, critical merges, deployments, billable increases and policy weakening require founder authorization.
- Market observations must carry provenance, timestamps, session, delay, and simulation state. Synthetic results are never promoted as observed market performance.
- No Indian exchanges in the intended global instrument catalog.

## Requirement-to-module map

### Product identity and operating principles

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q001 | All-in-one financial intelligence platform | `app/, desk.py, analytics.py` |
| Q002 | Personal-first, public-ready distribution | `launch.py, native/, docs/` |
| Q003 | Equal investing, trading and AI research focus | `analytics.py, broker.py, app/` |
| Q004 | Reduce information overload and improve decisions | `app/, desk.py` |
| Q005 | Autonomous research; live orders require human approval | `broker.py, desk.py` |
| Q006 | Wealth protection, market mastery, AI progress | `analytics.py, ledger.py` |
| Q007 | Original fusion of market terminal, charting, trading and research | `app/, native/` |
| Q008 | AI reasoning, unified workflow, transparent evaluation, local-first economics | `analytics.py, integrations.py` |
| Q009 | Non-negotiable AI research, capital protection, charts/trading | `analytics.py, ledger.py, app/` |
| Q010 | One-year goal: validated and trustworthy workstation | `docs/, tests/` |

### Instrument coverage, data, research and trade design

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q011 | All global asset classes eventually | `market.py` |
| Q012 | Exclude Indian exchanges | `market.py, future instrument registry` |
| Q013 | International equities with licensing checks | `market.py, filings.py` |
| Q014 | Deep crypto market structure and on-chain analysis | `market.py, future crypto connectors` |
| Q015 | Institutional global FX data and macro context | `market.py, future FX connectors` |
| Q016 | Commodity curves, inventory, seasonal and geopolitical research | `future commodity research` |
| Q017 | Options and derivatives analytics and margin simulation | `future derivatives engine` |
| Q018 | Universal market explorer and compound screening | `app/, future instrument catalog` |
| Q019 | All sessions and 24/7 research workers while host running | `desk.py, future worker service` |
| Q020 | Free-first hybrid data, clearly labeled quality and licenses | `market.py` |
| Q021 | SMC/ICT plus quantitative, fundamental and AI signals | `analytics.py, future strategy engine` |
| Q022 | Autonomous evidence-backed issuer research and valuation | `filings.py, analytics.py` |
| Q023 | Validated SMC/ICT pattern detection and chart annotation | `future chart analytics` |
| Q024 | Observed versus inferred liquidity and order flow clearly distinguished | `future market depth engine` |
| Q025 | Universal timeframes, multi-chart, tick/volume and replay | `app/, future chart engine` |
| Q026 | AI multi-timeframe agents with conflict-aware no-trade option | `future agent orchestrator` |
| Q027 | Autonomous macro research with scenario comparisons | `future macro engine` |
| Q028 | Event risk engine with automated restrictions and human resumption | `future event-risk service` |
| Q029 | Multi-language sandboxed strategy studio and backtesting | `analytics.py, future strategy studio` |
| Q030 | Evidence-based multi-layer decisions and independent risk veto | `analytics.py, broker.py` |

### Portfolio, broker, quantitative risk

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q031 | Multiple simulated multi-currency portfolios, historical replay | `ledger.py, future portfolio system` |
| Q032 | Multi-currency treasury, FX exposures and consolidation | `future treasury module` |
| Q033 | AI-assisted risk-aware capital allocation with hard exposure limits | `ledger.py, broker.py` |
| Q034 | Autonomous capital preservation, persistent halt, reconciled restart | `ledger.py, broker.py` |
| Q035 | Margin and liquidation defense | `broker.py, future margin engine` |
| Q036 | Institutional correlated and hidden concentration risk surveillance | `analytics.py, future portfolio risk` |
| Q037 | Human-approved risk-aware portfolio optimization and rebalancing | `future optimization` |
| Q038 | Historical, stochastic and adversarial crisis simulations | `future stress engine` |
| Q039 | Strategy performance attribution, calibration and decay tracking | `analytics.py, future evaluator` |
| Q040 | Human-confirmed, idempotent, isolated live orders and immutable audits | `broker.py, ledger.py, future audit ledger` |

### Agent intelligence and evidence

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q041 | Hierarchical adaptive specialist research with budgets | `analytics.py, swarm.py` |
| Q042 | Local/cloud multi-model gateway with scoped routing and cost control | `integrations.py, future model gateway` |
| Q043 | Point-in-time research memory and provenance knowledge graph | `future research memory` |
| Q044 | Primary-source claim verification, reproducibility and rejection | `filings.py, future verifier` |
| Q045 | Bounded research orchestration, replanning and reproducible trace | `swarm.py, future orchestrator` |
| Q046 | Independent AI research benchmark lab and human-approved deployment | `future evaluation lab` |
| Q047 | Default-deny isolated agent tool infrastructure and audited capabilities | `future tool gateway` |
| Q048 | Persistent scheduled research, checkpoints and priority queues | `desk.py, future workers` |
| Q049 | Context-aware text/voice financial copilot with human approvals | `future copilot` |
| Q050 | Evidence-linked financial research briefings and competing theses | `app/research.js, future reports` |

### Desktop experience and operations

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q051 | Adaptive, original institutional workstation visual language | `app/` |
| Q052 | Docking, multi-monitor, detach, presets and workspace context | `app/, native/` |
| Q053 | AI-native charts with quantitative overlays and provenance | `app/` |
| Q054 | Programmable sandboxed indicator and drawing studio | `future indicator studio` |
| Q055 | Point-in-time financial market replay lab | `analytics.py, future replay engine` |
| Q056 | AI-triaged compound alert center and user-approved escalations | `desk.py, future alerts` |
| Q057 | Command palette, macros, slash commands with policy checks | `future command interface` |
| Q058 | Unified navigation, synced context and pinned workflows | `app/` |
| Q059 | Agent mission control with traceable dependencies and checkpoints | `future mission control` |
| Q060 | Adaptive performance, GPU if available and resource diagnostics | `native/, future desktop runtime` |

### Data, platforms and resilience

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q061 | Versioned institutional data fabric and provider reconciliation | `market.py, future data layer` |
| Q062 | Multi-broker isolated gateway with independent order authorization | `broker.py, future adapters` |
| Q063 | Local-first data storage, event sourcing, migration, integrity and backup | `ledger.py, future stores` |
| Q064 | Fail-closed resilient recovery, provider outages and broker reconciliation | `desk.py, broker.py` |
| Q065 | OS-protected integration and secrets vault with scoped capabilities | `future vault` |
| Q066 | Signed, sandboxed and versioned extension SDK | `future extension service` |
| Q067 | Financial verification, fault injection and release engineering | `test_*.py, tests/` |
| Q068 | Service reliability observability, health and diagnostics | `desk.py, future observability` |
| Q069 | Signed portable/installed desktop lifecycle, backup and rollback | `launch.py, native/, future updater` |
| Q070 | Modular local-first distributed intelligence with isolated broker execution | `integrations.py, future workers` |

### Security, privacy and governance

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q071 | Zero-trust device identity, role access and step-up authorization | `future identity service` |
| Q072 | Encrypted privacy boundaries, egress controls, retention and deletion | `future privacy service` |
| Q073 | Autonomous financial security operations with human-approved recovery | `future security operations` |
| Q074 | Tamper-evident decision ledger with traceable evidence and approvals | `ledger.py, future audit ledger` |
| Q075 | Policy-as-code global compliance, market access and license governance | `future compliance engine` |
| Q076 | Zero-trust prompt-injection and poisoned-source defense for agents | `future agent firewall` |
| Q077 | Institutional backup and business continuity with broker reconciliation | `ledger.py, future recovery` |
| Q078 | Mutual-auth network isolation and separate live execution gateway | `desk.py, future network layer` |
| Q079 | Nondelegable human approval, risk vetoes and revocable AI permissions | `broker.py, future policy engine` |
| Q080 | Independent security assurance, CI gates and safe public live rollout | `tests/, future release process` |

### Delivery, product economics and future

| ID | Accepted decision | Candidate source or target |
|---|---|---|
| Q081 | Evidence-gated phased delivery from trusted personal workstation | `docs/, tests/` |
| Q082 | First: secure end-to-end vertical slice | `desk.py, analytics.py, market.py, ledger.py` |
| Q083 | Formal performance, security and test readiness gates | `tests/, docs/` |
| Q084 | Risk-adjusted engineering prioritization | `docs/` |
| Q085 | Institutional product success scorecard | `docs/, future metrics` |
| Q086 | Staged personal/alpha/beta/public rollout with separate live gate | `future release governance` |
| Q087 | Free local core, BYO keys, paid hosted and professional options | `future product packaging` |
| Q088 | Strategic open-core with protected research IP and license compliance | `LICENSE, integrations/README.md` |
| Q089 | Financial intelligence academy, simulated learning and gated capabilities | `future education` |
| Q090 | Opt-in telemetry, support triage and feedback intelligence | `future diagnostics` |
| Q091 | Free-first compute budget enforcement and human-paid approval | `future cost governance` |
| Q092 | Founder-controlled AI engineering organization | `docs/, future engineering orchestration` |
| Q093 | Architecture inventory and traceable debt governance | `docs/, test_*.py` |
| Q094 | Measured evolution of Windows-first stack, migration tests | `launch.py, native/, desk.py` |
| Q095 | Founder-controlled bootstrap, grant, credits, reinvestment strategy | `docs/` |
| Q096 | Vendor-independent partner ecosystem with founder IP control | `integrations.py, future adapter contracts` |
| Q097 | Verifiable financial intelligence operating system differentiation | `docs/` |
| Q098 | 2027 foundation: trustworthy personal workstation, conditional beta | `docs/, tests/` |
| Q099 | Long-term global verifiable financial intelligence ecosystem | `docs/` |
| Q100 | Audit, gap analysis, architecture, validated vertical slice and controlled engineering | `docs/, tests/` |

## Evidence classification

- **Observed in source:** functionality visible in inspected files; still needs test execution and security review.
- **Tested:** named command, environment, date, commit, and pass/fail evidence recorded.
- **Production-validated:** security, reliability, data rights, regulatory and broker behavior independently checked against an acceptance protocol.
- **Proposed:** all capabilities above not backed by direct code plus test evidence. Avoid treating a referenced integration or model file as proof of operational readiness.

A requirement may be partially implemented. Maintain per-requirement sub-checks and a permanent test ID before marking it verified.
