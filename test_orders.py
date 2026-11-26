"""Offline checks for paper accounting and broker dispatch. No broker calls are made."""
import concurrent.futures
import io
import json
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import uuid
from datetime import datetime, timezone
from email.utils import formatdate
from pathlib import Path
from unittest.mock import patch

from broker import Broker, OrderRejected
from ledger import Ledger


def order(symbol="BTC-USD", qty=1, limit=100, side="buy"):
    return {"symbol":symbol, "side":side, "qty":qty, "limit":limit, "id":str(uuid.uuid4()),
            "confirmation":f"PAPER {side.upper()} {symbol}"}


def quote():
    return {"source":"Exchange fixture", "asof":time.time()+230, "age_seconds":.1, "stale":False,
            "live":True, "bars":[{"close":100}], "bid":99.98, "ask":100.02}


def research():
    return {"veto":False, "reasons":[], "valuation":None}


class FakeBroker:
    def __init__(self):
        self.orders=[]
        self.pending=[]
        self.positions=[]
        self.cash=1500
        self.equity=10000
        self.age=.3
        self.price=100
        self.clock=True
        self.session_open=True
        self.blocked=False
        self.error=None
        self.ref=None
        self.status="filled"

    def __call__(self, method, url, body=None):
        if method=="POST":
            self.orders.append(body)
            if self.error:
                raise self.error
            return {"id":"order-1","client_order_id":self.ref or body["client_order_id"],"status":"accepted"}
        if url=="/v2/account":
            return {"status":"ACTIVE","equity":self.equity,"cash":self.cash,"trading_blocked":self.blocked}
        if url.startswith("/v2/orders?"):
            return self.pending
        if url.startswith("/v2/orders:"):
            return {"id":"order-1","client_order_id":url.split("=")[-1],"status":self.status}
        if url=="/v2/positions":
            return self.positions
        if url=="/v2/clock":
            return {"is_open":self.session_open}
        if url.startswith("/data/"):
            symbol=urllib.parse.unquote(url.split("symbols=")[1].split("&")[0])
            now=int(time.time())+230
            stamp=datetime.fromtimestamp(now+1-self.age,timezone.utc).isoformat()
            r={"quotes":{symbol:{"t":stamp,"ap":self.price+.02,"bp":self.price-.02}}}
            if self.clock:
                r["_clock"]=(now,.01,time.monotonic())
            return r
        raise AssertionError(f"Unexpected method/path {method} {url}")


class OrdersTests(unittest.TestCase):
    def setUp(self):
        scratch=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(scratch.cleanup)
        self.ledger=Ledger(Path(scratch.name)/"orders.sqlite")
        self.fake=FakeBroker()
        self.broker=Broker(self.ledger,self.fake)
        self.broker.mode="paper"
        self.broker.key=self.broker.secret="fixture"

    def submit(self, req=None, pack=None, result=None):
        return self.broker.submit(req or order(),pack or quote(),result or research())

    def test_paper_accounting_idempotency_and_exit(self):
        q=order(qty=1.5, limit=101)
        fill=self.ledger.fill(q,quote(),research(),{})
        self.assertAlmostEqual(fill["price"],100.02*1.0002)
        self.assertEqual(fill,self.ledger.fill(q,quote(),research(),{}))
        portfolio=self.ledger.portfolio({"BTC-USD":100})
        self.assertEqual(len(portfolio["orders"]),1)
        self.assertAlmostEqual(portfolio["cash"],100000-1.5*fill["price"]-fill["fee"])
        with self.assertRaisesRegex(ValueError,"identifier"):
            self.ledger.fill(dict(q,qty=1),quote(),research(),{})
        sale=self.ledger.fill(order(qty=1.5,limit=99,side="sell"),quote(),{"veto":True,"reasons":["risk"]},{})
        portfolio=self.ledger.portfolio({})
        self.assertFalse(portfolio["positions"])
        self.assertAlmostEqual(portfolio["cash"],100000+1.5*(sale["price"]-fill["price"])-sale["fee"]-fill["fee"])

    def test_paper_halt_cash_veto_limit_source_and_age(self):
        q=order(limit=101)
        cases=[
            (q,dict(quote(),age_seconds=None),research(),"Fresh"),
            (q,dict(quote(),age_seconds=3),research(),"Fresh"),
            (q,dict(quote(),age_seconds=float("nan")),research(),"Fresh"),
            (q,dict(quote(),stale=True),research(),"Fresh"),
            (q,dict(quote(),live=False),research(),"Fresh"),
            (q,dict(quote(),ask=105),research(),"two-sided"),
            (q,quote(),{"veto":True,"reasons":["legal"]},"veto"),
            (q,quote(),dict(research(),valuation={"target":100}),"ceiling"),
            (dict(q,limit=99),quote(),research(),"Limit not met"),
            (dict(q,qty=250),quote(),research(),"15%"),
            (dict(q,qty=2000),quote(),research(),"cash"),
            (order(side="sell",limit=99),quote(),research(),"held")]
        for request,pack,analysis,msg in cases:
            with self.subTest(msg=msg), self.assertRaisesRegex(ValueError,msg):
                self.ledger.fill(request,pack,analysis,{})
        self.ledger.halt(True)
        with self.assertRaisesRegex(ValueError,"halted"):
            self.ledger.fill(q,quote(),research(),{})
        self.assertEqual(Ledger(self.ledger.path).portfolio({})["halted"],1)
        self.ledger.halt(False)
        p=self.ledger.portfolio({})
        self.assertEqual((p["cash"],len(p["orders"]),len(p["positions"])),(100000,0,0))

    def test_concurrent_paper_commits_once_and_respects_exposure(self):
        q=order(qty=100,limit=101)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            fills=list(pool.map(lambda _:self.ledger.fill(q,quote(),research(),{}),range(2)))
        self.assertEqual(fills[0],fills[1])
        with self.assertRaisesRegex(ValueError,"15%"):
            self.ledger.fill(order(qty=90,limit=101),quote(),research(),{})

    def test_demo_execution_source_and_veto(self):
        sample={"live":False,"source":"Synthetic fixture","bars":[{"close":80}]}
        with self.assertRaisesRegex(ValueError,"veto"):
            self.ledger.fill(order("DEMO"),sample,{"veto":True,"reasons":["margin"]},{})
        self.assertEqual(self.ledger.fill(order("DEMO"),sample,research(),{})["source"],"Synthetic fixture")

    def test_broker_safety_checks_never_dispatch(self):
        q=order()
        for req,pack,result,msg in [
            (dict(q,confirmation="LIVE BUY BTC-USD"),quote(),research(),"confirmation"),
            (q,quote(),{"veto":True},"risk gate"),
            (q,dict(quote(),stale=True),research(),"risk gate"),
            (q,quote(),dict(research(),valuation={"target":99}),"ceiling")]:
            with self.assertRaisesRegex(ValueError,msg):
                self.submit(req,pack,result)
        self.ledger.halt(True)
        with self.assertRaisesRegex(ValueError,"halted"):
            self.submit(q)
        self.ledger.halt(False)
        self.fake.blocked=True
        with self.assertRaisesRegex(ValueError,"unavailable"):
            self.submit(q)
        self.fake.blocked=False
        self.fake.session_open=False
        with self.assertRaisesRegex(ValueError,"session"):
            self.submit(order("SPY"))
        self.assertFalse(self.fake.orders)
        self.assertFalse(self.broker.tickets())

    def test_broker_freshness_and_price_checks(self):
        self.fake.clock=False
        with self.assertRaisesRegex(ValueError,"clock"):
            self.submit()
        self.fake.clock=True
        for age in (-1,3):
            self.fake.age=age
            with self.assertRaisesRegex(ValueError,"two seconds"):
                self.submit()
        self.fake.age=.3
        self.fake.price=104
        with self.assertRaisesRegex(ValueError,"disagree"):
            self.submit()
        self.fake.price=100
        with self.assertRaisesRegex(ValueError,"within 2%"):
            self.submit(order(limit=108))
        self.assertFalse(self.fake.orders)
        self.assertEqual(self.submit(),"accepted")

    def test_broker_idempotency_and_final_status(self):
        q=order(qty=2)
        self.assertEqual(self.submit(q),"accepted")
        self.assertEqual(self.submit(q),"accepted")
        self.assertEqual(len(self.fake.orders),1)
        with self.assertRaisesRegex(ValueError,"different ticket"):
            self.submit(dict(q,qty=3))
        with self.assertRaisesRegex(ValueError,"previous broker ticket"):
            self.submit()
        self.assertEqual(self.broker.reconcile(q["id"]),"filled")
        self.fake.status="accepted"
        self.assertEqual(self.broker.reconcile(q["id"]),"filled")
        self.assertEqual(self.submit(q),"filled")

    def test_explicit_rejection_releases_reservation_timeout_preserves_it(self):
        q=order(qty=10)
        self.fake.error=OrderRejected("invalid quantity")
        with self.assertRaises(OrderRejected):
            self.submit(q)
        self.assertEqual(self.submit(q),"rejected")
        self.fake.error=TimeoutError("fixture timeout")
        q2=order(qty=10)
        with self.assertRaisesRegex(ValueError,"uncertain"):
            self.submit(q2)
        self.assertEqual(self.submit(q2),"dispatch pending")
        self.assertEqual(len(self.fake.orders),2)
        with self.assertRaisesRegex(ValueError,"previous broker ticket"):
            self.submit()
        with self.assertRaisesRegex(ValueError,"unreserved cash"):
            self.submit(order("ETH-USD",qty=6))
        self.fake.status="canceled"
        self.assertEqual(self.broker.reconcile(q2["id"]),"canceled")
        self.fake.error=None
        self.assertEqual(self.submit(order("ETH-USD",qty=6)),"accepted")

    def test_bad_ack_preserves_original_reference(self):
        q=order()
        self.fake.ref=str(uuid.uuid4())
        with self.assertRaisesRegex(ValueError,"uncertain"):
            self.submit(q)
        self.assertEqual(self.broker.tickets()[0]["status"],"dispatch pending")
        self.assertEqual(self.fake.orders[0]["client_order_id"],q["id"])

    def test_reserves_remote_and_local_orders_once(self):
        q=order(qty=10)
        self.submit(q)
        self.fake.pending=[{"symbol":"BTCUSD","side":"buy","qty":"10","filled_qty":"0",
                            "limit_price":"100","client_order_id":q["id"]}]
        with self.assertRaisesRegex(ValueError,"unreserved cash"):
            self.submit(order("ETH-USD",qty=6))
        self.assertEqual(self.submit(order("ETH-USD",qty=5)),"accepted")

    def test_broker_size_position_and_unknown_remote_liability(self):
        self.fake.positions=[{"symbol":"BTCUSD","qty":"12","qty_available":"2"}]
        with self.assertRaisesRegex(ValueError,"15%"):
            self.submit(order(qty=5))
        with self.assertRaisesRegex(ValueError,"available long"):
            self.submit(order(qty=3,side="sell"))
        self.fake.pending=[{"symbol":"SPY","side":"buy","qty":"3","limit_price":None}]
        with self.assertRaisesRegex(ValueError,"reservation"):
            self.submit()
        self.assertFalse(self.fake.orders)

    def test_http_rejection_and_duplicate_classification(self):
        for code,body,expected in [(422,b'{"message":"invalid increment"}',OrderRejected),
                                   (422,b'{"message":"client_order_id must be unique"}',ValueError),
                                   (503,b"unavailable",ValueError)]:
            err=urllib.error.HTTPError("https://paper-api.alpaca.markets/v2/orders",code,"HTTP",{},io.BytesIO(body))
            with patch.object(self.broker.opener,"open",side_effect=err):
                with self.assertRaises(expected) as caught:
                    self.broker.http("POST","/v2/orders",{})
            self.assertIs(type(caught.exception),expected)

    def test_http_response_clock_required(self):
        class Response(io.BytesIO):
            headers={}
        for good in (True,False):
            response=Response(json.dumps({"quotes":{}}).encode())
            stamp=int(time.time())+230
            response.headers={"Date":formatdate(stamp,usegmt=True)} if good else {}
            with patch.object(self.broker.opener,"open",return_value=response):
                if good:
                    data=self.broker.http("GET","/data/v2/stocks/quotes/latest?symbols=SPY")
                    self.assertEqual(data["_clock"][0],stamp)
                else:
                    with self.assertRaises((ValueError,KeyError)):
                        self.broker.http("GET","/data/v2/stocks/quotes/latest?symbols=SPY")


if __name__=="__main__":
    unittest.main()
