"""Human-confirmed Alpaca limit orders with durable client IDs and cash reservations."""
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from decimal import Decimal
from email.utils import parsedate_to_datetime

SYMBOLS = {"BTC-USD": "BTC/USD", "ETH-USD": "ETH/USD", "AAPL": "AAPL", "MSFT": "MSFT", "SPY": "SPY"}
_FINAL = {"filled", "canceled", "expired", "rejected", "replaced"}


class OrderRejected(ValueError):
    """The authenticated broker explicitly rejected creation of this order."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def _nonnegative(value, name):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"Invalid {name}.")
    return value


def _remote_reserve(order):
    if order["side"] != "buy":
        return 0.0
    if order.get("notional") is not None:
        return _nonnegative(order["notional"], "open notional")
    if order.get("asset_class") not in (None, "us_equity", "crypto") or not order.get("limit_price"):
        raise ValueError("An open broker purchase has no usable dollar reservation. Reconcile it first.")
    qty = _nonnegative(order["qty"], "open quantity")
    filled = _nonnegative(order.get("filled_qty", 0), "filled quantity")
    price = _nonnegative(order["limit_price"], "open limit")
    if filled > qty or price <= 0:
        raise ValueError("Broker open-order reservation is inconsistent.")
    return (qty - filled) * price


def _fresh_quote(response, ticker):
    q = response["quotes"][ticker]
    stamp = datetime.fromisoformat(q["t"].replace("Z", "+00:00"))
    clock = response.get("_clock")
    if stamp.tzinfo is None or not clock:
        raise ValueError("A broker timestamp and verified HTTP clock are required.")
    quote_utc = stamp.timestamp()
    server_utc, rtt, received = clock
    elapsed = time.monotonic() - received
    # HTTP Date has 1s precision. The entire request RTT bounds its transit delay.
    # Use the oldest plausible age and reject quotes ahead of the broker's response clock.
    age = server_utc + 1 + rtt + elapsed - quote_utc
    if (not all(math.isfinite(v) for v in (age, server_utc, rtt, elapsed, quote_utc))
            or rtt < 0 or elapsed < 0 or quote_utc > server_utc + 1 or not 0 <= age <= 2):
        raise ValueError("The broker quote cannot be verified within two seconds.")
    bid, ask = (float(q[k]) for k in ("bp", "ap"))
    if not all(math.isfinite(v) and v > 0 for v in (bid, ask)) or bid > ask or ask / bid > 1.01:
        raise ValueError("The broker spread or quote failed validation.")
    return bid, ask


class Broker:
    def __init__(self, ledger, transport=None):
        self.ledger = ledger
        self.transport = transport or self.http
        self.mode = os.environ.get("MERIDIAN_BROKER", "off").lower()
        self.key = os.environ.get("APCA_API_KEY_ID", "")
        self.secret = os.environ.get("APCA_API_SECRET_KEY", "")
        self.opener = urllib.request.build_opener(_NoRedirect())
        with ledger.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS broker_orders(id TEXT PRIMARY KEY, ts REAL, mode TEXT,
                        symbol TEXT, side TEXT, qty REAL, price REAL, status TEXT, broker_id TEXT)""")

    def status(self):
        enabled = self.mode in ("paper", "live")
        return {"mode": self.mode if enabled else "off", "configured": enabled and bool(self.key and self.secret)}

    def http(self, method, endpoint, body=None):
        if not self.status()["configured"]:
            raise ValueError("Set MERIDIAN_BROKER and the two Alpaca credentials before launching Meridian.")
        base = "https://paper-api.alpaca.markets" if self.mode == "paper" else "https://api.alpaca.markets"
        market = endpoint.startswith("/data/")
        url = "https://data.alpaca.markets/" + endpoint[6:] if market else base + endpoint
        request = urllib.request.Request(url, data=None if body is None else json.dumps(body).encode(),
            headers={"APCA-API-KEY-ID": self.key, "APCA-API-SECRET-KEY": self.secret,
                     "Content-Type": "application/json", "Cache-Control": "no-cache"}, method=method)
        started = time.monotonic()
        try:
            with self.opener.open(request, timeout=8) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("Broker response exceeded the size limit.")
                result = json.loads(raw) if raw else {}
                if market:
                    try:
                        server = parsedate_to_datetime(response.headers["Date"]).timestamp()
                        server += int(response.headers.get("Age", 0))
                    except (TypeError, ValueError, OverflowError, AttributeError):
                        raise ValueError("Broker response lacks a usable HTTP clock.") from None
                    if abs(time.time() - server) > 900:
                        raise ValueError("Broker and workstation clocks differ by more than 15 minutes.")
                    received = time.monotonic()
                    result["_clock"] = (server, received - started, received)
                return result
        except urllib.error.HTTPError as err:
            # Duplicate IDs and timeouts require reconciliation even if expressed as 4xx.
            reason = err.read(4096).decode("utf8", errors="replace").lower()
            duplicate = any(k in reason for k in ("already", "unique", "duplicat"))
            if method == "POST" and err.code in (400, 401, 403, 404, 405, 413, 415, 422) and not duplicate:
                raise OrderRejected(f"Alpaca rejected the order (HTTP {err.code}).") from None
            if method == "GET" and err.code == 404:
                raise LookupError("Broker has no matching record yet. The local reservation remains active.") from None
            raise ValueError(f"Alpaca returned HTTP {err.code}. Review the broker account.") from None

    def account(self):
        a = self.transport("GET", "/v2/account")
        return {"status": str(a["status"]), "equity": _nonnegative(a["equity"], "account equity"),
                "cash": _nonnegative(a["cash"], "account cash"),
                "blocked": bool(a.get("trading_blocked") or a.get("account_blocked"))}

    def tickets(self):
        with self.ledger.db() as db:
            return [dict(r) for r in db.execute("""SELECT * FROM broker_orders WHERE mode=?
                ORDER BY (status IN ('filled','canceled','expired','rejected','replaced')), ts DESC LIMIT 50""", (self.mode,))]

    def update(self, ticket, ref):
        if ticket.get("client_order_id") != ref or not ticket.get("id") or not ticket.get("status"):
            raise ValueError("Broker acknowledgement does not match the submitted ticket.")
        with self.ledger.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT symbol,status FROM broker_orders WHERE id=? AND mode=?", (ref, self.mode)).fetchone()
            if not row:
                raise ValueError("Unknown local broker ticket.")
            if row["status"] in _FINAL:
                return row["status"]
            db.execute("UPDATE broker_orders SET status=?,broker_id=? WHERE id=? AND mode=?",
                       (ticket["status"], ticket["id"], ref, self.mode))
            self.ledger._log(db, "BROKER STATUS", row[0], f"{ref} · {ticket['status']}")
        return str(ticket["status"])

    def reconcile(self, order_id):
        ref = str(uuid.UUID(order_id))
        with self.ledger.db() as db:
            if not db.execute("SELECT 1 FROM broker_orders WHERE mode=? AND id=?", (self.mode, ref)).fetchone():
                raise ValueError("Unknown local broker ticket.")
        data = self.transport("GET", "/v2/orders:by_client_order_id?client_order_id=" + ref)
        return self.update(data, ref)

    def _prior(self, db, ref, symbol, side, qty, limit):
        old = db.execute("SELECT * FROM broker_orders WHERE id=?", (ref,)).fetchone()
        if old and (old["mode"], old["symbol"], old["side"], old["qty"], old["price"]) != (self.mode, symbol, side, qty, limit):
            raise ValueError("This client reference belongs to a different ticket.")
        return old["status"] if old else None

    @staticmethod
    def _version(db):
        return db.execute("SELECT COALESCE(MAX(id),0) FROM audit WHERE category LIKE 'BROKER %'").fetchone()[0]

    def submit(self, request, pack, analysis):
        symbol, side = request["symbol"], request["side"]
        if not self.status()["configured"] or symbol not in SYMBOLS or side not in ("buy", "sell"):
            raise ValueError("Choose a supported instrument and a configured broker.")
        if request.get("confirmation") != f"{self.mode.upper()} {side.upper()} {symbol}":
            raise ValueError("The typed broker confirmation does not match this order.")
        qty, limit = float(request["qty"]), float(request["limit"])
        if not all(math.isfinite(x) and x > 0 for x in (qty, limit, qty * limit)):
            raise ValueError("Quantity and limit must be positive finite numbers.")
        ref = str(uuid.UUID(request["id"]))
        with self.ledger.db() as db:
            prior = self._prior(db, ref, symbol, side, qty, limit)
            if prior:
                return prior
            if db.execute("SELECT halted FROM account").fetchone()[0]:
                raise ValueError("Trading is halted.")
            version = self._version(db)
        if not pack["live"] or pack.get("stale") or (side == "buy" and analysis["veto"]):
            raise ValueError("Instrument source or entry risk gate blocks this order.")
        valuation = analysis.get("valuation")
        if side == "buy" and valuation and limit > valuation["target"]:
            raise ValueError("Buy limit exceeds the margin-of-safety entry ceiling.")
        ticker = SYMBOLS[symbol]
        crypto = "/" in ticker
        if not crypto and not qty.is_integer():
            raise ValueError("Use whole shares for these equity limit orders.")
        if not crypto and not self.transport("GET", "/v2/clock")["is_open"]:
            raise ValueError("The equity trading session is closed.")
        acct = self.account()
        if acct["blocked"] or acct["status"] != "ACTIVE":
            raise ValueError("Broker account is unavailable for trading.")
        pending = self.transport("GET", "/v2/orders?status=open&limit=500")
        if not isinstance(pending, list) or len(pending) >= 500:
            raise ValueError("The full open broker order list could not be verified.")
        normalized = ticker.replace("/", "")
        if any(o["symbol"].replace("/", "") == normalized for o in pending):
            raise ValueError("Resolve existing open broker orders for this instrument first.")
        remote_ids = {o.get("client_order_id") for o in pending}
        remote_reserved = sum(_remote_reserve(o) for o in pending) if side == "buy" else 0.0
        positions = self.transport("GET", "/v2/positions")
        held = next((p for p in positions if p["symbol"].replace("/", "") == normalized), {})
        position = float(held.get("qty", 0))
        if not math.isfinite(position) or position < 0:
            raise ValueError("Only verified long positions are supported.")
        if side == "sell" and qty > min(position, _nonnegative(held.get("qty_available", position), "available quantity")):
            raise ValueError("This ticket exceeds the available long position.")
        path = "v1beta3/crypto/us/latest/quotes" if crypto else "v2/stocks/quotes/latest"
        data = self.transport("GET", "/data/" + path + "?symbols=" + urllib.parse.quote(ticker, safe="")
                              + ("" if crypto else "&feed=iex"))
        with self.ledger.db() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = self._prior(db, ref, symbol, side, qty, limit)
            if prior:
                return prior
            if db.execute("SELECT halted FROM account").fetchone()[0]:
                raise ValueError("Trading is halted.")
            if self._version(db) != version:
                raise ValueError("Broker orders changed during preflight. Refresh and submit the ticket again.")
            local = [r for r in db.execute("SELECT * FROM broker_orders WHERE mode=?", (self.mode,)) if r["status"] not in _FINAL]
            if any(r["symbol"] == symbol for r in local):
                raise ValueError("Reconcile the previous broker ticket for this symbol first.")
            reserved = remote_reserved + sum(r["qty"] * r["price"] for r in local
                                             if r["side"] == "buy" and r["id"] not in remote_ids)
            bid, ask = _fresh_quote(data, ticker)
            reference = float(pack["bars"][-1]["close"])
            if not math.isfinite(reference) or reference <= 0 or abs((ask + bid) / 2 / reference - 1) > .02:
                raise ValueError("Broker and research prices disagree by more than 2%.")
            if abs(limit / (ask if side == "buy" else bid) - 1) > .02:
                raise ValueError("Limit must be within 2% of the current broker quote.")
            if side == "buy" and (qty * limit + reserved > acct["cash"]
                                  or (position + qty) * max(limit, ask) > acct["equity"] * .15):
                raise ValueError("Order exceeds unreserved cash or the 15% single-position limit.")
            db.execute("INSERT INTO broker_orders VALUES(?,?,?,?,?,?,?,?,?)",
                       (ref, time.time(), self.mode, symbol, side, qty, limit, "dispatch pending", ""))
            self.ledger._log(db, "BROKER TICKET", symbol, f"{self.mode.upper()} {side} {qty:g} limit {limit:g} · {ref}")
        body = {"symbol": ticker, "side": side, "qty": format(Decimal(str(qty)), "f"), "type": "limit",
                "time_in_force": "gtc" if crypto else "day", "limit_price": format(Decimal(str(limit)), "f"),
                "client_order_id": ref}
        try:
            response = self.transport("POST", "/v2/orders", body)
            return self.update(response, ref)
        except OrderRejected:
            with self.ledger.db() as db:
                db.execute("UPDATE broker_orders SET status='rejected' WHERE id=? AND status='dispatch pending'", (ref,))
                self.ledger._log(db, "BROKER REJECTED", symbol, ref)
            raise
        except Exception as err:
            raise ValueError(f"Submission status uncertain. Reconcile ticket {ref} before taking further action. {err}") from None
