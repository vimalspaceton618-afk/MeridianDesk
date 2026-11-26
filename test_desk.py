"""Desktop API integration checks. All temporary accounts are inside E:/MeridianDesk/tests."""
import base64
from contextlib import contextmanager
import http.client
import json
import os
from pathlib import Path
import secrets
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uuid

import desk
import market


ROOT = Path(__file__).resolve().parent
DEMO_QUERY = "/api/state?symbol=DEMO"
REPORT = """APEX-FX SIGNAL REPORT
PAIR: EURUSD
DIRECTION: LONG
TIMESTAMP: 2026-11-25 10:00 UTC
CONFLUENCE SCORE: 62
RISK FLAGS: synthetic report test
DISCLAIMER: Testing report import.
"""


@contextmanager
def local_session(database):
    engine = desk.Desk(database, verification=True)
    token = secrets.token_urlsafe(24)
    server = desk.serve(engine, token)
    assert server.server_address[0] == "127.0.0.1"
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
    thread.start()
    try:
        yield engine, server.server_port, token
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
        engine.stop()
        engine.pool.shutdown(wait=True)


class DesktopServiceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(dir=ROOT / "tests", prefix="desk-api-")
        self.addCleanup(self.directory.cleanup)
        self.db = Path(self.directory.name) / "account.sqlite3"
        self.env = patch.dict(os.environ, {"MERIDIAN_BROKER": "off", "APCA_API_KEY_ID": "", "APCA_API_SECRET_KEY": ""})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.open()

    def open(self):
        self.session = local_session(self.db)
        self.service, self.port, self.token = self.session.__enter__()
        self.addCleanup(self.close, self.session)

    def close(self, session):
        if session is self.session:
            self.session = None
            session.__exit__(None, None, None)

    def request(self, path, body=None, *, headers=None, token=True, raw=False):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=8)
        data = None if body is None else json.dumps(body)
        head = {"Content-Type": "application/json", "Origin": f"http://127.0.0.1:{self.port}"}
        if token:
            head["Authorization"] = "Bearer " + self.token
        head.update(headers or {})
        try:
            conn.request("POST" if body is not None else "GET", path, data, head)
            resp = conn.getresponse()
            status = resp.status
            payload = resp.read()
            return status, payload.decode("utf-8") if raw else json.loads(payload)
        finally:
            conn.close()

    def ok(self, path, body=None):
        status, result = self.request(path, body)
        self.assertEqual(status, 200, result)
        return result

    def order(self, side="buy", qty=1, price=None):
        p = self.ok(DEMO_QUERY)["market"]["bars"][-1]["close"]
        return {"id": str(uuid.uuid4()), "symbol": "DEMO", "side": side, "qty": qty,
                "limit": price if price is not None else p * (1.01 if side == "buy" else .99)}

    def wait_job(self, job, timeout=20):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            tasks = self.ok(DEMO_QUERY)["jobs"]
            latest = next(item for item in tasks if item["id"] == job["id"])
            if latest["state"] != "running":
                return latest
            time.sleep(.03)
        self.fail(f"Job {job['task']} did not finish")

    def test_session_guards_and_local_shell(self):
        status, html = self.request("/", raw=True)
        self.assertEqual(status, 200)
        self.assertIn("Meridian Desk", html)
        self.assertEqual(self.request(DEMO_QUERY, token=False)[0], 403)
        self.assertEqual(self.request("/api/halt", {"enabled": True}, token=False)[0], 403)
        self.assertEqual(self.request("/api/halt", {"enabled": True}, headers={"Origin": "https://example.invalid"})[0], 403)
        self.assertEqual(self.request("/api/halt", {"enabled": True}, headers={"Content-Type": "text/plain"})[0], 403)
        self.assertFalse(self.ok(DEMO_QUERY)["portfolio"]["halted"])
        self.assertEqual(self.request("/api/unknown")[0], 404)
        self.assertEqual(self.request("/api/state?symbol=INVALID")[0], 400)

    def test_registry_and_renderable_analysis(self):
        state = self.ok(DEMO_QUERY)
        self.assertFalse(state["market"]["live"])
        self.assertIn("Synthetic", state["market"]["source"])
        self.assertFalse(state["analysis"]["veto"], state["analysis"]["reasons"])
        self.assertTrue(state["analysis"]["valuation"]["synthetic"])
        self.assertEqual(len(state["analysis"]["agents"]), 12)
        self.assertEqual(len({a["pod_id"] for a in state["analysis"]["agents"]}), 8)
        registry = self.ok("/api/registry")
        self.assertEqual(len(registry), 300)
        self.assertEqual(len({a["id"] for a in registry}), 300)
        self.assertEqual(state["portfolio"]["cash"], 100000)
        self.assertFalse(state["broker"]["configured"])
        self.assertIsNone(self.ok("/api/state?symbol=AAPL")["market"])

    def test_fill_retries_sizing_and_restart(self):
        ticket = self.order(qty=3)
        fill = self.ok("/api/paper", ticket)
        self.assertEqual(fill["id"], ticket["id"])
        self.assertLessEqual(fill["price"], ticket["limit"])
        self.assertGreater(fill["fee"], 0)
        same = self.ok("/api/paper", ticket)
        self.assertEqual(same, fill)
        self.assertEqual(self.request("/api/paper", dict(ticket, qty=4))[0], 400)
        status, error = self.request("/api/paper", self.order(qty=300))
        self.assertEqual(status, 400)
        self.assertIn("15%", error["error"])
        self.assertEqual(self.request("/api/paper", self.order("sell", qty=4))[0], 400)
        self.assertEqual(self.request("/api/paper", self.order(price=1))[0], 400)
        self.ok("/api/halt", {"enabled": True})
        self.assertIn("halted", self.request("/api/paper", self.order("sell"))[1]["error"])
        self.close(self.session)
        self.open()
        state = self.ok(DEMO_QUERY)
        self.assertTrue(state["portfolio"]["halted"])
        self.assertEqual(len(state["portfolio"]["orders"]), 1)
        self.assertAlmostEqual(state["portfolio"]["cash"], 100000 - fill["qty"] * fill["price"] - fill["fee"])
        self.assertEqual(state["portfolio"]["positions"][0]["qty"], 3)
        self.assertTrue(any(a["category"] == "ORDER BLOCKED" for a in state["audit"]))
        self.ok("/api/halt", {"enabled": False})
        self.ok("/api/paper", self.order("sell", qty=3))
        self.assertEqual(self.ok(DEMO_QUERY)["portfolio"]["positions"], [])

    def test_jobs_and_local_ruflo(self):
        expected = {e["id"]:e for e in self.ok("/api/engines")}
        self.assertEqual(set(expected), {"ruflo", "tradingagents", "kronos"})
        self.assertEqual(expected["ruflo"]["status"], "Ready")
        for kind, pattern in (("research", "Governance evidence"), ("backtest", "Out-of-sample bars"),
                              ("integration", "Ruflo completed 4 assigned tasks")):
            with self.subTest(kind=kind):
                job = self.ok("/api/job", {"kind": kind, "symbol": "DEMO", "engine": "ruflo"})
                done = self.wait_job(job)
                self.assertEqual(done["state"], "complete", done["result"])
                self.assertIn(pattern, done["result"])
        self.assertEqual(self.request("/api/job", {"kind":"integration","symbol":"DEMO","engine":"unknown"})[0], 400)

    def test_combined_swarm_real_local_workers_no_hosted_provider(self):
        job = self.ok("/api/job", {"kind": "swarm", "symbol": "DEMO"})
        completed = self.wait_job(job, timeout=115)
        self.assertEqual(completed["state"], "complete", completed["result"])
        report = completed["result"]
        for text in ("SIMULATED", "Specialist panel", "Governance evidence", "Kronos-mini",
                     "Model close", "Ruflo completed 4 assigned tasks"):
            self.assertIn(text, report)
        self.assertNotIn("\nTradingAgents\n", report)
        self.assertNotIn("Worker failed", report)
        state = self.ok(DEMO_QUERY)
        self.assertEqual(state["portfolio"]["orders"], [])
        self.assertEqual(state["broker_orders"], [])
        self.assertEqual(self.request("/api/job", {"kind":"swarm","symbol":"DEMO","engine":"unexpected"})[0], 400)

    def test_fresh_price_dislocation_queues_local_swarm_once(self):
        pack = market.demo_bars("BTC-USD")
        pack.update(live=True, transport="WebSocket", source="Test tick", age_seconds=.1)
        base={"verdict":"TEST", "veto":False, "reasons":[], "risk":{"drawdown":.19}, "valuation":None}
        stress={**base, "risk":{"drawdown":.20}}
        with patch("desk.analyze", side_effect=[base, stress, base, stress]), patch.object(self.service, "job") as job:
            for _ in range(4):
                self.service.accept("BTC-USD", pack)
            job.assert_called_once_with("swarm", "BTC-USD", captured=(pack,stress))
        alerts=[r for r in self.service.ledger.recent() if r["category"]=="MARKET ALERT"]
        self.assertEqual(len(alerts), 1)
        self.assertIn("Drawdown crossed 20%", alerts[0]["detail"])

    def test_duplicate_job_and_reported_worker_error(self):
        entered, release = threading.Event(), threading.Event()
        def worker(*args):
            entered.set()
            release.wait(timeout=5)
            raise RuntimeError("Provider was unavailable in test")
        body = {"kind": "integration", "symbol": "DEMO", "engine": "tradingagents"}
        with patch("integrations.run_integration", side_effect=worker):
            job = self.ok("/api/job", body)
            self.assertTrue(entered.wait(timeout=2))
            try:
                duplicate = self.ok("/api/job", body)
                self.assertEqual(duplicate["id"], job["id"])
            finally:
                release.set()
            final = self.wait_job(job)
        self.assertEqual(final["state"], "error")
        self.assertIn("unavailable in test", final["result"])

    def test_indicative_and_stale_sources_block_fills(self):
        pack = market.demo_bars("BTC-USD")
        pack.update(live=True, transport="REST", source="Test public bar", age_seconds=1)
        self.service.accept("BTC-USD", pack, save=False)
        def buy():
            return self.request("/api/paper", {"id": str(uuid.uuid4()), "symbol":"BTC-USD",
                                               "side":"buy","qty":.001,"limit":999999})
        self.assertIn("two-sided quote", buy()[1]["error"])
        pack.update(bid=60000, ask=60010, stale=True, age_seconds=10)
        self.service.accept("BTC-USD", pack, save=False)
        self.assertIn("Fresh exchange quotes", buy()[1]["error"])
        self.assertEqual(self.ok(DEMO_QUERY)["portfolio"]["cash"], 100000)

    def test_mt5_report_import(self):
        content = base64.b64encode(REPORT.encode("utf-16")).decode("ascii")
        item = self.ok("/api/mt5", {"content":content})
        self.assertIn("PAIR: EURUSD", item["report"])
        self.assertEqual(self.ok(DEMO_QUERY)["audit"][0]["category"], "MT5 IMPORT")
        self.assertEqual(self.request("/api/mt5", {"content":"bm90IGEgc2lnbmFs"})[0], 400)


if __name__ == "__main__":
    unittest.main()
