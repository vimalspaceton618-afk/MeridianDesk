"""Regression for first-run MT5 log import on a clean source checkout.

The report import is local-only: no trade dispatch, broker credentials, network
requests or bundled Windows runtime are required.
"""
import base64
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import desk


class Mt5ImportCleanCheckoutTests(unittest.TestCase):
    def test_creates_missing_temp_directory_and_removes_report_files(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent / "tests") as directory:
            root = Path(directory)
            report = ("APEX-FX SIGNAL REPORT\n"
                      "CONFLUENCE SCORE: 7/10\n"
                      "PAIR: EURUSD\n"
                      "DIRECTION: LONG\n"
                      "TIMESTAMP: 2026.11.25 16:00:00 UTC\n"
                      "RISK FLAGS: None active\n"
                      "DISCLAIMER: simulation only.\n")
            fixture = base64.b64encode(report.encode("utf-8")).decode("ascii")
            with patch.dict(os.environ, {"MERIDIAN_BROKER": "off",
                                          "APCA_API_KEY_ID": "", "APCA_API_SECRET_KEY": ""}), \
                 patch.object(desk, "ROOT", root):
                app = desk.Desk(root / "account.sqlite3", verification=True)
                try:
                    self.assertFalse((root / "cache" / "temp").exists(),
                                     "Fixture must reproduce a clean installation")
                    with patch.object(app.broker, "transport",
                                      side_effect=AssertionError("No broker contact permitted")):
                        result = app.action("/api/mt5", {"content": fixture})
                    self.assertIn("PAIR: EURUSD", result["report"])
                    self.assertTrue(any(event["category"] == "MT5 IMPORT"
                                        for event in app.ledger.recent()))
                    self.assertTrue((root / "cache" / "temp").is_dir())
                    self.assertFalse(list((root / "cache" / "temp").glob("*.log")),
                                     "Imported plaintext should be deleted")
                    with self.assertRaisesRegex(ValueError, "No complete"):
                        app.action("/api/mt5", {"content": base64.b64encode(b"invalid").decode()})
                    self.assertFalse(list((root / "cache" / "temp").glob("*.log")),
                                     "Invalid reports should not leave plaintext files")
                finally:
                    app.stop()


if __name__ == "__main__":
    unittest.main()
