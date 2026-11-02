"""Reviewer UI and JSON API - Python standard library only.

  python -m tds serve                       # http://127.0.0.1:8000
  HOST=0.0.0.0 PORT=8080 TDS_PUBLIC=1 python -m tds serve   # behind a proxy / in Docker

Endpoints
  GET  /                 reviewer UI
  GET  /healthz          liveness probe
  GET  /api/meta         sample cases, vendors, codes, server mode
  GET  /api/audit        recent audit records (disabled when TDS_PUBLIC=1)
  POST /api/run          {"invoice": {...}, "mode": "llm"|"baseline", "samples": 1-5}
  POST /api/override     {"invoice": {...}, "codes": ["194C", ...]}
  POST /api/decision     {"audit_id", "action", "codes", "tds_total", "reviewer", "note"}
"""
import json
import sys
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import audit, config, data, llm
from .pipeline import process
from .rules import all_codes
from .schema import InvalidInvoice

STATIC = Path(__file__).parent / "static"


class RateLimiter:
    """Sliding one-minute window per client key."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            return True


LIMITER = RateLimiter(config.LLM_REQUESTS_PER_MINUTE)


def limited_chat(client: str):
    """chat_fn that serves cache hits freely but rate-limits live (paid/quota) calls per client."""
    def chat_fn(messages, model=None, temperature=0.0, sample_idx=0):
        if not llm.is_cached(messages, model, temperature, sample_idx) and not LIMITER.allow(client):
            raise llm.LLMError("too many live LLM requests from your address - try again in a minute")
        return llm.chat(messages, model=model, temperature=temperature, sample_idx=sample_idx)
    return chat_fn


def meta() -> dict:
    return {
        "cases": data.test_cases(), "vendors": data.vendors(), "codes": all_codes(),
        "llm_configured": bool(config.OPENROUTER_API_KEY), "live_llm": config.LIVE_LLM,
        "model": config.OPENROUTER_MODEL, "public": config.PUBLIC_MODE,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "tds-copilot"

    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode(), "application/json")

    def _error(self, status: int, message: str, details=None) -> None:
        self._json({"error": message, "details": details or []}, status)

    def _client(self) -> str:
        forwarded = self.headers.get("X-Forwarded-For", "")
        return forwarded.split(",")[0].strip() or self.client_address[0]

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n > config.MAX_BODY_BYTES:
            raise InvalidInvoice([f"request body larger than {config.MAX_BODY_BYTES} bytes"])
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            raise InvalidInvoice([f"body is not valid JSON: {e.msg}"]) from e
        if not isinstance(body, dict):
            raise InvalidInvoice(["body must be a JSON object"])
        return body

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[web] {self._client()} {fmt % args}\n")

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/healthz":
            return self._json({"ok": True})
        if path in ("/api/meta", "/api/cases"):
            return self._json(meta())
        if path == "/api/audit":
            if config.PUBLIC_MODE:
                return self._error(403, "audit trail is not shown on the public demo")
            return self._json(audit.recent())
        self._error(404, "not found")

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            b = self._body()
            if path == "/api/run":
                mode = b.get("mode", "llm")
                if mode not in ("llm", "baseline"):
                    raise InvalidInvoice(["mode must be 'llm' or 'baseline'"])
                return self._json(process(b.get("invoice"), mode=mode, samples=int(b.get("samples", 1)),
                                          chat_fn=limited_chat(self._client())))
            if path == "/api/override":
                return self._json(process(b.get("invoice"), mode="human", override_codes=b.get("codes")))
            if path == "/api/decision":
                if b.get("action") not in ("approve", "override", "reject"):
                    raise InvalidInvoice(["action must be approve, override or reject"])
                rid = audit.write("review_decision", {
                    "ref_audit_id": str(b.get("audit_id", ""))[:32], "action": b["action"],
                    "reviewer": str(b.get("reviewer") or "unnamed")[:80], "final_codes": b.get("codes"),
                    "final_tds": b.get("tds_total"), "note": str(b.get("note", ""))[:500],
                })
                return self._json({"ok": True, "record_id": rid})
            self._error(404, "not found")
        except InvalidInvoice as e:
            self._error(400, "invalid request", e.errors)
        except (TypeError, ValueError) as e:
            self._error(400, f"invalid request: {e}")
        except Exception as e:  # keep the server alive; details go to the log only
            sys.stderr.write(f"[web] internal error: {type(e).__name__}: {e}\n")
            self._error(500, "internal error")


def make_server(host: str = config.HOST, port: int = config.PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def serve(host: str = config.HOST, port: int = config.PORT) -> None:
    server = make_server(host, port)
    mode = "PUBLIC" if config.PUBLIC_MODE else "local"
    llm_state = "live" if config.LIVE_LLM and config.OPENROUTER_API_KEY else "cache-only"
    print(f"TDS Copilot on http://{host}:{port}  ({mode} mode, LLM {llm_state}, model {config.OPENROUTER_MODEL})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    serve()
