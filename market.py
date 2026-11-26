"""Meridian Desk market data. Public quotes, historical candles and MT5 log import."""
from __future__ import annotations

import codecs
import copy
import hashlib
import json
import math
import random
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

SYMBOLS = {
    "BTC-USD": "Bitcoin / US Dollar",
    "ETH-USD": "Ether / US Dollar",
    "SPY": "SPDR S&P 500 ETF",
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft",
    "EURUSD=X": "Euro / US Dollar",
    "GC=F": "COMEX Gold Futures",
    "DEMO": "Meridian Sample Equity",
}
_KRAKEN = {"BTC-USD": "XBTUSD", "ETH-USD": "ETHUSD"}
_DEMO_LEVEL = dict(zip(SYMBOLS, (62000, 2250, 585, 207, 439, 1.09, 2770, 80)))
_CACHE = {}
_HISTORY = {}
_RETRIES = {}
_TICKS = {}
_FORMING = {}
_CLOCKS = {}
_LOCK = threading.RLock()
_STOP = threading.Event()
_THREAD = None
_WS = None


class FeedUnavailable(RuntimeError):
    """The public endpoints could not supply valid price history."""


def _json(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MeridianDesk/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as response:
            data = response.read(4_000_001)
            date = response.headers.get("Date")
            if date:
                try:
                    server_time = parsedate_to_datetime(date).timestamp() + int(response.headers.get("Age", 0))
                    _record_clock(urllib.parse.urlsplit(url).hostname, server_time)
                except (ValueError, OverflowError, TypeError):
                    pass
        if len(data) > 4_000_000:
            raise FeedUnavailable("Response exceeded the market-feed size limit")
        return json.loads(data)
    except (ValueError, OSError, urllib.error.URLError) as err:
        raise FeedUnavailable(str(err)) from err


def _record_clock(venue, utc):
    # Only allow a bounded clock correction. Never move a feed clock backwards.
    if abs(utc - time.time()) <= 900:
        with _LOCK:
            old = _CLOCKS.get(venue)
            monotonic = time.monotonic()
            if old is None or utc >= old[0] + monotonic - old[1] - 2:
                _CLOCKS[venue] = (utc, monotonic)


def _venue_now(venue):
    with _LOCK:
        clock = _CLOCKS.get(venue)
        heartbeat = _CLOCKS.get((venue, "websocket"))
    if heartbeat:
        # A heartbeat and trade come from the same exchange stream. The REST CDN
        # may use a different clock; it must never supersede the stream's clock.
        elapsed = time.monotonic() - heartbeat[1]
        if 0 <= elapsed <= 15:
            return heartbeat[0] + elapsed
    if clock:
        elapsed = time.monotonic() - clock[1]
        if elapsed <= 180:
            # Old CDN response dates cannot make delayed observations appear fresh.
            return max(time.time(), clock[0] + elapsed)
    return time.time()


def _bar(timestamp, open_, high, low, close, volume):
    try:
        stamp = int(timestamp)
        op, hi, lo, cl, vol = map(float, (open_, high, low, close, volume or 0))
    except (TypeError, ValueError, OverflowError):
        return None
    if not all(math.isfinite(x) for x in (op, hi, lo, cl, vol)):
        return None
    if stamp <= 0 or lo <= 0 or vol < 0 or lo > min(op, cl) or hi < max(op, cl):
        return None
    return {"time": stamp, "open": op, "high": hi, "low": lo, "close": cl, "volume": vol}


def _payload(rows, source, interval="5m", session="24/7"):
    valid = {r["time"]: r for r in rows if r is not None}
    bars = [valid[k] for k in sorted(valid)]
    if len(bars) < 2:
        raise FeedUnavailable("The provider returned fewer than two usable OHLC observations")
    return {"bars": bars, "source": source, "live": True, "asof": bars[-1]["time"],
            "interval": interval, "session": session, "transport": "REST", "stale": False}


def _coinbase(symbol):
    rows = _json(f"https://api.exchange.coinbase.com/products/{symbol}/candles?granularity=300")
    if not isinstance(rows, list):
        raise FeedUnavailable("Coinbase candles unavailable")
    bars = (_bar(r[0], r[3], r[2], r[1], r[4], r[5]) for r in rows
            if isinstance(r, list) and len(r) >= 6)
    result = _payload(bars, "Coinbase Exchange · 5m bars")
    result["venue"] = "api.exchange.coinbase.com"
    return result


def _kraken(symbol):
    data = _json(f"https://api.kraken.com/0/public/OHLC?pair={_KRAKEN[symbol]}&interval=5")
    if not isinstance(data, dict) or data.get("error"):
        raise FeedUnavailable("Kraken candles unavailable")
    rows = next((v for k, v in data.get("result", {}).items() if k != "last"), [])
    result = _payload((_bar(r[0], r[1], r[2], r[3], r[4], r[6]) for r in rows
                     if isinstance(r, list) and len(r) >= 7), "Kraken · 5m bars")
    result["venue"] = "api.kraken.com"
    return result


def _parse_yahoo(data, interval, now):
    chart = data.get("chart") or {}
    if chart.get("error") or not chart.get("result"):
        raise FeedUnavailable("Yahoo Finance did not return a chart")
    result = chart["result"][0]
    quotes = (result.get("indicators", {}).get("quote") or [{}])[0]
    timestamps = result.get("timestamp") or []
    rows = zip(timestamps, *(quotes.get(k) or [] for k in ("open", "high", "low", "close")),
               quotes.get("volume") or [0] * len(timestamps))
    periods = result.get("meta", {}).get("currentTradingPeriod") or {}
    session = next((name.capitalize() for name in ("regular", "pre", "post")
                    if (periods.get(name) or {}).get("start", now + 1) <= now
                    < (periods.get(name) or {}).get("end", 0)), "Outside reported session")
    return _payload((_bar(*r) for r in rows), "Yahoo Finance · indicative / may be delayed",
                    interval, session)


def _yahoo(symbol, host="query1", span="5d", interval="5m"):
    ticker = urllib.parse.quote(symbol, safe="")
    args = urllib.parse.urlencode({"interval": interval, "range": span,
                                   "includePrePost": "true" if interval != "1d" else "false"})
    url = f"https://{host}.finance.yahoo.com/v8/finance/chart/{ticker}?{args}"
    venue = urllib.parse.urlsplit(url).hostname
    raw = _json(url)
    result = _parse_yahoo(raw, interval, _venue_now(venue))
    result["venue"] = venue
    return result


def demo_bars(symbol="DEMO", *, now=None, daily=False):
    """Repeatable synthetic series anchored to absolute bar times, including overlapping refreshes."""
    if symbol not in SYMBOLS:
        raise ValueError("Unknown instrument")
    now = float(time.time() if now is None else now)
    step = 86400 if daily else 300
    count = 1095 if daily else 330
    last = int(now) // step
    seed = int.from_bytes(hashlib.sha256(symbol.encode()).digest()[:8], "big")
    level = _DEMO_LEVEL[symbol]
    wave = 0.06 if daily else 0.018

    def price(i):
        noise = random.Random(i ^ seed).gauss(0, wave * 0.12)
        return level * math.exp(wave * (math.sin(i / 31) + 0.6 * math.sin(i / 9)) + noise)

    bars = []
    previous = price(last - count)
    for i in range(last - count + 1, last + 1):
        close = price(i)
        rng = random.Random((seed + i) ^ 0x9FA3)
        wiggle = rng.uniform(0.0004, wave * 0.2)
        bars.append(_bar(i * step, previous, max(previous, close) * (1 + wiggle),
                         min(previous, close) * (1 - wiggle), close, rng.randrange(110, 18000)))
        previous = close
    return {"bars": bars, "source": "Synthetic fixture · simulated prices", "live": False,
            "asof": last * step, "interval": "1d" if daily else "5m", "stale": False,
            "session": "Simulation", "transport": "SIMULATION", "age_seconds": 0}


def _load_candidates(candidates):
    errors = []
    for load in candidates:
        try:
            return load()
        except (FeedUnavailable, ValueError, TypeError, IndexError, AttributeError, KeyError) as err:
            errors.append(str(err))
    raise FeedUnavailable("Market data unavailable: " + " / ".join(errors))


def _retry_seconds(attempt):
    return min(30, 2 ** min(5, max(0, attempt - 1)) * random.uniform(0.85, 1.15))


def _with_latest(symbol, payload, *, error=None):
    data = copy.deepcopy(payload)
    with _LOCK:
        tick = dict(_TICKS.get(symbol, {}))
        forming = dict(_FORMING.get(symbol, {}))
    now = _venue_now(data.get("venue"))
    if tick and not error and data["source"].startswith("Coinbase"):
        ts = tick["time"]
        if data["asof"] <= ts <= now + 2 and max(now - ts, time.monotonic() - tick["received"]) <= 15:
            bucket = int(ts) // 300 * 300
            last = data["bars"][-1]
            price = tick["price"]
            if forming and forming["time"] == bucket:
                if bucket > last["time"]:
                    data["bars"].append(forming)
                elif bucket == last["time"]:
                    # The REST and ticker windows overlap. Keep a lower bound on in-progress
                    # volume to avoid counting trades twice. REST reconciles the finished bar.
                    last.update(close=price, high=max(last["high"], forming["high"]),
                                low=min(last["low"], forming["low"]),
                                volume=max(last["volume"], forming["volume"]))
            data["partial_bar"] = True
            data.update(asof=ts, bid=tick["bid"], ask=tick["ask"], transport="WebSocket",
                        source="Coinbase Exchange · live ticker + 5m bars")
    max_age = 15 if data["transport"] == "WebSocket" else 600
    age = max(0.0, now - data["asof"])
    if data["transport"] == "WebSocket":
        age = max(age, time.monotonic() - tick["received"])
    data["age_seconds"] = round(age, 2)
    data["stale"] = bool(error or age > max_age or data["asof"] > now + 2)
    if error:
        data["error"] = error
        data["transport"] = "CACHED"
    return data


def fetch_bars(symbol):
    """Public intraday snapshots. On outages, keep a cached source visibly stale."""
    if symbol not in SYMBOLS:
        raise ValueError("Unknown instrument")
    if symbol == "DEMO":
        return demo_bars(symbol)
    now = time.monotonic()
    with _LOCK:
        old = _CACHE.get(symbol)
        retry = _RETRIES.get(symbol)
    if retry and now < retry[1]:
        if old:
            return _with_latest(symbol, old[1], error=retry[2])
        raise FeedUnavailable(retry[2])
    if old and now - old[0] < (15 if symbol in _KRAKEN else 45):
        return _with_latest(symbol, old[1])
    candidates = ((lambda: _coinbase(symbol), lambda: _kraken(symbol)) if symbol in _KRAKEN
                  else (lambda: _yahoo(symbol), lambda: _yahoo(symbol, "query2")))
    try:
        data = _load_candidates(candidates)
    except FeedUnavailable as err:
        attempt = (retry[0] if retry else 0) + 1
        with _LOCK:
            _RETRIES[symbol] = (attempt, now + _retry_seconds(attempt), str(err))
        if old:
            return _with_latest(symbol, old[1], error=str(err))
        raise
    with _LOCK:
        _RETRIES.pop(symbol, None)
        _CACHE[symbol] = (now, data)
    return _with_latest(symbol, data)


def fetch_history(symbol):
    """Five-year provider OHLC (excludes dividend reinvestment) from Yahoo, or three years of explicit demo data."""
    if symbol not in SYMBOLS:
        raise ValueError("Unknown instrument")
    if symbol == "DEMO":
        return demo_bars(symbol, daily=True)
    now = time.monotonic()
    with _LOCK:
        old = _HISTORY.get(symbol)
        if old and now - old[0] < 3600:
            return copy.deepcopy(old[1])
    data = _load_candidates([lambda: _yahoo(symbol, "query1", "5y", "1d"),
                             lambda: _yahoo(symbol, "query2", "5y", "1d")])
    with _LOCK:
        _HISTORY[symbol] = (now, data)
    return copy.deepcopy(data)


def _tick(message):
    if message.get("type") == "heartbeat":
        utc = datetime.fromisoformat(message["time"].replace("Z", "+00:00")).timestamp()
        _record_clock(("api.exchange.coinbase.com", "websocket"), utc)
        return
    if message.get("type") != "ticker" or message.get("product_id") not in _KRAKEN:
        return
    price, bid, ask = (float(message[k]) for k in ("price", "best_bid", "best_ask"))
    ts = datetime.fromisoformat(message["time"].replace("Z", "+00:00")).timestamp()
    if not all(math.isfinite(v) and v > 0 for v in (ts, price, bid, ask)) or bid > ask:
        return
    symbol = message["product_id"]
    trade_id = int(message.get("trade_id", 0))
    size = float(message.get("last_size", 0))
    if size < 0 or not math.isfinite(size):
        return
    with _LOCK:
        previous = _TICKS.get(symbol, {})
        if ts < previous.get("time", 0) or (trade_id and trade_id <= previous.get("trade_id", 0)):
            return
        _TICKS[symbol] = {"time": ts, "price": price, "bid": bid, "ask": ask,
                          "received": time.monotonic(), "trade_id": trade_id}
        bucket = int(ts) // 300 * 300
        forming = _FORMING.get(symbol)
        if forming is None or bucket != forming["time"]:
            _FORMING[symbol] = _bar(bucket, price, price, price, price, size)
        else:
            forming.update(high=max(forming["high"], price), low=min(forming["low"], price),
                           close=price, volume=forming["volume"] + size)


def _stream():
    global _WS
    # Project-local dependency installed on E: with its license and distribution metadata.
    path = str(Path(__file__).resolve().parent / "runtime" / "feeddeps")
    if path not in sys.path:
        sys.path.insert(0, path)
    try:
        import websocket
    except ImportError:
        return  # REST feed remains operational on an installation lacking this dependency.
    attempt = 0
    while not _STOP.is_set():
        conn = None
        try:
            conn = websocket.create_connection("wss://ws-feed.exchange.coinbase.com",
                                               timeout=5, suppress_origin=True)
            with _LOCK:
                _WS = conn
            conn.send(json.dumps({"type": "subscribe", "product_ids": list(_KRAKEN),
                                  "channels": ["ticker", "heartbeat"]}))
            while not _STOP.is_set():
                item = json.loads(conn.recv())
                if item.get("type") == "error":
                    raise FeedUnavailable(str(item.get("message", "Subscription error")))
                _tick(item)
                if item.get("type") == "ticker":
                    attempt = 0
        except (OSError, websocket.WebSocketException, FeedUnavailable, ValueError, KeyError, TypeError):
            attempt += 1
        finally:
            with _LOCK:
                _WS = None
                _TICKS.clear()
                _FORMING.clear()
            if conn is not None:
                try:
                    conn.close(timeout=1)
                except (OSError, websocket.WebSocketException):
                    conn.shutdown()
        if _STOP.wait(_retry_seconds(attempt)):
            break


def start_live():
    """Start one daemon subscriber. REST histories are retrieved on demand."""
    global _THREAD
    with _LOCK:
        if _THREAD is None or not _THREAD.is_alive():
            _STOP.clear()
            _THREAD = threading.Thread(target=_stream, name="Coinbase ticker", daemon=True)
            _THREAD.start()


def stop_live():
    _STOP.set()
    with _LOCK:
        conn, thread = _WS, _THREAD
    if conn is not None:
        try:
            conn.shutdown()
        except OSError:
            pass
    if thread and thread is not threading.current_thread():
        thread.join(timeout=6)


def read_mt5_report(path):
    """Extract the most recent complete EA report from a plain text export or MT5 Experts log."""
    file = Path(path)
    with file.open("rb") as handle:
        head = handle.read(100)
        size = handle.seek(0, 2)
        start = max(0, size - 8 * 1024 * 1024)
        handle.seek(start - start % 2)
        raw = handle.read()
    if head.startswith(codecs.BOM_UTF16_LE) or head[1::2].count(0) > 12:
        encoding = "utf-16-le"
    elif head.startswith(codecs.BOM_UTF16_BE) or head[::2].count(0) > 12:
        encoding = "utf-16-be"
    else:
        encoding = "utf-8-sig"
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace") if encoding == "utf-8-sig" else raw.decode(encoding, "replace")
    candidates = text.split("APEX-FX SIGNAL REPORT")
    for report in reversed(candidates[1:]):
        # MT5 prefixes tab-separated facility, level, time, and source on individual log records.
        lines = [line.rsplit("\t", 1)[-1].strip("\ufeff\r") for line in report.splitlines()[:100]]
        end = next((i for i, line in enumerate(lines) if re.match(r"^\s*DISCLAIMER\s*:", line)), None)
        if end is None:
            continue
        body = "\n".join(lines[:end + 1]).strip()
        if all(re.search(r"^\s*" + term + r"\s*:", body, re.MULTILINE)
               for term in ("CONFLUENCE SCORE", "PAIR", "DIRECTION", "TIMESTAMP", "RISK FLAGS")):
            return "APEX-FX SIGNAL REPORT\n" + body
    raise ValueError("No complete APEX-FX SIGNAL REPORT in the last 8 MiB of this file. "
                     "Choose an MT5 Experts log or the EA's exported report text.")
