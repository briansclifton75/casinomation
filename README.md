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

## Phase 2 features

- API authentication with `CASINOMATION_API_KEY`
- Daily scheduled collector run with `CASINOMATION_DAILY_RUN_AT`
- CSV export endpoint (`/api/claims.csv`)

## Configuration

```bash
export CASINOMATION_DB=/path/to/casinomation.db
export CASINOMATION_API_KEY="replace-with-strong-token"
export CASINOMATION_DAILY_RUN_AT="09:00"     # local machine time, HH:MM
export CASINOMATION_SCHEDULER_ENABLED="true" # true/false
```

## API endpoints

Public:

- `GET /api/health`

Protected (requires `Authorization: Bearer <key>` or `X-API-Key: <key>`):

- `GET /api/totals`
- `GET /api/claims`
- `GET /api/claims.csv`
- `POST /api/collect`
- `POST /api/email` with JSON `{ "sender": "...", "subject": "...", "body": "..." }`

### Example

```bash
curl -H "Authorization: Bearer $CASINOMATION_API_KEY" http://localhost:8000/api/totals
```

## Run tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

## Notes

This MVP includes a **manual-safe collector simulation** rather than real casino automation. Integrations are represented as connectors with clear statuses (`claimed`, `manual_required`, `failed`) so the project can be extended safely and in compliance with site terms.
