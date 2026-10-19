#!/usr/bin/env python3
"""Collect RSS/Atom items into a dated JSON archive."""
import json
import os
import re
import hashlib
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDS = ROOT / "config" / "feeds.txt"
ARCHIVE = ROOT / "archive"
TIMEOUT = 20
HEADERS = {
    "User-Agent": "SudanNewsArchive/1.0 (RSS reader)"
}


def text_of(element, names):
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    return ""


def get_link(item, atom=False):
    if not atom:
        return text_of(item, ["link"])
    for link in item.findall("{*}link"):
        if link.attrib.get("rel", "alternate") == "alternate":
            href = link.attrib.get("href", "").strip()
            if href:
                return href
    return ""


def parse_date(value):
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return value.strip()


def fetch_feed(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read(8 * 1024 * 1024 + 1)
    if len(raw) > 8 * 1024 * 1024:
        raise ValueError("Feed exceeds 8 MiB")
    root = ET.fromstring(raw)
    atom = root.tag.endswith("feed")
    items = root.findall(".//{*}entry") if atom else root.findall(".//item")
    if not items and not atom:
        items = root.findall(".//{*}item")

    records = []
    for item in items:
        title = text_of(item, ["title", "{*}title"])
        link = get_link(item, atom=atom)
        if not title or not link:
            continue

        published = text_of(
            item,
            ["pubDate", "published", "updated", "{*}published", "{*}updated"]
        )
        summary = text_of(
            item,
            ["description", "summary", "content", "{*}summary", "{*}content"]
        )
        guid = text_of(item, ["guid", "id", "{*}id"])
        identity = link or guid or title
        records.append({
            "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "title": title,
            "url": link,
            "published_at": parse_date(published),
            "summary": re.sub(r"\s+", " ", summary)[:3000],
            "source_feed": url,
            "verification_status": "unverified",
        })
    return records


def main():
    if not FEEDS.exists():
        raise SystemExit("Missing config/feeds.txt")

    urls = []
    for line in FEEDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            if line.startswith(("https://", "http://")):
                urls.append(line)
            else:
                print(f"SKIP invalid feed URL: {line}")

    if not urls:
        print("No feeds configured. Add RSS/Atom URLs to config/feeds.txt.")
        return

    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    records = []
    failures = []

    for url in dict.fromkeys(urls):
        try:
            found = fetch_feed(url)
            records.extend(found)
            print(f"OK: {url} — {len(found)} items")
        except Exception as exc:
            failures.append({"feed": url, "error": str(exc)})
            print(f"ERROR: {url} — {exc}")

    # Deduplicate items within this collection by normalized URL.
    unique = {}
    for item in records:
        key = item["url"].strip().rstrip("/")
        if key:
            unique.setdefault(key, item)

    target = ARCHIVE / now.strftime("%Y") / now.strftime("%m") / f"{day}.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8")).get("items", [])
        except (OSError, json.JSONDecodeError):
            print(f"WARNING: Could not read existing archive: {target}")

    merged = {}
    for item in existing + list(unique.values()):
        merged.setdefault(item.get("url", "").strip().rstrip("/"), item)
    merged.pop("", None)

    payload = {
        "date_utc": day,
        "collected_at_utc": now.isoformat(),
        "source_count": len(set(urls)),
        "item_count": len(merged),
        "failed_feeds": failures,
        "items": list(merged.values()),
        "notes": (
            "Collected feed items are unverified claims, not confirmed facts. "
            "Repeated publication does not independently verify a claim."
        ),
    }
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Saved {len(merged)} items to {target}")


if __name__ == "__main__":
    main()
