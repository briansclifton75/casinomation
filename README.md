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

Optional DB override:

```bash
export CASINOMATION_DB=/path/to/casinomation.db
```

## API endpoints

- `GET /api/health`
- `GET /api/totals`
- `GET /api/claims`
- `POST /api/collect`
- `POST /api/email` with JSON `{ "sender": "...", "subject": "...", "body": "..." }`

## Run tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

## Notes

This MVP includes a **manual-safe collector simulation** rather than real casino automation. Integrations are represented as connectors with clear statuses (`claimed`, `manual_required`, `failed`) so the project can be extended safely and in compliance with site terms.
