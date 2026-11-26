"""Transactional local paper account and research audit trail."""
import json
import math
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path


class Ledger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS account(id INTEGER PRIMARY KEY CHECK(id=1), cash REAL NOT NULL, halted INTEGER NOT NULL);
                INSERT OR IGNORE INTO account VALUES (1,100000,0);
                CREATE TABLE IF NOT EXISTS positions(symbol TEXT PRIMARY KEY, qty REAL NOT NULL, basis REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS orders(id TEXT PRIMARY KEY, ts REAL, symbol TEXT, side TEXT, qty REAL,
                    price REAL, fee REAL, requested REAL, source TEXT);
                CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, ts REAL, category TEXT, symbol TEXT, detail TEXT);
                CREATE TABLE IF NOT EXISTS snapshots(symbol TEXT PRIMARY KEY, payload TEXT NOT NULL);
            """)

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _log(db, kind, symbol, detail):
        db.execute("INSERT INTO audit(ts,category,symbol,detail) VALUES(?,?,?,?)", (time.time(),kind,symbol,detail))

    def log(self, kind, symbol, detail):
        with self.db() as db:
            self._log(db,kind,symbol,str(detail)[:16000])

    def halt(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Choose a valid halt state.")
        with self.db() as db:
            db.execute("UPDATE account SET halted=? WHERE id=1",(int(enabled),))
            self._log(db,"CONTROL","DESK","New orders halted." if enabled else "New orders resumed.")

    def snapshot(self, symbol, value=None):
        with self.db() as db:
            if value is None:
                row=db.execute("SELECT payload FROM snapshots WHERE symbol=?",(symbol,)).fetchone()
                return json.loads(row[0]) if row else None
            db.execute("INSERT OR REPLACE INTO snapshots VALUES(?,?)",(symbol,json.dumps(value,allow_nan=False)))

    def recent(self):
        with self.db() as db:
            return [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 80")]

    def portfolio(self, marks):
        with self.db() as db:
            db.execute("BEGIN")
            account = dict(db.execute("SELECT cash,halted FROM account").fetchone())
            positions=[]
            for r in db.execute("SELECT * FROM positions ORDER BY symbol"):
                mark=marks.get(r["symbol"])
                price=mark or r["basis"]
                positions.append({**dict(r),"mark":price,"estimated":not bool(mark),
                    "value":r["qty"]*price,"pnl":r["qty"]*(price-r["basis"])})
            orders=[dict(r) for r in db.execute("SELECT * FROM orders ORDER BY ts DESC LIMIT 75")]
        return {**account,"equity":account["cash"]+sum(p["value"] for p in positions),"positions":positions,"orders":orders}

    def fill(self, request, pack, analysis, marks, now=None):
        started=time.monotonic()
        now=time.time() if now is None else now
        symbol,side=request["symbol"], request["side"]
        order_id=str(uuid.UUID(request["id"]))
        qty,limit=float(request["qty"]),float(request["limit"])
        if side not in ("buy","sell") or not all(math.isfinite(v) and v>0 for v in (qty,limit)) or qty>1e9:
            raise ValueError("Enter a positive quantity and limit price.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            previous=db.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone()
            if previous:
                if (previous["symbol"],previous["side"],previous["qty"],previous["requested"])!=(symbol,side,qty,limit):
                    raise ValueError("This order identifier was already used for another ticket.")
                return dict(previous)
            cash,halted=db.execute("SELECT cash,halted FROM account").fetchone()
            if halted:
                raise ValueError("Trading is halted.")
            is_demo=symbol=="DEMO" and not pack["live"]
            if not is_demo:
                age=pack.get("age_seconds")
                if (not pack["live"] or pack.get("stale") or type(age) not in (int, float)
                        or not math.isfinite(age) or age < 0 or age + (time.monotonic() - started) > 2):
                    raise ValueError("Fresh exchange quotes within two seconds are required for a fill.")
            if side=="buy" and analysis["veto"]:
                raise ValueError("Entry veto: "+" ".join(analysis["reasons"]))
            if not is_demo:
                bid,ask=pack.get("bid"),pack.get("ask")
                if (not all(isinstance(v,(int,float)) and math.isfinite(v) and v>0 for v in (bid,ask))
                        or bid>ask or ask/bid>1.01):
                    raise ValueError("A tradable two-sided quote within the 1% spread limit is required.")
            reference=pack.get("ask" if side=="buy" else "bid")
            if not reference and is_demo:
                reference=pack["bars"][-1]["close"]
            if not reference or not math.isfinite(reference) or reference<=0:
                raise ValueError("A tradable bid and ask are unavailable.")
            price=reference*(1.0002 if side=="buy" else .9998)
            if (side=="buy" and price>limit) or (side=="sell" and price<limit):
                raise ValueError("Limit not met at the modeled fill price. No fill was booked.")
            valuation=analysis.get("valuation")
            if side=="buy" and valuation and price>valuation["target"]:
                raise ValueError("Modeled fill exceeds the margin-of-safety entry ceiling.")
            value=price*qty
            if not math.isfinite(value):
                raise ValueError("Order value exceeds the supported range.")
            fee=round(max(.01,value*.0001),2)
            row=db.execute("SELECT qty,basis FROM positions WHERE symbol=?",(symbol,)).fetchone()
            old,basis=tuple(row) if row else (0.,0.)
            if side=="buy":
                equity=cash+sum(r["qty"]*marks.get(r["symbol"],r["basis"]) for r in db.execute("SELECT * FROM positions"))
                if value+fee>cash or (old+qty)*price>equity*.15:
                    raise ValueError("Entry exceeds cash or the 15% single-position limit.")
                new_qty=old+qty
                new_basis=(old*basis+value+fee)/new_qty
                cash-=value+fee
            else:
                if qty>old:
                    raise ValueError("Quantity exceeds the held position.")
                new_qty=old-qty
                new_basis=basis
                if cash+value<fee:
                    raise ValueError("Insufficient cash to cover the simulated exit fee.")
                cash+=value-fee
            if new_qty<=1e-12:
                db.execute("DELETE FROM positions WHERE symbol=?",(symbol,))
            else:
                db.execute("INSERT OR REPLACE INTO positions VALUES(?,?,?)",(symbol,new_qty,new_basis))
            db.execute("UPDATE account SET cash=? WHERE id=1",(cash,))
            db.execute("INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?)",(order_id,now,symbol,side,qty,price,fee,limit,pack["source"]))
            self._log(db,"PAPER FILL",symbol,f"{side.upper()} {qty:g} at {price:.5f} • fee {fee:.2f} • {pack['source']}")
            return dict(db.execute("SELECT * FROM orders WHERE id=?",(order_id,)).fetchone())
