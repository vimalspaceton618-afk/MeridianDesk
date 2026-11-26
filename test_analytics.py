"""Numerical, point-in-time and portfolio gate regressions. Run python -B -m unittest test_analytics."""
from collections import Counter
from math import sin
import unittest

import analytics as a


def bars(n=160, price=80, seconds=60):
    close = [price * (1 + .01 * sin(i / 8)) for i in range(n)]
    return [dict(time=1_790_000_000 + i * seconds, open=close[max(0, i-1)],
                 high=max(close[max(0, i-1)], v) * 1.001,
                 low=min(close[max(0, i-1)], v) / 1.001, close=v, volume=3)
            for i, v in enumerate(close)]


class ValuationChecks(unittest.TestCase):
    def test_earnings_and_perpetuity(self):
        self.assertEqual(a.owner_earnings(dict(net_income=20, da=5, maintenance_capex=3, delta_wc=4)), 18)
        self.assertAlmostEqual(a.dcf(10, .02, hurdle=.10, terminal=.02, net_cash=10, shares=5),
                               (10 * 1.02 / .08 + 10) / 5)
        self.assertAlmostEqual(a.dcf(10, 0, hurdle=.1, terminal=0), 100)
        for args in ((10, .05, .07, .02), (10, .03, .1, .04), (0, .04, .1, .02)):
            with self.assertRaises(ValueError):
                a.dcf(*args)

    def test_fixture_isolated_from_live_symbols(self):
        demo = a.demo_fundamentals()
        self.assertEqual(len(demo['annual']), 10)
        wrong = a.analyze("MSFT", bars(), fundamentals=demo)
        self.assertIsNone(wrong["valuation"])
        self.assertTrue(wrong["veto"])
        crypto = a.analyze("BTC-USD", bars(), fundamentals=demo)
        self.assertIsNone(crypto["valuation"])
        self.assertFalse(crypto["veto"])

    def test_numerical_fixture_and_governance_overrides(self):
        demo = a.demo_fundamentals()
        verdict = a.analyze("DEMO", bars(), fundamentals=demo)
        self.assertFalse(verdict["veto"], verdict["reasons"])
        self.assertAlmostEqual(verdict["valuation"]["intrinsic"], 129.15642120255728)
        self.assertAlmostEqual(verdict["valuation"]["target"], 90.40949484179009)
        self.assertIn(verdict["valuation"]["f_score"], range(10))
        self.assertTrue(verdict["valuation"]["synthetic"])
        bad = a.analyze("DEMO", bars(), fundamentals=demo, governance_flags=["qualified audit opinion"])
        self.assertTrue(bad["veto"])
        self.assertIn("qualified audit opinion", " ".join(bad["reasons"]))
        demo["governance_reviewed"] = False
        self.assertTrue(a.analyze("DEMO", bars(), fundamentals=demo)["veto"])

    def test_optional_interest_and_quality_inputs_are_audited(self):
        d = a.demo_fundamentals()
        del d["annual"][-1]["interest"]
        d["annual"][2]["gross_profit"] = None
        result = a.analyze("DEMO", bars(), fundamentals=d)
        self.assertTrue(result["veto"])
        self.assertGreater(result["valuation"]["intrinsic"], 0)
        self.assertIsNone(result["valuation"]["interest_coverage"])
        self.assertIsNone(result["valuation"]["margin_dispersion"])
        self.assertIn("no interest added back", " ".join(result["reasons"]))

    def test_sec_retrieval_date_and_restatement_availability(self):
        d = a.demo_fundamentals()
        d.update(as_of_basis="retrieval",as_of="2026-11-25",symbol="TEST",synthetic=False)
        d["annual"][-1]["filed"] = "2026-11-03"
        prior_bar = a._iso_epoch("2026-11-24T20:00:00+00:00")
        val, _ = a._valuation("TEST", 84, prior_bar, d)
        self.assertEqual(val["as_of"], "2026-11-03")
        self.assertEqual(val["retrieved_as_of"], "2026-11-25")
        self.assertIsNone(val["share_growth"])
        future = a._iso_epoch("2026-11-03T12:00:00+00:00")
        val, issues = a._valuation("TEST", 84, future, d)
        self.assertIsNone(val)
        self.assertIn("550", " ".join(issues))

    def test_price_ceiling_overrides_high_quality(self):
        result = a.analyze("DEMO", bars(price=120), fundamentals=a.demo_fundamentals())
        self.assertTrue(result["veto"])
        self.assertTrue(any(c["veto"] and c["name"] == "Margin of safety" for c in result["agents"]))

    def test_history_and_point_in_time(self):
        for mode in ("future", "sparse", "losses", "gap", "future_file"):
            with self.subTest(mode=mode):
                d = a.demo_fundamentals()
                if mode == "future":
                    d["as_of"] = "2099-01-01"
                elif mode == "sparse":
                    d["annual"] = d["annual"][-4:]
                elif mode == "gap":
                    del d["annual"][-2]
                elif mode == "losses":
                    for r in d["annual"][-4:-1]:
                        r["net_income"] = -1_000_000_000
                else:
                    for r in d["annual"][-7:]:
                        r["filed"] = "2099-01-01"
                result = a.analyze("DEMO", bars(), fundamentals=d)
                self.assertIsNone(result["valuation"])
                self.assertTrue(result["veto"])


    def test_value_replay_uses_only_published_statements(self):
        statements = a.demo_fundamentals()
        history = a.demo_history()
        cutoff = a._iso_epoch("2023-01-01")
        prefix = [r for r in history if r["time"] < cutoff]
        observed = a._value_replay(statements, prefix)
        for row in statements["annual"]:
            if a._iso_epoch(row["filed"]) > cutoff:
                row["net_income"] *= 1_000
        self.assertEqual(observed, a._value_replay(statements, prefix))
        self.assertTrue(observed["Test period"].startswith("2020-03-17"))
        whole = a.demo_value_backtest()
        self.assertGreater(int(whole["Out-of-sample bars"]), 1200)
        self.assertGreater(int(whole["Fills"]), 1)



class RiskChecks(unittest.TestCase):
    def test_registry_and_panel(self):
        cards = a.registry()
        self.assertEqual(len({r["id"] for r in cards}), 300)
        self.assertEqual(Counter(c["pod_id"] for c in cards), dict(enumerate((48,48,36,36,36,36,30,30),1)))
        self.assertEqual(len({(c["name"],c["profile"]) for c in cards}), 300)
        report = a.analyze("EUR/USD", bars())
        self.assertEqual(len(report["agents"]), 12)
        self.assertEqual(len(report["pod_counts"]), 8)
        self.assertEqual(sum(report["pod_counts"].values()), 12)
        cards[0]["name"] = ""
        self.assertTrue(a.registry()[0]["name"])

    def test_flat_and_volatile(self):
        data = bars()
        for b in data:
            b.update(open=80, close=80, high=80, low=80)
        flat = a.analyze("BTC-USD", data)
        self.assertEqual(flat["risk"]["cvar99"], 0)
        self.assertIsNone(flat["risk"]["quarter_kelly"])
        self.assertFalse(flat["veto"])
        for i, b in enumerate(data):
            p = 80 if i % 2 == 0 else 50
            b.update(open=p, close=p, low=p, high=p)
        v = a.analyze("BTCUSD", data)
        self.assertGreater(v["risk"]["cvar99"], .08)
        self.assertGreaterEqual(v["risk"]["cvar99"], v["risk"]["var99"])
        self.assertTrue(v["veto"])
        self.assertEqual(v, a.analyze("BTCUSD", data))

    def test_single_bar_sparse_history_and_corrupt_bars(self):
        self.assertTrue(a.analyze("BTCUSD", bars(1))["veto"])
        self.assertTrue(a.analyze("EURUSD", [])["veto"])
        for field, value in (("time", 0), ("close", float("nan")), ("low", -1), ("volume", -1), ("high", 1)):
            b = bars()
            b[-1][field] = value
            self.assertTrue(a.analyze("BTCUSD", b)["veto"])
            self.assertEqual(a.backtest("BTCUSD", b)["Status"], "Invalid bars")

    def test_unknown_equity_has_no_implicit_clearance(self):
        report = a.analyze("MSFT", bars())
        self.assertTrue(report["veto"])
        self.assertIsNone(report["valuation"])

    def test_walk_forward_costs_and_horizon(self):
        self.assertEqual(a.backtest("X", bars(59))["Status"], "Insufficient history")
        rising = bars(160, seconds=86_400)
        for i, b in enumerate(rising):
            b.update(open=100+i, high=101+i, close=101+i, low=100+i)
        bt = a.backtest("TEST", rising)
        start = 160 // 3
        expected = (1-.001) ** 2 * rising[-1]["close"] / rising[start]["open"] - 1
        self.assertEqual(bt["Net return"], f"{expected:.2%}")
        self.assertEqual(bt["Buy and hold (same asset)"], f"{expected:.2%}")
        self.assertEqual(bt["One-way turnover"], "2.0×")
        self.assertIn("Under one year", bt["CAGR"])
        self.assertEqual(bt["Status"], "Complete")

    def test_fill_after_signal_not_before_gap(self):
        nav, change = a._advance(1, 0, 1, 100, dict(open=200, close=200), .001)
        self.assertEqual(change, 1)
        self.assertAlmostEqual(nav, .999)
        nav, _ = a._advance(1, 1, 0, 100, dict(open=50, close=120), .001)
        self.assertAlmostEqual(nav, .5*.999)


if __name__ == "__main__":
    unittest.main()
