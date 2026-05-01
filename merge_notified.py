#!/usr/bin/env python3
"""Git merge driver for notified-*.json files.

Both sides are dict[event_id, record]. Merge takes the union of keys; when both
sides have the same key, prefer the record with non-null sent_at, or the one
with the more recent sent_at when both have it.

Invoked by git as: merge_notified.py %O %A %B (base, ours, theirs).
Writes the merged result to %A and exits 0 on success.
"""

import json
import sys


def load(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def pick(ours, theirs):
    ours_sent = ours.get("sent_at") if isinstance(ours, dict) else None
    theirs_sent = theirs.get("sent_at") if isinstance(theirs, dict) else None
    if ours_sent and theirs_sent:
        return theirs if theirs_sent > ours_sent else ours
    if theirs_sent and not ours_sent:
        return theirs
    return ours


def main():
    if len(sys.argv) < 4:
        print("usage: merge_notified.py BASE OURS THEIRS", file=sys.stderr)
        return 2

    _, ours_path, theirs_path = sys.argv[1:4]
    ours = load(ours_path)
    theirs = load(theirs_path)

    if not isinstance(ours, dict) or not isinstance(theirs, dict):
        return 1

    merged = dict(ours)
    for eid, rec in theirs.items():
        if eid in merged:
            merged[eid] = pick(merged[eid], rec)
        else:
            merged[eid] = rec

    with open(ours_path, "w", encoding="utf-8") as f:
        json.dump(merged, f, sort_keys=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
