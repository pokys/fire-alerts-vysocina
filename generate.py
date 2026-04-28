#!/usr/bin/env python3

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from pyproj import Transformer

_jtsk_to_wgs84 = Transformer.from_crs("EPSG:5514", "EPSG:4326", always_xy=True)


API_URL = "http://webohled.hasici-vysocina.cz/udalosti/api/"
CALENDAR_PATH = Path("calendar-pelhrimov.ics")
CALENDAR_VYSOCINA_PATH = Path("calendar-vysocina.ics")
NOTIFIED_PATH = Path("notified.json")
NOTIFIED_VYSOCINA_PATH = Path("notified-vysocina.json")
RAW_RESPONSE_PATH = Path("last_response.json")
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

TYPE_EMOJIS = {
    3100: "🔥",
    3200: "🚗",
    3400: "☣️",
    3500: "🛠️",
    3550: "🚑",
    3800: "⚠️",
}


SUBTYPE_LABELS = {
    3101: "budova",
    3103: "technologie",
    3105: "cvičení",
    3106: "tráva/plocha",
    3107: "trafostanice",
    3108: "vozidlo",
    3109: "odpad",
    3110: "les",
    3111: "venkovní požár",
    3112: "kůlna/přístřešek",
    3117: "saze v komíně",
    3211: "se zraněním",
    3212: "bez zranění",
    3213: "úklid místa",
    3214: "dopravní nehoda",
    3401: "olej/PHM",
    3403: "neznámá látka",
    3404: "plyn",
    3501: "ostatní",
    3502: "spolupráce IZS",
    3504: "dovoz vody",
    3505: "strom",
    3521: "záchrana na vodě",
    3522: "záchrana ze stromu",
    3523: "otevření/asistence",
    3524: "vyproštění osoby",
    3525: "otevření bytu/auta",
    3526: "odstranění překážky",
    3527: "čerpání vody",
    3528: "měření koncentrace",
    3530: "spolupráce ZZS",
    3531: "záchrana zvířete",
    3541: "monitoring",
    3542: "obtížný hmyz",
    3543: "transport pacienta",
    3811: "planý poplach",
}

VEHICLE_ABBREVS = [
    ("cisternová automobilová stříkačka", "CAS"),
    ("automobilový žebřík", "AŽ"),
    ("výškový automobil", "VYA"),
    ("vyprošťovací automobil", "VYA"),
    ("rychlý zásahový automobil", "RZA"),
    ("technický automobil", "TA"),
    ("velitelský automobil", "VEA"),
    ("kontejnerový automobil", "KA"),
    ("dopravní automobil", "DA"),
    ("přenosná motorová stříkačka", "PMS"),
]


def abbrev_vehicle(name):
    name_lower = name.lower()
    for full, short in VEHICLE_ABBREVS:
        if name_lower.startswith(full):
            return short
    return name


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_api_datetime(value):
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


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


def pick_value(payload, *keys):
    for key in keys:
        if key in payload and payload[key] not in (None, ""):
            return payload[key]
    return None


def join_parts(*parts):
    values = []
    for part in parts:
        if part is None:
            continue
        text = str(part).strip()
        if text and text not in values:
            values.append(text)
    return ", ".join(values)


def build_location(raw_event):
    okres = raw_event.get("okres")
    okres_nazev = okres.get("nazev") if isinstance(okres, dict) else None
    return join_parts(
        pick_value(raw_event, "ulice", "Ulice"),
        pick_value(raw_event, "castObce", "CastObce"),
        pick_value(raw_event, "obec", "Obec"),
        okres_nazev,
    )


def build_type(raw_event):
    text_type = str(pick_value(raw_event, "typ", "Typ") or "").strip()
    if text_type:
        return text_type

    podtyp_id = pick_value(raw_event, "podtypId", "PodtypId")
    typ_id = pick_value(raw_event, "typId", "TypId")
    stav_id = pick_value(raw_event, "stavId", "StavId")

    if podtyp_id:
        return f"Incident {podtyp_id}"
    if typ_id:
        return f"Incident {typ_id}"
    if stav_id:
        return f"Incident {stav_id}"
    return "Incident"


def build_summary(event):
    typ_id = event.get("typId")
    podtyp_id = event.get("podtypId")
    obec = event.get("obec") or event["misto"]

    emoji = TYPE_EMOJIS.get(typ_id, "🚨")
    subtype_label = SUBTYPE_LABELS.get(podtyp_id, "")

    if subtype_label:
        return f"{emoji} {subtype_label} - {obec}"
    return f"{emoji} {obec}"


def jtsk_to_wgs84(gis1, gis2):
    try:
        # EPSG:5514 (East North) with always_xy=True: input (Easting, Northing) → (lng, lat)
        # API values are traditional Krovak: gis1 ≈ Westing, gis2 ≈ Southing (both positive)
        # EPSG:5514 Easting = −Westing, Northing = −Southing → negate both
        lng, lat = _jtsk_to_wgs84.transform(-float(gis1), -float(gis2))
        if not (49 <= lat <= 51 and 12 <= lng <= 19):  # bounding box ČR
            return None, None
        return lat, lng
    except Exception:
        return None, None


def build_geo(event):
    """Return (lat, lng) from S-JTSK coordinates, or (None, None)."""
    gis1 = event.get("gis1")
    gis2 = event.get("gis2")
    if gis1 and gis2:
        return jtsk_to_wgs84(gis1, gis2)
    return None, None


def _get_with_retry(url, params=None, timeout=TIMEOUT_SECONDS, max_retries=3):
    last_exc = None
    for attempt in range(max_retries):
        try:
            response = requests.get(url, params=params, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                print(
                    f"Request failed (attempt {attempt + 1}/{max_retries}), retrying in {wait}s: {exc}",
                    file=sys.stderr,
                )
                time.sleep(wait)
    raise last_exc


def fetch_technics(event_id):
    try:
        url = f"http://webohled.hasici-vysocina.cz/udalosti/api/udalosti/{event_id}/technika"
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []
    except Exception:
        return []


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


def fetch_events(okres_id=OKRES_ID):
    now = utc_now()
    since = now - timedelta(hours=48)

    params = {
        "krajId": KRAJ_ID,
        "casOd": format_api_datetime(since),
        "casDo": format_api_datetime(now),
    }
    if okres_id is not None:
        params["okresId"] = okres_id
    for stav_id in STAV_IDS:
        params.setdefault("stavIds", []).append(stav_id)

    response = _get_with_retry(API_URL, params=params)

    try:
        data = response.json()
    except ValueError as exc:
        raise requests.RequestException(f"Invalid JSON from API: {exc}") from exc
    if isinstance(data, list):
        raw_events = data
    elif isinstance(data, dict):
        raw_events = (
            data.get("items")
            or data.get("data")
            or data.get("udalosti")
            or data.get("events")
        )
    else:
        raw_events = None

    if not isinstance(raw_events, list):
        RAW_RESPONSE_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        raise ValueError("API response does not contain a list of events")

    events = []
    seen_ids = set()

    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue

        event_id = pick_value(raw_event, "id", "Id", "ID")
        cas_vzniku = pick_value(
            raw_event, "casVzniku", "CasVzniku", "casOhlaseni", "CasOhlaseni"
        )
        typ = build_type(raw_event)
        misto = str(pick_value(raw_event, "misto", "Misto") or "").strip() or build_location(raw_event)

        if not event_id or not cas_vzniku or not typ or not misto:
            continue

        event_id = str(event_id)
        if event_id in seen_ids:
            continue

        event_dt = parse_event_datetime(cas_vzniku)
        seen_ids.add(event_id)

        typ_id = pick_value(raw_event, "typId", "TypId")
        podtyp_id = pick_value(raw_event, "podtypId", "PodtypId")
        obec = str(pick_value(raw_event, "obec", "Obec") or "").strip()
        ulice = str(pick_value(raw_event, "ulice", "Ulice") or "").strip()
        gis1 = pick_value(raw_event, "gis1")
        gis2 = pick_value(raw_event, "gis2")

        events.append(
            {
                "id": event_id,
                "casVzniku": event_dt,
                "typ": typ,
                "typId": int(typ_id) if typ_id is not None else None,
                "podtypId": int(podtyp_id) if podtyp_id is not None else None,
                "obec": obec,
                "ulice": ulice,
                "gis1": gis1,
                "gis2": gis2,
                "misto": misto,
                "popis": str(
                    pick_value(
                        raw_event,
                        "popis",
                        "Popis",
                        "poznamkaProMedia",
                        "PoznamkaProMedia",
                    )
                    or ""
                ).strip(),
                "technika": fetch_technics(event_id),
            }
        )

    events.sort(key=lambda item: (item["casVzniku"], item["id"]))

    print(
        f"API returned {len(raw_events)} items, accepted {len(events)} events.",
        file=sys.stderr,
    )
    if raw_events and not events:
        RAW_RESPONSE_PATH.write_text(
            json.dumps(raw_events[:5], ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        print(
            f"No events matched expected fields. Sample saved to {RAW_RESPONSE_PATH}.",
            file=sys.stderr,
        )

    return events[-MAX_EVENTS:]


def build_ics(events, name="Hasiči Vysočina - okres"):
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//pokys//hasici-vysocina//CS",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{name}",
    ]

    for event in events:
        dt = format_ics_datetime(event["casVzniku"])
        dt_end = format_ics_datetime(event["casVzniku"] + timedelta(hours=1))
        summary = escape_ics_text(build_summary(event))

        lines.extend(
            [
                "BEGIN:VEVENT",
                fold_ics_line(f"UID:{escape_ics_text(event['id'])}"),
                f"DTSTART:{dt}",
                f"DTEND:{dt_end}",
                f"DTSTAMP:{dt}",
                fold_ics_line(f"SUMMARY:{summary}"),
            ]
        )

        location_parts = [p for p in [event.get("ulice"), event.get("obec")] if p]
        if location_parts:
            lines.append(fold_ics_line(f"LOCATION:{escape_ics_text(', '.join(location_parts))}"))

        lat, lng = build_geo(event)
        if lat and lng:
            lines.append(f"GEO:{lat:.6f};{lng:.6f}")
            lines.append(f"URL:geo:{lat:.6f},{lng:.6f}")

        desc_parts = []
        if event["misto"] and event["misto"] != event.get("obec", ""):
            desc_parts.append(f"📍 {event['misto']}")
        if event["popis"]:
            desc_parts.append(f"💬 {event['popis']}")
        tech_items = event.get("technika") or []
        tech_lines = []
        for t in tech_items:
            typ_t = t.get("typ", "")
            jednotka = t.get("jednotka", "")
            pocet = t.get("pocet", 1)
            if typ_t:
                vehicle = abbrev_vehicle(typ_t)
                line = f"🚒 {vehicle}"
                if jednotka:
                    line += f" ({jednotka})"
                if pocet and pocet > 1:
                    line += f" ×{pocet}"
                tech_lines.append(line)
        if tech_lines:
            if desc_parts:
                desc_parts.append("")
            desc_parts.extend(tech_lines)
        if desc_parts:
            lines.append(fold_ics_line(f"DESCRIPTION:{escape_ics_text(chr(10).join(desc_parts))}"))

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def write_calendar(content, path):
    path.write_text(content, encoding="utf-8", newline="")


def load_notified(path=NOTIFIED_PATH):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if isinstance(data, list):
        return {eid: {"message_id": None, "chat_id": None, "sent_at": None, "content_hash": None} for eid in data}
    if isinstance(data, dict):
        return data
    return {}


def save_notified(records, path=NOTIFIED_PATH):
    path.write_text(json.dumps(records, sort_keys=True), encoding="utf-8")


def _parse_sent_at(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def compute_content_hash(event):
    tech_items = event.get("technika") or []
    tech_key = "|".join(
        sorted(
            f"{t.get('typ', '')}:{t.get('jednotka', '')}:{t.get('pocet', 1)}"
            for t in tech_items
        )
    )
    raw = f"{event.get('popis', '')}||{tech_key}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


_PRAGUE_TZ = ZoneInfo("Europe/Prague")


def format_telegram_message(event):
    cas = event["casVzniku"].astimezone(_PRAGUE_TZ)
    lines = [f"<b>{build_summary(event)}</b>"]
    lines.append(f"🕐 {cas.strftime('%-d. %-m. %H:%M')}")
    if event["misto"] and event["misto"] != event.get("obec", ""):
        lines.append(f"📍 {event['misto']}")
    if event["popis"]:
        lines.append(f"💬 {event['popis']}")
    tech_items = event.get("technika") or []
    tech_lines = []
    for t in tech_items:
        typ_t = t.get("typ", "")
        jednotka = t.get("jednotka", "")
        pocet = t.get("pocet", 1)
        if typ_t:
            vehicle = abbrev_vehicle(typ_t)
            line = f"🚒 {vehicle}"
            if jednotka:
                line += f" ({jednotka})"
            if pocet and pocet > 1:
                line += f" ×{pocet}"
            tech_lines.append(line)
    if tech_lines:
        lines.append("")
        lines.extend(tech_lines)
    lat, lng = build_geo(event)
    if lat and lng:
        lines.append(f"\n🗺 <a href=\"https://maps.google.com/maps?q={lat:.6f},{lng:.6f}\">Otevřít mapu</a>")
    return "\n".join(lines)


def send_telegram(token, chat_id, text):
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        response.raise_for_status()
        return response.json()["result"]["message_id"]
    except Exception as exc:
        print(f"Telegram notification failed: {exc}", file=sys.stderr)
        return None


def edit_telegram(token, chat_id, message_id, text):
    try:
        url = f"https://api.telegram.org/bot{token}/editMessageText"
        response = requests.post(url, json={
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text + "\n✏️ <i>aktualizováno</i>",
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=10)
        response.raise_for_status()
        return True
    except Exception as exc:
        print(f"Telegram edit failed (msg {message_id}): {exc}", file=sys.stderr)
        return False


EDIT_WINDOW = timedelta(hours=3)
PRUNE_AGE = timedelta(hours=6)


def notify_new_events(events, token, chat_id, notified_path=NOTIFIED_PATH):
    records = load_notified(notified_path)
    now = utc_now()
    changed = False

    for event in events:
        eid = event["id"]
        new_hash = compute_content_hash(event)
        text = format_telegram_message(event)

        if eid not in records:
            msg_id = send_telegram(token, chat_id, text)
            records[eid] = {
                "message_id": msg_id,
                "chat_id": str(chat_id),
                "sent_at": now.isoformat(),
                "content_hash": new_hash,
            }
            print(f"Telegram: notified event {eid}", file=sys.stderr)
            changed = True
        else:
            rec = records[eid]
            msg_id = rec.get("message_id")
            sent_at = _parse_sent_at(rec.get("sent_at"))

            if msg_id is None or sent_at is None:
                continue
            if now - sent_at > EDIT_WINDOW:
                continue
            if rec.get("content_hash") == new_hash:
                continue

            if edit_telegram(token, chat_id, msg_id, text):
                rec["content_hash"] = new_hash
                print(f"Telegram: edited event {eid}", file=sys.stderr)
                changed = True

    for eid in list(records.keys()):
        sent_at = _parse_sent_at(records[eid].get("sent_at"))
        if sent_at is not None and now - sent_at > PRUNE_AGE:
            del records[eid]
            changed = True

    if changed:
        save_notified(records, notified_path)


def main():
    try:
        events_okres = fetch_events(okres_id=OKRES_ID)
        write_calendar(
            build_ics(events_okres, name="Hasiči - Pelhřimov"),
            CALENDAR_PATH,
        )

        events_kraj = fetch_events(okres_id=None)
        write_calendar(
            build_ics(events_kraj, name="Hasiči - Vysočina"),
            CALENDAR_VYSOCINA_PATH,
        )
    except requests.RequestException as exc:
        print(f"API request failed after retries: {exc}", file=sys.stderr)
        return 0
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"Invalid API response: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 1

    print(f"Wrote {CALENDAR_PATH} with {len(events_okres)} events.")
    print(f"Wrote {CALENDAR_VYSOCINA_PATH} with {len(events_kraj)} events.")

    tg_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    tg_chat = os.environ.get("TELEGRAM_CHAT_ID")
    tg_chat_vysocina = os.environ.get("TELEGRAM_CHAT_ID_VYSOCINA")
    if tg_token and tg_chat:
        notify_new_events(events_okres, tg_token, tg_chat)
    else:
        print("Telegram not configured, skipping notifications.", file=sys.stderr)
    if tg_token and tg_chat_vysocina:
        notify_new_events(events_kraj, tg_token, tg_chat_vysocina, NOTIFIED_VYSOCINA_PATH)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
