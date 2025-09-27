"""Extract Yahoo realtime search session headers and cookies from a HAR file.

This helper inspects a browser-exported HAR capture, finds requests to
Yahoo's realtime search API, and produces artifacts that can be fed into the
`scrape_gofile_links.py` CLI (`--headers` JSON file and cookie string or
YAHOO_COOKIE environment variable).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional

HEADER_EXCLUDE = {
    ":authority",
    ":method",
    ":path",
    ":scheme",
    "content-length",
    "cookie",
}

DEFAULT_PATTERN = r"https://search\.yahoo\.co\.jp/realtime/api/v1/(pagination|autoscroll)"


def load_har(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def iter_matching_entries(har: dict, pattern: re.Pattern[str]) -> Iterable[dict]:
    log = har.get("log", {})
    entries: List[dict] = log.get("entries", [])
    for entry in entries:
        request = entry.get("request", {})
        url = request.get("url", "")
        if pattern.search(url):
            yield entry


def extract_headers(entry: dict) -> Dict[str, str]:
    headers: Dict[str, str] = {}
    for header in entry.get("request", {}).get("headers", []):
        name = header.get("name")
        value = header.get("value")
        if not name or value is None:
            continue
        lower = name.lower()
        if lower in HEADER_EXCLUDE:
            continue
        headers[name] = value
    return headers


def extract_cookie(entry: dict) -> str:
    request = entry.get("request", {})
    # Prefer cookie header value because browsers send the exact string.
    for header in request.get("headers", []):
        if header.get("name", "").lower() == "cookie":
            return header.get("value", "")
    # Fall back to cookie objects in the HAR.
    cookie_pairs = []
    for cookie in request.get("cookies", []):
        name = cookie.get("name")
        value = cookie.get("value")
        if name and value:
            cookie_pairs.append(f"{name}={value}")
    return "; ".join(cookie_pairs)


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract Yahoo realtime search session data from a HAR file."
    )
    parser.add_argument("har", type=Path, help="Path to a HAR export captured in the browser")
    parser.add_argument(
        "--pattern",
        default=DEFAULT_PATTERN,
        help="Regex used to pick the request of interest (default targets pagination/autoscroll).",
    )
    parser.add_argument(
        "--headers-json",
        type=Path,
        help="Optional path to write the derived headers JSON file for scrape_gofile_links.py",
    )
    parser.add_argument(
        "--print-cookie",
        action="store_true",
        help="Print the cookie string that should be passed via --cookies or YAHOO_COOKIE.",
    )
    parser.add_argument(
        "--index",
        type=int,
        default=0,
        help="If multiple HAR entries match, choose the Nth (default: 0, the first match).",
    )

    args = parser.parse_args(list(argv) if argv is not None else None)

    har = load_har(args.har)
    pattern = re.compile(args.pattern)
    matches = list(iter_matching_entries(har, pattern))

    if not matches:
        parser.error(
            "No HAR entries matched the given pattern. Ensure you exported the pagination/autoscroll request."
        )
        return 2

    index = args.index
    if index < 0 or index >= len(matches):
        parser.error(f"--index {index} is out of range (found {len(matches)} matches)")
        return 2

    entry = matches[index]
    headers = extract_headers(entry)
    cookie_string = extract_cookie(entry)

    if args.headers_json:
        args.headers_json.write_text(json.dumps(headers, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {len(headers)} headers to {args.headers_json}")
    else:
        print(json.dumps(headers, indent=2, ensure_ascii=False))

    if args.print_cookie and cookie_string:
        print("\n# Cookie string")
        print(cookie_string)

    if not args.headers_json:
        print(
            "\nPass --headers pointing to a JSON file if you want to reuse these headers without re-running the extractor."
        )

    if args.print_cookie and cookie_string:
        print("\nYou can export this cookie via `export YAHOO_COOKIE=...` or pass it with --cookies.")

    if args.print_cookie and not cookie_string:
        print("\nNo cookie data found in the HAR entry.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
