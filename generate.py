#!/usr/bin/env python3

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests


API_URL = "http://webohled.hasici-vysocina.cz/udalosti/api/"
CALENDAR_PATH = Path("calendar.ics")
MAX_EVENTS = 100
TIMEOUT_SECONDS = 30
KRAJ_ID = 108
OKRES_ID = 3304
STAV_IDS = [
    210,
    400,
    410,
    420,
    430,
    440,
    500,
    510,
    520,
    600,
    610,
    620,
    700,
    710,
    750,
    760,
    780,
    800,
]


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_api_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_event_datetime(value):
    if not value:
        raise ValueError("Missing casVzniku")

    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc).replace(microsecond=0)


def format_ics_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def escape_ics_text(value):
    if value is None:
        return ""

    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
        .replace("\r", "\\n")
        .replace(",", "\\,")
        .replace(";", "\\;")
    )


def fold_ics_line(line, limit=75):
    chunks = []
    while len(line) > limit:
        chunks.append(line[:limit])
        line = " " + line[limit:]
    chunks.append(line)
    return "\r\n".join(chunks)


def fetch_events():
    now = utc_now()
    since = now - timedelta(hours=24)

    params = {
        "krajId": KRAJ_ID,
        "okresId": OKRES_ID,
        "casOd": format_api_datetime(since),
        "casDo": format_api_datetime(now),
    }
    for stav_id in STAV_IDS:
        params.setdefault("stavIds", []).append(stav_id)

    response = requests.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
    response.raise_for_status()

    data = response.json()
    if not isinstance(data, list):
        raise ValueError("API response is not a list of events")

    events = []
    seen_ids = set()

    for raw_event in data:
        if not isinstance(raw_event, dict):
            continue

        event_id = raw_event.get("id")
        cas_vzniku = raw_event.get("casVzniku")
        typ = (raw_event.get("typ") or "").strip()
        misto = (raw_event.get("misto") or "").strip()

        if not event_id or not cas_vzniku or not typ or not misto:
            continue

        event_id = str(event_id)
        if event_id in seen_ids:
            continue

        event_dt = parse_event_datetime(cas_vzniku)
        seen_ids.add(event_id)
        events.append(
            {
                "id": event_id,
                "casVzniku": event_dt,
                "typ": typ,
                "misto": misto,
                "popis": (raw_event.get("popis") or "").strip(),
            }
        )

    events.sort(key=lambda item: (item["casVzniku"], item["id"]))
    return events[-MAX_EVENTS:]


def build_ics(events):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//fire-alerts-vysocina//MVP//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Fire Alerts Vysocina",
    ]

    for event in events:
        dt = format_ics_datetime(event["casVzniku"])
        summary = escape_ics_text(f'{event["typ"]} - {event["misto"]}')

        lines.extend(
            [
                "BEGIN:VEVENT",
                fold_ics_line(f"UID:{escape_ics_text(event['id'])}"),
                f"DTSTART:{dt}",
                f"DTSTAMP:{dt}",
                fold_ics_line(f"SUMMARY:{summary}"),
            ]
        )

        if event["popis"]:
            lines.append(fold_ics_line(f"DESCRIPTION:{escape_ics_text(event['popis'])}"))

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def write_calendar(content):
    CALENDAR_PATH.write_text(content, encoding="utf-8", newline="")


def main():
    try:
        events = fetch_events()
        calendar_content = build_ics(events)
        write_calendar(calendar_content)
    except requests.RequestException as exc:
        print(f"API request failed: {exc}", file=sys.stderr)
        return 1
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid API response: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {CALENDAR_PATH} with {len(events)} events.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
