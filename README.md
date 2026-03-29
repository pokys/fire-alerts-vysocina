# Fire Alerts Vysocina

Minimal MVP script that fetches recent fire incident events from the Vysocina API and generates `calendar.ics`.

## What it does

- fetches events for the last 24 hours in UTC
- filters by:
  - `krajId=108`
  - `okresId=3304`
  - required `stavIds`
- sorts events by `casVzniku`
- de-duplicates by `id`
- writes a valid RFC5545 iCalendar file to `calendar.ics`
- keeps only the latest 100 events for a compact output

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 generate.py
```

## Expected JSON shape

```json
[
  {
    "id": 123456,
    "casVzniku": "2026-03-29T10:15:00Z",
    "typ": "Pozar",
    "misto": "Jihlava",
    "popis": "Hori osobni automobil"
  }
]
```

## GitHub Actions

The workflow in `.github/workflows/generate.yml` runs every 5 minutes and also supports manual runs.

If you want the generated `calendar.ics` committed back to the repository, the workflow already includes commit-and-push logic.
