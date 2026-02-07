from __future__ import annotations

import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .db import ClaimStore
from .services import RewardService

store = ClaimStore()
service = RewardService(store)


class AppHandler(BaseHTTPRequestHandler):
    def _send_html(self, page: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(page.encode("utf-8"))

    def _send_json(self, payload: dict | list, status: HTTPStatus = HTTPStatus.OK) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            return json.loads(raw) if raw else {}

        data = parse_qs(raw)
        return {k: v[0] if isinstance(v, list) and v else "" for k, v in data.items()}

    def _render_home(self) -> str:
        totals = service.dashboard_totals()
        claims_rows = "".join(
            f"<tr><td>{html.escape(c.claimed_at)}</td><td>{html.escape(c.source)}</td>"
            f"<td>{html.escape(c.reward_type)}</td><td>{c.amount_sc:.2f}</td>"
            f"<td>{html.escape(c.status)}</td><td>{html.escape(c.details)}</td></tr>"
            for c in service.recent_claims()
        )
        return f"""
<!doctype html>
<html>
<head>
  <meta charset=\"utf-8\" />
  <title>Casinomation MVP</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
    .grid {{ display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
    .card {{ background: #1e293b; border-radius: 10px; padding: 1rem; }}
    button {{ background: #22c55e; color: #052e16; border: 0; border-radius: 6px; padding: .6rem 1rem; font-weight: bold; cursor: pointer; }}
    input, textarea {{ width: 100%; margin: .4rem 0; padding: .5rem; border-radius: 6px; border: 1px solid #475569; background: #0b1220; color: #e2e8f0; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: .9rem; }}
    th, td {{ border-bottom: 1px solid #334155; padding: .5rem; text-align: left; vertical-align: top; }}
    .layout {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }}
    code {{ background: #020617; border-radius: 4px; padding: 2px 6px; }}
  </style>
</head>
<body>
  <h1>🎰 Casinomation MVP</h1>
  <p>Collect daily SC and parse email promos for free SC / free spins.</p>

  <div class=\"grid\">
    <div class=\"card\"><strong>Total Claimed SC</strong><br>{totals['total_sc']:.2f}</div>
    <div class=\"card\"><strong>Free Spins Found</strong><br>{int(totals['free_spins'])}</div>
    <div class=\"card\"><strong>Successful Claims</strong><br>{int(totals['successful_claims'])}</div>
    <div class=\"card\"><strong>Unresolved</strong><br>{int(totals['unresolved'])}</div>
  </div>

  <div class=\"layout\">
    <div class=\"card\">
      <h3>Run Daily Collector</h3>
      <form method=\"post\" action=\"/collect\">
        <button type=\"submit\">Run now</button>
      </form>
    </div>

    <div class=\"card\">
      <h3>Ingest Promo Email</h3>
      <form method=\"post\" action=\"/email\">
        <label>Sender</label>
        <input name=\"sender\" placeholder=\"promos@casino.com\" required />
        <label>Subject</label>
        <input name=\"subject\" placeholder=\"Claim 5 SC + 25 free spins\" required />
        <label>Body</label>
        <textarea rows=\"4\" name=\"body\" placeholder=\"Promo details...\" required></textarea>
        <button type=\"submit\">Parse email</button>
      </form>
    </div>
  </div>

  <h3>Recent Claims</h3>
  <table>
    <thead><tr><th>Time</th><th>Source</th><th>Type</th><th>SC</th><th>Status</th><th>Details</th></tr></thead>
    <tbody>{claims_rows}</tbody>
  </table>

  <p>API: <code>GET /api/health</code>, <code>GET /api/totals</code>, <code>GET /api/claims</code>, <code>POST /api/collect</code>, <code>POST /api/email</code></p>
</body>
</html>
"""

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_html(self._render_home())
            return

        if self.path in ("/health", "/api/health"):
            self._send_json({"status": "ok"})
            return

        if self.path == "/api/totals":
            self._send_json(service.dashboard_totals())
            return

        if self.path == "/api/claims":
            claims = [c.__dict__ for c in service.recent_claims()]
            self._send_json(claims)
            return

        self._send_html("Not Found", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        payload = self._read_payload()

        if self.path in ("/collect", "/api/collect"):
            events = [e.__dict__ for e in service.run_daily()]
            if self.path.startswith("/api/"):
                self._send_json({"events": events, "count": len(events)})
                return
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if self.path in ("/email", "/api/email"):
            sender = payload.get("sender", "")
            subject = payload.get("subject", "")
            body = payload.get("body", "")
            if not (sender and subject and body):
                self._send_json(
                    {"error": "sender, subject, and body are required"},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            events = [e.__dict__ for e in service.ingest_email(sender, subject, body)]
            if self.path.startswith("/api/"):
                self._send_json({"events": events, "count": len(events)})
                return

            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Casinomation running on http://{host}:{port}")
    server.serve_forever()
