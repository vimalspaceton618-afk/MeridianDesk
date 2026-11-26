"""M1 backend acceptance: synthetic research -> risk -> paper fill -> audit -> restart.

Runs offline with stdlib unittest. Does not start market workers, call a broker,
use hosted models, or enable live trading. Windows UI validation is separate.
"""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

import market
from desk import Desk


HERE = Path(__file__).resolve().parent


class Phase1PaperVerticalSlice(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(dir=HERE / "tests", prefix="phase1-")
        self.addCleanup(scratch.cleanup)
        self.database = Path(scratch.name) / "acceptance.sqlite3"
        self.env = patch.dict(
            os.environ,
            {"MERIDIAN_BROKER": "off", "APCA_API_KEY_ID": "", "APCA_API_SECRET_KEY": ""},
        )
        self.env.start()
        self.addCleanup(self.env.stop)

    def new_desk(self):
        engine = Desk(self.database, verification=True)
        self.addCleanup(engine.stop)
        return engine

    @staticmethod
    def ticket(symbol, price, *, qty=1):
        return {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": "buy",
            "qty": qty,
            "limit": price * 1.01,
        }

    def test_synthetic_research_paper_fill_idempotency_and_persistent_halt(self):
        first = self.new_desk()
        self.assertEqual(first.broker.status()["mode"], "off")
        self.assertFalse(first.broker.status()["configured"])

        market_snapshot, research = first.selected("DEMO")
        self.assertFalse(market_snapshot["live"])
        self.assertIn("Synthetic", market_snapshot["source"])
        self.assertFalse(market_snapshot["stale"])
        self.assertFalse(research["veto"], research["reasons"])
        self.assertTrue(research["agents"])
        self.assertTrue(research["valuation"]["synthetic"])

        price = market_snapshot["bars"][-1]["close"]
        request = self.ticket("DEMO", price)
        with patch.object(first.broker, "transport", side_effect=AssertionError("broker contact forbidden")):
            fill = first.action("/api/paper", request)
            same = first.action("/api/paper", request)
        self.assertEqual(fill, same, "An idempotent retry must not create another fill")
        state = first.state("DEMO")
        self.assertEqual(len(state["portfolio"]["orders"]), 1)
        self.assertEqual(state["portfolio"]["positions"][0]["qty"], 1)
        self.assertTrue(any(entry["category"] == "PAPER FILL" for entry in state["audit"]))
        self.assertTrue(all(entry["source"].startswith("Synthetic") for entry in state["portfolio"]["orders"]))

        first.action("/api/halt", {"enabled": True})
        with self.assertRaisesRegex(ValueError, "halted"):
            first.action("/api/paper", self.ticket("DEMO", price))
        self.assertEqual(len(first.state("DEMO")["portfolio"]["orders"]), 1)

        # Simulate a new process (without running watchers or a real-market provider).
        first.stop()
        restarted = self.new_desk()
        after_restart = restarted.state("DEMO")
        self.assertEqual(after_restart["portfolio"]["halted"], 1)
        self.assertEqual(len(after_restart["portfolio"]["orders"]), 1)
        self.assertTrue(any(entry["category"] == "CONTROL" for entry in after_restart["audit"]))
        with self.assertRaisesRegex(ValueError, "halted"):
            restarted.action("/api/paper", self.ticket("DEMO", price))

    def test_synthetic_real_symbol_is_never_treated_as_fresh_exchange_quote(self):
        engine = self.new_desk()
        fixture = market.demo_bars("BTC-USD")
        self.assertFalse(fixture["live"])
        engine.accept("BTC-USD", fixture, save=False)
        price = fixture["bars"][-1]["close"]
        with self.assertRaisesRegex(ValueError, "Fresh exchange quotes"):
            engine.action("/api/paper", self.ticket("BTC-USD", price, qty=0.001))
        self.assertEqual(engine.state("DEMO")["portfolio"]["orders"], [])
        self.assertFalse(engine.broker.status()["configured"])


if __name__ == "__main__":
    unittest.main()
