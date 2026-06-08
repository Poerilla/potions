from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict

from .store import FlatFileStore


class HealthServer:
    def __init__(self, store: FlatFileStore, host: str = "127.0.0.1", port: int = 8765):
        self.store = store
        self.host = host
        self.port = port

    def serve_forever(self) -> None:
        store = self.store

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # type: ignore[override]
                if self.path == "/healthz":
                    payload = store.read_json("health.json") or {"status": "unknown"}
                elif self.path == "/state":
                    payload = {"strategies": store.read_table("strategy_instances")}
                elif self.path == "/positions":
                    payload = {"positions": store.read_table("positions")}
                elif self.path == "/orders":
                    payload = {"orders": store.read_table("orders")}
                elif self.path == "/jobs":
                    payload = {"jobs": store.read_table("jobs")}
                else:
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        HTTPServer((self.host, self.port), Handler).serve_forever()
