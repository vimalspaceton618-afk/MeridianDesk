"""Offline coverage for public feed parsing, freshness, failover and the supplied MT5 log format."""
import codecs
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import market


class MarketTests(unittest.TestCase):
    def setUp(self):
        with market._LOCK:
            for cache in (market._CACHE, market._TICKS, market._RETRIES, market._HISTORY, market._CLOCKS, market._FORMING):
                cache.clear()

    def test_fixture_series_shifts_one_bar_without_rewriting_history(self):
        now = 1780000000
        first = market.demo_bars("BTC-USD", now=now)
        second = market.demo_bars("BTC-USD", now=now + 300)
        self.assertFalse(first["live"])
        self.assertEqual(first["bars"][1:], second["bars"][:-1])
        self.assertEqual(first, market.demo_bars("BTC-USD", now=now))
        self.assertNotEqual(first["bars"], market.demo_bars("ETH-USD", now=now)["bars"])
        self.assertGreater(len(market.demo_bars("DEMO", daily=True)["bars"]), 1000)

    def test_ohlc_integrity(self):
        for vals in ((100, 1, 2, 0, 2, 0), (100, 1, 2, 1, 3, 1), (100, 1, 2, 1, 2, -1),
                     (100, 1, float("nan"), 1, 2, 10)):
            self.assertIsNone(market._bar(*vals))
        self.assertEqual(market._bar(100, 1, 2, 1, 1.5, None)["volume"], 0)

    def test_yahoo_missing_quotes_and_published_session(self):
        data = {"chart":{"result":[{"timestamp":[100,200,300], "meta":{"currentTradingPeriod":{
            "pre":{"start":85,"end":190},"regular":{"start":190,"end":310}}},
            "indicators":{"quote":[{"open":[1,None,2],"close":[2,None,3],"high":[2,None,4],
                                     "low":[1,None,1],"volume":[0,None,0]}]}}]}}
        result = market._parse_yahoo(data, "5m", 315)
        self.assertEqual([b["time"] for b in result["bars"]], [100,300])
        self.assertEqual(result["asof"], 300)
        self.assertEqual(result["session"], "Outside reported session")
        self.assertIn("delayed", result["source"])

    def test_coinbase_layout_and_duplicate_candles(self):
        rows = [[600,9,13,10,12,105], [300,6,10,7,9,50], [300,6,10,7,9,50]]
        with patch.object(market, "_json", return_value=rows):
            result = market._coinbase("BTC-USD")
        self.assertEqual([b["time"] for b in result["bars"]], [300, 600])
        self.assertEqual(result["bars"][-1]["open"], 10)
        self.assertEqual(result["bars"][-1]["close"], 12)

    def test_failover_is_attributed_and_cached_failure_stays_stale(self):
        now = int(time.time())
        records = [[now-300,4,5,3,4,0,10,3], [now,4,6,3,5,0,20,5]]
        with patch.object(market, "_coinbase", side_effect=market.FeedUnavailable("outage")), \
             patch.object(market, "_json", return_value={"error":[], "result":{"XXBTZUSD":records}}):
            result = market.fetch_bars("BTC-USD")
        self.assertTrue(result["live"])
        self.assertIn("Kraken", result["source"])
        market._CACHE["BTC-USD"] = (-100, market._CACHE["BTC-USD"][1])
        with patch.object(market, "_load_candidates", side_effect=market.FeedUnavailable("offline")) as load:
            outage = market.fetch_bars("BTC-USD")
            self.assertTrue(outage["stale"])
            self.assertEqual(outage["asof"], result["asof"])
            self.assertEqual(outage["transport"], "CACHED")
            market.fetch_bars("BTC-USD")
            load.assert_called_once()
        market._RETRIES["BTC-USD"] = (1, 0, "offline")
        with patch.object(market, "_load_candidates", return_value=result):
            recovered = market.fetch_bars("BTC-USD")
        self.assertFalse(recovered["stale"])

    def test_cold_failure_never_becomes_synthetic_or_live(self):
        with patch.object(market, "_load_candidates", side_effect=market.FeedUnavailable("network down")):
            with self.assertRaisesRegex(market.FeedUnavailable, "network down"):
                market.fetch_bars("SPY")

    def test_exchange_clock_overlay_and_duplicate_out_of_order_ticks(self):
        venue = "api.exchange.coinbase.com"
        now = int(time.time())
        stamp = now + 180
        bucket = stamp // 300 * 300
        rows = [market._bar(bucket-300, 10, 11, 9, 10, 5), market._bar(bucket, 10, 13, 8, 12, 8)]
        payload = market._payload(rows, "Coinbase Exchange · 5m bars")
        payload["venue"] = venue
        iso = lambda n: datetime.fromtimestamp(n, timezone.utc).isoformat()
        # The CDN's HTTP Date/Age estimate can be a minute ahead of the exchange.
        market._record_clock(venue, stamp + 58)
        market._tick({"type":"heartbeat", "time":iso(stamp)})
        market._record_clock(venue, stamp + 59)
        def quote(t, price):
            return {"type":"ticker", "product_id":"BTC-USD", "time":iso(t),
                    "best_bid":"12", "best_ask":"13", "price":str(price)}
        market._tick(dict(quote(stamp, 15), trade_id=15, last_size="2"))
        market._tick(dict(quote(stamp, 14), trade_id=15, last_size="20"))
        market._tick(dict(quote(stamp, 12.5), trade_id=16, last_size="3"))
        market._tick(quote(stamp - 5, 11))
        actual = market._with_latest("BTC-USD", payload)
        self.assertEqual(actual["transport"], "WebSocket")
        self.assertEqual(actual["asof"], stamp)
        self.assertLess(actual["age_seconds"], 2)
        self.assertFalse(actual["stale"])
        self.assertEqual(actual["bars"][-1]["close"], 12.5)
        self.assertEqual(actual["bars"][-1]["high"], 15)
        self.assertEqual(market._FORMING["BTC-USD"]["volume"], 5)
        self.assertEqual(payload["bars"][-1]["close"], 12)
        self.assertEqual(actual["bars"][-1]["volume"], 8)

    def test_bad_symbols_backoff_and_closed_session_age(self):
        with self.assertRaises(ValueError):
            market.fetch_bars("../../other")
        self.assertLessEqual(market._retry_seconds(1000), 30)
        p = market._payload([market._bar(300,1,2,1,2,0),market._bar(600,1,3,1,2,1)],"test")
        self.assertTrue(market._with_latest("SPY", p)["stale"])

    def test_mt5_utf16_latest_complete_and_utf8_plain(self):
        report = ("APEX-FX SIGNAL REPORT\n====================\nCONFLUENCE SCORE: 7/10\n"
                  "PAIR         : EURUSD\nDIRECTION    : LONG\nTIMESTAMP    : 2026.11.25 16:00:00 UTC\n"
                  "RISK FLAGS   : None active\nREGIME NOTE  : example\nDISCLAIMER   : sample.\n")
        lines = ["AK\t0\t16:22:21\tAPEX_FX_Agent (EURUSD,H1)\t" + line for line in report.splitlines()]
        text = "other system log\n" + "\r\n".join(lines) + "\r\nAPEX-FX SIGNAL REPORT\npartial"
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as directory:
            file = Path(directory) / "expert.log"
            file.write_bytes(codecs.BOM_UTF16_LE + text.encode("utf-16-le"))
            extracted = market.read_mt5_report(file)
            self.assertIn("EURUSD", extracted)
            self.assertNotIn("16:22:21", extracted)
            self.assertNotIn("partial", extracted)
            file.write_text(report, encoding="utf-8")
            self.assertEqual(market.read_mt5_report(file), extracted)
            file.write_text("log without a report", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "No complete"):
                market.read_mt5_report(file)


if __name__ == "__main__":
    unittest.main()
