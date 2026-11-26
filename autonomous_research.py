"""Bounded autonomous *research*, not delegated trading, for MeridianDesk.

Six deterministic specialist workers plan, examine, challenge and verify a single
frozen OHLCV observation. They never access tools, networks, LLM providers,
credentials, brokerage APIs or mutable account state. Missing source evidence
leads to abstention, not invented fundamentals or performance promises.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import time

from analytics import clean_bars


VERSION = "research-agents.v1"
LIMIT = 6
MISSIONS = (
    ("provenance", "Source and temporal integrity"),
    ("continuity", "Market-data continuity"),
    ("trend", "Trend observation"),
    ("risk", "Capital-risk challenger"),
    ("contrarian", "Adversarial counter-thesis"),
    ("fundamentals", "Issuer-evidence gap"),
)


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _pct(value):
    return "Unavailable" if not _number(value) else f"{value:+.2%}"


def _entry(mid, status, summary, *keys):
    return {"id": mid, "name": dict(MISSIONS)[mid], "signal": status,
            "summary": summary, "evidence": list(keys)}


def _provenance(facts):
    bad = facts["stale"] or not facts["provider_observed"]
    note = ("Quote is stale or not an observed market feed; research must abstain."
            if bad else "Source and UTC observation time are recorded. Venue licensing and latency remain unverified.")
    return _entry("provenance", "HOLD" if bad else "OBSERVE", note,
                  "source", "asof_utc", "transport", "stale", "provider_observed")


def _continuity(facts):
    gaps = facts["gaps_over_2x_interval"]
    limited = facts["bar_count"] < 32
    return _entry("continuity", "HOLD" if limited else "WATCH" if gaps else "OBSERVE",
                  (f"{gaps} inter-bar gaps exceed twice median spacing; scheduled market closures may explain gaps."
                   if gaps else "No >2x inter-bar gaps in this observation window.") +
                  (" Fewer than 32 bars, insufficient for a reliable short-window study." if limited else ""),
                  "bar_count", "gaps_over_2x_interval", "interval")


def _trend(facts):
    n = facts["bar_count"]
    if n < 32:
        return _entry("trend", "UNKNOWN",
                      "Insufficient completed observations to compare price windows.",
                      "bar_count")
    momentum = facts["return_20"]
    direction = ("higher" if momentum > .01 else "lower" if momentum < -.01 else "flat")
    return _entry("trend", "OBSERVE",
                  f"Last 20-bar close return {_pct(momentum)}; recent prices are {direction} on that one window. "
                  "Not a forecast or a recommendation.",
                  "return_20", "last_close", "interval")


def _risk(facts):
    tail = facts["cvar99"]
    tail_bad = not _number(tail)
    stressed = facts["drawdown"] >= .20 or (_number(tail) and tail >= .08)
    return _entry("risk", "HOLD" if (stressed or tail_bad) else "WATCH",
                  f"Close-to-peak drawdown {_pct(facts['drawdown'])}; modeled one-bar expected shortfall "
                  f"{_pct(tail)}. Model assumptions are unverified for this exchange.",
                  "drawdown", "cvar99", "regime")


def _contrarian(facts):
    return _entry("contrarian", "WATCH",
                  f"Adverse case: the observed maximum drawdown reached {_pct(facts['max_drawdown'])}; "
                  f"the window return was {_pct(facts['window_return'])}. "
                  "Historical observation does not establish future downside, liquidity or news-event risk.",
                  "max_drawdown", "window_return", "currency")


def _fundamentals(facts):
    if not facts["issuer_statements"]:
        return _entry("fundamentals", "UNKNOWN",
                      "No verified, time-aligned issuer statements, corporate actions or governance files "
                      "were supplied; earnings quality and fair value are not established.",
                      "issuer_statements", "currency")
    return _entry("fundamentals", "OBSERVE",
                  "The existing research snapshot contains a sourced valuation; independent audit and "
                  "listing-currency comparability remain outstanding.",
                  "issuer_statements", "currency")


_WORKERS = {
    "provenance": _provenance, "continuity": _continuity, "trend": _trend,
    "risk": _risk, "contrarian": _contrarian, "fundamentals": _fundamentals,
}


def investigate(symbol, snapshot, assessment, *, now=None):
    """Plan → execute → verify → synthesize. Returns a JSON-safe report.

    The scheduler and analyst cannot issue orders. Data must be pre-acquired
    through the existing selected-symbol flow, and no provider is contacted.
    """
    if not isinstance(symbol, str) or not symbol or not isinstance(snapshot, dict):
        raise ValueError("A frozen, identified market snapshot is required.")
    if not isinstance(assessment, dict):
        raise ValueError("A risk-assessment snapshot is required.")
    # Strictly bounded input reduces CPU, memory and payload cost.
    raw = snapshot.get("bars")
    if not isinstance(raw, list) or not 2 <= len(raw) <= 3000:
        raise ValueError("Research requires between 2 and 3000 ordered OHLCV bars.")
    clean = clean_bars(raw)
    selected = clean[-256:]
    last = selected[-1]
    asof = snapshot.get("asof")
    if not _number(asof) or asof < last["time"] or asof - last["time"] > 3600:
        raise ValueError("Source and bar timestamps cannot be reconciled.")
    if not isinstance(snapshot.get("source"), str) or not snapshot["source"].strip():
        raise ValueError("Source attribution is mandatory.")
    if assessment.get("asof") != clean[-1]["time"]:
        raise ValueError("Risk analysis does not match the captured OHLCV snapshot.")

    utc = datetime.fromtimestamp(asof, timezone.utc).isoformat()
    risk = assessment.get("risk") or {}
    steps = [b["time"] - a["time"] for a,b in zip(selected,selected[1:])]
    median_step = sorted(steps)[len(steps)//2]
    # Canonical evidence is derived exclusively from the same bounded snapshot.
    facts = {
        "symbol":symbol, "source":snapshot["source"], "asof_utc":utc,
        "transport":str(snapshot.get("transport") or "UNKNOWN"),
        "stale": bool(snapshot.get("stale", True)),
        "provider_observed": bool(snapshot.get("live", False)),
        "interval":str(snapshot.get("interval") or "unknown"),
        "currency":str(snapshot.get("currency") or "UNVERIFIED"),
        "bar_count":len(selected), "last_close":last["close"],
        "window_return":selected[-1]["close"]/selected[0]["close"]-1,
        "return_20":selected[-1]["close"]/selected[-21]["close"]-1 if len(selected)>20 else None,
        "max_drawdown":risk.get("max_drawdown"),
        "drawdown":risk.get("drawdown"),
        "cvar99":risk.get("cvar99"),
        "regime":str(risk.get("regime") or "UNKNOWN"),
        "gaps_over_2x_interval":sum(delta>2*median_step for delta in steps),
        "issuer_statements":bool(assessment.get("valuation")),
    }
    # Never permit NaN/Infinity to enter a signed or audited report.
    if not _number(facts["max_drawdown"]) or not _number(facts["drawdown"]):
        raise ValueError("Valid drawdown evidence is required.")
    # Independently verify key risk metrics against the raw snapshot. The
    # specialist panel cannot launder arbitrary risk values into source facts.
    closes=[bar["close"] for bar in clean]
    expected_drawdown=1-closes[-1]/max(closes)
    peak=closes[0]
    expected_max=0.
    for closing in closes:
        peak=max(peak,closing)
        expected_max=max(expected_max,1-closing/peak)
    if (not math.isclose(facts["drawdown"],expected_drawdown,rel_tol=1e-9,abs_tol=1e-9)
            or not math.isclose(facts["max_drawdown"],expected_max,rel_tol=1e-9,abs_tol=1e-9)):
        raise ValueError("Risk metrics do not agree with the source OHLCV snapshot.")
    if facts["cvar99"] is not None and (not _number(facts["cvar99"]) or
                                         not 0 <= facts["cvar99"] <= 1):
        raise ValueError("Modeled tail-loss evidence must be a finite fraction.")
    text = json.dumps({"symbol":symbol, "bars":selected,
                       "source":snapshot["source"], "asof":asof,
                       "interval":facts["interval"], "currency":facts["currency"]},
                      sort_keys=True, separators=(",",":"), allow_nan=False)
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()

    # Bounded deterministic planner: roles chosen by availability, never by user-supplied instructions.
    plan = [{"id":mid, "purpose":name} for mid,name in MISSIONS][:LIMIT]
    outputs = []
    for task in plan:
        mid = task["id"]
        try:
            result = _WORKERS[mid](facts)
        except (ArithmeticError, TypeError, ValueError, KeyError) as exc:
            result = _entry(mid, "HOLD", "The worker could not validate its evidence: "+
                            type(exc).__name__)
        outputs.append(result)

    # Independent evidence verifier: reject unknown references, duplicated roles,
    # and mismatched results before publishing a research report.
    verified = len(outputs)==len(plan) and len({o["id"] for o in outputs})==len(outputs)
    verified = verified and all(o["id"]==plan[i]["id"] and
                                o["signal"] in ("OBSERVE","WATCH","UNKNOWN","HOLD") and
                                all(key in facts for key in o["evidence"])
                                for i,o in enumerate(outputs))
    if not verified:
        raise ValueError("Autonomous specialist report failed evidence verification.")
    holds = [o["name"] for o in outputs if o["signal"]=="HOLD"]
    unknown = [o["name"] for o in outputs if o["signal"]=="UNKNOWN"]
    veto = bool(assessment.get("veto"))
    # No 'BUY' or 'SELL' state exists; even the cleanest report is REVIEW ONLY.
    abstain = (facts["stale"] or not facts["provider_observed"] or veto or bool(holds)
               or not facts["issuer_statements"])
    decision = "ABSTAIN" if abstain else "REVIEW ONLY"
    reasons = []
    if facts["stale"]: reasons.append("Price observation is stale.")
    if not facts["provider_observed"]: reasons.append("Source is simulated or not an observed provider feed.")
    if veto: reasons.append("Independent risk/valuation veto is active.")
    if holds: reasons.append("Specialist holds: "+", ".join(holds))
    if unknown: reasons.append("Evidence gaps: "+", ".join(unknown))
    if not facts["issuer_statements"]:
        reasons.append("Missing independently verified issuer fundamentals.")
    if not reasons:
        reasons.append("Source risk checks passed; no trading authority or return forecast exists.")
    return {
        "schema":VERSION, "mode":"OFFLINE RULE-BASED AUTONOMOUS RESEARCH",
        "symbol":symbol, "decision":decision, "execution":"DISABLED", "model":"None / deterministic",
        "created_utc":datetime.fromtimestamp(time.time() if now is None else now, timezone.utc).isoformat(),
        "snapshot_sha256":digest, "source":facts["source"],
        "source_asof":facts["asof_utc"], "currency":facts["currency"],
        "data_policy":{"observed":facts["provider_observed"],"stale":facts["stale"],
                       "exchange_entitlement_verified":False,
                       "corporate_actions_verified":False},
        "plan":plan, "agents":outputs, "verifier":{"passed":True,"evidence_fields":len(facts)},
        "reasons":reasons,
        "constraints":["No broker operations", "No trades or portfolio changes",
                       "No model, cloud or external tool calls",
                       "Source provenance is not a market-data license",
                       "No issuer valuation without verified filings",
                       "Not a forecast of returns or an investment recommendation"],
    }


def report_text(report):
    """Bounded human-readable audit summary (the UI retains structured evidence)."""
    lines = [f"{report['symbol']} — {report['decision']} — autonomous local research",
             f"Source: {report['source']} · {report['source_asof']} · {report['currency']}",
             "Input SHA256: "+report["snapshot_sha256"],
             "Evidence verification: "+("PASS" if report["verifier"]["passed"] else "FAIL"),
             "Execution: DISABLED",
             "Reasons: "+"; ".join(report["reasons"])]
    lines.extend(f"{a['name']} [{a['signal']}]: {a['summary']}" for a in report["agents"])
    return "\n".join(lines)
