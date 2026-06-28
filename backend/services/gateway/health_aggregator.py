#!/usr/bin/env python3
"""Health aggregator sidecar for the VietCropDoctor gateway.

Listens on 127.0.0.1:8099 (loopback only).
Nginx proxies GET /api/services → http://127.0.0.1:8099/.

Returns a JSON object with the reachability status of every upstream service.
Uses only the Python standard library — no extra packages required.
"""
import http.server
import json
import time
import urllib.error
import urllib.request

SERVICES: dict[str, str] = {
    "vision-ai":    "http://vision-ai:8001/health",
    "rag-engine":   "http://rag-engine:8002/health",
}
PROBE_TIMEOUT = 5  # seconds per service


def _probe(url: str) -> dict:
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as resp:
            elapsed_ms = round((time.monotonic() - t0) * 1000)
            try:
                detail = json.loads(resp.read())
            except Exception:
                detail = {}
            return {"status": "up", "elapsed_ms": elapsed_ms, "detail": detail}
    except urllib.error.URLError as exc:
        return {"status": "down", "error": str(exc.reason)}
    except Exception as exc:
        return {"status": "down", "error": type(exc).__name__}


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        t0 = time.monotonic()
        results = {name: _probe(url) for name, url in SERVICES.items()}
        all_up = all(s["status"] == "up" for s in results.values())

        body = json.dumps(
            {
                "status": "ok" if all_up else "degraded",
                "gateway": "up",
                "services": results,
                "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_ms": round((time.monotonic() - t0) * 1000),
            },
            indent=2,
        ).encode()

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Silence per-request access logs — nginx already logs the outer request
    def log_message(self, *_) -> None:
        pass


if __name__ == "__main__":
    addr = ("127.0.0.1", 8099)
    server = http.server.HTTPServer(addr, _Handler)
    print(f"Health aggregator listening on {addr[0]}:{addr[1]}", flush=True)
    server.serve_forever()
