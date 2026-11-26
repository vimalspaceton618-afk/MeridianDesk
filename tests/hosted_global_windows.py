"""Hosted Windows UI fixture for research-only global explorer acceptance.

Uses a temporary SQLite account and explicitly synthetic market observations.
Never starts the actual market watchers, broker, external models, or paid services.
"""
import atexit
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import market
from desk import Desk,serve

if os.getenv("MERIDIAN_BROKER")!="off" or os.getenv("APCA_API_KEY_ID") or os.getenv("APCA_API_SECRET_KEY"):
    raise RuntimeError("Windows hosted UI acceptance requires broker OFF and empty secrets")

def fixture_fetch(symbol):
    if symbol!="7203.T":
        raise market.FeedUnavailable("Hosted test does not request real market data")
    pack=market.demo_bars("DEMO")
    pack.update(source="SYNTHETIC TEST FIXTURE - NOT REAL TOYOTA PRICES",
                currency="JPY",transport="FIXTURE",session="Simulation",
                live=False,stale=False)
    return pack

market.fetch_bars=fixture_fetch
tmp=tempfile.TemporaryDirectory(prefix="meridian-global-windows-")
atexit.register(tmp.cleanup)
desk=Desk(Path(tmp.name)/"demo.sqlite3",verification=True)
token=secrets.token_urlsafe(32)
server=serve(desk,token)
print(f"READY http://127.0.0.1:{server.server_port}/#{token}~verify",flush=True)

def stop_on_stdin():
    sys.stdin.readline()
    server.shutdown()

threading.Thread(target=stop_on_stdin,daemon=True).start()
try:
    server.serve_forever(poll_interval=.1)
finally:
    server.server_close()
    desk.stop()
