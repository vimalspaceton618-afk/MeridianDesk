"""Offline global equity discovery, cache, broker isolation and API regressions."""
import http.client
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
import uuid
from unittest.mock import patch

import market
import universe
from desk import Desk, serve


class GlobalMarketTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent / "tests")
        self.addCleanup(self.tmp.cleanup)
        self.env = patch.dict(os.environ, {
            "MERIDIAN_BROKER": "off", "APCA_API_KEY_ID": "", "APCA_API_SECRET_KEY": "",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def new_desk(self):
        desk = Desk(Path(self.tmp.name) / "research.sqlite3", verification=True)
        self.addCleanup(desk.stop)
        # Windows may keep temporary SQLite files locked while a background
        # research task is still finishing; join it before temp cleanup.
        self.addCleanup(lambda: desk.pool.shutdown(wait=True, cancel_futures=True))
        return desk

    def test_coverage_does_not_expand_eight_background_watchers(self):
        catalog=universe.entries()
        self.assertGreaterEqual(len(catalog),150)
        self.assertGreaterEqual(len({row["country"] for row in catalog}),25)
        self.assertEqual(len({row["symbol"] for row in catalog}),len(catalog))
        self.assertEqual(len(market.SYMBOLS),8)
        self.assertTrue(all(row["execution"]=="research-only" for row in catalog))
        self.assertNotIn("India", {row["country"] for row in catalog})
        self.assertFalse(any(row["symbol"].endswith((".NS",".BO")) for row in catalog))
        for ticker,country,currency in (
            ("NVDA","United States","USD"), ("7203.T","Japan","JPY"),
            ("ASML.AS","Netherlands","EUR"), ("SHEL.L","United Kingdom","GBp"),
            ("BHP.AX","Australia","AUD"), ("0700.HK","Hong Kong","HKD"),
            ("2330.TW","Taiwan","TWD"), ("005930.KS","South Korea","KRW"),
            ("PETR4.SA","Brazil","BRL"), ("2222.SR","Saudi Arabia","SAR"),
        ):
            self.assertEqual(universe.CATALOG[ticker]["country"],country)
            self.assertEqual(universe.CATALOG[ticker]["currency"],currency)

    def test_international_quotes_have_no_synthetic_fallback(self):
        with patch.object(market,"_load_candidates",side_effect=market.FeedUnavailable("provider offline")):
            with self.assertRaisesRegex(market.FeedUnavailable,"provider offline"):
                market.fetch_bars("7203.T")
        with self.assertRaisesRegex(ValueError,"Unknown instrument"):
            market.fetch_bars("FAKE.NS")
        with self.assertRaisesRegex(ValueError,"Unknown instrument"):
            market.fetch_history("../../unsafe")
        with self.assertRaisesRegex(ValueError,"Unknown instrument"):
            market.demo_bars("7203.T")

    def test_currency_is_preserved_from_provider_metadata(self):
        now=int(time.time())
        yahoo={"chart":{"result":[{"timestamp":[now-300,now],
            "meta":{"currency":"JPY","currentTradingPeriod":{}},
            "indicators":{"quote":[{"open":[100.,101.],"high":[102.,103.],
             "low":[99.,100.],"close":[101.,102.],"volume":[20,30]}]}}]}}
        data=market._parse_yahoo(yahoo,"5m",now)
        self.assertEqual(data["currency"],"JPY")
        self.assertIn("indicative",data["source"])
        self.assertEqual(data["transport"],"REST")
        self.assertFalse("bid" in data or "ask" in data)

    def test_on_demand_quote_without_background_catalog_polling(self):
        desk=self.new_desk()
        now=int(time.time())
        bars=[market._bar(now-300,100,102,99,101,10),
              market._bar(now,101,104,100,103,20)]
        pack=market._payload(bars,"Mock public indicative feed",session="Outside session")
        pack.update(currency="JPY",age_seconds=0)
        with patch.object(market,"fetch_bars",return_value=pack) as provider:
            first=desk.state("7203.T")
            self.assertEqual(len(first["watch"]),9)
            self.assertEqual(first["instrument"]["currency"],"JPY")
            self.assertTrue(all(x["symbol"] in market.SYMBOLS for x in first["watch"][:8]))
            deadline=time.monotonic()+6
            while time.monotonic()<deadline:
                state=desk.state("7203.T")
                if state["market"] is not None:
                    break
                time.sleep(.025)
            self.assertIsNotNone(state["market"])
            self.assertEqual(state["market"]["currency"],"JPY")
            self.assertEqual(state["watch"][-1]["kind"],"PUBLIC")
            for _ in range(5):
                desk.state("7203.T")
            provider.assert_called_once_with("7203.T")
        self.assertEqual(len(desk.state("DEMO")["watch"]),8)

    def test_catalog_stocks_never_reach_paper_or_broker_dispatch(self):
        desk=self.new_desk()
        request={"id":str(uuid.uuid4()),"symbol":"NVDA","side":"buy","qty":1,"limit":1000000}
        with patch.object(desk.broker,"submit",
                          side_effect=AssertionError("Broker dispatch forbidden")):
            for path in ("/api/paper","/api/broker/order"):
                with self.assertRaisesRegex(ValueError,"research-only"):
                    desk.action(path,request)
        self.assertEqual(desk.state("DEMO")["portfolio"]["orders"],[])

    def test_catalog_endpoint_requires_loopback_authentication(self):
        desk=self.new_desk()
        service=serve(desk,"fixture-session-secret")
        thread=threading.Thread(target=service.serve_forever,daemon=True)
        thread.start()
        try:
            def query(authorized):
                conn=http.client.HTTPConnection("127.0.0.1",service.server_port,timeout=5)
                headers={"Host":f"127.0.0.1:{service.server_port}"}
                if authorized:
                    headers["Authorization"]="Bearer fixture-session-secret"
                try:
                    conn.request("GET","/api/catalog",headers=headers)
                    response=conn.getresponse()
                    return response.status,json.loads(response.read())
                finally:
                    conn.close()
            self.assertEqual(query(False)[0],403)
            status,rows=query(True)
            self.assertEqual(status,200)
            self.assertGreaterEqual(len(rows),150)
            self.assertTrue(all(r["execution"]=="research-only" for r in rows))
        finally:
            service.shutdown()
            service.server_close()
            thread.join(timeout=3)

    def test_local_global_favorites_persist_across_restart_without_network(self):
        db=Path(self.tmp.name)/"watched.sqlite3"
        desk=Desk(db,verification=True)
        try:
            first=desk.action("/api/watchlist",{"symbol":"7203.T","enabled":True})
            self.assertEqual(first["pinned"],["7203.T"])
            desk.action("/api/watchlist",{"symbol":"7203.T","enabled":True})
            self.assertEqual(desk.state("DEMO")["pinned"],["7203.T"])
            self.assertEqual(len(desk.state("DEMO")["watch"]),9)
            self.assertIsNone(desk.state("DEMO")["watch"][-1]["price"])
        finally:
            desk.stop()
        restarted=Desk(db,verification=True)
        try:
            self.assertEqual(restarted.state("DEMO")["pinned"],["7203.T"])
            self.assertEqual(restarted.state("DEMO")["watch"][-1]["symbol"],"7203.T")
            restarted.action("/api/watchlist",{"symbol":"7203.T","enabled":False})
            self.assertEqual(restarted.state("DEMO")["pinned"],[])
            self.assertEqual(len(restarted.state("DEMO")["watch"]),8)
        finally:
            restarted.stop()

    def test_bounded_favorites_validate_symbol_and_input_type(self):
        desk=self.new_desk()
        symbols=list(universe.CATALOG)[:17]
        for symbol in symbols[:16]:
            desk.action("/api/watchlist",{"symbol":symbol,"enabled":True})
        with self.assertRaisesRegex(ValueError,"limit of 16"):
            desk.action("/api/watchlist",{"symbol":symbols[16],"enabled":True})
        with self.assertRaisesRegex(ValueError,"approved international"):
            desk.action("/api/watchlist",{"symbol":"FAKE.NS","enabled":True})
        with self.assertRaisesRegex(ValueError,"Invalid watchlist"):
            desk.action("/api/watchlist",{"symbol":symbols[0],"enabled":"yes"})
        self.assertEqual(len(desk.state("DEMO")["pinned"]),16)
        self.assertEqual(len(desk.state("DEMO")["watch"]),24)



if __name__=="__main__":
    unittest.main()
