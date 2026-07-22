"""Fill a CSV test plan with the live ASK Vera bot responses.

This script reads a CSV test plan, calls the deployed widget API for each
question, and writes a new CSV with the "Bot Actual Response" column filled.
It intentionally leaves pass/fail judgement to a human reviewer.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_API_URL = "https://api.vera-api.xyz"
DEFAULT_ORIGIN = "http://localhost:9000"
DEFAULT_WIDGET_ID = "askvera-demo"
ACTUAL_RESPONSE_COLUMN = "Bot Actual Response"
COUNTRY_CODES = {
    "canada": "CA",
    "ca": "CA",
    "united states": "US",
    "usa": "US",
    "us": "US",
    "u.s.": "US",
}
LANGUAGE_CODES = {
    "english": "en",
    "en": "en",
    "french": "fr",
    "français": "fr",
    "francais": "fr",
    "fr": "fr",
    "spanish": "es",
    "español": "es",
    "espanol": "es",
    "es": "es",
}
ROLE_CODES = {
    "new_prospect": "new_prospect",
    "prospect": "new_prospect",
    "preferred_customer": "new_prospect",
    "preferred customer": "new_prospect",
    "retail_customer": "new_prospect",
    "retail customer": "new_prospect",
    "customer": "new_prospect",
    "fbo": "active_distributor",
    "distributor": "active_distributor",
    "active_distributor": "active_distributor",
    "active distributor": "active_distributor",
    "compliance_officer": "compliance_officer",
    "compliance officer": "compliance_officer",
}


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int) -> dict[str, Any]:
    request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            **headers,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach {url}: {exc.reason}") from exc


def _init_widget(api_url: str, widget_id: str, origin: str, timeout: int) -> str:
    envelope = _post_json(
        f"{api_url.rstrip('/')}/api/widget/init",
        {"widgetId": widget_id, "origin": origin},
        {"Origin": origin},
        timeout,
    )
    token = ((envelope.get("data") or {}).get("token") or "").strip()
    if not token:
        raise RuntimeError(f"Widget init did not return a token: {envelope}")
    return token


def _record_consent(api_url: str, token: str, origin: str, session_id: str, country: str, language: str, timeout: int) -> None:
    envelope = _post_json(
        f"{api_url.rstrip('/')}/api/consent",
        {
            "sessionId": session_id,
            "country": country,
            "lang": language,
            "timestamp": datetime.now(UTC).isoformat(),
            "version": "2026.1",
        },
        {"Origin": origin, "Authorization": f"Bearer {token}"},
        timeout,
    )
    if not envelope.get("success"):
        raise RuntimeError(f"Consent was not recorded: {envelope}")


def _ask_bot(
    api_url: str,
    token: str,
    origin: str,
    question: str,
    session_id: str,
    country: str,
    language: str,
    role: str,
    timeout: int,
) -> str:
    envelope = _post_json(
        f"{api_url.rstrip('/')}/api/chat",
        {
            "message": question,
            "sessionId": session_id,
            "country": country,
            "language": language,
            "role": role,
            "trafficSource": "evaluation",
        },
        {"Origin": origin, "Authorization": f"Bearer {token}"},
        timeout,
    )
    if not envelope.get("success"):
        error = envelope.get("error") or {}
        return f"ERROR: {error.get('code', 'UNKNOWN_ERROR')} - {error.get('message', envelope)}"

    data = envelope.get("data") or {}
    answer = str(data.get("response") or "").strip()
    sources = data.get("sources") or []
    references = []
    for source in sources:
        title = str(source.get("title") or "").strip()
        page = str(source.get("page") or "").strip()
        if title and page:
            references.append(f"{title}, p. {page}")
        elif title:
            references.append(title)
    if references:
        answer = f"{answer}\n\nReferences:\n" + "\n".join(f"- {reference}" for reference in references)
    return answer


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    last_error: UnicodeDecodeError | None = None
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with path.open("r", newline="", encoding=encoding) as handle:
                reader = csv.DictReader(handle)
                rows = list(reader)
                fieldnames = list(reader.fieldnames or [])
            break
        except UnicodeDecodeError as exc:
            last_error = exc
    else:
        raise RuntimeError(f"Could not read CSV encoding for {path}") from last_error

    if ACTUAL_RESPONSE_COLUMN not in fieldnames:
        fieldnames.append(ACTUAL_RESPONSE_COLUMN)
        for row in rows:
            row.setdefault(ACTUAL_RESPONSE_COLUMN, "")
    return fieldnames, rows


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _country_code(value: str) -> str:
    normalized = value.strip().lower()
    return COUNTRY_CODES.get(normalized, value.strip().upper())


def _language_code(value: str) -> str:
    normalized = value.strip().lower()
    return LANGUAGE_CODES.get(normalized, normalized)


def _role_code(value: str) -> str:
    normalized = value.strip().lower()
    return ROLE_CODES.get(normalized, normalized or "new_prospect")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Input CSV test plan.")
    parser.add_argument("--output", type=Path, help="Output CSV path. Defaults to *_with_bot_responses.csv.")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--widget-id", default=DEFAULT_WIDGET_ID)
    parser.add_argument("--origin", default=DEFAULT_ORIGIN)
    parser.add_argument("--delay-seconds", type=float, default=1.0, help="Pause between questions to avoid rate limits.")
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of blank rows to fill.")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing bot responses.")
    parser.add_argument("--retry-errors", action="store_true", help="Replace cells that currently start with ERROR:.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = args.output or args.input.with_name(f"{args.input.stem}_with_bot_responses.csv")
    fieldnames, rows = _read_csv(args.input)
    token = _init_widget(args.api_url, args.widget_id, args.origin, args.timeout_seconds)

    filled = 0
    for index, row in enumerate(rows, start=1):
        question = (row.get("Test Question") or "").strip()
        if not question:
            continue
        existing_response = row.get(ACTUAL_RESPONSE_COLUMN, "").strip()
        should_retry_error = args.retry_errors and existing_response.startswith("ERROR:")
        if existing_response and not args.overwrite and not should_retry_error:
            continue
        if args.limit and filled >= args.limit:
            break

        country = _country_code(row.get("Country") or "CA")
        language = _language_code(row.get("Language") or "en")
        role = _role_code(row.get("User Role") or "new_prospect")
        session_id = f"csv-{row.get('Test ID', index)}-{uuid.uuid4()}"

        print(f"[{index}/{len(rows)}] Asking {row.get('Test ID', '')}: {question}")
        try:
            _record_consent(args.api_url, token, args.origin, session_id, country, language, args.timeout_seconds)
            row[ACTUAL_RESPONSE_COLUMN] = _ask_bot(
                args.api_url,
                token,
                args.origin,
                question,
                session_id,
                country,
                language,
                role,
                args.timeout_seconds,
            )
        except RuntimeError as exc:
            row[ACTUAL_RESPONSE_COLUMN] = f"ERROR: {exc}"

        filled += 1
        _write_csv(output, fieldnames, rows)
        if args.delay_seconds > 0:
            time.sleep(args.delay_seconds)

    _write_csv(output, fieldnames, rows)
    print()
    print(f"Filled responses: {filled}")
    print(f"Output CSV: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
