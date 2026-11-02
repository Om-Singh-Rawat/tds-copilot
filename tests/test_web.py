"""Starts the real HTTP server on a free port and exercises the API."""
import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

from tds import audit, config, data, web


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = web.make_server("127.0.0.1", 0)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        # keep the audit log of test runs out of the real one
        cls._log = mock.patch.object(audit, "LOG", config.ROOT / ".cache" / "test_audit.jsonl")
        cls._log.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls._log.stop()

    def call(self, path, body=None):
        req = urllib.request.Request(self.base + path, method="POST" if body is not None else "GET",
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    def test_health_and_meta(self):
        self.assertEqual(self.call("/healthz"), (200, {"ok": True}))
        status, meta = self.call("/api/meta")
        self.assertEqual(status, 200)
        self.assertEqual(len(meta["cases"]), len(data.test_cases()))

    def test_index_served(self):
        with urllib.request.urlopen(self.base + "/", timeout=10) as r:
            self.assertIn(b"TDS Copilot", r.read())

    def test_run_baseline(self):
        status, r = self.call("/api/run", {"invoice": data.test_case("T01")["invoice"], "mode": "baseline"})
        self.assertEqual(status, 200)
        self.assertEqual(r["tds_total"], 2400)

    def test_invalid_invoice_is_400_with_details(self):
        status, r = self.call("/api/run", {"invoice": {"vendor_id": "V001"}, "mode": "baseline"})
        self.assertEqual(status, 400)
        self.assertTrue(r["details"])

    def test_bad_mode_and_bad_override(self):
        inv = data.test_case("T01")["invoice"]
        self.assertEqual(self.call("/api/run", {"invoice": inv, "mode": "human"})[0], 400)
        self.assertEqual(self.call("/api/override", {"invoice": inv, "codes": ["194Z"]})[0], 400)

    def test_override_then_decision(self):
        status, r = self.call("/api/override", {"invoice": data.test_case("T13")["invoice"], "codes": ["194C"]})
        self.assertEqual((status, r["tds_total"]), (200, 2400))
        status, d = self.call("/api/decision", {"audit_id": r["audit_id"], "action": "override", "codes": ["194C"]})
        self.assertEqual(status, 200)
        self.assertTrue(d["ok"])

    def test_public_mode_hides_audit(self):
        with mock.patch.object(config, "PUBLIC_MODE", True):
            self.assertEqual(self.call("/api/audit")[0], 403)

    def test_unknown_path(self):
        self.assertEqual(self.call("/nope")[0], 404)


class RateLimiterTests(unittest.TestCase):
    def test_limits_per_client(self):
        rl = web.RateLimiter(2)
        self.assertTrue(rl.allow("a"))
        self.assertTrue(rl.allow("a"))
        self.assertFalse(rl.allow("a"))
        self.assertTrue(rl.allow("b"))


if __name__ == "__main__":
    unittest.main()
