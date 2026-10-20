#!/usr/bin/env python3
"""Collect RSS/Atom items into a dated JSON archive."""
import hashlib
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FEEDS = ROOT / "config" / "feeds.txt"
ARCHIVE = ROOT / "archive"
TIMEOUT = 20
MAX_FEED_BYTES = 8 * 1024 * 1024
RECENT_DAYS = 7

HEADERS = {
    "User-Agent": "SudanNewsArchive/1.1 (RSS reader)"
}


class HTMLTextExtractor(HTMLParser):
    """Extract readable text from HTML fragments."""
    BLOCK_TAGS = {
        "p", "div", "br", "li", "tr", "h1", "h2", "h3",
        "h4", "h5", "h6", "section", "article"
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.ignored += 1
        elif self.ignored == 0 and tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style"} and self.ignored:
            self.ignored -= 1
        elif self.ignored == 0 and tag in self.BLOCK_TAGS:
            self.parts.append(" ")

    def handle_data(self, data):
        if self.ignored == 0:
            self.parts.append(data)


def clean_html(value):
    if not value:
        return ""
    parser = HTMLTextExtractor()
    try:
        parser.feed(value)
        parser.close()
        value = " ".join(parser.parts)
    except Exception:
        pass
    return re.sub(r"\s+", " ", value).strip()[:3000]


def text_of(element, names):
    for name in names:
        found = element.find(name)
        if found is not None:
            value = "".join(found.itertext()).strip()
            if value:
                return value
    return ""


def get_link(item, atom=False):
    if not atom:
        return text_of(item, ["link", "{*}link"])
    for link in item.findall("{*}link"):
        if link.attrib.get("rel", "alternate") == "alternate":
            href = link.attrib.get("href", "").strip()
            if href:
                return href
    return ""


def parse_datetime(value):
    """Return a timezone-aware UTC datetime, or None if invalid."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        try:
            dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except (TypeError, ValueError, OverflowError):
            return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_date(value):
    dt = parse_datetime(value)
    if dt is not None:
        return dt.isoformat()
    return value.strip() if value else ""


def classify_freshness(published_at, now):
    """Classify publication age without deleting old or undated items."""
    published = parse_datetime(published_at)
    if published is None:
        return "unknown_date", None

    age_seconds = (now - published).total_seconds()
    if age_seconds < 0:
        return "future_date", None

    age_days = int(age_seconds // 86400)
    if age_days <= RECENT_DAYS:
        return "recent", age_days
    return "old", age_days



def classify_content_type(title, summary):
    text = (title + " " + summary).lower()
    promo = ["donate", "donation", "help us", "support our", "fundraise", "تبرع", "ادعم", "حملة تبرع"]
    opinion = ["opinion", "op-ed", "analysis", "commentary", "editorial", "رأي", "تحليل", "مقال"]
    if any(word in text for word in promo):
        return "promotional"
    if any(word in text for word in opinion):
        return "opinion_analysis"
    return "uncertain"

def classify_relevance(title, summary):
    text = (title + " " + summary).lower()
    direct = ["sudan", "khartoum", "darfur", "sudanese", "السودان", "الخرطوم", "دارفور", "سوداني"]
    indirect = ["egypt", "ethiopia", "chad", "south sudan", "red sea", "مصر", "إثيوبيا", "تشاد", "جنوب السودان"]
    if any(word in text for word in direct):
        return "direct"
    if any(word in text for word in indirect):
        return "indirect"
    return "unclear"

def fetch_feed(url):

    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        raw = response.read(MAX_FEED_BYTES + 1)

    if len(raw) > MAX_FEED_BYTES:
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
            [
                "pubDate", "published", "updated",
                "{*}published", "{*}updated", "{*}pubDate"
            ],
        )
        summary = text_of(
            item,
            [
                "description", "summary", "content",
                "{*}description", "{*}summary", "{*}content"
            ],
        )
        guid = text_of(item, ["guid", "id", "{*}id"])
        identity = link.strip() or guid.strip() or title

        records.append({
            "id": hashlib.sha256(identity.encode("utf-8")).hexdigest(),
            "title": re.sub(r"\s+", " ", title).strip(),
            "url": link.strip(),
            "published_at": parse_date(published),
            "summary": clean_html(summary),
            "source_feed": url,
            "verification_status": "unverified",
            "content_type": classify_content_type(title, clean_html(summary)),
            "relevance_to_sudan": classify_relevance(title, clean_html(summary)),
            "classification_method": "keyword_rules",
        })

    return records


def normalized_url(url):
    return url.strip().rstrip("/")


def main():
    if not FEEDS.exists():
        raise SystemExit("Missing config/feeds.txt")

    urls = []
    for line in FEEDS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("https://", "http://")):
            urls.append(line)
        else:
            print(f"SKIP invalid feed URL: {line}")

    urls = list(dict.fromkeys(urls))
    if not urls:
        print("No feeds configured. Add RSS/Atom URLs to config/feeds.txt.")
        return

    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    records = []
    failures = []

    for url in urls:
        try:
            found = fetch_feed(url)
            records.extend(found)
            print(f"OK: {url} — {len(found)} items")
        except Exception as exc:
            failures.append({"feed": url, "error": str(exc)})
            print(f"ERROR: {url} — {exc}")

    # Deduplicate the current collection by URL.
    unique = {}
    for item in records:
        key = normalized_url(item["url"])
        if key:
            unique.setdefault(key, item)

    target = ARCHIVE / now.strftime("%Y") / now.strftime("%m") / f"{day}.json"
    target.parent.mkdir(parents=True, exist_ok=True)

    existing = []
    if target.exists():
        try:
            old_payload = json.loads(target.read_text(encoding="utf-8"))
            existing = old_payload.get("items", [])
            if not isinstance(existing, list):
                existing = []
        except (OSError, json.JSONDecodeError, AttributeError):
            print(f"WARNING: Could not read existing archive: {target}")

    # Keep previously archived items, while allowing refreshed feed data
    # to update titles, summaries, dates, and source information.
    merged = {}
    for item in existing:
        if isinstance(item, dict):
            key = normalized_url(item.get("url", ""))
            if key:
                merged[key] = item

    for key, item in unique.items():
        merged[key] = item

    # Recalculate freshness every run; never use it to delete an item.
    for item in merged.values():
        status, age_days = classify_freshness(item.get("published_at", ""), now)
        item["freshness_status"] = status
        item["age_days"] = age_days
        if "content_type" not in item:
            item["content_type"] = classify_content_type(item.get("title", ""), item.get("summary", ""))
        if "relevance_to_sudan" not in item:
            item["relevance_to_sudan"] = classify_relevance(item.get("title", ""), item.get("summary", ""))
        if "classification_method" not in item:
            item["classification_method"] = "keyword_rules"

    payload = {
        "date_utc": day,
        "collected_at_utc": now.isoformat(),
        "source_count": len(urls),
        "item_count": len(merged),
        "failed_feeds": failures,
        "freshness_rule": f"recent means 0-{RECENT_DAYS} days old",
        "items": list(merged.values()),
        "notes": (
            "Items are unverified claims or publications, not confirmed facts. "
            "Freshness describes publication age, not accuracy or importance. "
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
