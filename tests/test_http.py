"""Exercise the actual local HTTP boundary with the standard library."""

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from msc_logger.engine import Engine
from msc_logger.server import LocalServer
from msc_logger.storage import Store


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.temp.name) / "test.sqlite3")
        self.server = LocalServer(Engine(self.store))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.store.close()
        self.temp.cleanup()

    def send(self, path, body=None, auth=True, headers=None):
        base = {"Authorization": "Bearer " + self.server.token} if auth else {}
        if body is not None:
            base["Content-Type"] = "application/json"
        base.update(headers or {})
        request = urllib.request.Request(self.server.origin + path, data=body, headers=base)
        try:
            return urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as error:
            return error

    def test_api_requires_session(self):
        with self.send("/api/state", auth=False) as response:
            self.assertEqual(response.status, 401)
        with self.send("/api/state") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("tasks", json.load(response))

    def test_foreign_origin_and_host_rejected(self):
        with self.send("/api/state", headers={"Origin": "https://example.invalid"}) as response:
            self.assertEqual(response.status, 403)
        with self.send("/api/state", headers={"Host": "evil.invalid"}) as response:
            self.assertEqual(response.status, 403)

    def test_malformed_and_oversized_body(self):
        with self.send("/api/action/report", b"{") as response:
            self.assertEqual(response.status, 400)
        with self.send("/api/action/report", b"x" * 256001) as response:
            self.assertEqual(response.status, 413)

    def test_traversal_and_security_headers(self):
        with self.send("/../engine.py") as response:
            self.assertEqual(response.status, 404)
        with self.send("/") as response:
            self.assertEqual(response.status, 200)
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
            self.assertNotIn(b"fonts.googleapis", response.read())

    def test_request_roundtrip_and_download(self):
        body = json.dumps({"operation_id": "http-test", "category": "Other", "description": "HTTP roundtrip", "priority": "routine"}).encode()
        with self.send("/api/action/report", body) as response:
            self.assertEqual(response.status, 200)
        with self.send("/api/export?kind=reports") as response:
            self.assertIn(b"HTTP roundtrip", response.read())
        with self.send("/api/backup") as response:
            self.assertTrue(response.read().startswith(b"SQLite format 3"))


if __name__ == "__main__":
    unittest.main()
