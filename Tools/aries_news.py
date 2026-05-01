"""
ARIES - News & Information Module
Fetches recent and reliable news from trusted sources with support for World, State, and City news.
"""

from datetime import datetime, timedelta, timezone
import aiohttp
import feedparser
import asyncio
from typing import Optional, List, Dict
from livekit.agents import function_tool
from livekit import rtc
import os
import json
from dotenv import load_dotenv
import logging
import re
import html
import time

# Global room context for broadcasting data to frontend
_room: Optional[rtc.Room] = None

def set_room_context(room: rtc.Room):
    global _room
    _room = room

# Configure logging
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# News API (requires free API key from newsapi.org)
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
NEWS_API_URL = "https://newsapi.org/v2"

# RSS feeds from trusted sources
TRUSTED_RSS_FEEDS = {
    "world": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "india": "https://feeds.bbci.co.uk/news/world/asia/india/rss.xml",
    "mumbai": "https://timesofindia.indiatimes.com/rssfeeds/-2128830453.cms", # TOI Mumbai
    "maharashtra": "https://timesofindia.indiatimes.com/rssfeeds/3947067.cms", # TOI Maharashtra
    "technology": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    "business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "science": "https://www.sciencedaily.com/rss/all.xml",
    "sports": "https://feeds.bbci.co.uk/news/sport/rss.xml",
    "entertainment": "https://feeds.bbci.co.uk/news/entertainment_and_arts/rss.xml"
}

async def _broadcast_news(articles: List[Dict], query: str):
    """Broadcast news data to the frontend via LiveKit DataChannel"""
    if _room and _room.local_participant:
        try:
            payload = json.dumps({
                "type": "NEWS_DATA",
                "query": query,
                "articles": articles,
                "timestamp": datetime.now().isoformat()
            }).encode('utf-8')
            await _room.local_participant.publish_data(payload, reliable=True)
            logger.info(f"Successfully broadcasted {len(articles)} news items to frontend")
        except Exception as e:
            logger.error(f"Failed to broadcast news: {e}")

async def _async_fetch_url(url: str, params: dict = None) -> dict:
    """Helper to fetch JSON from URL asynchronously"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as response:
                if response.status != 200:
                    logger.error(f"Error fetching {url}: {response.status}")
                    return {"articles": [], "error": f"HTTP {response.status}"}
                return await response.json()
    except Exception as e:
        logger.error(f"Async fetch exception: {e}")
        return {"articles": [], "error": str(e)}

@function_tool()
async def get_latest_news(
    topic: str = "",
    location: str = "world",
    category: str = "general",
    count: int = 5
) -> dict:
    """
    Fetch latest news for a specific topic, location (city/state/country), or category.

    Returns a structured response with articles, a readable summary, and metadata.
    """
    try:
        count = min(max(count or 1, 1), 10)
        location = (location or "world").strip() or "world"
        category = (category or "general").strip() or "general"
        topic = (topic or "").strip()

        query = topic if topic else ""
        if location and location.lower() not in ["world", "general"]:
            query = f"{location} {query}".strip()

        response = None
        if NEWS_API_KEY:
            logger.info(f"🔍 Fetching news via NewsAPI for query '{query or category}'")
            response = await _fetch_from_newsapi(query, category, count)

        if not response or response.get("status") != "ok" or not response.get("articles"):
            logger.info("🔄 Falling back to RSS because NewsAPI returned no usable results")
            response = await _fetch_from_rss(location, category, count)

        if response.get("status") != "ok":
            return response

        response["query"] = query or location or category
        response["category"] = category
        response["location"] = location
        response["fetched_at"] = datetime.now(timezone.utc).isoformat()
        response["raw_text"] = _build_readable_summary(response["articles"], response["source"], response["query"], count)
        response["tts_text"] = _build_tts_text(response["articles"], response["query"])

        return response

    except Exception as e:
        logger.error(f"🚨 Error in get_latest_news: {e}")
        return {
            "status": "error",
            "error": str(e),
            "query": location,
            "category": category,
            "articles": []
        }

@function_tool()
async def get_city_news(city: str = "Mumbai", count: int = 5) -> dict:
    return await get_latest_news(location=city, count=count)

@function_tool()
async def get_state_news(state: str = "Maharashtra", count: int = 5) -> dict:
    return await get_latest_news(location=state, count=count)

@function_tool()
async def get_person_info(
    person_name: str
) -> str:
    try:
        if not NEWS_API_KEY:
            return "ℹ️ News API key not configured. Cannot fetch person info."

        params = {
            "q": person_name,
            "apiKey": NEWS_API_KEY,
            "sortBy": "publishedAt",
            "pageSize": 10,
            "language": "en"
        }

        data = await _async_fetch_url(f"{NEWS_API_URL}/everything", params=params)
        articles = data.get("articles", [])
        if not articles:
            return f"ℹ️ No recent verified information found for {person_name}."

        result = {
            "status": "ok",
            "query": person_name,
            "source": "newsapi",
            "articles": [
                {
                    "title": article.get("title"),
                    "source": article.get("source", {}).get("name"),
                    "description": article.get("description"),
                    "url": article.get("url"),
                    "publishedAt": article.get("publishedAt")
                }
                for article in articles[:5]
            ]
        }
        return result

    except Exception as e:
        logger.error(f"Error in get_person_info: {e}")
        return {"status": "error", "error": str(e), "articles": []}

async def _fetch_from_newsapi(query: str, category: str, count: int) -> dict:
    try:
        if query:
            url = f"{NEWS_API_URL}/everything"
            params = {
                "q": query,
                "apiKey": NEWS_API_KEY,
                "sortBy": "publishedAt",
                "pageSize": count,
                "language": "en"
            }
        else:
            url = f"{NEWS_API_URL}/top-headlines"
            params = {
                "apiKey": NEWS_API_KEY,
                "category": category if category and category != "general" else None,
                "country": "in",
                "pageSize": count
            }

        params = {k: v for k, v in params.items() if v is not None}
        data = await _async_fetch_url(url, params=params)

        if data.get("status") != "ok":
            return {"status": "error", "error": data.get("message", "NewsAPI returned an error")}

        articles = [
            {
                "title": _clean_text(article.get("title")),
                "source": article.get("source", {}).get("name"),
                "summary": _clean_text(article.get("description")) or _clean_text(article.get("content", "")),
                "url": article.get("url"),
                "image": article.get("urlToImage"),
                "publishedAt": article.get("publishedAt")
            }
            for article in data.get("articles", [])
        ]

        if not articles:
            return {"status": "error", "error": "No articles returned from NewsAPI."}

        asyncio.create_task(_broadcast_news(articles, query or category))
        return {"status": "ok", "source": "newsapi", "articles": articles}

    except Exception as e:
        logger.error(f"Error in _fetch_from_newsapi: {e}")
        return {"status": "error", "error": str(e), "articles": []}

async def _fetch_from_rss(location: str, category: str, count: int) -> dict:
    try:
        loc_key = (location or "world").lower()
        cat_key = (category or "general").lower()

        feed_url = TRUSTED_RSS_FEEDS.get("world")
        if loc_key in TRUSTED_RSS_FEEDS:
            feed_url = TRUSTED_RSS_FEEDS[loc_key]
        elif cat_key in TRUSTED_RSS_FEEDS:
            feed_url = TRUSTED_RSS_FEEDS[cat_key]
        elif "mumbai" in loc_key:
            feed_url = TRUSTED_RSS_FEEDS["mumbai"]
        elif "maharashtra" in loc_key:
            feed_url = TRUSTED_RSS_FEEDS["maharashtra"]
        elif "india" in loc_key:
            feed_url = TRUSTED_RSS_FEEDS["india"]

        logger.info(f"🌐 Accessing RSS feed: {feed_url}")
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, feed_url)

        if getattr(feed, "bozo", False):
            error = getattr(feed, "bozo_exception", "RSS feed parse error")
            return {"status": "error", "error": str(error), "articles": []}

        entries = sorted(
            feed.entries,
            key=lambda e: _extract_entry_timestamp(e) or 0,
            reverse=True
        )[:count]

        articles = []
        for entry in entries:
            summary = _clean_text(entry.get('summary', entry.get('description', '')))
            image_url = None
            if 'media_content' in entry:
                image_url = entry.media_content[0].get('url')
            elif 'links' in entry:
                for link in entry.links:
                    if link.get('rel') == 'enclosure' and 'image' in link.get('type', ''):
                        image_url = link.get('href')
                        break

            articles.append({
                "title": _clean_text(entry.get('title', 'No Title')),
                "source": entry.get('source', {}).get('title', 'RSS Feed') if isinstance(entry.get('source'), dict) else entry.get('source', 'RSS Feed'),
                "summary": summary,
                "url": entry.get('link'),
                "image": image_url,
                "publishedAt": _normalize_timestamp(entry)
            })

        asyncio.create_task(_broadcast_news(articles, location or category))
        return {"status": "ok", "source": "rss", "articles": articles}

    except Exception as e:
        logger.error(f"Error in _fetch_from_rss: {e}")
        return {"status": "error", "error": str(e), "articles": []}

# Helper functions

def _clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', str(text))
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _extract_entry_timestamp(entry):
    parsed = entry.get('published_parsed') or entry.get('updated_parsed')
    if parsed:
        return time.mktime(parsed)
    return None


def _normalize_timestamp(entry):
    dt = None
    parsed_ts = _extract_entry_timestamp(entry)
    if parsed_ts:
        dt = datetime.fromtimestamp(parsed_ts, tz=timezone.utc)
        return dt.isoformat()
    return entry.get('published', '') or entry.get('updated', '') or ''


def _build_readable_summary(articles, source, query, count):
    lines = [f"📰 Latest {len(articles)} headlines for '{query}' ({source}).\n"]
    for index, item in enumerate(articles[:count], 1):
        lines.append(f"{index}. {item.get('title')}")
        if item.get('summary'):
            lines.append(f"   {item.get('summary')}")
        if item.get('url'):
            lines.append(f"   {item.get('url')}")
        lines.append("")
    return "\n".join(lines)


def _build_tts_text(articles, query):
    if not articles:
        return f"No news articles were found for {query}."
    lines = [f"Here are the top {len(articles)} headlines for {query}. "]
    for index, item in enumerate(articles[:10], 1):
        title = item.get('title') or 'No title available'
        summary = item.get('summary') or 'No summary is available for this headline.'
        lines.append(f"Headline {index}. {title}. {summary}.")
    return ' '.join(lines)

if __name__ == "__main__":
    async def test():
        response = await get_city_news("Mumbai", count=2)
        print(json.dumps(response, indent=2, ensure_ascii=False))

    asyncio.run(test())
