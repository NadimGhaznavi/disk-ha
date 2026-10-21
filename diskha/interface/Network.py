"""Resolve declared listeners and validated production overrides."""

from ipaddress import IPv4Address

from diskha.constants.DDiskHA import DDiskHA


class Network:
    def __init__(self, overrides: dict):
        self._bindings = {use: (interface, port) for use, interface, port in DDiskHA.CMDB_NETWORK}
        if not isinstance(overrides, dict) or set(overrides) - self._bindings.keys():
            raise ValueError("network must contain only declared listener uses.")
        for use, fields in overrides.items():
            if not isinstance(fields, dict) or set(fields) - {"interface", "port"}:
                raise ValueError(f"network.{use} accepts only interface and port.")
            interface, port = self._bindings[use]
            interface = fields.get("interface", interface)
            port = fields.get("port", port)
            if not isinstance(interface, str):
                raise ValueError(f"network.{use}.interface must be an IPv4 address.")
            try:
                IPv4Address(interface)
            except ValueError:
                raise ValueError(f"network.{use}.interface must be an IPv4 address.") from None
            if type(port) is not int or not 1 <= port <= 65535:
                raise ValueError(f"network.{use}.port must be an integer between 1 and 65535.")
            self._bindings[use] = interface, port

    def binding(self, use: str) -> tuple[str, int]:
        return self._bindings[use]

    def destination(self, use: str) -> tuple[str, int]:
        interface, port = self.binding(use)
        return ("127.0.0.1" if interface == "0.0.0.0" else interface), port

    def settings(self) -> dict:
        return {use: {"interface": interface, "port": port}
                for use, (interface, port) in self._bindings.items()}
