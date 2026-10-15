"""Verify web configuration validation without reading installed settings."""

from pathlib import Path
import tempfile
import unittest

from diskha.interface.WebConfiguration import WebConfiguration


class WebConfigurationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="disk-ha-web-config-test-")
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / "web-interface.cfg"

    def test_settings_accept_addresses_and_hostnames(self):
        for host in ("0.0.0.0", "127.0.0.1", "localhost", "disk-ha.example.com"):
            with self.subTest(host=host):
                self.path.write_text(f"[web]\nhost = {host}\nport = 23400\nrequest_timeout = 30\n")
                configuration = WebConfiguration(self.path)
                self.assertEqual((configuration.host, configuration.port, configuration.request_timeout),
                                 (host, 23400, 30))

    def test_invalid_values_identify_the_configuration_file(self):
        settings = {"host": "0.0.0.0", "port": "23300", "request_timeout": "15"}
        for field, value in (("host", ""), ("host", "256.1.1.1"), ("host", "http://localhost"),
                             ("host", "::1"), ("host", "bad host"), ("port", "0"), ("port", "65536"),
                             ("port", "abc"), ("request_timeout", "0"), ("request_timeout", "-1"),
                             ("request_timeout", "1.5"), ("request_timeout", "inf")):
            with self.subTest(field=field, value=value):
                values = settings | {field: value}
                self.path.write_text("[web]\n" + "".join(f"{key} = {item}\n" for key, item in values.items()))
                with self.assertRaises(ValueError) as raised:
                    WebConfiguration(self.path)
                self.assertIn(str(self.path), str(raised.exception))

    def test_missing_unknown_and_duplicate_fields_fail(self):
        valid = "[web]\nhost = 0.0.0.0\nport = 23300\nrequest_timeout = 15\n"
        for content in ("", "not an INI file", valid.replace("port = 23300\n", ""),
                        valid + "unknown = 1\n", valid + "port = 23400\n",
                        valid + "[other]\nvalue = 1\n", "[DEFAULT]\nvalue = 1\n" + valid):
            with self.subTest(content=content):
                self.path.write_text(content)
                with self.assertRaisesRegex(ValueError, "Invalid web configuration"):
                    WebConfiguration(self.path)


if __name__ == "__main__":
    unittest.main()
