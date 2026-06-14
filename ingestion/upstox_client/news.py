# ingestion/upstox_client/news.py
"""NewsAPI client for AlphaPulse.

Full pipeline per ticker:
  1. fetch_news()          — hits NewsAPI, returns raw articles
  2. validate_articles()   — Pydantic validation, drops bad articles
  3. filter_new_articles() — dedup, drops already-seen articles

All three live in unified modules (validator.py, idempotency.py).
This file only handles the HTTP fetch layer.
"""

import logging
import os
from typing import List

import requests
from dotenv import load_dotenv

from .instruments import get_company_name
from validator import validate_articles, NewsResponse
from idempotency import filter_new_articles

load_dotenv()

logger = logging.getLogger(__name__)

NEWSAPI_URL = "https://newsapi.org/v2/everything"


def _get_api_key() -> str:
    key = os.getenv("NEWS_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "NEWS_API_KEY not set. Add it to .env:\nNEWS_API_KEY=your_key"
        )
    logger.info("DEBUG: Using NEWS_API_KEY of length %d", len(key))
    return key


def fetch_news(ticker: str, page_size: int = 10) -> List[dict]:
    """Fetch raw articles from NewsAPI for a ticker.

    Args:
        ticker: NSE trading symbol.
        page_size: Articles to fetch (max 100).

    Returns:
        List of raw article dicts.

    Raises:
        RuntimeError: On auth failure or API error.
    """
    try:
        company_name = get_company_name(ticker)
    except KeyError as exc:
        raise RuntimeError(str(exc)) from exc

    api_key = _get_api_key()
    params = {
        "q": company_name,
        "language": "en",
        "sortBy": "publishedAt",
        "pageSize": min(page_size, 100),
        "apiKey": api_key,
    }

    logger.info("Fetching news for %s (%s)", ticker, company_name)
    logger.info("DEBUG: API Key first 10 chars: %s... last 8 chars: ...%s", api_key[:10], api_key[-8:])

    try:
        resp = requests.get(NEWSAPI_URL, params=params, timeout=30)
    except requests.RequestException as e:
        raise RuntimeError(f"NewsAPI request failed: {e}") from e

    logger.info("DEBUG: NewsAPI response status: %d", resp.status_code)
    
    if resp.status_code == 401:
        logger.error("DEBUG: 401 response body: %s", resp.text[:200])
        raise RuntimeError("NewsAPI key invalid or expired")
    if resp.status_code == 429:
        raise RuntimeError("NewsAPI rate limit hit")
    if resp.status_code != 200:
        raise RuntimeError(f"NewsAPI error [{resp.status_code}]: {resp.text}")

    articles = resp.json().get("articles", [])
    logger.info("Fetched %d raw articles for %s", len(articles), ticker)
    return articles


def run_news_pipeline(ticker: str, page_size: int = 10) -> NewsResponse:
    """Fetch, validate, and deduplicate news for one ticker.

    Returns empty NewsResponse on failure — never raises,
    so one bad ticker doesn't block others.

    Args:
        ticker: NSE trading symbol.
        page_size: Articles to fetch.

    Returns:
        NewsResponse with only new, valid articles.
    """
    raw = fetch_news(ticker, page_size=page_size)
    validated = validate_articles(ticker, raw)
    deduped = filter_new_articles(validated)

    logger.info(
        "%s: %d new articles (fetched %d, validated %d)",
        ticker,
        deduped.total_valid,
        validated.total_fetched,
        validated.total_valid,
    )
    return deduped