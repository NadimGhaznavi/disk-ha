"""Serve the nfs-ha web interface."""

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files

from nfs_ha.constants.DNFSHA import DNFSHA


ASSETS = {
    "/": (files("nfs_ha.server") / "static/index.html", "text/html; charset=utf-8"),
}


class WebHandler(BaseHTTPRequestHandler):
    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(DNFSHA.WEB_REQUEST_TIMEOUT)

    def do_GET(self) -> None:
        self.serve()

    def do_HEAD(self) -> None:
        self.serve()

    def serve(self) -> None:
        path = self.path.split("?", 1)[0]
        asset = ASSETS.get(path)
        if path == DNFSHA.WEB_READY_PATH:
            status, body, content_type = 200, b'{"ready": true}\n', "application/json; charset=utf-8"
        elif asset is None:
            status, body, content_type = 404, b"Not found.\n", "text/plain; charset=utf-8"
        else:
            resource, content_type = asset
            body = resource.read_bytes()
            status = 200
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DNFSHA.WEB_HOST)
    parser.add_argument("--port", type=int, default=DNFSHA.WEB_PORT)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")
    try:
        with ThreadingHTTPServer((args.host, args.port), WebHandler) as server:
            print(f"nfs-ha Web UI: http://{args.host}:{server.server_port}/", flush=True)
            server.serve_forever()
    except KeyboardInterrupt:
        pass
    except OSError as error:
        parser.exit(1, f"nfs-ha: {error}\n")


if __name__ == "__main__":
    main()
