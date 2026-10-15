"""Verify the web server and installed archive without production changes."""

from contextlib import redirect_stdout
from functools import partial
import io
import json
import os
from pathlib import Path
import select
import socket
import subprocess
import sys
import tempfile
from threading import Thread
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from http.server import ThreadingHTTPServer
from diskha.server.__main__ import WebHandler
from diskha.server.DrivePage import render_page
from test_install import installer


ROOT = Path(__file__).resolve().parents[1]


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), partial(WebHandler, request_timeout=15))
        cls.thread = Thread(target=cls.server.serve_forever)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.opener = build_opener(ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    @patch("diskha.server.DrivePage.read_drives", side_effect=OSError("not installed"))
    def test_page_and_head(self, usage):
        expected = render_page()
        with self.opener.open(self.url + "/?test=1", timeout=2) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), expected)
            self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        with self.opener.open(Request(self.url + "/", method="HEAD"), timeout=2) as response:
            self.assertEqual(int(response.headers["Content-Length"]), len(expected))
            self.assertEqual(response.read(), b"")

    def test_readiness_and_unknown_paths(self):
        with self.opener.open(self.url + "/ready", timeout=2) as response:
            self.assertEqual(json.load(response), {"ready": True})
        for path in ("/unknown", "/../constants/DDiskHA.py", "/conf/credentials.env"):
            with self.assertRaises(HTTPError) as raised:
                self.opener.open(self.url + path, timeout=2)
            self.assertEqual(raised.exception.code, 404)
            raised.exception.close()

    def test_health_output_link_get_and_head(self):
        with patch("diskha.server.DrivePage.read_drives", side_effect=OSError("not installed")):
            self.assertIn(b'<a href="/health/output">Most recent health check output</a>', render_page())
        with patch("diskha.server.__main__.render_health_output", return_value=b"<pre>health</pre>") as render:
            with self.opener.open(self.url + "/health/output", timeout=2) as response:
                self.assertEqual(response.read(), b"<pre>health</pre>")
                self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            with self.opener.open(Request(self.url + "/health/output", method="HEAD"), timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"")

    def test_logo_get_and_head(self):
        expected = (ROOT / "pages/images/diskha.png").read_bytes()
        with self.opener.open(self.url + "/static/diskha.png", timeout=2) as response:
            self.assertEqual(response.read(), expected)
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        with self.opener.open(Request(self.url + "/static/diskha.png", method="HEAD"), timeout=2) as response:
            self.assertEqual(int(response.headers["Content-Length"]), len(expected))
            self.assertEqual(response.read(), b"")

    @patch("diskha.server.__main__.select_drives", return_value={"source": {}, "target": {}})
    def test_directory_selection_requires_same_origin_and_only_directory_fields(self, select):
        body = b'{"source":"/disk1/archive/incoming/movies","target":"/disk2/inbox/media-center"}'
        for action in ("check", "save"):
            request = Request(self.url + "/drives/" + action, data=body,
                              headers={"Origin": self.url, "Content-Type": "application/json"})
            with self.opener.open(request, timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response), {"source": {}, "target": {}})
            select.assert_called_with("/disk1/archive/incoming/movies", "/disk2/inbox/media-center", save=action == "save")
        select.reset_mock()
        for data, headers, code in ((body, {"Content-Type": "application/json"}, 403),
                                    (body, {"Origin": "http://other.example", "Content-Type": "application/json"}, 403),
                                    (b'{}', {"Origin": self.url, "Content-Type": "application/json"}, 400),
                                    (b'[]', {"Origin": self.url, "Content-Type": "application/json"}, 400),
                                    (b'x' * 16385, {"Origin": self.url, "Content-Type": "application/json"}, 400),
                                    (body, {"Origin": self.url, "Content-Type": "text/plain"}, 400)):
            with self.assertRaises(HTTPError) as raised:
                self.opener.open(Request(self.url + "/drives/save", data=data, headers=headers), timeout=2)
            self.assertEqual(raised.exception.code, code)
            raised.exception.close()
        select.assert_not_called()
        for error, status in ((ValueError("Same physical drive"), 400), (OSError("worker active"), 503)):
            select.side_effect = error
            with self.assertRaises(HTTPError) as raised:
                self.opener.open(Request(self.url + "/drives/save", data=body,
                                        headers={"Origin": self.url, "Content-Type": "application/json"}), timeout=2)
            self.assertEqual(raised.exception.code, status)
            raised.exception.close()

    @patch("diskha.server.__main__.update_sync_schedule",
           return_value={"enabled": True, "expression": "0 */4 * * *"})
    def test_sync_schedule_update_and_output_page(self, update):
        body = b'{"enabled":true,"expression":"0 */4 * * *"}'
        request = Request(self.url + "/sync/schedule", data=body,
                          headers={"Origin": self.url, "Content-Type": "application/json"})
        with self.opener.open(request, timeout=2) as response:
            self.assertEqual(json.load(response)["expression"], "0 */4 * * *")
        update.assert_called_once_with(True, "0 */4 * * *")
        update.reset_mock()
        with self.assertRaises(HTTPError) as raised:
            self.opener.open(Request(self.url + "/sync/schedule", data=body,
                                    headers={"Origin": "http://other.example", "Content-Type": "application/json"}), timeout=2)
        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()
        update.assert_not_called()
        with patch("diskha.server.__main__.render_sync_output", return_value=iter([b"<pre>output", b"</pre>"])):
            with self.opener.open(self.url + "/sync/output", timeout=2) as response:
                self.assertEqual(response.read(), b"<pre>output</pre>")
                self.assertEqual(response.headers["Content-Type"], "text/html; charset=utf-8")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            with self.opener.open(Request(self.url + "/sync/output", method="HEAD"), timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.read(), b"")

    @patch("diskha.server.__main__.request_sync")
    def test_sync_now_requires_same_origin_empty_post_and_reports_failure(self, sync):
        with self.opener.open(Request(self.url + "/sync/run", data=b"",
                                      headers={"Origin": self.url}), timeout=2) as response:
            self.assertEqual(response.status, 202)
            self.assertIn(b"Sync requested", response.read())
        sync.assert_called_once_with()
        sync.reset_mock()
        for data, origin, code in ((b"", None, 403), (b"", "http://other.example", 403),
                                   (b"unexpected", self.url, 400)):
            headers = {} if origin is None else {"Origin": origin}
            with self.assertRaises(HTTPError) as raised:
                self.opener.open(Request(self.url + "/sync/run", data=data, headers=headers), timeout=2)
            self.assertEqual(raised.exception.code, code)
            raised.exception.close()
        sync.assert_not_called()
        with self.assertRaises(HTTPError) as raised:
            self.opener.open(self.url + "/sync/run", timeout=2)
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()
        sync.side_effect = OSError("service denied")
        with self.assertRaises(HTTPError) as raised:
            self.opener.open(Request(self.url + "/sync/run", data=b"",
                                    headers={"Origin": self.url}), timeout=2)
        self.assertEqual(raised.exception.code, 503)
        raised.exception.close()

    @patch("diskha.server.__main__.request_check")
    def test_manual_check_accepts_only_same_origin_post(self, check):
        with self.opener.open(Request(self.url + "/health/run", data=b"",
                                      headers={"Origin": self.url}), timeout=2) as response:
            self.assertEqual(response.status, 202)
        check.assert_called_once_with()
        check.reset_mock()
        for origin in (None, "http://other.example", "null", "http://[", self.url + "/other"):
            headers = {} if origin is None else {"Origin": origin}
            with self.assertRaises(HTTPError) as raised:
                self.opener.open(Request(self.url + "/health/run", data=b"", headers=headers), timeout=2)
            self.assertEqual(raised.exception.code, 403)
            raised.exception.close()
        check.assert_not_called()
        with self.assertRaises(HTTPError) as raised:
            self.opener.open(self.url + "/health/run", timeout=2)
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()

    @patch("diskha.server.__main__.request_check", side_effect=OSError("denied"))
    def test_manual_check_reports_start_failure(self, check):
        with self.assertRaises(HTTPError) as raised:
            self.opener.open(Request(self.url + "/health/run", data=b"",
                                      headers={"Origin": self.url}), timeout=2)
        self.assertEqual(raised.exception.code, 503)
        self.assertIn(b"Cannot start check", raised.exception.read())
        raised.exception.close()

    @patch("diskha.server.__main__.request_email_report")
    def test_email_report_requires_same_origin_post_and_reports_start_failure(self, email):
        with self.opener.open(Request(self.url + "/health/email-report", data=b"",
                                      headers={"Origin": self.url}), timeout=2) as response:
            self.assertEqual(response.status, 202)
            self.assertIn(b"report requested", response.read())
        email.assert_called_once_with()
        email.reset_mock()
        for origin in (None, "http://other.example"):
            headers = {} if origin is None else {"Origin": origin}
            with self.assertRaises(HTTPError) as raised:
                self.opener.open(Request(self.url + "/health/email-report", data=b"", headers=headers), timeout=2)
            self.assertEqual(raised.exception.code, 403)
            raised.exception.close()
        email.assert_not_called()
        with self.assertRaises(HTTPError) as raised:
            self.opener.open(self.url + "/health/email-report", timeout=2)
        self.assertEqual(raised.exception.code, 404)
        raised.exception.close()
        email.side_effect = OSError("permission denied")
        with self.assertRaises(HTTPError) as raised:
            self.opener.open(Request(self.url + "/health/email-report", data=b"",
                                      headers={"Origin": self.url}), timeout=2)
        self.assertEqual(raised.exception.code, 503)
        raised.exception.close()

    @patch("diskha.server.__main__.update_schedule",
           return_value={"enabled": True, "expression": "*/20 * * * *"})
    def test_schedule_update_and_validation_errors(self, update):
        def post(body, origin=None):
            return self.opener.open(Request(self.url + "/health/schedule", data=body,
                                           headers={"Origin": origin or self.url,
                                                    "Content-Type": "application/json"}), timeout=2)

        with post(b'{"enabled":true,"expression":"*/20 * * * *"}') as response:
            self.assertEqual(json.load(response), {"enabled": True, "expression": "*/20 * * * *"})
        update.assert_called_once_with(True, "*/20 * * * *")
        update.reset_mock()
        for body in (b"{", b"[]", b'{"enabled":true}', b"x" * 1025):
            with self.assertRaises(HTTPError) as raised:
                post(body)
            self.assertEqual(raised.exception.code, 400)
            raised.exception.close()
        update.assert_not_called()
        with self.assertRaises(HTTPError) as raised:
            post(b'{"enabled":true,"expression":"0 3 * * *"}', "http://other.example")
        self.assertEqual(raised.exception.code, 403)
        raised.exception.close()
        for error, status in ((ValueError("Invalid cron expression"), 400), (OSError("cron denied"), 503)):
            update.side_effect = error
            with self.assertRaises(HTTPError) as raised:
                post(b'{"enabled":true,"expression":"0 3 * * *"}')
            self.assertEqual(raised.exception.code, status)
            raised.exception.close()

    def test_packaged_server_serves_without_checkout(self):
        with tempfile.TemporaryDirectory(prefix="disk-ha-web-test-") as temporary:
            target = Path(temporary) / "prod"
            with patch.object(installer.DDiskHA, "INSTALL_DIR", str(target)), \
                    patch.object(installer.DDiskHA, "WEB_SERVICE_FILE", str(Path(temporary) / "service")), \
                    patch.object(installer.DDiskHA, "HEALTH_SERVICE_FILE", str(Path(temporary) / "health.service")), \
                    patch.object(installer.DDiskHA, "EMAIL_REPORT_SERVICE_FILE", str(Path(temporary) / "email.service")), \
                    patch.object(installer.DDiskHA, "SYNC_SERVICE_FILE", str(Path(temporary) / "sync.service")), \
                    patch.object(installer.DDiskHA, "HEALTH_SUDOERS_FILE", str(Path(temporary) / "sudoers")), \
                    patch.object(installer.subprocess, "run"), \
                    patch.object(installer.SystemAccount, "provision",
                                 return_value=SimpleNamespace(pw_uid=os.geteuid(), pw_gid=os.getegid())), \
                    patch.object(installer.DatabaseProvisioning, "provision"), \
                    patch.object(installer.HealthSchedule, "apply"), \
                    patch.object(installer.SyncSchedule, "apply"), \
                    patch.object(installer.os, "access", return_value=True), \
                    patch.object(installer, "systemctl"), patch.object(installer, "restart"), \
                    redirect_stdout(io.StringIO()):
                installer.install()
            archive = target / "bin/disk-ha-web"
            configuration = target / "conf/web-interface.cfg"
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            configuration.write_text(f"[web]\nhost = 127.0.0.1\nport = {port}\nrequest_timeout = 1\n")
            process = subprocess.Popen(
                [str(archive), "--config", str(configuration)],
                cwd=temporary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(select.select([process.stdout], [], [], 5)[0], "Startup timed out")
                self.assertIn(f"http://127.0.0.1:{port}/", process.stdout.readline())
                with self.opener.open(f"http://127.0.0.1:{port}/", timeout=2) as response:
                    page = response.read()
                    self.assertIn(b"Drive Configuration", page)
                    self.assertIn(b"Drive settings unavailable", page)
                    self.assertNotIn(b"{{disk", page)
                    self.assertIn(b'src="/static/diskha.png"', page)
                with self.opener.open(f"http://127.0.0.1:{port}/static/diskha.png", timeout=2) as response:
                    self.assertEqual(response.headers["Content-Type"], "image/png")
                    self.assertEqual(response.read(), (ROOT / "pages/images/diskha.png").read_bytes())
                # An incomplete request is closed using the configured socket timeout.
                with socket.create_connection(("127.0.0.1", port), timeout=3) as connection:
                    connection.sendall(b"GET /ready HTTP/1.1\r\n")
                    self.assertEqual(connection.recv(1), b"")
            finally:
                process.terminate()
                process.communicate(timeout=5)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                new_port = listener.getsockname()[1]
            configuration.write_text(f"[web]\nhost = localhost\nport = {new_port}\nrequest_timeout = 5\n")
            process = subprocess.Popen(
                [str(archive), "--config", str(configuration)],
                cwd=temporary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertTrue(select.select([process.stdout], [], [], 5)[0], "Restart timed out")
                self.assertIn(f"http://localhost:{new_port}/", process.stdout.readline())
                with self.opener.open(f"http://127.0.0.1:{new_port}/ready", timeout=2) as response:
                    self.assertEqual(json.load(response), {"ready": True})
            finally:
                process.terminate()
                process.communicate(timeout=5)
            process = subprocess.Popen(
                [sys.executable, str(archive), "--config", str(configuration),
                 "--host", "127.0.0.1", "--port", str(self.server.server_port)],
                cwd=temporary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            # An occupied port must fail, rather than report successful startup.
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 1)
            self.assertIn("disk-ha:", stderr)
            self.assertNotIn("Web UI:", stdout)
            process = subprocess.Popen(
                [sys.executable, "-u", str(archive), "--host", "127.0.0.1", "--port", "0"],
                cwd=temporary, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 2)
            self.assertIn("--port must be between", stderr)
            configuration.write_text("[web]\nhost = 127.0.0.1\nport = 0\nrequest_timeout = 15\n")
            result = subprocess.run([str(archive), "--config", str(configuration)],
                                    cwd=temporary, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertIn("Invalid web configuration", result.stderr)
            self.assertIn("port must be between", result.stderr)
            self.assertNotIn("Web UI:", result.stdout)
            configuration.unlink()
            result = subprocess.run([str(archive), "--config", str(configuration)],
                                    cwd=temporary, capture_output=True, text=True, timeout=5)
            self.assertEqual(result.returncode, 1)
            self.assertIn(str(configuration), result.stderr)
            self.assertNotIn("Traceback", result.stderr)


class ReadinessTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="disk-ha-readiness-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "conf").mkdir()
        self.configuration = self.root / "conf/web-interface.cfg"
        self.configuration.write_bytes((ROOT / "conf/web-interface.cfg").read_bytes())
        root = patch.object(installer, "installation_root", return_value=self.root)
        root.start()
        self.addCleanup(root.stop)

    def test_restart_checks_service_and_http_with_timeouts(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.status = 200
        with patch.object(installer, "systemctl") as control, \
                patch.object(installer, "build_opener", return_value=opener), redirect_stdout(io.StringIO()):
            installer.restart()
        control.assert_any_call("restart", "disk-ha-web.service")
        control.assert_any_call("is-active", "--quiet", "disk-ha-web.service")
        args, kwargs = opener.open.call_args
        self.assertEqual(args[0].full_url, "http://127.0.0.1:23300/ready")
        self.assertEqual(args[0].method, "HEAD")
        self.assertEqual(kwargs["timeout"], 1)

    def test_restart_checks_configured_host_and_port(self):
        self.configuration.write_text("[web]\nhost = 127.0.0.2\nport = 23400\nrequest_timeout = 30\n")
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.status = 200
        with patch.object(installer, "systemctl"), \
                patch.object(installer, "build_opener", return_value=opener), redirect_stdout(io.StringIO()):
            installer.restart()
        self.assertEqual(opener.open.call_args.args[0].full_url, "http://127.0.0.2:23400/ready")

    def test_invalid_configuration_prevents_restart(self):
        self.configuration.write_text("[web]\nport = 0\n")
        with patch.object(installer, "systemctl") as control:
            with self.assertRaisesRegex(ValueError, "Invalid web configuration"):
                installer.restart()
        control.assert_not_called()

    def test_unavailable_server_fails_after_deadline(self):
        opener = MagicMock()
        opener.open.side_effect = URLError("Connection refused")
        with patch.object(installer, "systemctl"), \
                patch.object(installer, "build_opener", return_value=opener), \
                patch.object(installer.time, "monotonic", side_effect=[0, 11]):
            with self.assertRaisesRegex(ValueError, "did not respond on port 23300"):
                installer.restart()


if __name__ == "__main__":
    unittest.main()
