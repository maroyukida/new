"""Utility for scraping gofile links from Yahoo Realtime Search.

This module provides a small CLI that mimics the requests a browser makes
when visiting Yahoo's realtime search page.  It calls the documented
pagination/autoscroll endpoints and extracts ``gofile`` links from the tweet
payloads that are returned.

The script purposefully keeps the request layer flexible – headers or cookies
can be supplied via a simple configuration file or environment variables so
that it can be adapted when Yahoo introduces anti-bot mitigations.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Iterable, Iterator, List, Optional, Sequence, Set

import requests


YAHOO_REALTIME_API = "https://search.yahoo.co.jp/realtime/api/v1"
GOFILE_PATTERN = re.compile(r"https?://(?:www\.)?gofile\.io/\S+")


@dataclass
class SearchWindow:
    """Pagination state for Yahoo's realtime search endpoints."""

    next_oldest_id: Optional[str] = None
    latest_id: Optional[str] = None
    offset: int = 1

    def advance(self, batch_size: int) -> None:
        self.offset += batch_size


class YahooRealtimeClient:
    """Lightweight client that wraps the Yahoo realtime search endpoints."""

    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self._ensure_default_headers()

    def _ensure_default_headers(self) -> None:
        headers = self.session.headers
        headers.setdefault(
            "User-Agent",
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        headers.setdefault("Accept", "application/json, text/javascript, */*; q=0.01")
        headers.setdefault("Accept-Language", "ja,en-US;q=0.9,en;q=0.8")
        headers.setdefault("Referer", "https://search.yahoo.co.jp/realtime/")

    def update_from_cookie_string(self, cookie_string: str) -> None:
        for assignment in cookie_string.split(";"):
            if not assignment.strip():
                continue
            name, _, value = assignment.strip().partition("=")
            if name and value:
                self.session.cookies.set(name, value)

    def pagination(
        self,
        query: str,
        window: SearchWindow,
        batch_size: int,
        relevance: int = 3,
    ) -> dict:
        params = {
            "p": query,
            "rkf": relevance,
            "b": window.offset,
        }
        if window.next_oldest_id:
            params["oldestTweetId"] = window.next_oldest_id

        response = self.session.get(f"{YAHOO_REALTIME_API}/pagination", params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()

        timeline = payload.get("timeline", {})
        window.next_oldest_id = timeline.get("nextOldestTweetId")
        window.latest_id = window.latest_id or timeline.get("latestTweetId")
        window.advance(batch_size)
        return payload

    def autoscroll(
        self,
        query: str,
        window: SearchWindow,
        relevance: int = 3,
    ) -> dict:
        if not window.latest_id:
            raise ValueError("autoscroll requires SearchWindow.latest_id to be set")

        params = {
            "p": query,
            "rkf": relevance,
            "b": -1,
            "latestTweetId": window.latest_id,
        }

        response = self.session.get(f"{YAHOO_REALTIME_API}/autoscroll", params=params, timeout=20)
        response.raise_for_status()
        payload = response.json()

        timeline = payload.get("timeline", {})
        window.latest_id = timeline.get("latestTweetId", window.latest_id)
        return payload


def extract_gofile_links(text: str) -> List[str]:
    return GOFILE_PATTERN.findall(text)


def extract_from_tweets(tweets: Iterable[dict]) -> Set[str]:
    links: Set[str] = set()
    for tweet in tweets:
        text = tweet.get("text")
        if not text:
            continue
        links.update(extract_gofile_links(text))
    return links


def iter_tweets_from_payload(payload: dict) -> Iterator[dict]:
    for entry in payload.get("timeline", {}).get("tweets", []):
        tweet = entry.get("tweet") if isinstance(entry, dict) else None
        if not tweet:
            continue
        yield tweet


def fetch_links(
    client: YahooRealtimeClient,
    query: str,
    pages: int,
    batch_size: int,
    relevance: int = 3,
) -> Set[str]:
    window = SearchWindow()
    collected: Set[str] = set()

    for _ in range(pages):
        payload = client.pagination(query, window, batch_size, relevance)
        collected.update(extract_from_tweets(iter_tweets_from_payload(payload)))
        if not window.next_oldest_id:
            break

    if window.latest_id:
        payload = client.autoscroll(query, window, relevance)
        collected.update(extract_from_tweets(iter_tweets_from_payload(payload)))

    return collected


def load_headers(path: Optional[str]) -> Optional[dict]:
    if not path:
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def configure_session_from_args(session: requests.Session, args: argparse.Namespace) -> None:
    session.trust_env = not args.no_env_proxies

    if args.proxy:
        for mapping in args.proxy:
            key, sep, value = mapping.partition("=")
            if not sep:
                raise ValueError("--proxy requires entries in the form scheme=url, e.g. https=http://proxy:8080")
            session.proxies[key.strip()] = value.strip()

    headers = load_headers(args.headers)
    if headers:
        session.headers.update(headers)

    cookie_string = args.cookies or os.getenv("YAHOO_COOKIE", "")
    if cookie_string:
        client = YahooRealtimeClient(session=session)
        client.update_from_cookie_string(cookie_string)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect gofile links from Yahoo realtime search.")
    parser.add_argument("query", nargs="?", default="gofile", help="Search keyword to use (default: gofile)")
    parser.add_argument("--pages", type=int, default=3, help="Number of pagination pages to request")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Assumed batch size per pagination request (used for offset calculation)",
    )
    parser.add_argument(
        "--relevance",
        type=int,
        default=3,
        help="Value for the 'rkf' parameter (3=最新順).",
    )
    parser.add_argument(
        "--headers",
        help="Path to JSON file containing additional HTTP headers to merge into the session",
    )
    parser.add_argument(
        "--cookies",
        help="Cookie string to append to the request (defaults to YAHOO_COOKIE environment variable)",
    )
    parser.add_argument(
        "--output",
        help="Optional path to write the collected links (defaults to stdout)",
    )
    parser.add_argument(
        "--no-env-proxies",
        action="store_true",
        help="Ignore proxy configuration inherited from environment variables.",
    )
    parser.add_argument(
        "--proxy",
        action="append",
        metavar="SCHEME=URL",
        help="Explicit proxy override, e.g. --proxy https=http://proxy:8080",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    session = requests.Session()
    configure_session_from_args(session, args)
    client = YahooRealtimeClient(session)

    try:
        links = fetch_links(client, args.query, args.pages, args.batch_size, args.relevance)
    except requests.HTTPError as exc:
        status = getattr(exc.response, "status_code", None)
        if status in {401, 403}:
            parser.error(
                (
                    "Request failed with an authorization error ({status}). Yahoo may be rejecting raw HTTP "
                    "clients—refresh your cookies/headers via har_session_extractor.py or switch to "
                    "a browser automation workflow."
                ).format(status=status)
            )
        elif status == 429:
            parser.error(
                "Yahoo returned HTTP 429 (rate limited). Reduce --pages, wait a bit, or try a "
                "different network."
            )
        else:
            parser.error(f"Request failed: {exc}")
        return 2
    except requests.exceptions.ProxyError as exc:
        parser.error(
            "Proxy connection failed. Try --no-env-proxies to bypass inherited settings or configure explicit --proxy entries."
        )
        return 2
    except requests.exceptions.ConnectionError as exc:
        parser.error(
            "Failed to reach search.yahoo.co.jp. Check your network connectivity or proxy settings (see --proxy)."
        )
        return 2
    except Exception as exc:  # pragma: no cover - defensive fallback
        parser.error(str(exc))
        return 2

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            for link in sorted(links):
                f.write(f"{link}\n")
    else:
        for link in sorted(links):
            print(link)

    return 0


if __name__ == "__main__":
    sys.exit(main())
