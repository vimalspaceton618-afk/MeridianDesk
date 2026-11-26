"""Coordinate installed research engines over a frozen, source-labelled snapshot."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from integrations import run_integration, statuses


def combined_review(symbol, snapshot, analysis, *, with_provider=False, worker=run_integration, availability=statuses):
    engines = ["ruflo", "kronos"]
    if with_provider:
        engines.append("tradingagents")
    installed = {row["id"]: row for row in availability()}
    bars = snapshot["bars"]
    asof = datetime.fromtimestamp(snapshot["asof"], timezone.utc).isoformat()
    provenance = ("SIMULATED" if not snapshot["live"] else
                  "STALE" if snapshot.get("stale") else snapshot["transport"])
    gate = "HOLD" if analysis["veto"] or snapshot.get("stale") else "Research gate clear"
    sections = [f"{symbol} · combined research review", f"{provenance} · {snapshot['source']} · {asof}",
                f"Observation window: {len(bars)} bars at {snapshot['interval']}.",
                f"Entry assessment: {gate}. Broker checks run separately at order time.",
                "\nSpecialist panel", analysis["verdict"]]
    sections.extend(analysis.get("reasons") or [])
    sections.extend(f"{a['pod']} / {a['name']} — {a['signal']} · {a['detail']}" for a in analysis["agents"])
    reports = {}
    with ThreadPoolExecutor(max_workers=len(engines), thread_name_prefix="swarm") as pool:
        pending = {}
        for engine in engines:
            item = installed[engine]
            if item["status"] != "Ready":
                reports[engine] = f"{item['status']} · {item['detail']}"
            else:
                pending[pool.submit(worker,engine,symbol,bars)] = engine
        for completed in as_completed(pending):
            engine = pending[completed]
            try:
                reports[engine] = str(completed.result())
            except Exception as error:
                reports[engine] = "Worker failed · " + (str(error) or type(error).__name__)
    for engine in engines:
        sections += ["\n"+installed[engine]["name"], reports[engine]]
    return "\n".join(sections)
