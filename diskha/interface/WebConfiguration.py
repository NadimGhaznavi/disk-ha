"""Load and validate web interface startup settings."""

from configparser import ConfigParser, Error
from ipaddress import IPv4Address
from pathlib import Path
import re


class WebConfiguration:
    def __init__(self, path: Path):
        configuration = ConfigParser(interpolation=None)
        try:
            with path.open(encoding="utf-8") as stream:
                configuration.read_file(stream)
            if (configuration.sections() != ["web"] or configuration.defaults()
                    or set(configuration["web"]) != {"host", "port", "request_timeout"}):
                raise ValueError("Provide only host, port, and request_timeout in the [web] section.")
            self.host = configuration["web"]["host"]
            try:
                IPv4Address(self.host)
            except ValueError:
                if (not self.host or len(self.host) > 253
                        or all(character in "0123456789." for character in self.host)
                        or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                                   for label in self.host.rstrip(".").split("."))):
                    raise ValueError("host must be an IPv4 address or hostname.") from None
            self.port = configuration.getint("web", "port")
            if not 1 <= self.port <= 65535:
                raise ValueError("port must be between 1 and 65535.")
            self.request_timeout = configuration.getint("web", "request_timeout")
            if not 1 <= self.request_timeout <= 2147483647:
                raise ValueError("request_timeout must be a positive integer of at most 2147483647 seconds.")
        except (Error, ValueError, UnicodeError) as error:
            raise ValueError(f"Invalid web configuration {path}: {error}") from None
