# Phase 2 — Windows desktop navigation and observation provenance

**Scope:** UI-only work on the existing MeridianDesk application. No changes to broker, risk, storage, model weights, bundled runtime, live orders or trading policy.

## User-visible changes

- **Quick switch:** click **Search desk** at the top of the workstation, or press **Ctrl+K** or **/** (outside text inputs). Filter workspaces and the eight existing instruments; use arrows and Enter to select, Escape to close. No privileged submit-order, halt toggle or broker action is exposed.
- **Data provenance:** above the Market overview quotes, inspect source, timestamp and age, reported session, and bid/ask availability. Status distinguishes SIMULATED, STALE, PUBLIC BAR and EXCHANGE TICKER. These are descriptive labels, not trade authorization. Independent backend risk and broker checks still run for every order.
- **Visual shell:** improve dark-blue surface contrast, selected navigation and focus rings, responsive command search and observation details. Existing chart, research, portfolio and execution workflows remain intact.

## Verification evidence and limitations

1. GitHub CI runs the same 41 Python unit tests and seven authenticated local API tests as Phase 1.
2. Added Node JavaScript syntax checks and an offline VM contract that tests keyboard shortcuts, navigation, provenance labels, HTML escaping and restricted command types.
3. Extended tests/verify-desktop.cjs Windows Edge acceptance to check visible SIMULATED provenance and page/instrument quick navigation.
4. The real Edge/WebView2 installation, E-drive runtime, bundled workers and laptop-specific graphical performance **cannot be certified by the Linux CI runner**. Windows GUI testing remains a separate acceptance gate.

## Safe installation after reviewed merge

The GitHub source checkout is not the complete E-drive deployment. After founder approval and merge, **close MeridianDesk** and back up these exact three source files in E:\MeridianDesk\app:

- index.html
- app.js
- app.css

Copy the corresponding three files from the **pinned merged commit**, without replacing the runtime, data, model weights, EAs, credentials, SDK or launcher. Reopen Open Meridian Desk.lnk and verify the search button, data provenance strip, DEMO navigation, existing charts, and persistent halt state. Then run the Windows UI acceptance test from the existing deployment. If the UI fails, close it and restore the three backed-up files. The native Meridian Desk.exe does not need rebuilding for this frontend-only change.

## Safety acceptance before public use

- Verify real/simulated and stale source labels in the Windows desktop, including data outages.
- Verify the command picker cannot submit an order, alter trading controls, reach providers or invoke tools.
- Confirm keyboard focus/Escape, mobile-width/compact window layouts and readable source detail.
- Confirm no change to broker configuration, live execution controls, local account data or backups.
- Record actual Windows performance and accessibility failures against a pinned source revision.

**This phase does not claim production/institutional readiness or licensed real-time entitlements.**
