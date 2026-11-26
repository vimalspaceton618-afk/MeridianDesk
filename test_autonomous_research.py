"""Offline safety and evidence tests for global-market autonomous research.

No API tokens, broker connection, model provider or external market is used.
"""
import copy
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import autonomous_research as agents
from analytics import analyze
import market
from desk import Desk


def sample(symbol="7203.T", *, observed=True, stale=False):
    bars=market.demo_bars("DEMO")["bars"]
    pack={"bars":bars,"source":"Test source · fictional prices, NOT a real quote",
          "asof":bars[-1]["time"],"interval":"5m","session":"Fiction",
          "currency":"JPY","live":observed,"stale":stale,"transport":"FIXTURE",
          "age_seconds":1}
    assessment=analyze(symbol,bars)
    return pack,assessment


class AgentEvidenceTests(unittest.TestCase):
    def test_six_specialists_are_verified_but_never_authorize_orders(self):
        pack,assessment=sample()
        before=copy.deepcopy(pack)
        report=agents.investigate("7203.T",pack,assessment,now=1780000000)
        self.assertEqual(len(report["plan"]),6)
        self.assertEqual(len(report["agents"]),6)
        self.assertEqual(len({a["id"] for a in report["agents"]}),6)
        self.assertTrue(report["verifier"]["passed"])
        self.assertEqual(report["decision"],"ABSTAIN")
        self.assertEqual(report["execution"],"DISABLED")
        self.assertEqual(report["data_policy"]["exchange_entitlement_verified"],False)
        self.assertFalse(report["data_policy"]["corporate_actions_verified"])
        self.assertIn("No model",report["constraints"][2])
        self.assertEqual(pack,before,"Planning must not mutate price evidence")
        self.assertIn("7203.T",agents.report_text(report))
        self.assertIn(report["snapshot_sha256"],agents.report_text(report))

    def test_deterministic_hash_and_result_with_frozen_clock(self):
        pack,assessment=sample()
        a=agents.investigate("7203.T",pack,assessment,now=1780000000)
        b=agents.investigate("7203.T",pack,assessment,now=1780000000)
        self.assertEqual(a,b)
        pack["bars"][-1]["close"]*=.99
        # Changed bar is invalid without high/low adjustment and must be rejected.
        pack["bars"][-1]["low"]=min(pack["bars"][-1]["low"],pack["bars"][-1]["close"])
        updated=analyze("7203.T",pack["bars"])
        self.assertNotEqual(a["snapshot_sha256"],
                            agents.investigate("7203.T",pack,updated,now=1780000000)["snapshot_sha256"])

    def test_stale_and_simulated_observations_abstain(self):
        for observed,stale in ((False,False),(True,True),(False,True)):
            with self.subTest(observed=observed,stale=stale):
                pack,analysis=sample(observed=observed,stale=stale)
                item=agents.investigate("7203.T",pack,analysis)
                self.assertEqual(item["decision"],"ABSTAIN")
                self.assertTrue(item["reasons"])
                self.assertEqual(item["execution"],"DISABLED")

    def test_rejects_mismatched_or_invalid_evidence(self):
        pack,analysis=sample()
        bad=copy.deepcopy(analysis);bad["asof"]-=300
        with self.assertRaisesRegex(ValueError,"does not match"):
            agents.investigate("7203.T",pack,bad)
        wrong=copy.deepcopy(pack);wrong["bars"][-1]["high"]=0
        with self.assertRaises(ValueError):
            agents.investigate("7203.T",wrong,analysis)
        wrong=copy.deepcopy(pack);wrong["asof"]=wrong["bars"][-1]["time"]-10000
        with self.assertRaisesRegex(ValueError,"cannot be reconciled"):
            agents.investigate("7203.T",wrong,analysis)

    def test_malicious_worker_evidence_is_rejected(self):
        pack,analysis=sample()
        def forged(facts):
            return {"id":"provenance","name":"Fake","signal":"OBSERVE",
                    "summary":"Unsupported claim","evidence":["not_in_the_snapshot"]}
        with patch.dict(agents._WORKERS,{"provenance":forged}):
            with self.assertRaisesRegex(ValueError,"verification"):
                agents.investigate("7203.T",pack,analysis)

    def test_rejects_forged_risk_metrics_even_when_timestamp_matches(self):
        pack,assessment=sample()
        corrupt=copy.deepcopy(assessment)
        corrupt["risk"]["drawdown"]=.99
        with self.assertRaisesRegex(ValueError,"Risk metrics do not agree"):
            agents.investigate("7203.T",pack,corrupt)
        corrupt=copy.deepcopy(assessment)
        corrupt["risk"]["cvar99"]=float("nan")
        with self.assertRaisesRegex(ValueError,"finite fraction"):
            agents.investigate("7203.T",pack,corrupt)

    def test_bounded_snapshot_rejects_unbounded_payload(self):
        pack,analysis=sample()
        pack["bars"]*=200
        with self.assertRaisesRegex(ValueError,"between 2 and 3000"):
            agents.investigate("7203.T",pack,analysis)


class AutonomousJobTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent/"tests")
        self.addCleanup(temp.cleanup)
        env=patch.dict(os.environ,{"MERIDIAN_BROKER":"off",
                   "APCA_API_KEY_ID":"","APCA_API_SECRET_KEY":""})
        env.start();self.addCleanup(env.stop)
        self.desk=Desk(Path(temp.name)/"autonomous.sqlite3",verification=True)
        self.addCleanup(self.desk.stop)
        self.addCleanup(lambda: self.desk.pool.shutdown(wait=True, cancel_futures=True))

    def _wait(self,symbol="7203.T",timeout=6):
        stop=time.monotonic()+timeout
        while time.monotonic()<stop:
            jobs=[j for j in self.desk.jobs.values() if j["task"]=="autonomous" and j["symbol"]==symbol]
            if jobs and jobs[-1]["state"]!="running":
                return jobs[-1]
            time.sleep(.02)
        self.fail("Autonomous research job did not finish")

    def test_selected_global_symbol_auto_runs_once_with_no_broker_or_model(self):
        pack,_=sample()
        with patch.object(market,"fetch_bars",return_value=pack) as provider, \
             patch.object(self.desk.broker,"submit",side_effect=AssertionError("no broker")), \
             patch("integrations.run_integration",side_effect=AssertionError("no hosted model")):
            self.desk.state("7203.T")
            finished=self._wait()
            self.assertEqual(finished["state"],"complete",finished["result"])
            self.assertEqual(finished["result"]["decision"],"ABSTAIN")
            self.assertEqual(len(finished["result"]["agents"]),6)
            for _ in range(4):self.desk.state("7203.T")
            self.assertEqual(len([j for j in self.desk.jobs.values() if j["task"]=="autonomous"]),1)
            provider.assert_called_once_with("7203.T")
        self.assertTrue(any(a["category"]=="AUTONOMOUS" for a in self.desk.ledger.recent()))
        self.assertEqual(self.desk.state("DEMO")["portfolio"]["orders"],[])

    def test_foreign_stock_local_swarm_only_and_explicitly_requested(self):
        pack,_=sample()
        self.desk.accept("7203.T",pack,save=False)
        with self.assertRaisesRegex(ValueError,"local-only"):
            self.desk.action("/api/job",{"kind":"swarm","symbol":"7203.T",
                                            "engine":"with-provider"})
        with patch("swarm.combined_review",return_value="Mock local model result; no broker access") as worker:
            job=self.desk.action("/api/job",{"kind":"swarm","symbol":"7203.T"})
            self.assertEqual(job["task"],"swarm")
            limit=time.monotonic()+4
            while time.monotonic()<limit:
                done=self.desk.jobs[job["id"]]
                if done["state"]!="running":
                    break
                time.sleep(.02)
            self.assertEqual(done["state"],"complete",done["result"])
            self.assertIn("Mock local",done["result"])
            worker.assert_called_once()
            self.assertFalse(worker.call_args.kwargs["with_provider"])
            # Job status flips before asynchronous SQLite audit logging completes.
            # Join the worker before the temporary test directory is removed.
            self.desk.pool.shutdown(wait=True)

    def test_international_watchlist_does_not_disguise_synthetic_source_as_public(self):
        pack,_=sample(observed=False)
        with patch.object(market,"fetch_bars",return_value=pack):
            self.desk.state("7203.T")
            finished=self._wait()
            self.assertEqual(finished["result"]["decision"],"ABSTAIN")
            selected=next(x for x in self.desk.state("7203.T")["watch"]
                          if x["symbol"]=="7203.T")
            self.assertEqual(selected["kind"],"SIM")
        self.desk.pool.shutdown(wait=True)

    def test_completed_job_requires_durable_audit_entry(self):
        """A finished agent cannot be visible while its SQLite audit is pending."""
        import threading
        pack,_=sample()
        self.desk.accept("7203.T",pack,save=False)
        reached=threading.Event()
        release=threading.Event()
        original=self.desk.ledger.log

        def slow_audit(*args,**kwargs):
            reached.set()
            if not release.wait(timeout=6):
                raise TimeoutError("Test audit gate timed out")
            return original(*args,**kwargs)

        with patch.object(self.desk.ledger,"log",side_effect=slow_audit):
            try:
                job=self.desk.action("/api/job",{"kind":"autonomous","symbol":"7203.T"})
                self.assertTrue(reached.wait(timeout=6),"Worker never reached audit")
                self.assertEqual(self.desk.jobs[job["id"]]["state"],"running",
                                 "Completed job must imply durable audit")
            finally:
                release.set()
            done=self._wait()
            self.assertEqual(done["id"],job["id"])
            self.assertEqual(done["state"],"complete")
            self.assertTrue(any(r["category"]=="AUTONOMOUS"
                                for r in self.desk.ledger.recent()))
        self.desk.pool.shutdown(wait=True)

    def test_audit_error_does_not_report_successful_agent(self):
        pack,_=sample()
        self.desk.accept("7203.T",pack,save=False)
        with patch.object(self.desk.ledger,"log",side_effect=OSError("disk unavailable")):
            self.desk.action("/api/job",{"kind":"autonomous","symbol":"7203.T"})
            done=self._wait()
            self.assertEqual(done["state"],"error")
            self.assertIn("audit persistence failed",done["result"])
        self.desk.pool.shutdown(wait=True)

    def test_manual_local_agent_run_without_external_provider(self):
        pack,_=sample()
        self.desk.accept("7203.T",pack,save=False)
        with self.assertRaisesRegex(ValueError,"locally"):
            self.desk.action("/api/job",{"kind":"autonomous","engine":"tradingagents",
                                            "symbol":"7203.T"})
        job=self.desk.action("/api/job",{"kind":"autonomous","symbol":"7203.T"})
        self.assertEqual(job["task"],"autonomous")
        result=self._wait()
        self.assertEqual(result["state"],"complete")
        self.assertEqual(result["result"]["execution"],"DISABLED")
        self.assertEqual(self.desk.state("DEMO")["portfolio"]["cash"],100000)


if __name__=="__main__":
    unittest.main()
