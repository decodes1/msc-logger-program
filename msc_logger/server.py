"""Authenticated loopback HTTP interface. No remote service is contacted."""

import hmac
import json
import logging
import mimetypes
import secrets
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .engine import ValidationError

STATIC = Path(__file__).parent / "static"
MAX_BODY = 256000


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, engine, port=0):
        self.engine = engine
        self.token = secrets.token_urlsafe(32)
        self.stop_event = threading.Event()
        self.last_error = ""
        self.last_backup = None
        self.slots = threading.BoundedSemaphore(16)
        super().__init__(("127.0.0.1", port), Handler)
        self.origin = f"http://127.0.0.1:{self.server_port}"
        self.url = self.origin + "/#token=" + self.token

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()

    def worker(self):
        last_backup = 0
        while not self.stop_event.is_set():
            try:
                self.engine.tick()
                if time.monotonic() - last_backup > 300:
                    folder = self.engine.store.path.parent / "backups"
                    name = f"{self.engine.store.path.stem}-{time.time_ns()}.sqlite3"
                    path = self.engine.store.backup(folder / name)
                    self.last_backup = time.time()
                    for old in sorted(folder.glob(f"{self.engine.store.path.stem}-*.sqlite3"))[:-5]:
                        old.unlink()
                    last_backup = time.monotonic()
                    logging.info("Verified backup saved: %s", path)
                self.last_error = ""
            except Exception:
                logging.exception("Background processing failed")
                self.last_error = "Background processing paused by a storage error. Check disk space and the app log."
            self.stop_event.wait(0.5)


class Handler(BaseHTTPRequestHandler):
    server_version = "MSCLogger/1.0"

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        logging.debug(fmt, *args)

    def respond(self, status, body, content_type="application/json", filename=None):
        if not isinstance(body, bytes):
            body = json.dumps(body, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def authorize(self, api=False):
        if self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}":
            raise ValidationError("Invalid local host.", 403)
        origin = self.headers.get("Origin")
        if origin and origin != self.server.origin:
            raise ValidationError("Cross-origin requests are not allowed.", 403)
        if api:
            actual = self.headers.get("Authorization", "")
            if not hmac.compare_digest(actual, "Bearer " + self.server.token):
                raise ValidationError("Session expired. Reopen MSC Logger to reconnect.", 401)

    def do_GET(self):
        try:
            parsed = urlsplit(self.path)
            self.authorize(parsed.path.startswith("/api/"))
            if parsed.path == "/api/state":
                state = self.server.engine.snapshot()
                state["health"] = {"error": self.server.last_error, "backup_at": self.server.last_backup}
                self.respond(200, state)
            elif parsed.path == "/api/export":
                kind = parse_qs(parsed.query).get("kind", [""])[0]
                self.respond(200, self.server.engine.export(kind), "text/csv; charset=utf-8", f"msc-{kind}.csv")
            elif parsed.path == "/api/backup":
                path = self.server.engine.store.path.parent / "exports" / "msc-backup.sqlite3"
                self.server.engine.store.backup(path)
                self.respond(200, path.read_bytes(), "application/octet-stream", "msc-backup.sqlite3")
            elif parsed.path.startswith("/api/"):
                raise ValidationError("Route not found.", 404)
            else:
                relative = "index.html" if parsed.path == "/" else parsed.path.lstrip("/")
                path = (STATIC / relative).resolve()
                if not path.is_relative_to(STATIC.resolve()) or not path.is_file():
                    raise ValidationError("File not found.", 404)
                content_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
                self.respond(200, path.read_bytes(), content_type)
        except ValidationError as error:
            self.respond(error.status, {"error": str(error)})
        except Exception:
            logging.exception("Request failed")
            self.respond(500, {"error": "Unable to read local records. Check disk space and the app log."})

    def do_POST(self):
        try:
            self.authorize(api=True)
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValidationError("Send JSON data.", 415)
            if self.headers.get("Transfer-Encoding"):
                raise ValidationError("Chunked requests are not supported.")
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValidationError("Invalid request length.") from None
            if not 0 < size <= MAX_BODY:
                raise ValidationError("Request is empty or exceeds 256 KB.", 413)
            try:
                data = json.loads(self.rfile.read(size))
            except (json.JSONDecodeError, UnicodeDecodeError):
                raise ValidationError("The request contains invalid JSON.") from None
            path = urlsplit(self.path).path
            if path == "/api/shutdown":
                if data != {"confirm": True}:
                    raise ValidationError("Shutdown confirmation is required.")
                self.respond(200, {"message": "All saved records remain on this computer. App stopped."})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            elif path.startswith("/api/action/"):
                result = self.server.engine.command(path.removeprefix("/api/action/"), data)
                self.respond(200, result)
            else:
                raise ValidationError("Route not found.", 404)
        except ValidationError as error:
            self.respond(error.status, {"error": str(error)})
        except sqlite3.OperationalError:
            logging.exception("Storage unavailable")
            self.respond(503, {"error": "Storage is busy or unavailable. Your change was not confirmed. Retry after checking disk space."})
        except Exception:
            logging.exception("Action failed")
            self.respond(500, {"error": "The change was not confirmed. Check the app log before retrying."})
