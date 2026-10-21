"""Read web settings once and resolve declared network defaults."""

import json
from pathlib import Path

from diskha.interface.Network import Network


class WebConfiguration:
    def __init__(self, path: Path):
        try:
            try:
                settings = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                settings = {}
            if not isinstance(settings, dict) or set(settings) - {"network", "request_timeout"}:
                raise ValueError("Provide only network and request_timeout settings.")
            self.request_timeout = settings.get("request_timeout", 15)
            if type(self.request_timeout) is not int or not 1 <= self.request_timeout <= 2147483647:
                raise ValueError("request_timeout must be a positive integer of at most 2147483647 seconds.")
            self.network = Network(settings.get("network", {}))
            self.host, self.port = self.network.binding("http")
        except (ValueError, UnicodeError) as error:
            raise ValueError(f"Invalid web configuration {path}: {error}") from None

    def settings(self) -> dict:
        return {"network": self.network.settings(), "request_timeout": self.request_timeout}
