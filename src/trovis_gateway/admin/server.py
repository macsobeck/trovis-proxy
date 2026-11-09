"""Small dependency-free admin HTTP server for controller profiles and status."""

from __future__ import annotations

import asyncio
import json
import mimetypes
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from .. import __version__
from ..config import ControllerProfile, InfrastructureSettings
from ..connection_test import test_connection
from ..metrics import GatewayMetrics
from ..store import ConfigStore, public_profile

STATIC_ROOT = Path(__file__).parent / "static"
MAX_JSON_BYTES = 256 * 1024


class AdminServer:
    def __init__(
        self,
        settings: InfrastructureSettings,
        store: ConfigStore,
        metrics: GatewayMetrics,
        event_loop: asyncio.AbstractEventLoop,
    ) -> None:
        self.settings = settings
        self.store = store
        self.metrics = metrics
        self.event_loop = event_loop
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def bound_port(self) -> int | None:
        return self._server.server_port if self._server is not None else None

    def start(self) -> None:
        context = self

        class Handler(AdminHandler):
            admin = context

        self._server = ThreadingHTTPServer(
            (self.settings.admin_host, self.settings.admin_port),
            Handler,
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="gateway-admin",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=3)
            self._thread = None


class AdminHandler(BaseHTTPRequestHandler):
    admin: AdminServer
    server_version = f"TrovisGatewayAdmin/{__version__}"

    def log_message(self, format: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/config":
            self._json(HTTPStatus.OK, self.admin.store.public_document())
            return
        if path == "/api/status":
            active = self.admin.store.active_profile()
            self._json(
                HTTPStatus.OK,
                {
                    "version": __version__,
                    "listener": {
                        "address": self.admin.settings.listen_host,
                        "port": self.admin.settings.listen_port,
                    },
                    "active_profile": public_profile(active) if active else None,
                    "metrics": self.admin.metrics.snapshot(),
                },
            )
            return
        if path == "/health":
            self._json(HTTPStatus.OK, {"status": "ok"})
            return
        self._static(path)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        try:
            payload = self._read_json()
            if path == "/api/profiles":
                profile = self.admin.store.upsert_profile(payload)
                self._json(HTTPStatus.CREATED, public_profile(profile))
                return
            if path == "/api/test-connection":
                profile_id = payload.pop("id", None)
                if profile_id:
                    existing = next(
                        (
                            item
                            for item in self.admin.store.snapshot().profiles
                            if item.id == profile_id
                        ),
                        None,
                    )
                else:
                    existing = None
                if not payload.get("access_key") and existing is not None:
                    payload["access_key"] = existing.access_key
                payload.pop("access_key_configured", None)
                payload.pop("clear_access_key", None)
                profile = ControllerProfile.model_validate(payload)
                future = asyncio.run_coroutine_threadsafe(
                    test_connection(profile),
                    self.admin.event_loop,
                )
                self._json(HTTPStatus.OK, future.result(timeout=130))
                return
            parts = path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["api", "profiles"] and parts[3] == "activate":
                self.admin.store.activate_profile(parts[2])
                self._json(HTTPStatus.OK, self.admin.store.public_document())
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except KeyError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
        except TimeoutError:
            self._json(HTTPStatus.GATEWAY_TIMEOUT, {"error": "connection test timed out"})

    def do_PUT(self) -> None:
        path = urlsplit(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "profiles"]:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            profile = self.admin.store.upsert_profile(self._read_json(), parts[2])
            self._json(HTTPStatus.OK, public_profile(profile))
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_DELETE(self) -> None:
        path = urlsplit(self.path).path
        parts = path.strip("/").split("/")
        if len(parts) != 3 or parts[:2] != ["api", "profiles"]:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            self.admin.store.delete_profile(parts[2])
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        except KeyError as exc:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(exc)})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_JSON_BYTES:
            raise ValueError("invalid JSON body size")
        payload = json.loads(self.rfile.read(length))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _json(self, status: HTTPStatus, payload: object) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _static(self, path: str) -> None:
        relative = "index.html" if path in {"", "/"} else path.lstrip("/")
        candidate = (STATIC_ROOT / relative).resolve()
        if STATIC_ROOT.resolve() not in candidate.parents and candidate != STATIC_ROOT.resolve():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not candidate.is_file():
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        body = candidate.read_bytes()
        content_type, _ = mimetypes.guess_type(candidate.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
