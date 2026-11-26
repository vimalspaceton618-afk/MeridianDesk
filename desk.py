"""Meridian Desk local workstation service. The native window owns its lifetime."""
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import base64
import hmac
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import uuid

from analytics import analyze, backtest, demo_fundamentals, demo_value_backtest, registry
from broker import Broker
from filings import cached as cached_filing, refresh as refresh_filing
from ledger import Ledger
import market
import universe
from autonomous_research import investigate, report_text

ROOT=Path(__file__).resolve().parent
ASSETS={"/research.js":("research.js","text/javascript"),"/":("index.html","text/html; charset=utf-8"),"/app.css":("app.css","text/css"),"/app.js":("app.js","text/javascript"),"/meridian.ico":("meridian.ico","image/x-icon")}


def research_trigger(previous,current):
    """Detect new dislocations on successive usable snapshots of the same instrument."""
    old_v, new_v = previous.get("valuation") or {}, current.get("valuation") or {}
    old_margin, new_margin = old_v.get("margin"), new_v.get("margin")
    if old_margin is not None and new_margin is not None and old_margin < .30 <= new_margin:
        return "Price crossed the 30% margin-of-safety threshold."
    for field,limit,label in (("drawdown",.20,"Drawdown crossed 20%."),("cvar99",.08,"Modeled one-bar CVaR crossed 8%.")):
        old, new = previous["risk"].get(field), current["risk"].get(field)
        if old is not None and new is not None and old < limit <= new:
            return label
    return ""


class Desk:
    def __init__(self, database, verification=False):
        self.ledger=Ledger(database)
        self.pinned=self.ledger.watched()
        self.broker=Broker(self.ledger)
        self.lock=threading.RLock()
        self.order_lock=threading.RLock()
        self.done=threading.Event()
        self.quotes={}
        self.analyses={}
        self.errors={}
        self.jobs={}
        self.status_cache=None
        self.last_save={}
        self.last_gate={}
        self.last_alert={}
        self.verify=verification
        self.catalog_pending=set()
        self.catalog_attempt={}
        self.auto_checked={}
        self.pool=ThreadPoolExecutor(max_workers=4,thread_name_prefix="research")
        self.workers=[]
        self.fund={s:cached_filing(s) for s in ("AAPL","MSFT")}
        self.fund["DEMO"]=demo_fundamentals()
        for s in market.SYMBOLS:
            pack=self.ledger.snapshot(s)
            if pack and s!="DEMO":
                pack.update(stale=True,session="Cached snapshot",age_seconds=None)
                self.accept(s,pack,save=False)
        for s in self.pinned:
            cached=self.ledger.snapshot(s)
            if cached:
                cached.update(stale=True,session="Cached research snapshot",age_seconds=None)
                self.accept(s,cached,save=False)
        self.accept("DEMO",market.demo_bars("DEMO"),save=False)

    def start(self):
        market.start_live()
        for symbols,delay in [(["BTC-USD","ETH-USD"],.65),(["DEMO"],3),(["SPY","AAPL","MSFT","EURUSD=X","GC=F"],22)]:
            t=threading.Thread(target=self.watch,args=(symbols,delay),daemon=True)
            t.start()
            self.workers.append(t)

    def watch(self,symbols,delay):
        while not self.done.is_set():
            for s in symbols:
                if self.done.is_set():
                    return
                try:
                    self.accept(s,market.fetch_bars(s))
                except Exception as e:
                    with self.lock:
                        self.errors[s]=str(e)[:280]
                        if s in self.quotes:
                            self.quotes[s]={**self.quotes[s],"stale":True}
            self.done.wait(delay)

    def accept(self,s,pack,save=True):
        observed=time.monotonic()
        a=analyze(s,pack["bars"],fundamentals=self.fund.get(s))
        with self.lock:
            old_pack=self.quotes.get(s)
            old_analysis=self.analyses.get(s)
            self.quotes[s]={**pack,"observed":observed}
            self.analyses[s]=a
            self.errors.pop(s,None)
            gate=a["veto"]
            previous=self.last_gate.get(s)
            self.last_gate[s]=gate
        if previous is not None and previous!=gate and save:
            self.ledger.log("RISK GATE",s,a["verdict"]+" • "+" ".join(a["reasons"]))
        if save and old_pack and old_analysis and pack["live"] and not pack.get("stale") and not old_pack.get("stale"):
            event=research_trigger(old_analysis,a)
            if event and not self.done.is_set() and observed-self.last_alert.get(s,-1000)>=900:
                self.last_alert[s]=observed
                self.ledger.log("MARKET ALERT",s,event+" • "+pack["source"])
                try:
                    self.job("swarm",s,captured=(pack,a))
                except ValueError as error:
                    self.ledger.log("RESEARCH DEFERRED",s,str(error))
        if save and pack["live"] and time.monotonic()-self.last_save.get(s,0)>60:
            self.ledger.snapshot(s,pack)
            self.last_save[s]=time.monotonic()

    def marks(self):
        with self.lock:
            return {s:q["bars"][-1]["close"] for s,q in self.quotes.items()}

    def request_catalog(self,s):
        """Schedule at most two public research quote requests; never poll the full catalog."""
        if not universe.available(s) or self.done.is_set():
            return
        now=time.monotonic()
        with self.lock:
            if (s in self.catalog_pending or len(self.catalog_pending)>=2 or
                    now-self.catalog_attempt.get(s,-1000000)<180):
                return
            self.catalog_pending.add(s)
            self.catalog_attempt[s]=now
        def run():
            try:
                pack=market.fetch_bars(s)
                self.accept(s,pack)
                identity=(pack.get("asof"),pack.get("source"),pack.get("stale"))
                with self.lock:
                    already=self.auto_checked.get(s)==identity
                    assessment=copy.deepcopy(self.analyses[s])
                    if not already:
                        self.auto_checked[s]=identity
                # One bounded, offline review per new observed snapshot on explicit
                # instrument selection. This does not enable paid model workers.
                if not already:
                    try:
                        self.job("autonomous",s,captured=(copy.deepcopy(pack),assessment))
                    except (RuntimeError,ValueError) as error:
                        self.ledger.log("RESEARCH DEFERRED",s,"Autonomous review: "+str(error))
            except Exception as exc:
                with self.lock:
                    self.errors[s]="International public market feed unavailable: "+str(exc)[:220]
                    if s in self.quotes:
                        self.quotes[s]["stale"]=True
            finally:
                with self.lock:
                    self.catalog_pending.discard(s)
        try:
            self.pool.submit(run)
        except RuntimeError:
            with self.lock:
                self.catalog_pending.discard(s)

    def selected(self,symbol):
        if symbol not in market.SYMBOLS and not universe.available(symbol):
            raise ValueError("Unknown instrument.")
        with self.lock:
            if symbol not in self.quotes:
                raise ValueError(self.errors.get(symbol,"Waiting for the first market observation."))
            pack=self.quotes[symbol].copy()
            age=pack.get("age_seconds")
            if isinstance(age,(int,float)):
                pack["age_seconds"]=max(0,age)+max(0,time.monotonic()-pack["observed"])
            pack.pop("observed",None)
            return pack,self.analyses[symbol]

    def state(self,s):
        if s not in market.SYMBOLS and not universe.available(s):
            raise ValueError("Unknown instrument.")
        if universe.available(s):
            self.request_catalog(s)
        with self.lock:
            watch=[]
            for k,name in market.SYMBOLS.items():
                q=self.quotes.get(k)
                b=q["bars"] if q else []
                watch.append({"symbol":k,"name":name,"price":b[-1]["close"] if b else None,
                    "change":(b[-1]["close"]/b[-2]["close"]-1) if len(b)>1 else None,
                    "kind":"SIM" if k=="DEMO" else "WAIT" if not q else "STALE" if q.get("stale") else
                    "LIVE" if q.get("transport","").upper() in ("WEBSOCKET","WS") else "PUBLIC",
                    "spark":[v["close"] for v in b[-18:]]})
            for ticker in dict.fromkeys(self.pinned+([s] if universe.available(s) else [])):
                record=universe.CATALOG[ticker]
                q=self.quotes.get(ticker)
                b=q["bars"] if q else []
                watch.append({"symbol":ticker,"name":record["name"],"price":b[-1]["close"] if b else None,
                    "change":b[-1]["close"]/b[-2]["close"]-1 if len(b)>1 else None,
                    "kind":"WAIT" if not q else "STALE" if q.get("stale") else
                    "SIM" if not q.get("live") else "PUBLIC",
                    "currency":q.get("currency",record["currency"]) if q else record["currency"],
                    "spark":[v["close"] for v in b[-18:]]})
            pack,a=self.selected(s) if s in self.quotes else (None,None)
            jobs=list(self.jobs.values())[-25:]
            err=self.errors.get(s,"")
        return {"watch":watch,"market":pack,"analysis":a,"error":err,"symbol":s,
            "instrument":dict(universe.CATALOG[s]) if universe.available(s) else None,
            "pinned":list(self.pinned),"portfolio":self.ledger.portfolio(self.marks()),
            "audit":self.ledger.recent(),"broker":self.broker.status(),"broker_orders":self.broker.tickets(),
            "jobs":jobs,"filings":self.fund.get(s,{}).get("filings",[]) if self.fund.get(s) else [],"clock":time.time()}

    def engines(self):
        import integrations
        with self.lock:
            if self.status_cache and time.monotonic()-self.status_cache[0]<15:
                return self.status_cache[1]
        result=integrations.statuses()
        with self.lock:
            self.status_cache=(time.monotonic(),result)
        return result

    def job(self,kind,symbol,engine=None,*,captured=None):
        if (kind not in ("research","backtest","integration","filings","swarm","autonomous") or
                (symbol not in market.SYMBOLS and not universe.available(symbol))):
            raise ValueError("Unknown research request.")
        if universe.available(symbol) and kind not in ("research","backtest","autonomous","swarm"):
            raise ValueError("International catalog research supports only review, local swarm, autonomous analysis and backtest.")
        if universe.available(symbol) and kind=="swarm" and engine is not None:
            raise ValueError("Global equities permit local-only Ruflo/Kronos swarm; external provider modes are disabled.")
        if kind=="autonomous" and engine not in (None,"local"):
            raise ValueError("Autonomous research runs locally; provider routing is not authorized.")
        pack,snapshot_analysis=captured if captured is not None else self.selected(symbol)
        if kind=="integration" and engine not in ("kronos","tradingagents","ruflo"):
            raise ValueError("Unknown integration.")
        if kind=="swarm" and engine not in (None,"with-provider"):
            raise ValueError("Unknown combined review mode.")
        tag=engine if kind=="integration" else ("swarm + provider" if kind=="swarm" and engine else kind)
        with self.lock:
            active=[r for r in self.jobs.values() if r["state"]=="running"]
            duplicate=next((r for r in active if r["task"]==tag and r["symbol"]==symbol),None)
            if duplicate:
                return duplicate
            if len(active)>=4:
                raise ValueError("Four research jobs are already in progress.")
            key=uuid.uuid4().hex
            row={"id":key,"task":tag,"symbol":symbol,"state":"running","ts":time.time(),"result":""}
            self.jobs[key]=row
            if len(self.jobs)>80:
                finished=next((k for k,v in self.jobs.items() if v["state"]!="running"),None)
                if finished:
                    del self.jobs[finished]
        def run():
            try:
                if kind=="autonomous":
                    result=investigate(symbol,copy.deepcopy(pack),copy.deepcopy(snapshot_analysis))
                elif kind=="swarm":
                    from swarm import combined_review
                    result=combined_review(symbol,pack,snapshot_analysis,with_provider=(engine=="with-provider"))
                elif kind=="integration":
                    from integrations import run_integration
                    result=run_integration(engine,symbol,pack["bars"])
                elif kind=="backtest" and symbol=="DEMO":
                    result=demo_value_backtest()
                elif kind=="backtest":
                    data=market.fetch_history(symbol)
                    result={"Source":data["source"],"Interval":data["interval"],**backtest(symbol,data["bars"])}
                elif kind=="filings":
                    self.fund[symbol]=refresh_filing(symbol)
                    self.accept(symbol,market.fetch_bars(symbol))
                    result=f"Loaded {len(self.fund[symbol]['annual'])} annual statements from SEC Company Facts."
                else:
                    a=analyze(symbol,pack["bars"],fundamentals=self.fund.get(symbol))
                    result=a["verdict"]+"\n"+"\n".join(r["name"]+" — "+r["signal"]+" • "+r["detail"] for r in a["agents"])
                success=True
            except Exception as e:
                result=str(e) or type(e).__name__
                success=False
            with self.lock:
                self.jobs[key]={**row,"state":"complete" if success else "error","result":result,"finished":time.time()}
            self.ledger.log(tag.upper(),symbol,
                            report_text(result) if kind=="autonomous" and success
                            else result if isinstance(result,str)
                            else json.dumps(result,ensure_ascii=False))
        self.pool.submit(run)
        return row

    def action(self,path,body):
        if path=="/api/watchlist":
            symbol=body.get("symbol")
            if not universe.available(symbol):
                raise ValueError("Only approved international research symbols can be pinned.")
            with self.lock:
                self.pinned=self.ledger.watch(symbol,body.get("enabled"))
                return {"pinned":list(self.pinned)}
        if path=="/api/job":
            return self.job(body["kind"],body["symbol"],body.get("engine"))
        if path=="/api/halt":
            with self.order_lock:
                self.ledger.halt(body["enabled"])
            return {"ok":True}
        if path in ("/api/paper","/api/broker/order"):
            s=body["symbol"]
            if universe.available(s):
                raise ValueError("International catalog equities are research-only; trading requires separate currency, venue and broker authorization.")
            with self.order_lock:
                pack,a=self.selected(s)
                if path=="/api/broker/order":
                    return {"status":self.broker.submit(body,pack,a)}
                try:
                    return self.ledger.fill(body,pack,a,self.marks())
                except ValueError as e:
                    self.ledger.log("ORDER BLOCKED",s,str(e))
                    raise
        if path=="/api/broker/account":
            return self.broker.account()
        if path=="/api/broker/reconcile":
            return {"status":self.broker.reconcile(body["id"])}
        if path=="/api/mt5":
            raw=base64.b64decode(body["content"],validate=True)
            if len(raw)>4_000_000:
                raise ValueError("Import a report or the last 4 MB of an Experts log.")
            folder=ROOT/"cache"/"temp"
            folder.mkdir(parents=True,exist_ok=True)
            dest=folder/(uuid.uuid4().hex+".log")
            try:
                dest.write_bytes(raw)
                report=market.read_mt5_report(dest)
            finally:
                dest.unlink(missing_ok=True)
            self.ledger.log("MT5 IMPORT","APEX-FX",report)
            return {"report":report}
        raise ValueError("Unknown action.")

    def stop(self):
        self.done.set()
        market.stop_live()
        self.pool.shutdown(wait=False,cancel_futures=True)


def serve(desk,secret):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):
            return
        def reply(self,code,content,ctype="application/json; charset=utf-8"):
            if not isinstance(content,bytes):
                content=json.dumps(content,ensure_ascii=False,allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type",ctype)
            self.send_header("Content-Length",str(len(content)))
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Cache-Control","no-store")
            self.send_header("Referrer-Policy","no-referrer")
            self.send_header("Content-Security-Policy","default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(content)
        def guard(self):
            if self.headers.get("Host")!="127.0.0.1:"+str(self.server.server_port):
                self.reply(403,{"error":"Invalid host."}); return False
            if not hmac.compare_digest(self.headers.get("Authorization",""),"Bearer "+secret):
                self.reply(403,{"error":"Invalid desktop session."}); return False
            if self.command=="POST" and (self.headers.get("Origin") not in (None,"http://"+self.headers["Host"]) or self.headers.get_content_type()!="application/json"):
                self.reply(403,{"error":"Invalid desktop origin or content type."}); return False
            return True
        def do_GET(self):
            parts=urlsplit(self.path)
            if parts.path in ASSETS:
                file,kind=ASSETS[parts.path]
                return self.reply(200,(ROOT/"app"/file).read_bytes(),kind)
            if not self.guard():
                return
            try:
                if parts.path=="/api/state":
                    result=desk.state(parse_qs(parts.query).get("symbol",["BTC-USD"])[0])
                elif parts.path=="/api/engines":
                    result=desk.engines()
                elif parts.path=="/api/registry":
                    result=registry()
                elif parts.path=="/api/catalog":
                    result=universe.entries()
                else:
                    return self.reply(404,{"error":"Unknown route."})
                self.reply(200,result)
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                return
            except Exception as e:
                self.reply(400,{"error":str(e)})
        def do_POST(self):
            if not self.guard():
                return
            try:
                size=int(self.headers.get("Content-Length","0"))
                if not 0<size<=5500000:
                    raise ValueError("Invalid request length.")
                body=json.loads(self.rfile.read(size))
                if not isinstance(body,dict):
                    raise ValueError("Expected a JSON object.")
                self.reply(200,desk.action(self.path,body))
            except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):
                return
            except Exception as e:
                self.reply(400,{"error":str(e) or type(e).__name__})
    return ThreadingHTTPServer(("127.0.0.1",0),Handler)


def main():
    verify="--verify" in sys.argv
    folder=ROOT/("tests" if verify else "data")
    desk=Desk(folder/("smoke.sqlite3" if verify else "desk.sqlite3"),verify)
    token=secrets.token_urlsafe(32)
    http=serve(desk,token)
    print(f"http://127.0.0.1:{http.server_port}/#{token}"+("~verify" if verify else ""),flush=True)
    desk.start()
    if "--desktop" in sys.argv:
        def owner():
            sys.stdin.readline()
            http.shutdown()
        threading.Thread(target=owner,daemon=True).start()
    try:
        http.serve_forever(poll_interval=.2)
    finally:
        http.server_close()
        desk.stop()

if __name__=="__main__":
    main()
