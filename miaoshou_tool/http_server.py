from __future__ import annotations

from collections.abc import Callable
from http.server import BaseHTTPRequestHandler

from . import http_routes


def make_handler(deps_factory: Callable[[], dict[str, object]], json_dumps: Callable[..., str]):
    class Handler(BaseHTTPRequestHandler):
        def current_username(self) -> str | None:
            return deps_factory()["DEFAULT_OPERATOR"]

        def redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.end_headers()

        def send_html(self, content: bytes, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, payload: dict, status: int = 200) -> None:
            content = json_dumps(payload, compact=True).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self) -> None:
            http_routes.handle_get(self, deps_factory())

        def do_POST(self) -> None:
            http_routes.handle_post(self, deps_factory())

        def log_message(self, format: str, *args) -> None:
            return

    return Handler
