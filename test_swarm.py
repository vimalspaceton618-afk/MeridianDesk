import unittest

from analytics import analyze, demo_fundamentals
from market import demo_bars
from swarm import combined_review


class CombinedTests(unittest.TestCase):
    def setUp(self):
        self.pack=demo_bars("DEMO")
        self.a=analyze("DEMO",self.pack["bars"],fundamentals=demo_fundamentals())
        self.seen=[]
        self.status=lambda:[{"id":i,"name":i,"status":"Ready","detail":"Ready"} for i in ("ruflo","kronos","tradingagents")]

    def worker(self,engine,symbol,bars):
        self.assertIs(bars,self.pack["bars"])
        self.seen.append(engine)
        if engine=="kronos":
            raise RuntimeError("Forecast unavailable")
        return "Review complete"

    def test_shared_snapshot_local_workers_and_degradation(self):
        report=combined_review("DEMO",self.pack,self.a,worker=self.worker,availability=self.status)
        self.assertEqual(set(self.seen),{"ruflo","kronos"})
        for term in ("SIMULATED","Worker failed","Forecast unavailable","Review complete"):
            self.assertIn(term,report)

    def test_provider_opt_in_and_stale_gate(self):
        self.pack["stale"]=True
        report=combined_review("DEMO",self.pack,self.a,with_provider=True,worker=self.worker,availability=self.status)
        self.assertIn("tradingagents",self.seen)
        self.assertIn("Entry assessment: HOLD",report)

if __name__=="__main__":
    unittest.main()
