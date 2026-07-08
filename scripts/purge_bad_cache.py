"""Purge cached ASK Vera responses from Redis/Valkey.

Run this from the API environment when a bad answer may have been cached.
Use --dry-run first to see matching keys.
"""

from __future__ import annotations

import argparse
import json
from typing import Iterable

from services.cache import init_cache


SUSPECT_PHRASES = (
    "path 1",
    "path 2",
    "60 open group case credits",
    "75 open group case credits",
    "120 open group case credits",
    "150 open group case credits",
)


def _iter_keys(client, pattern: str) -> Iterable[str]:
    cursor = 0
    while True:
        cursor, keys = client.scan(cursor=cursor, match=pattern, count=500)
        yield from keys
        if cursor == 0:
            break


def _looks_suspect(raw_value: str | None) -> bool:
    if not raw_value:
        return False
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError:
        payload = {"response": raw_value}
    response = str(payload.get("response", "")).lower()
    return any(phrase in response for phrase in SUSPECT_PHRASES)


def main() -> int:
    parser = argparse.ArgumentParser(description="Purge cached ASK Vera responses.")
    parser.add_argument("--country", default="*", help="Country segment to purge, for example CA.")
    parser.add_argument("--language", default="*", help="Language segment to purge, for example en.")
    parser.add_argument("--role", default="*", help="Role segment to purge, for example new-prospect.")
    parser.add_argument("--purge-all", action="store_true", help="Delete all matching keys.")
    parser.add_argument(
        "--purge-suspect",
        action="store_true",
        help="Delete only matching keys whose cached response contains known suspect phrases.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without deleting.")
    args = parser.parse_args()

    if not args.purge_all and not args.purge_suspect:
        parser.error("Choose --purge-all or --purge-suspect.")

    client = init_cache(correlation_id="cache-purge-script")
    if client is None:
        print("Cache is not configured.")
        return 1

    pattern = f"ask-vera:{args.country}:{args.language}:{args.role}:*"
    matched = 0
    deleted = 0

    for key in _iter_keys(client, pattern):
        matched += 1
        raw = client.get(key) if args.purge_suspect else None
        should_delete = args.purge_all or _looks_suspect(raw)
        if not should_delete:
            continue

        print(("Would delete" if args.dry_run else "Deleting") + f" {key}")
        if not args.dry_run:
            client.delete(key)
        deleted += 1

    print(f"Matched {matched} key(s); {'would delete' if args.dry_run else 'deleted'} {deleted}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
