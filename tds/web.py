"""Reviewer UI - stdlib HTTP server, no install needed.

  python -m tds.web            # then open http://127.0.0.1:8000
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import audit, config
from .pipeline import process, vendors
from .rules import all_codes

STATIC = Path(__file__).parent / "static"


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json")

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n) or b"{}")

    def log_message(self, fmt, *args):
        sys.stderr.write("[web] " + fmt % args + "\n")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if self.path == "/api/cases":
            cases = json.loads(config.TEST_CASES_PATH.read_text(encoding="utf-8"))["cases"]
            return self._json({"cases": cases, "vendors": vendors(), "codes": all_codes(),
                               "llm_configured": bool(config.OPENROUTER_API_KEY), "model": config.OPENROUTER_MODEL})
        if self.path == "/api/audit":
            lines = audit.LOG.read_text(encoding="utf-8").splitlines()[-30:] if audit.LOG.exists() else []
            return self._json([json.loads(l) for l in reversed(lines)])
        self._send(404, b"not found", "text/plain")

    def do_POST(self):
        try:
            b = self._body()
            if self.path == "/api/run":
                return self._json(process(b["invoice"], mode=b.get("mode", "llm"), samples=int(b.get("samples", 1))))
            if self.path == "/api/override":
                return self._json(process(b["invoice"], mode="human", override_codes=b["codes"]))
            if self.path == "/api/decision":
                rid = audit.write("review_decision", {
                    "ref_audit_id": b.get("audit_id"), "action": b.get("action"),
                    "reviewer": b.get("reviewer") or "unnamed", "final_codes": b.get("codes"),
                    "final_tds": b.get("tds_total"), "note": b.get("note", ""),
                })
                return self._json({"ok": True, "record_id": rid})
            self._send(404, b"not found", "text/plain")
        except Exception as e:
            self._json({"error": f"{type(e).__name__}: {e}"}, status=500)


def main(port: int = 8000) -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else port
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"TDS Copilot reviewer UI on http://127.0.0.1:{port}  (Ctrl+C to stop)")
    server.serve_forever()


if __name__ == "__main__":
    main()
