"""Verify saved health output is readable and safe to display."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from diskha.server.HealthPage import render_health_output


class HealthPageTests(unittest.TestCase):
    def test_saved_results_show_raw_output_and_escape_external_text(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = Path(temporary) / "health.json"
            with patch("diskha.server.HealthPage.DDiskHA.HEALTH_RESULT", str(result)):
                for problems in ([], ["Degraded"], ["SMART overall health failed."],
                                 ["SMART overall health result is unavailable."]):
                    with self.subTest(problems=problems):
                        result.write_text(json.dumps({
                            "checked_at": "2026-10-15T14:00:00-04:00",
                            "disks": [{"disk": {"device_path": f"/dev/disk/by-id/ata-{number}"},
                                       "problems": problems if number == 1 else [],
                                       "smart_output": f"SMART {number} <script>alert(1)</script>"}
                                      for number in (1, 2)],
                            "notification_error": "Delivery failed <error>"}))
                        page = render_health_output()
                        self.assertIn(b"2026-10-15T14:00:00-04:00", page)
                        self.assertIn(b"Overall result: FAIL" if problems else b"Overall result: PASS", page)
                        for number in (1, 2):
                            self.assertIn(f"SMART {number} &lt;script&gt;".encode(), page)
                        for problem in problems:
                            self.assertIn(f"FAIL: {problem}".encode(), page)
                        self.assertIn(b"Notification failure: Delivery failed &lt;error&gt;", page)
                        self.assertNotIn(b"<script>", page)

    def test_missing_corrupt_and_unreadable_results(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = Path(temporary) / "health.json"
            with patch("diskha.server.HealthPage.DDiskHA.HEALTH_RESULT", str(result)):
                self.assertIn(b"No health check recorded.", render_health_output())
                result.write_text("invalid json")
                self.assertIn(b"Health results unavailable.", render_health_output())
                with patch("diskha.server.HealthPage.HealthResult.read", side_effect=PermissionError):
                    self.assertIn(b"Health results unavailable.", render_health_output())
