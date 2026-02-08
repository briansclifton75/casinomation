from __future__ import annotations

import csv
import html
import io
import json
import os
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from .db import ClaimStore
from .services import RewardService
from .playwright_runner import run_claim_dict

store = ClaimStore()
service = RewardService(store)

_RAW_API_KEYS = os.getenv("CASINOMATION_API_KEYS", "").strip()
if _RAW_API_KEYS:
    API_KEYS = {k.strip() for k in _RAW_API_KEYS.split(",") if k.strip()}
else:
    single = os.getenv("CASINOMATION_API_KEY", "").strip()
    API_KEYS = {single} if single else set()

SCHEDULE_ENABLED = os.getenv("CASINOMATION_SCHEDULER_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
SCHEDULE_TIME = os.getenv("CASINOMATION_DAILY_RUN_AT", "09:00").strip()
EMAIL_SCAN_INTERVAL_MIN = int(os.getenv("CASINOMATION_EMAIL_SCAN_INTERVAL_MIN", "15"))

RATE_LIMIT_ENABLED = os.getenv("CASINOMATION_RATE_LIMIT_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
RATE_LIMIT_MAX = int(os.getenv("CASINOMATION_RATE_LIMIT_MAX", "60"))
RATE_LIMIT_WINDOW_SEC = int(os.getenv("CASINOMATION_RATE_LIMIT_WINDOW_SEC", "60"))

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: dict[str, tuple[float, int]] = {}


def _extract_api_token(headers) -> str:
    auth = headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        return auth.removeprefix("Bearer ").strip()
    return headers.get("X-API-Key", "").strip()


def _client_identifier(handler: BaseHTTPRequestHandler) -> str:
    token = _extract_api_token(handler.headers)
    if token:
        return f"token:{token[:8]}"
    ip = handler.client_address[0] if handler.client_address else "unknown"
    return f"ip:{ip}"


def _rate_limited(key: str) -> bool:
    if not RATE_LIMIT_ENABLED:
        return False

    now = time.time()
    with _rate_limit_lock:
        window_start, count = _rate_limit_buckets.get(key, (now, 0))
        if now - window_start >= RATE_LIMIT_WINDOW_SEC:
            window_start, count = now, 0

        count += 1
        _rate_limit_buckets[key] = (window_start, count)
        return count > RATE_LIMIT_MAX


def _csv_for_claims() -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "claimed_at", "source", "reward_type", "amount_sc", "status", "details"])
    for c in service.recent_claims():
        writer.writerow([c.id, c.claimed_at, c.source, c.reward_type, f"{c.amount_sc:.2f}", c.status, c.details])
    return output.getvalue()


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

    def _send_csv(self, content: str, filename: str = "claims.csv") -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def _read_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            return json.loads(raw) if raw else {}

        data = parse_qs(raw)
        return {k: v[0] if isinstance(v, list) and v else "" for k, v in data.items()}

    def _rate_limit_guard(self) -> bool:
        if not self.path.startswith("/api/"):
            return True
        key = _client_identifier(self)
        if _rate_limited(key):
            self._send_json(
                {
                    "error": "Too Many Requests",
                    "limit": RATE_LIMIT_MAX,
                    "window_sec": RATE_LIMIT_WINDOW_SEC,
                },
                HTTPStatus.TOO_MANY_REQUESTS,
            )
            return False
        return True

    def _require_api_auth(self) -> bool:
        if not self.path.startswith("/api/") or self.path == "/api/health":
            return True
        if not API_KEYS:
            self._send_json(
                {"error": "API key not configured on server"},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
            return False
        token = _extract_api_token(self.headers)
        if token not in API_KEYS:
            self._send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
            return False
        return True

    def _render_home(self) -> str:
        totals = service.dashboard_totals()
        claims_rows = "".join(
            f"<tr><td>{html.escape(c.claimed_at)}</td><td>{html.escape(c.source)}</td>"
            f"<td>{html.escape(c.reward_type)}</td><td>{c.amount_sc:.2f}</td>"
            f"<td>{html.escape(c.status)}</td><td>{html.escape(c.details)}</td></tr>"
            for c in service.recent_claims()
        )
        auth_hint = (
            "Set CASINOMATION_API_KEY or CASINOMATION_API_KEYS to protect API endpoints."
            if not API_KEYS
            else f"API auth enabled ({len(API_KEYS)} active key(s); supports rotation)."
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
    .muted {{ color: #94a3b8; }}
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

  <p>API: <code>GET /api/health</code>, <code>GET /api/totals</code>, <code>GET /api/claims</code>, <code>GET /api/promos/pending</code>, <code>GET /api/claims.csv</code>, <code>POST /api/collect</code>, <code>POST /api/email</code>, <code>POST /api/email/scan</code>, <code>POST /api/claim/run</code></p>
  <p class=\"muted\">{html.escape(auth_hint)} Scheduler: {'enabled' if SCHEDULE_ENABLED else 'disabled'} at {html.escape(SCHEDULE_TIME)} local time. Rate limit: {'on' if RATE_LIMIT_ENABLED else 'off'} ({RATE_LIMIT_MAX}/{RATE_LIMIT_WINDOW_SEC}s).</p>
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

        if not self._rate_limit_guard():
            return

        if not self._require_api_auth():
            return

        if self.path == "/api/totals":
            self._send_json(service.dashboard_totals())
            return

        if self.path == "/api/claims":
            claims = [c.__dict__ for c in service.recent_claims()]
            self._send_json(claims)
            return

        if self.path == "/api/promos/pending":
            limit = int(self.headers.get("X-Limit", "50") or 50)
            self._send_json(service.pending_promos(limit=limit))
            return

        if self.path == "/api/claims.csv":
            self._send_csv(_csv_for_claims())
            return

        self._send_html("Not Found", HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        payload = self._read_payload()

        if self.path == "/collect":
            service.run_daily()
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if self.path == "/email":
            sender = payload.get("sender", "")
            subject = payload.get("subject", "")
            body = payload.get("body", "")
            if not (sender and subject and body):
                self._send_json(
                    {"error": "sender, subject, and body are required"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            service.ingest_email(sender, subject, body)
            self.send_response(HTTPStatus.SEE_OTHER)
            self.send_header("Location", "/")
            self.end_headers()
            return

        if self.path.startswith("/api/"):
            if not self._rate_limit_guard():
                return
            if not self._require_api_auth():
                return

        if self.path == "/api/collect":
            events = [e.__dict__ for e in service.run_daily()]
            self._send_json({"events": events, "count": len(events)})
            return

        if self.path == "/api/email":
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
            self._send_json({"events": events, "count": len(events)})
            return

        if self.path == "/api/email/scan":
            if not service.imap.configured():
                self._send_json(
                    {
                        "error": "IMAP credentials not configured",
                        "required": [
                            "CASINOMATION_IMAP_USER",
                            "CASINOMATION_IMAP_APP_PASSWORD",
                        ],
                    },
                    HTTPStatus.SERVICE_UNAVAILABLE,
                )
                return
            max_messages = int(payload.get("max_messages", 20) or 20)
            summary = service.scan_email_inbox(max_messages=max_messages)
            self._send_json(summary)
            return

        if self.path == "/api/claim/run":
            casino = payload.get("casino", "chumba")
            promo_url = payload.get("promo_url", "")
            claim_id = int(payload.get("claim_id", 0) or 0)
            dry_run = str(payload.get("dry_run", "true")).lower() in {"1", "true", "yes", "on"}

            if claim_id and not promo_url:
                claim = store.get_claim(claim_id)
                if not claim or not claim.claim_url:
                    self._send_json({"error": "claim_id not found or missing claim_url"}, HTTPStatus.BAD_REQUEST)
                    return
                promo_url = claim.claim_url

            if not promo_url:
                self._send_json({"error": "promo_url is required"}, HTTPStatus.BAD_REQUEST)
                return

            result = run_claim_dict(casino=casino, promo_url=promo_url, dry_run=dry_run)
            if claim_id and result.get("status") in {"claimed", "failed", "manual_required"}:
                store.update_claim_status(claim_id, result["status"], result.get("details", ""))
            self._send_json(result)
            return

        self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)


def _scheduler_loop(stop_event: threading.Event) -> None:
    last_run_date = ""
    last_email_scan_ts = 0.0
    while not stop_event.is_set():
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        hhmm = now.strftime("%H:%M")

        if hhmm == SCHEDULE_TIME and today != last_run_date:
            service.run_daily()
            last_run_date = today
            print(f"[scheduler] Daily collector executed at {now.isoformat(timespec='seconds')}")

        if service.imap.configured() and EMAIL_SCAN_INTERVAL_MIN > 0:
            now_ts = time.time()
            if now_ts - last_email_scan_ts >= EMAIL_SCAN_INTERVAL_MIN * 60:
                summary = service.scan_email_inbox(max_messages=30)
                last_email_scan_ts = now_ts
                if summary["new_events"]:
                    print(f"[scheduler] Email scan found {summary['new_events']} new promo events")

        stop_event.wait(20)


def run(host: str = "0.0.0.0", port: int = 8000) -> None:
    stop_event = threading.Event()

    if SCHEDULE_ENABLED:
        scheduler = threading.Thread(
            target=_scheduler_loop,
            args=(stop_event,),
            daemon=True,
            name="daily-collector-scheduler",
        )
        scheduler.start()

    server = ThreadingHTTPServer((host, port), AppHandler)
    print(f"Casinomation running on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        stop_event.set()
