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

## Run tests

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

## Notes

This MVP includes a **manual-safe collector simulation** rather than real casino automation. Integrations are represented as connectors with clear statuses (`claimed`, `manual_required`, `failed`) so the project can be extended safely and in compliance with site terms.
