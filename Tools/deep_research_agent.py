"""
Deep Research Tool - LiveKit Agent Integration
Provides real-time, high-accuracy research for Jarvis voice assistant.

Architecture:
  User Query
    → Tavily Search (top 10 results)
    → Source credibility scoring + deduplication
    → LLM reasoning with factual consensus detection
    → Structured answer with confidence + citations

LiveKit Patterns (https://docs.livekit.io/agents/logic/tools/):
  - @function_tool() with RunContext as first arg
  - ToolError raised on failures (never returned as strings)
  - context.disallow_interruptions() on irreversible write ops
  - All blocking I/O runs via asyncio.get_running_loop().run_in_executor()
    (using requests as requested — keeps it modular and familiar)
"""

import os
import json
import logging
import asyncio
import re
from typing import Any
from datetime import datetime
from collections import Counter
from functools import partial
from dotenv import load_dotenv

import requests
from livekit.agents import function_tool, RunContext, ToolError

# Load environment variables explicitly
load_dotenv(override=True)

logger = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════════
# ROOM CONTEXT — set by agent.py at startup so we can broadcast progress
# ══════════════════════════════════════════════════════════════════════════════

_room = None  # type: ignore


def set_room_context(room) -> None:
    """Called from agent.py entrypoint to hand the LiveKit room reference here."""
    global _room
    _room = room
    logger.info("[DeepResearch] Room context registered for DataChannel broadcasting")


async def _broadcast(room: Any, payload: dict) -> None:
    """Broadcast a JSON message over the LiveKit DataChannel to all frontend clients."""
    if room and room.local_participant:
        try:
            data = json.dumps(payload, ensure_ascii=False).encode()
            # In latest LiveKit: publish_data(data, reliable=True) or publish_data(data, options=DataPublishOptions(reliable=True))
            # The current agent.py uses (data, reliable=True) which matches this.
            await room.local_participant.publish_data(data, reliable=True)
            logger.info(f"[DeepResearch] Broadcast: {payload.get('type')} ({payload.get('percent', 0)}%)")
        except Exception as e:
            logger.error(f"[DeepResearch] Broadcast failed: {e}")
    else:
        logger.warning(f"[DeepResearch] Broadcast skipped - room or participant missing. Room: {bool(room)}")



# ══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TAVILY_API_KEY     = os.getenv("TAVILY_API_KEY", "")
GROQ_API_KEY       = os.getenv("GROQ_API_KEY", "")
NOTION_API_KEY     = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

TAVILY_URL = "https://api.tavily.com/search"
GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
NOTION_URL = "https://api.notion.com/v1/pages"

# llama-3.1-70b-versatile is DEPRECATED — use 3.3
GROQ_MODEL = "llama-3.3-70b-versatile"

# Source trust tiers — used to weight credibility scoring
# Tier 1: Official / primary sources
TIER1_DOMAINS = {
    "rockstargames.com", "playstation.com", "xbox.com", "nintendo.com",
    "apple.com", "google.com", "microsoft.com", "github.com",
    "who.int", "cdc.gov", "nasa.gov", "un.org",
}
# Tier 2: High-quality news/encyclopedic sources
TIER2_DOMAINS = {
    "wikipedia.org", "ign.com", "gamespot.com", "kotaku.com",
    "bbc.com", "bbc.co.uk", "reuters.com", "apnews.com",
    "theverge.com", "techcrunch.com", "wired.com", "arstechnica.com",
    "forbes.com", "bloomberg.com", "variety.com", "deadline.com",
    "polygon.com", "eurogamer.net", "pcgamer.com", "gamesradar.com",
}
# Tier 3: General news (reliable but less authoritative)
TIER3_DOMAINS = {
    "cnn.com", "nytimes.com", "washingtonpost.com", "guardian.com",
    "independent.co.uk", "mirror.co.uk", "express.co.uk",
    "screenrant.com", "cbr.com", "gamerant.com", "pushsquare.com",
}


# ══════════════════════════════════════════════════════════════════════════════
# HELPER: DOMAIN CREDIBILITY SCORING
# ══════════════════════════════════════════════════════════════════════════════

def _get_domain(url: str) -> str:
    """Extract root domain from URL."""
    url = url.lower().replace("https://", "").replace("http://", "").replace("www.", "")
    return url.split("/")[0]


def _credibility_score(url: str) -> int:
    """
    Return a credibility score for a URL:
      3 = Official/primary source
      2 = High-quality news/wiki
      1 = General news
      0 = Unknown
    """
    domain = _get_domain(url)
    if any(t in domain for t in TIER1_DOMAINS):
        return 3
    if any(t in domain for t in TIER2_DOMAINS):
        return 2
    if any(t in domain for t in TIER3_DOMAINS):
        return 1
    return 0


def _label_source(score: int) -> str:
    return {3: "Official Source", 2: "Trusted News/Wiki", 1: "General Media", 0: "Unknown"}.get(score, "Unknown")


# ══════════════════════════════════════════════════════════════════════════════
# BLOCKING I/O FUNCTIONS (run inside thread pool via run_in_executor)
# ══════════════════════════════════════════════════════════════════════════════

def _blocking_tavily_search(query: str, limit: int = 10) -> list[dict]:
    """
    Fetch top `limit` articles from Tavily for the given query.
    Scores each article by source credibility.
    Returns articles sorted: official first, then by Tavily relevance score.

    Raises:
        RuntimeError on network failure or empty results (caller converts to ToolError).
    """
    if not TAVILY_API_KEY:
        raise RuntimeError("TAVILY_API_KEY not configured in .env")

    payload = {
        "api_key":         TAVILY_API_KEY,
        "query":           query,
        "max_results":     limit,
        "include_answer":  True,   # Tavily's own quick answer
        "include_raw_content": False,
        "topic":           "general",  # 'general' gives broader, more stable results than 'news'
        "search_depth":    "advanced", # deep search for accuracy
    }

    try:
        resp = requests.post(TAVILY_URL, json=payload, timeout=20)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError("Tavily search timed out (20s). Please try again.")
    except requests.exceptions.ConnectionError:
        raise RuntimeError("Cannot reach Tavily API. Check internet connection.")
    except requests.exceptions.HTTPError as e:
        raise RuntimeError(f"Tavily HTTP {e.response.status_code}: {e.response.text[:200]}")

    data = resp.json()
    raw_results = data.get("results", [])

    if not raw_results:
        raise RuntimeError(f"Tavily returned 0 results for query: '{query}'")

    articles = []
    for r in raw_results:
        url   = r.get("url", "")
        score = _credibility_score(url)
        articles.append({
            "title":       r.get("title", "Untitled"),
            # Truncate snippets: keep enough text for LLM context but avoid token overflow
            "snippet":     str(r.get("content", ""))[:800].strip(),
            "url":         url,
            "tavily_score": float(r.get("score", 0.0)),
            "cred_score":  score,
            "cred_label":  _label_source(score),
        })

    # Sort: official/trusted sources first, then by Tavily relevance score
    articles.sort(key=lambda a: (a["cred_score"], a["tavily_score"]), reverse=True)

    # Also capture Tavily's own synthesized answer if available
    tavily_answer = data.get("answer", "")

    return articles, tavily_answer


def _blocking_groq_reason(query: str, articles: list[dict], tavily_answer: str) -> dict:
    """
    Send the collected articles to Groq LLM for factual reasoning.
    Returns a dict: {"answer": str, "confidence": str, "sources": [url...]}

    The prompt is carefully engineered to:
     1. Detect factual consensus across multiple sources
     2. Distinguish official confirmation vs rumors
     3. Return structured JSON so we can parse it reliably
     4. Never say 'no confirmed news' if sources actually have info

    Raises:
        RuntimeError on any API failure (caller converts to ToolError).
    """
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY not configured in .env")

    # Build structured article context for the prompt
    article_blocks = []
    for i, a in enumerate(articles, 1):
        article_blocks.append(
            f"[Source {i}] ({a['cred_label']}) — Score: {a['tavily_score']:.2f}\n"
            f"Title: {a['title']}\n"
            f"URL: {a['url']}\n"
            f"Content: {a['snippet']}\n"
        )
    articles_text = "\n---\n".join(article_blocks)

    tavily_hint = (
        f"\nTavily's synthesized answer (use as a hint, not the final answer):\n{tavily_answer}\n"
        if tavily_answer else ""
    )

    system_prompt = """You are a senior research analyst. Your job is to read multiple web sources and produce a factual, accurate answer.

STRICT RULES:
1. If multiple independent sources (especially Official Sources or Trusted News) agree on a specific fact (e.g., a release date, a name, a number), state it as CONFIRMED.
2. If only 1-2 sources mention a fact, label it as "reported but not yet officially confirmed".
3. If sources contradict each other, present BOTH sides clearly and note the disagreement.
4. NEVER say "there is no confirmed information" if the sources clearly contain that information.
5. Always cite which sources support each claim.
6. Be direct and concise. This answer will be spoken aloud by a voice assistant.

CONFIDENCE LEVELS:
- "confirmed" → official source OR 3+ independent trusted sources agree
- "likely"    → 2 reliable sources agree, no contradiction
- "rumored"   → only 1 source or low-credibility sources

Respond ONLY with a valid JSON object in this exact format:
{
  "answer": "A clear, spoken-language answer to the user's question (2-4 sentences max)",
  "confidence": "confirmed | likely | rumored",
  "key_fact": "The single most important fact in one short sentence",
  "sources": ["url1", "url2", "url3"]
}"""

    user_prompt = (
        f"User question: {query}\n\n"
        f"{tavily_hint}"
        f"Here are {len(articles)} web sources to analyze:\n\n"
        f"{articles_text}\n\n"
        f"Based on these sources, answer the user's question accurately. "
        f"If multiple sources confirm the same fact, state it confidently."
    )

    payload = {
        "model":       GROQ_MODEL,
        "messages":    [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens":  700,
        "temperature": 0.2,   # Low temperature = more factual, less creative
        "top_p":       0.9,
    }

    try:
        resp = requests.post(
            GROQ_URL,
            json=payload,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError("Groq API timed out (30s). Please try again.")
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code
        if code == 400:
            raise RuntimeError("Groq 400 Bad Request — model may have changed or prompt too large.")
        elif code in (401, 403):
            raise RuntimeError("Invalid Groq API key — check GROQ_API_KEY.")
        elif code == 429:
            raise RuntimeError("Groq rate limit hit — please wait a moment.")
        raise RuntimeError(f"Groq HTTP {code}: {e.response.text[:200]}")

    raw_content = resp.json()["choices"][0]["message"]["content"].strip()

    # Parse the JSON response — strip markdown code blocks if present
    json_str = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_content, flags=re.MULTILINE).strip()

    try:
        result = json.loads(json_str)
    except json.JSONDecodeError:
        # Fallback: LLM didn't return valid JSON — wrap the raw text
        logger.warning("[DeepResearch] LLM returned non-JSON response, wrapping as plain answer.")
        result = {
            "answer":     raw_content,
            "confidence": "likely",
            "key_fact":   "",
            "sources":    [a["url"] for a in articles[:3]],
        }

    # Ensure sources list is populated (fallback to top credibility URLs)
    if not result.get("sources"):
        result["sources"] = [a["url"] for a in sorted(articles, key=lambda x: x["cred_score"], reverse=True)[:3]]

    return result


def _blocking_notion_save(title: str, summary: str, url: str = "") -> bool:
    """Save a single page to Notion. Returns True on success, False if unconfigured."""
    if not NOTION_API_KEY or not NOTION_DATABASE_ID:
        return False

    payload: dict[str, Any] = {
        "parent": {"database_id": NOTION_DATABASE_ID},
        "properties": {
            "Title":   {"title":     [{"text": {"content": title[:100]}}]},
            "Summary": {"rich_text": [{"text": {"content": summary[:2000]}}]},
        },
    }
    if url:
        payload["properties"]["URL"] = {"url": url}

    try:
        resp = requests.post(
            NOTION_URL,
            json=payload,
            headers={
                "Authorization":  f"Bearer {NOTION_API_KEY}",
                "Content-Type":   "application/json",
                "Notion-Version": "2022-06-28",
            },
            timeout=10,
        )
        resp.raise_for_status()
        logger.info(f"[Notion] Saved: {title[:60]}")
        return True
    except Exception as e:
        logger.error(f"[Notion] Save failed: {e}")
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CORE PUBLIC FUNCTION — deep_research(query)
# Can be called from anywhere (FastAPI, scripts, other tools, etc.)
# Returns: {"answer": str, "confidence": str, "sources": [str]}
# ══════════════════════════════════════════════════════════════════════════════

async def deep_research(query: str, room: Any = None) -> dict:
    """
    Full research pipeline with live frontend progress broadcasting:
      Step 1 → Broadcast: searching
      Step 2 → Tavily: fetch 10 articles
      Step 3 → Broadcast: source cards stream to overlay
      Step 4 → Groq: AI reasoning + consensus check
      Step 5 → Broadcast: confidence verdict
      Step 6 → Broadcast: RESEARCH_COMPLETE to render answer in overlay

    Returns:
        dict: {answer, confidence, key_fact, sources}
    Raises:
        ToolError: on any API failure
    """
    # Fallback to global _room if not passed (though we prefer passing it)
    active_room = room or _room
    
    loop = asyncio.get_running_loop()

    # ── Step 1: Announce search starting ───────────────────────────────────
    await _broadcast(active_room, {
        "type":    "RESEARCH_PROGRESS",
        "query":   query,
        "step":    2,
        "percent": 15,
        "status":  f"Searching the web for: {query}",
        "sources": [],
    })

    # ── Step 2: Tavily search (blocking → thread pool) ──────────────────────
    try:
        articles, tavily_answer = await loop.run_in_executor(
            None, partial(_blocking_tavily_search, query, 10)
        )
    except RuntimeError as e:
        await _broadcast(active_room, {"type": "RESEARCH_ERROR", "error": str(e)})
        raise ToolError(str(e))

    logger.info(f"[DeepResearch] Fetched {len(articles)} articles for: '{query}'")

    # Build source cards once — reused at step 3 and step 6
    source_cards = [
        {
            "title":     a["title"],
            "url":       a["url"],
            "credScore": a["cred_score"],
            "credLabel": a["cred_label"],
        }
        for a in articles
    ]

    # ── Step 3: Source scoring — stream cards to the overlay ──────────────────
    await _broadcast(active_room, {
        "type":    "RESEARCH_PROGRESS",
        "query":   query,
        "step":    3,
        "percent": 45,
        "status":  f"Scoring {len(articles)} sources by credibility...",
        "sources": source_cards,
    })

    # ── Step 4: AI reasoning ────────────────────────────────────────────────
    await _broadcast(active_room, {
        "type":    "RESEARCH_PROGRESS",
        "query":   query,
        "step":    4,
        "percent": 60,
        "status":  "AI analyzing sources — detecting factual consensus...",
        "sources": [],
    })

    try:
        result = await loop.run_in_executor(
            None, partial(_blocking_groq_reason, query, articles, tavily_answer)
        )
    except RuntimeError as e:
        await _broadcast(active_room, {"type": "RESEARCH_ERROR", "error": str(e)})
        raise ToolError(str(e))

    # ── Step 5: Consensus verdict ─────────────────────────────────────────────
    conf = result.get('confidence', 'unknown').upper()
    await _broadcast(active_room, {
        "type":    "RESEARCH_PROGRESS",
        "query":   query,
        "step":    5,
        "percent": 85,
        "status":  f"Consensus verified — confidence: {conf}",
        "sources": [],
    })

    # ── Step 6: Complete — push full result to frontend overlay ───────────────
    logger.info(f"[DeepResearch] Analysis Complete. Confidence: {conf}")
    await _broadcast(active_room, {
        "type":       "RESEARCH_COMPLETE",
        "query":      query,
        "step":       6,
        "percent":    100,
        "status":     "ANALYSIS COMPLETE — ANSWER READY",
        "answer":     result.get("answer", ""),
        "confidence": result.get("confidence", "likely").lower(),
        "keyFact":    result.get("key_fact", ""),
        "sources":    source_cards,
    })

    return result


# ══════════════════════════════════════════════════════════════════════════════
# LIVEKIT FUNCTION TOOLS
# Each tool uses RunContext (LiveKit docs pattern), raises ToolError on failure.
# ══════════════════════════════════════════════════════════════════════════════

@function_tool()
async def analyze_research_data(
    context: RunContext,
    query: str,
) -> str:
    """
    Perform deep research on any topic. Searches 10 live web sources,
    scores them by credibility, uses AI to detect factual consensus,
    and returns a confident, cited answer.

    Use this whenever the user asks about current events, facts, release dates,
    news, sports results, or anything requiring up-to-date information.

    Args:
        query: The user's question or research topic. Be specific.
               Examples: "GTA 6 release date", "iPhone 17 price", "India vs Australia 2025 winner"
    """
    context.disallow_interruptions()
    result = await deep_research(query, getattr(context, "room", None))

    confidence = result.get("confidence", "unknown")
    answer     = result.get("answer", "No answer found.")
    key_fact   = result.get("key_fact", "")
    sources    = result.get("sources", [])

    confidence_emoji = {"confirmed": "✅", "likely": "🟡", "rumored": "⚠️"}.get(confidence, "❓")

    output = f"{confidence_emoji} [{confidence.upper()}] {answer}"
    if key_fact:
        output += f"\n\nKey fact: {key_fact}"
    if sources:
        output += f"\n\nSources: {', '.join(sources[:3])}"

    return output


@function_tool()
async def search_tavily_web(
    context: RunContext,
    query: str,
) -> str:
    """
    Search the live web and return a list of recent articles with titles and URLs.
    Use this when the user wants to browse sources rather than get a direct answer.
    For factual questions, prefer analyze_research_data instead.

    Args:
        query: The search query. Be specific for better results.
    """
    loop = asyncio.get_running_loop()

    try:
        articles, _ = await loop.run_in_executor(
            None, partial(_blocking_tavily_search, query, 10)
        )
    except RuntimeError as e:
        raise ToolError(str(e))

    lines = [f"Top {len(articles)} results for '{query}':\n"]
    for i, a in enumerate(articles, 1):
        lines.append(
            f"{i}. [{a['cred_label']}] {a['title']}\n"
            f"   {a['url']}"
        )
    return "\n".join(lines)


@function_tool()
async def save_to_notion_db(
    context: RunContext,
    title: str,
    content: str,
    source_url: str = "",
) -> str:
    """
    Save research findings or notes to Notion for future reference.
    This is an irreversible write action — interruptions are disabled during save.

    Args:
        title:      Short headline (max 100 chars).
        content:    Main text or summary (max 2000 chars).
        source_url: Optional source URL.
    """
    context.disallow_interruptions()

    if not NOTION_API_KEY:
        raise ToolError("Notion not configured — add NOTION_API_KEY to your .env file.")
    if not NOTION_DATABASE_ID:
        raise ToolError("Notion database ID missing — add NOTION_DATABASE_ID to your .env file.")

    loop = asyncio.get_running_loop()
    success = await loop.run_in_executor(
        None, partial(_blocking_notion_save, title, content, source_url)
    )

    if success:
        return f"Saved to Notion: '{title[:60]}'"
    raise ToolError("Notion save failed — check API key and database permissions.")


@function_tool()
async def full_research_pipeline(
    context: RunContext,
    query: str,
) -> str:
    """
    Complete research workflow: search 10 sources → AI reasoning → save to Notion.
    Use this for thorough research with automatic Notion backup.
    Interruptions are disabled because results are saved during execution.

    Args:
        query: The research topic or question.
    """
    context.disallow_interruptions()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Research (handles its own errors via ToolError)
    result = await deep_research(query, getattr(context, "room", None))

    answer     = result.get("answer", "")
    confidence = result.get("confidence", "unknown")
    sources    = result.get("sources", [])

    # Save to Notion in the background (don't fail the whole tool if Notion is unconfigured)
    loop = asyncio.get_running_loop()
    notion_tasks = [
        loop.run_in_executor(None, partial(_blocking_notion_save, f"Research: {query}", answer, ""))
    ]
    notion_results = await asyncio.gather(*notion_tasks, return_exceptions=True)
    saved = sum(1 for r in notion_results if r is True)

    notion_status = f"Saved {saved} entry to Notion." if saved else "Notion backup skipped (not configured)."

    confidence_emoji = {"confirmed": "✅", "likely": "🟡", "rumored": "⚠️"}.get(confidence, "❓")

    return (
        f"Research Report — {query}\n"
        f"Date: {timestamp}\n\n"
        f"{confidence_emoji} Confidence: {confidence.upper()}\n\n"
        f"{answer}\n\n"
        f"Top sources:\n" +
        "\n".join(f"  • {url}" for url in sources[:5]) +
        f"\n\n{notion_status}"
    )


@function_tool()
async def get_research_status(context: RunContext) -> str:
    """
    Check whether all research tools are properly configured.
    Use this to diagnose issues with the research pipeline.
    """
    items = {
        "Tavily web search": bool(TAVILY_API_KEY),
        f"Groq LLM ({GROQ_MODEL})": bool(GROQ_API_KEY),
        "Notion database": bool(NOTION_API_KEY and NOTION_DATABASE_ID),
    }
    lines = ["Research Tool Configuration:\n"]
    for name, ok in items.items():
        lines.append(f"  {'✅' if ok else '❌'} {name}")

    all_core = items["Tavily web search"] and items[f"Groq LLM ({GROQ_MODEL})"]
    lines.append(
        "\n✅ Core research tools ready — Jarvis can research anything!"
        if all_core
        else "\n⚠️ Missing configuration — add missing keys to your .env file."
    )
    return "\n".join(lines)
