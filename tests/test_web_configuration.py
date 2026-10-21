"""Verify CMDB listener defaults and production override validation."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from diskha.constants.DDiskHA import DDiskHA
from diskha.interface.WebConfiguration import WebConfiguration
from diskha.server.__main__ import main


class WebConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="disk-ha-web-config-test-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "diskha.json"

    def test_missing_file_uses_declaration(self):
        with patch.object(DDiskHA, "CMDB_NETWORK", (("http", "127.0.0.2", 23400),)):
            configuration = WebConfiguration(self.path)
        self.assertEqual((configuration.host, configuration.port), ("127.0.0.2", 23400))
        self.assertEqual(configuration.network.destination("http"), ("127.0.0.2", 23400))
        self.assertEqual(configuration.request_timeout, 15)

    def test_partial_overrides_and_local_destinations(self):
        for overrides, expected in (({}, ("0.0.0.0", 23300)),
                                    ({"port": 23400}, ("0.0.0.0", 23400)),
                                    ({"interface": "127.0.0.2"}, ("127.0.0.2", 23300))):
            with self.subTest(overrides=overrides):
                self.path.write_text(json.dumps({"network": {"http": overrides}, "request_timeout": 30}))
                configuration = WebConfiguration(self.path)
                self.assertEqual(configuration.network.binding("http"), expected)
                host = "127.0.0.1" if expected[0] == "0.0.0.0" else expected[0]
                self.assertEqual(configuration.network.destination("http"), (host, expected[1]))
                self.assertEqual(configuration.request_timeout, 30)
                self.path.write_text(json.dumps(configuration.settings()))
                self.assertEqual(WebConfiguration(self.path).settings(), configuration.settings())

    def test_server_uses_resolved_defaults_and_cli_overrides(self):
        self.path.write_text('{"network":{"http":{"port":23401}}}')
        for arguments, expected in (([], ("127.0.0.2", 23401)),
                                    (["--host", "127.0.0.1", "--port", "23402"],
                                     ("127.0.0.1", 23402))):
            with self.subTest(arguments=arguments), \
                    patch.object(DDiskHA, "CMDB_NETWORK", (("http", "127.0.0.2", 23400),)), \
                    patch("sys.argv", ["disk-ha-web", "--config", str(self.path), *arguments]), \
                    patch("diskha.server.__main__.ThreadingHTTPServer") as server:
                server.return_value.__enter__.side_effect = KeyboardInterrupt
                main()
                self.assertEqual(server.call_args.args[0], expected)

    def test_invalid_values_identify_the_configuration_file(self):
        invalid = [[], None, {"unknown": 1}, {"network": []}, {"network": {"backend": {}}},
                   {"network": {"http": []}}, {"network": {"http": {"host": "127.0.0.1"}}}]
        invalid += [{"network": {"http": {"interface": value}}}
                    for value in (None, True, 123, "localhost", "::1", "256.1.1.1", "")]
        invalid += [{"network": {"http": {"port": value}}}
                    for value in (None, True, 0, 65536, "23300", 23300.0)]
        invalid += [{"request_timeout": value} for value in (None, True, 0, -1, 1.5, "15", 2147483648)]
        for settings in invalid:
            with self.subTest(settings=settings):
                self.path.write_text(json.dumps(settings))
                with self.assertRaises(ValueError) as raised:
                    WebConfiguration(self.path)
                self.assertIn(str(self.path), str(raised.exception))

    def test_malformed_json_and_ini_are_rejected(self):
        for content in ("", "{", "[web]\nhost = 0.0.0.0\nport = 23300\n"):
            with self.subTest(content=content):
                self.path.write_text(content)
                with self.assertRaisesRegex(ValueError, "Invalid web configuration"):
                    WebConfiguration(self.path)


if __name__ == "__main__":
    unittest.main()
