"""Deterministic research and risk checks for Meridian Desk. Python standard library."""
from __future__ import annotations


from datetime import datetime, timezone
from functools import lru_cache
from math import ceil, expm1, isfinite, log, sqrt
from random import Random
from statistics import fmean, median, pstdev, stdev

YEAR = 365.2425 * 86400
PROFILES = (
    "Consumer_Staples_Moat", "Enterprise_Software_Switching",
    "Financials_Insurance_Float", "Healthcare_IP_Scale",
    "Industrials_CostAdvantage", "Macro_Index_24x7",
)
PODS = (
    ("Moat & competence", (
        "Pricing power", "Network effects", "Switching costs", "Cost advantage",
        "Regulatory barriers", "Obsolescence", "Unit economics", "Gross margin stability")),
    ("Accounting & valuation", (
        "Owner earnings", "Accrual quality", "Goodwill exposure", "Lease liabilities",
        "Maintenance investment", "Return on capital", "Terminal value", "Valuation sensitivity")),
    ("Inversion & debate", (
        "Downside case", "Compounding case", "Asset backing", "Narrative reconciliation",
        "Capital allocation", "Thesis arbitration")),
    ("Governance & filings", (
        "Risk disclosures", "Debt covenants", "Regulatory litigation", "Audit opinion",
        "Restatement review", "Governance evidence")),
    ("Macro & regime", (
        "Real rates", "Yield curve", "Inflation pass-through", "Credit spreads",
        "Currency exposure", "Volatility regime")),
    ("Portfolio risk", (
        "Margin of safety", "Capital loss", "Concentration", "Correlation",
        "Tail loss", "Cash reserve")),
    ("Execution research", (
        "Bar continuity", "Participation", "Session range", "Holding period", "Cost sensitivity")),
    ("Research integrity", (
        "Source scope", "Observation depth", "Forecast calibration", "Thesis drift", "Data lineage")),
)


@lru_cache(maxsize=1)
def _registry():
    return tuple(
        {"id": f"P{pod:02}-R{role:02}-S{sector:02}", "pod": pod_name,
         "pod_id": pod, "name": name, "profile": profile,
         "has_hard_veto": pod in (4, 6),
         "mandate": f"Review {name.lower()} for the {profile.replace('_', ' ')} profile using time-aligned evidence."}
        for pod, (pod_name, roles) in enumerate(PODS, 1)
        for role, name in enumerate(roles, 1)
        for sector, profile in enumerate(PROFILES, 1)
    )


def registry():
    return [dict(card) for card in _registry()]


def _number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a finite number")
    try:
        n = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"{name} must be a finite number") from None
    if not isfinite(n):
        raise ValueError(f"{name} must be finite")
    return n


def clean_bars(bars):
    result = []
    for i, bar in enumerate(bars):
        try:
            b = {k: _number(bar[k], k) for k in ("time", "open", "high", "low", "close", "volume")}
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"Invalid bar {i + 1}: {error}") from None
        if result and b["time"] <= result[-1]["time"]:
            raise ValueError("Bar timestamps must increase strictly")
        if (b["time"] < 0 or b["time"] > 253402300799 or b["volume"] < 0
                or b["low"] <= 0 or b["low"] > min(b["open"], b["close"])
                or b["high"] < max(b["open"], b["close"])):
            raise ValueError(f"Invalid timestamp, OHLC range or volume in bar {i + 1}")
        result.append(b)
    return result


def _iso_epoch(value):
    if isinstance(value, str):
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    return _number(value, "filing date")


def _pct(value):
    return "Unavailable" if value is None else f"{value:.2%}"


def _drawdown(values):
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = max(worst, 1 - value / peak)
    return worst


@lru_cache(maxsize=1)
def _stress_shocks():
    # Common random numbers avoid changing the measured risk on an unchanged book.
    rng = Random(7331)
    return tuple(sorted(rng.gauss(0.0, 1.0) for _ in range(10_000))[:100])


def _price_risk(clean):
    closes = [r["close"] for r in clean]
    simple = [b / a - 1 for a, b in zip(closes, closes[1:])]
    logret = [log(b) - log(a) for a, b in zip(closes, closes[1:])]
    intervals = [b["time"] - a["time"] for a, b in zip(clean, clean[1:])]
    step = median(intervals) if intervals else None
    risk = {
        "bars": len(clean), "median_interval_sec": step,
        "gaps_over_2x_interval": sum(x > 2 * step for x in intervals),
        "window_return": closes[-1] / closes[0] - 1,
        "drawdown": 1 - closes[-1] / max(closes),
        "max_drawdown": _drawdown(closes), "bar_volatility": None,
        "forecast_volatility": None, "cvar99": None, "var99": None,
        "historical_cvar99": None, "quarter_kelly": None,
        "regime": "Warming up", "momentum": None,
    }
    if len(logret) < 20:
        return risk
    # Fixed GARCH(1,1) coefficients, long-run variance targeted to observed returns.
    unconditional = stdev(logret) ** 2
    variance = unconditional
    mean = fmean(logret)
    for r in logret:
        variance = .04 * unconditional + .08 * (r - mean) ** 2 + .88 * variance
    sigma = sqrt(variance)
    # Zero-drift one-bar stress; report losses as positive fractions.
    tail = [max(0.0, -expm1(sigma * z)) for z in _stress_shocks()]
    risk.update(bar_volatility=sqrt(unconditional), forecast_volatility=sigma,
                cvar99=fmean(tail), var99=tail[-1],
                momentum=closes[-1] / closes[-21] - 1)
    if len(simple) >= 100:
        n = ceil(len(simple) * .01)
        risk["historical_cvar99"] = max(0, -fmean(sorted(simple)[:n]))
    if len(simple) >= 60:
        gains = [r for r in simple if r > 0]
        losses = [-r for r in simple if r < 0]
        if gains and losses:
            odds = fmean(gains) / fmean(losses)
            # Flat bars contribute no information about the conditional win odds.
            p = len(gains) / (len(gains) + len(losses))
            risk["quarter_kelly"] = min(.15, max(0.0, .25 * (p - (1 - p) / odds)))
    elevated = unconditional > 0 and sigma > 1.4 * sqrt(unconditional)
    risk["regime"] = ("Stressed" if risk["drawdown"] >= .15 or elevated else
                      "Pullback" if risk["drawdown"] >= .05 else "Orderly")
    return risk


def owner_earnings(row):
    """Net income + D&A - estimated maintenance capex - increase in working capital."""
    return (_number(row["net_income"], "net income") + _number(row["da"], "D&A")
            - _number(row["maintenance_capex"], "maintenance capex")
            - _number(row["delta_wc"], "working-capital change"))


def dcf(cash_flow, growth, hurdle=.10, terminal=.025, *, net_cash=0, shares=1):
    """Two-stage present value; years 6–10 fade linearly to terminal growth."""
    cash_flow, growth, hurdle, terminal, net_cash, shares = [
        _number(x, label) for x, label in zip(
            (cash_flow, growth, hurdle, terminal, net_cash, shares),
            ("cash flow", "growth", "discount rate", "terminal growth", "net cash", "shares"))
    ]
    if (cash_flow <= 0 or shares <= 0 or not .09 <= hurdle <= 1
            or not -1 < terminal <= .03 or not -1 < growth <= 1 or hurdle <= terminal):
        raise ValueError("DCF requires positive flow and shares, 9–100% hurdle, growth above −100% and terminal growth at most 3%")
    discounted = 0.0
    flow = cash_flow
    for year in range(1, 11):
        rate = growth if year <= 5 else growth + (terminal - growth) * (year - 5) / 5
        flow *= 1 + rate
        discounted += flow / (1 + hurdle) ** year
    terminal_pv = flow * (1 + terminal) / (hurdle - terminal) / (1 + hurdle) ** 10
    return (discounted + terminal_pv + net_cash) / shares


def demo_fundamentals():
    """Ten synthetic audited-scenario years, amounts in USD and shares in units."""
    rows = []
    for i, year in enumerate(range(2015, 2025)):
        sales = 250_000_000 * 1.055 ** i
        rows.append(dict(
            year=year, filed=f"{year + 1}-03-15", net_income=.19 * sales,
            da=.026 * sales, maintenance_capex=.024 * sales, delta_wc=.006 * sales,
            shares=10_200_000 * .997 ** i, cash=.14 * sales, debt=.07 * sales,
            revenue=sales, gross_profit=(.46 + i * .0003) * sales, ebit=.25 * sales,
            tax_rate=.24, invested_capital=.88 * sales, reinvestment=.33,
            interest=.008 * sales, assets=1.1 * sales, retained_earnings=.40 * sales,
            current_assets=.32 * sales, current_liabilities=.15 * sales,
            liabilities=.44 * sales, operating_cf=.23 * sales, long_term_debt=.06 * sales, new_equity_issued=0,
        ))
    return {"symbol": "DEMO", "source": "Synthetic ten-year manufacturing fixture",
            "profile": PROFILES[4], "as_of": "2025-03-15", "asset_type": "equity",
            "governance_reviewed": True, "synthetic": True, "annual": rows}


def _ratio(a, b):
    return a / b if b else None


def _f_score(rows):
    # Piotroski signals use opening assets; turnover uses average assets.
    if len(rows) < 3:
        return None
    a, b, c = rows[-3:]
    try:
        roa_now = c["net_income"] / b["assets"]
        roa_old = b["net_income"] / a["assets"]
        gross = lambda row: row["gross_profit"] / row["revenue"]
        turnover = lambda r, prev: r["revenue"] / ((r["assets"] + prev["assets"]) / 2)
        # Requires segregated long-term debt. Total debt is not a substitute.
        return sum((
            roa_now > 0, c["operating_cf"] > 0, roa_now > roa_old,
            c["operating_cf"] > c["net_income"],
            c["long_term_debt"] / ((c["assets"] + b["assets"]) / 2)
            < b["long_term_debt"] / ((b["assets"] + a["assets"]) / 2),
            c["current_assets"] / c["current_liabilities"] > b["current_assets"] / b["current_liabilities"],
            c["new_equity_issued"] == 0,
            gross(c) > gross(b), turnover(c, b) > turnover(b, a),
        ))
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def _z_score(row, price):
    try:
        a = row["assets"]
        return (1.2 * (row["current_assets"] - row["current_liabilities"]) / a
                + 1.4 * row["retained_earnings"] / a + 3.3 * row["ebit"] / a
                + .6 * price * row["shares"] / row["liabilities"] + row["revenue"] / a)
    except (KeyError, TypeError, ZeroDivisionError):
        return None


def _valuation(symbol, price, asof, data):
    if data is None:
        return None, []
    try:
        if symbol != str(data["symbol"]).upper() or not str(data["source"]).strip():
            raise ValueError("Fundamentals lack a matching symbol or source")
        if data.get("synthetic") and symbol != "DEMO":
            raise ValueError("Synthetic statements are restricted to DEMO")
        if data.get("asset_type", "equity") != "equity":
            raise ValueError("Corporate valuation requires an operating-equity instrument")
        if data.get("profile") in (PROFILES[2], PROFILES[5]):
            raise ValueError("This operating-company DCF does not cover banks, insurers or macro assets")
        stamp = _iso_epoch(data["as_of"])
        retrieval = data.get("as_of_basis") == "retrieval"
        if (stamp > asof and not retrieval) or (not data.get("synthetic") and asof - stamp > 550 * 86400):
            raise ValueError("Fundamentals are future-dated or stale relative to this snapshot")
        rows = []
        filing_dates = []
        for raw in data["annual"]:
            filed = raw.get("filed")
            if retrieval and not filed:
                continue
            if filed:
                filed_at = _iso_epoch(filed)
                # With only a filing day, wait until the day ends. Intra-day
                # filing timestamps can instead be used as soon as published.
                earliest = filed_at + (86400 if isinstance(filed, str) and len(filed) == 10 and retrieval else 0)
                if filed_at > stamp or earliest > asof:
                    continue
                filing_dates.append(filed_at)
            row = {k: _number(v, k) for k, v in raw.items() if k != "filed" and v is not None}
            if not 1900 <= row["year"] <= datetime.fromtimestamp(asof, timezone.utc).year:
                raise ValueError("Statement year is outside the analysis window")
            if row["shares"] <= 0 or row["maintenance_capex"] < 0 or row["da"] < 0:
                raise ValueError("Shares, D&A or maintenance capex are invalid")
            rows.append(row)
        if retrieval and filing_dates and asof - max(filing_dates) > 550 * 86400:
            raise ValueError("Latest available annual filing exceeds the 550-day evidence limit")
        rows.sort(key=lambda r: r["year"])
        rows = rows[-10:]
        if len(rows) < 5 or any(b["year"] - a["year"] != 1 for a, b in zip(rows, rows[1:])):
            raise ValueError("Outside circle of competence: five consecutive clean years required")
        earnings = [owner_earnings(r) for r in rows]
        if earnings[-1] <= 0 or sum(x < 0 for x in earnings[-5:]) >= 3:
            raise ValueError("Outside circle of competence: owner earnings failed the five-year check")
        last = rows[-1]
        gaps = []
        roic = None
        if all(r.get("invested_capital", 0) > 0 and "ebit" in r
               and 0 <= r.get("tax_rate", -1) <= 1 for r in rows):
            roic = median(r["ebit"] * (1 - r["tax_rate"]) / r["invested_capital"] for r in rows)
        gm_sd = None
        if all(r.get("revenue", 0) > 0 and "gross_profit" in r for r in rows):
            gm_sd = pstdev(r["gross_profit"] / r["revenue"] for r in rows)
        if roic is None or not 0 <= last.get("reinvestment", -1) <= 1:
            gaps.append("Growth-cap inputs incomplete; near-term growth capped at zero")
        earnings_growth = ((earnings[-1] / earnings[0]) ** (1 / (len(rows) - 1)) - 1
                           if earnings[0] > 0 else 0)
        growth_cap = 0 if gaps else roic * last["reinvestment"]
        growth = max(-.25, min(.12, earnings_growth, growth_cap))
        # Convert the equity-based owner earnings to operating flow by adding
        # after-tax interest, then bridge operating value to equity with cash less debt.
        if last.get("interest", -1) >= 0 and 0 <= last.get("tax_rate", -1) <= 1:
            after_tax_interest = last["interest"] * (1 - last["tax_rate"])
        else:
            after_tax_interest = 0
            gaps.append("Interest or tax-rate evidence missing; no interest added back to operating flow")
        operating_flow = earnings[-1] + after_tax_interest
        bridge = last["cash"] - last["debt"]
        intrinsic = dcf(operating_flow, growth, net_cash=bridge, shares=last["shares"])
        if intrinsic <= 0:
            raise ValueError("Estimated equity value is non-positive after net debt")
        return {
            "source": data["source"], "as_of": (datetime.fromtimestamp(max(filing_dates), timezone.utc).date().isoformat()
                                                if filing_dates else data["as_of"]),
            "retrieved_as_of": data["as_of"], "coverage_gaps": gaps, "synthetic": bool(data.get("synthetic")),
            "years": len(rows), "owner_earnings": earnings[-1], "median_roic": roic,
            "margin_dispersion": gm_sd, "net_debt_multiple": -bridge / earnings[-1],
            "interest_coverage": (_ratio(last["ebit"], last["interest"])
                                  if "ebit" in last and last.get("interest", 0) > 0 else None),
            "share_growth": (last["shares"] / rows[0]["shares"] - 1 if
                             data.get("synthetic") or data.get("shares_split_adjusted") is True else None),
            "intrinsic": intrinsic, "target": .7 * intrinsic, "margin": 1 - price / intrinsic,
            "growth": growth, "hurdle": .10, "terminal": .025,
            "stressed_intrinsic": dcf(operating_flow, growth, .12, .015, net_cash=bridge, shares=last["shares"]),
            "f_score": _f_score(rows),
            "z_score": _z_score(last, price) if data.get("profile") == PROFILES[4] else None,
        }, []
    except KeyError as error:
        return None, [f"Missing required annual-statement input: {error.args[0]}"]
    except (ValueError, TypeError, OverflowError, OSError, ZeroDivisionError) as error:
        return None, [str(error)]


def _market_only(symbol):
    compact = symbol.replace("/", "").replace("-", "").replace("=X", "")
    currencies = {"AUD", "CAD", "CHF", "EUR", "GBP", "JPY", "NZD", "USD", "CNY", "INR", "XAU", "XAG"}
    crypto = ("BTC", "ETH", "SOL", "ADA", "XRP", "DOGE", "LTC", "DOT", "AVAX", "LINK")
    return (symbol.startswith("^") or symbol.endswith("=F") or symbol in {"SPY"} or
            (len(compact) == 6 and compact[:3] in currencies and compact[3:] in currencies) or
            any(compact in (base, base + "USD", base + "USDT", base + "EUR") for base in crypto))


def _review(card, signal, detail):
    return dict(id=card["id"], pod=card["pod"], pod_id=card["pod_id"],
                name=card["name"], profile=card["profile"], signal=signal,
                detail=detail, veto=card["has_hard_veto"] and signal == "VETO")


def analyze(symbol, bars, *, fundamentals=None, governance_flags=()):
    """Run a deterministic twelve-specialist panel against one immutable price snapshot."""
    symbol = str(symbol).strip().upper()
    try:
        clean = clean_bars(bars)
        if not clean:
            raise ValueError("No completed bars are available")
    except (TypeError, ValueError) as error:
        return dict(verdict="DATA HOLD", veto=True, reasons=[str(error)], metrics={},
                    agents=[], risk={}, valuation=None, pod_counts={}, asof=None)
    last = clean[-1]
    risk = _price_risk(clean)
    market_only = _market_only(symbol)
    val, issues = (None, []) if market_only else _valuation(symbol, last["close"], last["time"], fundamentals)
    if not market_only and fundamentals is None:
        issues.append("Issuer financials are unavailable for valuation")
    profile = (fundamentals or {}).get("profile", PROFILES[0])
    if market_only:
        profile = PROFILES[5]
    if profile not in PROFILES:
        profile = PROFILES[0]
    cards = {c["name"]: c for c in _registry() if c["profile"] == profile}
    panel = []

    def add(name, signal, detail):
        panel.append(_review(cards[name], signal, detail))

    if val:
        dispersion = val["margin_dispersion"]
        add("Gross margin stability", "UNKNOWN" if dispersion is None else "PASS" if dispersion < .03 else "WATCH",
            f'{val["years"]} years of statements. Gross-margin standard deviation {_pct(val["margin_dispersion"])}.')
        add("Owner earnings", "PASS", f'Latest owner earnings {val["owner_earnings"]:,.0f} in reporting currency. {val["source"]}.')
        add("Downside case", "WATCH" if last["close"] > .7 * val["stressed_intrinsic"] else "PASS",
            f'At a 12% hurdle and 1.5% terminal growth, intrinsic value falls to {val["stressed_intrinsic"]:,.2f} per share.')
        roic = val["median_roic"]
        add("Compounding case", "UNKNOWN" if roic is None else "PASS" if roic > .15 else "WATCH",
            f'Median ROIC {_pct(val["median_roic"])}. Modeled near-term growth {_pct(val["growth"])}.')
    else:
        why = "Corporate statements do not apply to this instrument." if market_only else "; ".join(issues)
        add("Gross margin stability", "N/A" if market_only else "UNKNOWN", why)
        add("Owner earnings", "N/A" if market_only else "UNKNOWN", why)
        add("Downside case", "WATCH" if risk["max_drawdown"] >= .10 else "OBSERVE",
            f'Peak-to-trough close drawdown {_pct(risk["max_drawdown"])} in the observed window.')
        add("Thesis arbitration", "OBSERVE", f'The first-to-last close return is {_pct(risk["window_return"])} across {len(clean)} bars.')

    if isinstance(governance_flags, str):
        governance_flags = [governance_flags]
    flags = [str(flag) for flag in (governance_flags or ()) if str(flag).strip()]
    if flags:
        add("Governance evidence", "VETO", "Governance flag: " + "; ".join(flags))
    elif market_only:
        add("Governance evidence", "N/A", "Issuer-filing check does not apply to this instrument.")
    elif (fundamentals or {}).get("governance_reviewed") is not True:
        add("Governance evidence", "VETO", "A completed issuer governance review has not been supplied.")
    else:
        add("Governance evidence", "PASS", "Governance screening marked reviewed in the supplied statement set.")

    add("Volatility regime", "WATCH" if risk["regime"] == "Stressed" else "OBSERVE",
        f'{risk["regime"]} regime. Conditional one-bar volatility {_pct(risk["forecast_volatility"])}.')
    if market_only:
        add("Margin of safety", "N/A", "Market-risk screen only. No intrinsic-value estimate for this instrument.")
    elif not val:
        add("Margin of safety", "VETO", "; ".join(issues))
    elif val["coverage_gaps"]:
        add("Margin of safety", "VETO", f'Indicative margin {_pct(val["margin"])}. ' + "; ".join(val["coverage_gaps"]))
    else:
        add("Margin of safety", "PASS" if val["margin"] + 1e-12 >= .30 else "VETO",
            f'Margin of safety {_pct(val["margin"])}. The 30% entry ceiling is {val["target"]:,.2f}.')
    if risk["cvar99"] is None:
        add("Tail loss", "VETO", "At least 21 completed bars are required for one-bar risk estimation.")
    else:
        add("Tail loss", "VETO" if risk["cvar99"] >= .08 else "PASS",
            f'99% one-bar expected shortfall {_pct(risk["cvar99"])} under 10,000 fixed-seed normal shocks. Policy limit 8%.')
    add("Capital loss", "VETO" if risk["drawdown"] >= .20 else "PASS",
        f'Current drawdown {_pct(risk["drawdown"])} from the window high. Policy limit 20%.')
    add("Bar continuity", "WATCH" if risk["gaps_over_2x_interval"] else "OBSERVE",
        f'{risk["gaps_over_2x_interval"]} intervals exceed twice the median spacing. This can include session closures.')
    add("Session range", "OBSERVE",
        f'Latest bar low {last["low"]:,.5f}, high {last["high"]:,.5f}. Volume {last["volume"]:,.2f} feed units.')
    add("Source scope", "OBSERVE",
        (f'Valuation source: {val["source"]}. Available as of {val["as_of"]}.' if val
         else f'Analysis uses {len(clean)} OHLCV bars. No eligible corporate valuation.'))
    # Written policy is evaluated after the panel. Neither add-on opinions nor a vote
    # can overturn an explicit governance or portfolio risk veto.
    reasons = [a["detail"] for a in panel if a["veto"]]
    veto = bool(reasons)
    if veto:
        verdict = "RISK HOLD"
    elif market_only:
        verdict = "PAPER ELIGIBLE"
    else:
        verdict = "VALUE SCREEN PASS"
    if not reasons:
        reasons = [f'Price risk is inside the paper policy. {risk["bars"]} bars reviewed.',
                   ("Corporate value screen does not apply." if market_only else
                    f'The quote clears the 30% screen at {val["target"]:,.2f} or below.')]
    metrics = {
        "Window return": _pct(risk["window_return"]), "Peak drawdown": _pct(risk["max_drawdown"]),
        "99% expected shortfall / bar": _pct(risk["cvar99"]),
        "Realized volatility / bar": _pct(risk["bar_volatility"]),
        "Market regime": risk["regime"], "Observations": str(len(clean)),
        "Quarter Kelly, capped": _pct(risk["quarter_kelly"]),
    }
    if val:
        metrics.update({
            "Intrinsic value / share": f'{val["intrinsic"]:,.2f}', "30% entry ceiling": f'{val["target"]:,.2f}',
            "Margin of safety": _pct(val["margin"]), "Median ROIC": _pct(val["median_roic"]),
            "Net debt / earnings": f'{val["net_debt_multiple"]:.2f}×',
            "Share-count change": ("Split-adjusted history required" if val["share_growth"] is None
                                   else _pct(val["share_growth"])),
            "Piotroski F-score": "Unavailable" if val["f_score"] is None else f'{val["f_score"]}/9',
            "Industrial Altman Z": "Unavailable" if val["z_score"] is None else f'{val["z_score"]:.2f}',
            "Interest coverage": "Unavailable" if val["interest_coverage"] is None else f'{val["interest_coverage"]:.2f}×',
            "Fundamentals available": str(val["as_of"]), "Fundamental source": val["source"],
        })
    return dict(verdict=verdict, reasons=reasons, veto=veto, metrics=metrics,
                agents=panel, risk=risk, valuation=val, asof=last["time"],
                pod_counts={name: sum(a["pod"] == name for a in panel) for name, _ in PODS})


def _advance(nav, position, target, previous_close, row, cost):
    opening_nav = nav * (1 + position * (row["open"] / previous_close - 1))
    change = abs(target - position)
    end_nav = opening_nav * (1 - cost * change) * (1 + target * (row["close"] / row["open"] - 1))
    return end_nav, change


def _signal(clean, index, lookback):
    # index is the bar whose open is used for the fill; all signals end at index - 1.
    return int(clean[index - 1]["close"] > clean[index - 1 - lookback]["close"])


def backtest(symbol, bars):
    """Expanding-window long/cash momentum benchmark with next-open fills and costs."""
    try:
        clean = clean_bars(bars)
    except (TypeError, ValueError) as error:
        return {"Status": "Invalid bars", "Reason": str(error)}
    if len(clean) < 60:
        return {"Status": "Insufficient history", "Required": "60 chronological OHLCV bars", "Available": str(len(clean))}
    choices = (5, 10, 20)
    cost = .001  # 10 bp per one-way transition, charged on opening notional
    start = max(40, len(clean) // 3)
    fold_size = max(10, ceil((len(clean) - start) / 5))
    gates = set(range(start, len(clean), fold_size))
    window = choices[0]
    scores = {n: 1.0 for n in choices}
    train_pos = {n: 0 for n in choices}
    navs = [1.0]
    strategy_returns = []
    turnover = 0.0
    position = 0
    exit_cost = 0
    for i in range(1 + max(choices), len(clean)):
        prev = clean[i - 1]["close"]
        if i in gates:
            # Training simulation includes only completed bars strictly before i.
            window = max(choices, key=scores.get)
        targets = {n: _signal(clean, i, n) for n in choices}
        if i >= start:
            target = targets[window]
            next_nav, traded = _advance(navs[-1], position, target, prev, clean[i], cost)
            turnover += traded
            position = target
            if i == len(clean) - 1 and position:
                next_nav *= 1 - cost
                turnover += 1
                exit_cost = 1
            strategy_returns.append(next_nav / navs[-1] - 1)
            navs.append(next_nav)
        for n in choices:
            scores[n], _ = _advance(scores[n], train_pos[n], targets[n], prev, clean[i], cost)
            train_pos[n] = targets[n]
    # Comparator buys at the same first test open, liquidates at the final close.
    passive = (1 - cost) ** 2 * clean[-1]["close"] / clean[start]["open"] - 1
    total = navs[-1] - 1
    dt = max(0, clean[-1]["time"] - clean[start]["time"])
    elapsed_years = dt / YEAR
    cagr = (navs[-1] ** (1 / elapsed_years) - 1) if elapsed_years >= 1 else None
    mean = fmean(strategy_returns)
    vol = stdev(strategy_returns)
    downside = sqrt(fmean(min(r, 0) ** 2 for r in strategy_returns))
    return {
        "Status": "Complete", "Strategy": "Walk-forward long/cash momentum",
        "Instrument": str(symbol), "Out-of-sample bars": str(len(strategy_returns)),
        "Refits": str(len(gates)), "Net return": _pct(total), "Maximum drawdown": _pct(_drawdown(navs)),
        "Buy and hold (same asset)": _pct(passive), "Excess vs buy and hold": _pct(total - passive),
        "CAGR": _pct(cagr) if cagr is not None else "Under one year of out-of-sample data",
        "Sharpe / bar (0% cash yield)": f"{mean / vol:.3f}" if vol else "Unavailable",
        "Sortino / bar (0% target)": f"{mean / downside:.3f}" if downside else "Unavailable",
        "One-way turnover": f"{turnover:.1f}×", "Cost per transition": "10 bp",
        "Final liquidation": "Included" if exit_cost else "Ended in cash",
    }


def demo_history():
    """Synthetic weekday bars, 2019–2025. Independent deterministic price process."""
    from datetime import date, timedelta
    from math import exp, sin
    rng = Random(305)
    day = date(2019, 1, 1)
    end = date(2025, 12, 31)
    previous = 59.0
    history = []
    i = 0
    shock = 0.0
    while day <= end:
        if day.weekday() < 5:
            shock = .92 * shock + rng.gauss(0, .009)
            mid = 65 * exp(.00024 * i + .23 * sin(i / 99) + .06 * sin(i / 30) + shock)
            opening = previous * exp(rng.gauss(0, .002))
            history.append({
                "time": datetime(day.year, day.month, day.day, 21, tzinfo=timezone.utc).timestamp(),
                "open": opening, "close": mid,
                "high": max(opening, mid) * (1 + rng.uniform(0, .008)),
                "low": min(opening, mid) * (1 - rng.uniform(0, .008)),
                "volume": rng.randrange(100_000, 450_000),
            })
            previous = mid
            i += 1
        day += timedelta(days=1)
    return history


def _value_replay(data, history):
    """Trade the prior close's published value estimate at the following open."""
    rows = sorted(data["annual"], key=lambda r: _iso_epoch(r["filed"]))
    active = []
    intrinsic = None
    shares, cash = 0.0, 1.0
    fee = .001
    turnover = 0.0
    trades = 0
    navs = [1.0]
    nav_returns = []
    start = None
    for i in range(1, len(history)):
        prev, bar = history[i - 1:i + 1]
        old_count = len(active)
        while len(active) < len(rows) and _iso_epoch(rows[len(active)]["filed"]) <= prev["time"]:
            active.append(rows[len(active)])
        if len(active) != old_count:
            dated = dict(data, as_of=active[-1]["filed"], annual=active)
            valuation, _ = _valuation(data["symbol"], prev["close"], prev["time"], dated)
            intrinsic = valuation["intrinsic"] if valuation else None
        if not intrinsic and start is None:
            continue
        if start is None:
            start = i
        opening = bar["open"]
        nav_open = cash + shares * opening
        # Price orders are subject to a next-open limit. Missing eligible
        # fundamentals suspend additional buys and close any existing allocation.
        if intrinsic and not shares and max(prev["close"], opening) <= .7 * intrinsic:
            notional = .15 * nav_open
            shares = notional / opening
            cash -= notional * (1 + fee)
            turnover += notional / nav_open
            trades += 1
        elif shares and (not intrinsic or prev["close"] >= intrinsic):
            sale = shares * opening
            cash += sale * (1 - fee)
            turnover += sale / nav_open
            shares = 0.0
            trades += 1
        nav = cash + shares * bar["close"]
        if i == len(history) - 1 and shares:
            sale = shares * bar["close"]
            turnover += sale / nav
            nav -= sale * fee
            trades += 1
        nav_returns.append(nav / navs[-1] - 1)
        navs.append(nav)
    if start is None:
        return {"Status": "Insufficient point-in-time statements"}
    years = (history[-1]["time"] - history[start]["time"]) / YEAR
    passive = (1 - fee) ** 2 * history[-1]["close"] / history[start]["open"] - 1
    ret = navs[-1] - 1
    avg = fmean(nav_returns)
    sigma = stdev(nav_returns) if len(nav_returns) > 1 else 0
    downside = sqrt(fmean(min(x, 0) ** 2 for x in nav_returns))
    iso_date = lambda b: datetime.fromtimestamp(b["time"], timezone.utc).date().isoformat()
    return {
        "Status": "Complete", "Strategy": "Historical value screen, synthetic DEMO",
        "Test period": f'{iso_date(history[start])} to {iso_date(history[-1])}',
        "Data": "Synthetic weekday OHLCV and dated annual statements",
        "Out-of-sample bars": str(len(nav_returns)), "Fills": str(trades),
        "Net return": _pct(ret), "Maximum drawdown": _pct(_drawdown(navs)),
        "CAGR": _pct(navs[-1] ** (1 / years) - 1) if years >= 1 else "Under one year",
        "Annualized Sharpe (0% cash yield)": f"{avg / sigma * sqrt(len(nav_returns) / years):.3f}" if sigma and years > 0 else "Unavailable",
        "Annualized Sortino (0% target)": f"{avg / downside * sqrt(len(nav_returns) / years):.3f}" if downside and years > 0 else "Unavailable",
        "Buy and hold (same synthetic asset)": _pct(passive), "Excess vs buy and hold": _pct(ret - passive),
        "One-way turnover": f"{turnover:.2f}×", "Cost per fill": "10 bp",
        "Entry and exit": "15% allocation at 30% discount; exit on full value",
    }


def demo_value_backtest():
    return _value_replay(demo_fundamentals(), demo_history())
