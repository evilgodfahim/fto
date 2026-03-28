#!/usr/bin/env python3
import feedparser
import requests
from xml.dom.minidom import Document
import email.utils
from datetime import datetime, timezone

RSS_URLS = [
    "https://www.ft.com/rss/comment/opinion"
]

ARCHIVE_PREFIX = "https://archive.is/qWySo/"
OUTPUT_FILE = "combined.xml"
FLARESOLVERR_URL = "http://localhost:8191/v1"
FLARESOLVERR_TIMEOUT = 60  # seconds


def fetch_via_flaresolverr(url):
    """
    Fetch a URL through FlareSolverr. Returns raw response string on success, None on failure.
    """
    try:
        resp = requests.post(
            FLARESOLVERR_URL,
            json={
                "cmd": "request.get",
                "url": url,
                "maxTimeout": FLARESOLVERR_TIMEOUT * 1000,
            },
            timeout=FLARESOLVERR_TIMEOUT + 10,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "ok":
            raw = data["solution"]["response"]
            if raw:
                return raw
            print(f"⚠️  FlareSolverr returned empty body for {url}")
    except requests.exceptions.ConnectionError:
        print(f"⚠️  FlareSolverr not reachable at {FLARESOLVERR_URL} — falling back to direct fetch")
    except Exception as e:
        print(f"⚠️  FlareSolverr error for {url}: {e}")
    return None


def parse_feed(url):
    """
    Try FlareSolverr first. If it yields entries, use those.
    Fall back to direct feedparser.parse(url) otherwise.
    """
    raw = fetch_via_flaresolverr(url)
    if raw:
        feed = feedparser.parse(raw)
        if feed.entries:
            print(f"✅ FlareSolverr: {len(feed.entries)} entries from {url}")
            return feed
        print(f"⚠️  FlareSolverr content parsed but no entries found for {url} — falling back")

    feed = feedparser.parse(url)
    status = "✅" if feed.entries else "❌"
    print(f"{status} Direct feedparser: {len(feed.entries)} entries from {url}")
    return feed


def parse_entry_datetime(entry):
    from time import mktime
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)
    return datetime.now(tz=timezone.utc)


# --- Build XML ---

doc = Document()
rss = doc.createElement("rss")
rss.setAttribute("version", "2.0")
doc.appendChild(rss)

channel = doc.createElement("channel")
rss.appendChild(channel)
channel.appendChild(doc.createElement("title")).appendChild(
    doc.createTextNode("Project Syndicate Archive Feed")
)
channel.appendChild(doc.createElement("link")).appendChild(
    doc.createTextNode("https://www.project-syndicate.org/")
)
channel.appendChild(doc.createElement("description")).appendChild(
    doc.createTextNode("Combined feed with archive links")
)

all_entries = []

for feed_url in RSS_URLS:
    feed = parse_feed(feed_url)
    for entry in feed.entries:
        dt = parse_entry_datetime(entry)
        all_entries.append({
            "title": getattr(entry, "title", "Untitled"),
            "orig_link": entry.link,
            "archive_link": ARCHIVE_PREFIX + entry.link,
            "summary": getattr(entry, "summary", "") or getattr(entry, "description", ""),
            "published_dt": dt,
        })

all_entries.sort(key=lambda x: x["published_dt"], reverse=True)

for it in all_entries:
    item_el = doc.createElement("item")
    channel.appendChild(item_el)
    item_el.appendChild(doc.createElement("title")).appendChild(
        doc.createTextNode(it["title"])
    )
    item_el.appendChild(doc.createElement("link")).appendChild(
        doc.createTextNode(it["archive_link"])
    )
    item_el.appendChild(doc.createElement("guid")).appendChild(
        doc.createTextNode(it["orig_link"])
    )
    item_el.appendChild(doc.createElement("description")).appendChild(
        doc.createTextNode(it["summary"])
    )
    pubdate = email.utils.format_datetime(it["published_dt"])
    item_el.appendChild(doc.createElement("pubDate")).appendChild(
        doc.createTextNode(pubdate)
    )

with open(OUTPUT_FILE, "wb") as f:
    f.write(doc.toxml(encoding="utf-8"))

print(f"✅ combined.xml generated with {len(all_entries)} articles.")
