"""Integration contract tests. All data, model execution and HTTP fixtures stay on this machine."""
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import integrations

BARS = [dict(time=1690000000 + 60 * i, open=100 + i * .1, high=102 + i * .1,
             low=99 + i * .1, close=101 + i * .1, volume=20) for i in range(64)]


class LocalModelFixture(BaseHTTPRequestHandler):
    """Expose one canned completion through the real upstream provider transport."""
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if self.path != "/v1/chat/completions" or body["model"] != "fixture":
            self.send_error(400)
            return
        self.server.seen.append(body)
        chunks = []
        for delta, finish in [({"role": "assistant", "content": "Fixture transport accepted."}, None), ({}, "stop")]:
            chunks.append({"id": "test", "object": "chat.completion.chunk", "created": 1690001000,
                           "model": "fixture", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]})
        payload = ("".join("data: " + json.dumps(p) + "\n\n" for p in chunks) + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


class Integrations(unittest.TestCase):
    def test_rejects_bad_market_data(self):
        for rows in [BARS + BARS[-1:], BARS[:-1] + [dict(BARS[-1], close=float("nan"))], BARS[:8]]:
            with self.assertRaises(ValueError):
                integrations._validated("TEST", rows)

    def test_ruflo_coordinates_real_four_task_review(self):
        report = integrations.run_integration("ruflo", "TEST", BARS)
        self.assertIn("Ruflo completed 4 assigned tasks", report)
        self.assertIn("Peak-to-trough drawdown 0.000%", report)

    def test_kronos_real_cpu_worker(self):
        report = integrations.run_integration("kronos", "TEST", BARS)
        self.assertIn("Kronos-mini", report)
        self.assertIn("Model close", report)
        self.assertIn("64 bars", report)

    def test_tradingagents_source_build_with_local_provider(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), LocalModelFixture)
        server.seen = []
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            env = {key: "" for key in integrations.PROVIDER_KEYS}
            env.update(TRADINGAGENTS_BASE_URL=f"http://127.0.0.1:{server.server_port}/v1",
                       TRADINGAGENTS_MODEL="fixture", TRADINGAGENTS_MODEL_API_KEY="",
                       NO_PROXY="127.0.0.1,localhost", TRADINGAGENTS_SYNC="off")
            with tempfile.TemporaryDirectory(dir=integrations.BASE / "cache" / "temp") as home, \
                    patch.object(integrations, "TA_HOME", Path(home)), patch.dict(integrations.os.environ, env):
                report = integrations.run_integration("tradingagents", "TEST", BARS)
            self.assertIn("Fixture transport accepted.", report)
            self.assertTrue(server.seen)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)


if __name__ == "__main__":
    unittest.main()
