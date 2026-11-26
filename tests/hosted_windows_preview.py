"""Ephemeral, offline source-checkout server for hosted Windows UI capture.

No production user database, bundled model workers, network market fetches,
or broker connection. Only synthetic DEMO state can be used for fills.
"""
import atexit
import os
from pathlib import Path
import secrets
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from desk import Desk, serve  # noqa: E402

if os.getenv("MERIDIAN_BROKER", "").lower() != "off":
    raise RuntimeError("Hosted preview requires MERIDIAN_BROKER=off")
if os.getenv("APCA_API_KEY_ID") or os.getenv("APCA_API_SECRET_KEY"):
    raise RuntimeError("Hosted preview requires empty broker credentials")

temp = tempfile.TemporaryDirectory(prefix="meridian-hosted-preview-")
atexit.register(temp.cleanup)
desk = Desk(Path(temp.name) / "preview.sqlite3", verification=True)
# Emit private URL to parent process ONLY. The screenshot and logs must not copy it.
token = secrets.token_urlsafe(32)
server = serve(desk, token)
print("READY " + f"http://127.0.0.1:{server.server_port}/#{token}~verify", flush=True)
try:
    server.serve_forever(poll_interval=0.1)
finally:
    server.server_close()
    desk.stop()
