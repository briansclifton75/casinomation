# casinomation

Casinomation is a lightweight MVP web app to track and collect daily sweepstakes-casino rewards:

- daily free-play SC claims
- email-promoted free SC / free spins links
- claim history and totals dashboard

## Quick start

```bash
python app.py
```

Open <http://localhost:8000>.

Optional flags:

```bash
python app.py --host 127.0.0.1 --port 8080
```

## Phase 3 features

- API authentication (`CASINOMATION_API_KEY` or rotating `CASINOMATION_API_KEYS`)
- Daily scheduled collector run (`CASINOMATION_DAILY_RUN_AT`)
- CSV export endpoint (`/api/claims.csv`)
- Basic in-memory API rate limiting
- Gmail IMAP inbox scanning + promo ingestion (deduplicated)
- Docker + docker-compose
- GitHub Actions CI (tests + compile + docker build)

## Configuration

```bash
export CASINOMATION_DB=/path/to/casinomation.db

# single key
export CASINOMATION_API_KEY="replace-with-strong-token"

# key rotation (comma-separated active keys)
export CASINOMATION_API_KEYS="current-key,next-key"

export CASINOMATION_DAILY_RUN_AT="09:00"     # local machine time, HH:MM
export CASINOMATION_SCHEDULER_ENABLED="true" # true/false

export CASINOMATION_RATE_LIMIT_ENABLED="true"
export CASINOMATION_RATE_LIMIT_MAX="60"
export CASINOMATION_RATE_LIMIT_WINDOW_SEC="60"

# Gmail IMAP ingestion (app password, not your normal password)
export CASINOMATION_IMAP_HOST="imap.gmail.com"
export CASINOMATION_IMAP_PORT="993"
export CASINOMATION_IMAP_USER="you@gmail.com"
export CASINOMATION_IMAP_APP_PASSWORD="xxxx xxxx xxxx xxxx"
export CASINOMATION_EMAIL_ALLOWLIST="chumbacasino,globalpoker,luckyland"
export CASINOMATION_EMAIL_SCAN_INTERVAL_MIN="15"

# Keep dummy collector off (recommended)
export CASINOMATION_ENABLE_DUMMY_COLLECTOR="false"

# Playwright credentials
export CASINOMATION_CHUMBA_USER="you@example.com"
export CASINOMATION_CHUMBA_PASSWORD="your-password"
export CASINOMATION_MODO_USER="you@example.com"
export CASINOMATION_MODO_PASSWORD="your-password"
export CASINOMATION_FORTUNE_USER="you@example.com"
export CASINOMATION_FORTUNE_PASSWORD="your-password"

# auto-run safety
export CASINOMATION_AUTO_RUN_MAX="3"
export CASINOMATION_AUTO_RUN_DRY="true"
```

## API endpoints

Public:

- `GET /api/health`

Protected (requires `Authorization: Bearer <key>` or `X-API-Key: <key>`):

- `GET /api/totals`
- `GET /api/claims`
- `GET /api/promos/pending`
- `GET /api/claims.csv`
- `POST /api/collect`
- `POST /api/email` with JSON `{ "sender": "...", "subject": "...", "body": "..." }`
- `POST /api/email/scan` with optional JSON `{ "max_messages": 30 }`
- `POST /api/claim/run` with JSON `{ "casino": "chumba", "promo_url": "...", "dry_run": true }` or `{ "claim_id": 123, "dry_run": true }`
- `POST /api/claim/auto-run` with optional JSON `{ "max_runs": 3, "dry_run": false }`

### Example

```bash
curl -H "Authorization: Bearer $CASINOMATION_API_KEY" http://localhost:8000/api/totals
```

## Docker

```bash
docker compose up --build
```

Then open <http://localhost:8000>.

## Run tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m py_compile app.py casinomation/*.py
pip install -r requirements.txt
playwright install chromium
```

## Notes

This MVP includes a **manual-safe collector simulation** rather than real casino automation. Integrations are represented as connectors with clear statuses (`claimed`, `manual_required`, `failed`) so the project can be extended safely and in compliance with site terms.
