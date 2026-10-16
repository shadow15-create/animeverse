import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from email.utils import parsedate_to_datetime

OUTPUT_FILE = Path("news.json")
MAX_ARTICLES = 100
TIMEOUT = 20

FEEDS = [
    {
        "name": "MyAnimeList",
        "url": "https://myanimelist.net/rss/news.xml",
    },
    {
        "name": "Anime News Network",
        "url": "https://www.animenewsnetwork.com/all/rss.xml?ann-edition=us",
    },
    {
        "name": "Crunchyroll",
        "url": "https://cr-news-api-service.prd.crunchyrollsvc.com/v1/en-US/rss",
    },
]


def clean_text(value):
    if not value:
        return ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def get_text(element, names):
    for child in element.iter():
        tag = child.tag.split("}")[-1].lower()
        if tag in names and child.text:
            return child.text.strip()
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
            return datetime.fromisoformat(
                value.replace("Z", "+00:00")
            ).astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError):
            return ""


def fetch_feed(feed):
    request = urllib.request.Request(
        feed["url"],
        headers={
            "User-Agent": "ANIMEVERSE-NewsBot/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )

    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        content = response.read(4_000_000)

    root = ET.fromstring(content)
    articles = []

    for item in root.iter():
        tag = item.tag.split("}")[-1].lower()
        if tag not in ("item", "entry"):
            continue

        title = get_text(item, {"title"})
        link = get_text(item, {"link"})

        if not link:
            for child in item:
                if child.tag.split("}")[-1].lower() == "link":
                    link = child.attrib.get("href", "")
                    if link:
                        break

        description = get_text(
            item, {"description", "summary", "content"}
        )
        published = get_text(
            item, {"pubdate", "published", "updated", "date"}
        )

        if not title or not link.startswith(("https://", "http://")):
            continue

        articles.append({
            "title": clean_text(title),
            "url": link,
            "source": feed["name"],
            "published": parse_date(published),
            "summary": clean_text(description)[:500],
        })

    return articles


def main():
    articles = []
    successful_sources = []
    failed_sources = []

    for feed in FEEDS:
        try:
            fetched = fetch_feed(feed)
            articles.extend(fetched)
            successful_sources.append(feed["name"])
            print(f'{feed["name"]}: {len(fetched)} articles')
        except Exception as error:
            failed_sources.append(feed["name"])
            print(f'{feed["name"]}: unavailable ({error})')

    if not successful_sources:
        raise RuntimeError(
            "All news feeds failed. Existing news.json was not changed."
        )

    unique = {}
    for article in articles:
        key = article["url"].split("#")[0].rstrip("/")
        if key not in unique:
            unique[key] = article

    result = sorted(
        unique.values(),
        key=lambda article: article["published"],
        reverse=True,
    )[:MAX_ARTICLES]

    output = {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "sourcesUpdated": successful_sources,
        "sourcesUnavailable": failed_sources,
        "articles": result,
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"Saved {len(result)} unique articles to news.json")


if __name__ == "__main__":
    main()
