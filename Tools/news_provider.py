import feedparser
import os
import html
import re
import time
import asyncio
from datetime import datetime
from livekit.agents import function_tool
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from livekit import rtc
import json

_room = None

def set_room_context(room: rtc.Room):
    global _room
    _room = room

async def _broadcast_news(articles, query):
    if _room and _room.local_participant:
        try:
            payload = json.dumps({
                "type": "NEWS_DATA",
                "query": query,
                "articles": articles,
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }).encode('utf-8')
            await _room.local_participant.publish_data(payload, reliable=True)
            logger.info(f"Successfully broadcasted {len(articles)} news items to frontend")
        except Exception as e:
            logger.error(f"Failed to broadcast news: {e}")

MAX_NEWS_COUNT = 10
RSS_TIMEOUT = 12

RSS_FEEDS = {
    "india": "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
    "usa": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    "uk": "https://feeds.bbci.co.uk/news/uk/rss.xml",
    "australia": "https://feeds.bbci.co.uk/news/world/australia/rss.xml",
    "canada": "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "sports": "https://feeds.bbci.co.uk/news/sport/rss.xml",
    "entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml",
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "general": "https://feeds.bbci.co.uk/news/rss.xml"
}

KEYWORD_MAPPING = {
    "today": "world",
    "latest": "world",
    "current": "world",
    "news": "world",
    "headlines": "world",
    "top": "world",
    "batao": "india",
    "sunao": "india",
    "khabar": "india",
    "samachar": "india",
    "breaking news": "world",
    "bol ke baate": "india"
}

@function_tool()
async def get_top_news(country: str = "india", count: int = 10) -> dict:
    """Fetch the top RSS headlines for a category or conversational query."""
    try:
        count = min(max(count or 1, 1), MAX_NEWS_COUNT)
        country_key = (country or "india").strip().lower()
        if country_key in KEYWORD_MAPPING:
            country_key = KEYWORD_MAPPING[country_key]

        if country_key not in RSS_FEEDS:
            available = ", ".join(sorted(RSS_FEEDS.keys()))
            error = f"Unknown news category '{country}'. Available options: {available}"
            logger.error(error)
            return {"status": "error", "error": error, "articles": []}

        feed_url = RSS_FEEDS[country_key]
        logger.info(f"Fetching RSS feed for '{country_key}' at {feed_url}")

        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

        if getattr(feed, "bozo", False):
            error = str(getattr(feed, "bozo_exception", "RSS parsing failed"))
            logger.error(f"RSS parse error: {error}")
            return {"status": "error", "error": error, "articles": []}

        if not getattr(feed, "entries", None):
            error = "No news entries found in RSS feed."
            logger.warning(error)
            return {"status": "error", "error": error, "articles": []}

        entries = sorted(
            feed.entries,
            key=lambda entry: _entry_timestamp(entry) or 0,
            reverse=True
        )[:count]

        articles = [_build_article(entry) for entry in entries]

        summary_text = _format_summary_text(articles, country_key)

        asyncio.create_task(_broadcast_news(articles, country_key))

        return {
            "status": "ok",
            "source": "rss",
            "category": country_key,
            "query": country,
            "fetched_at": datetime.utcnow().isoformat() + "Z",
            "summary": summary_text,
            "articles": articles
        }

    except Exception as e:
        logger.error(f"get_top_news failure: {e}")
        return {"status": "error", "error": str(e), "articles": []}


def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", "", str(text))
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _entry_timestamp(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if parsed:
        return time.mktime(parsed)
    return None


def _build_article(entry):
    summary = _clean_text(entry.get("summary", entry.get("description", "")))
    published_at = entry.get("published") or entry.get("updated") or ""
    image_url = None
    if "media_content" in entry and entry.media_content:
        image_url = entry.media_content[0].get("url")
    elif "links" in entry:
        for link in entry.links:
            if link.get("rel") == "enclosure" and "image" in link.get("type", ""):
                image_url = link.get("href")
                break

    return {
        "title": _clean_text(entry.get("title", "No Title")),
        "summary": summary,
        "url": entry.get("link", ""),
        "source": _clean_text(entry.get("source", {}).get("title", "RSS Feed") if isinstance(entry.get("source"), dict) else entry.get("source", "RSS Feed")),
        "publishedAt": published_at,
        "image": image_url
    }


def _format_summary_text(articles, category):
    lines = [f"Top {len(articles)} headlines for {category}." ]
    for index, item in enumerate(articles, 1):
        lines.append(f"Headline {index}. {item['title']}.")
    return " ".join(lines)

