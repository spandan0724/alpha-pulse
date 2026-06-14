# ingestion/idempotency.py
"""Unified idempotency guard for both price and news data.

Prices  → SHA256 of full payload snapshot (changes every tick)
News    → article URL as dedup key (stable across fetches)
          falls back to SHA256 of headline+source+published_at
          when URL is missing

Both share the same in-memory store with a type prefix in the key
so price keys and news keys never collide:
  price:{sha256}
  news:{url_or_hash}

In GCP swap the in-memory set for GCS marker files or Redis.
"""

import hashlib
import logging
from typing import List, Set

from validator import LTPResponse, NewsArticle, NewsResponse

logger = logging.getLogger(__name__)

# Shared in-memory store — prefixed keys prevent collisions
_seen: Set[str] = set()


# ---------------------------------------------------------------------------
# Internal key builders
# ---------------------------------------------------------------------------

def _price_key(payload_json: str) -> str:
    """SHA256 of the full LTP payload — unique per snapshot."""
    return "price:" + hashlib.sha256(payload_json.encode()).hexdigest()


def _article_key(article: NewsArticle) -> str:
    """URL-based key for news articles, hash fallback when URL missing."""
    if article.url:
        return "news:" + article.url.strip().lower()
    content = f"{article.headline}|{article.source}|{article.published_at}"
    return "news:" + hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Price idempotency
# ---------------------------------------------------------------------------

def process_price_idempotent(validated: LTPResponse) -> LTPResponse:
    """Check and mark a price snapshot as processed.

    Args:
        validated: Validated LTPResponse object.

    Returns:
        The same LTPResponse — new or cached duplicate.
    """
    key = _price_key(validated.model_dump_json())

    if key in _seen:
        logger.warning("Duplicate price snapshot — skipping. key=%s...", key[:18])
        return validated

    _seen.add(key)
    logger.info("New price snapshot processed")
    return validated


# ---------------------------------------------------------------------------
# News idempotency
# ---------------------------------------------------------------------------

def filter_new_articles(response: NewsResponse) -> NewsResponse:
    """Remove already-seen articles from a NewsResponse.

    Args:
        response: Validated NewsResponse from validator.validate_articles().

    Returns:
        New NewsResponse with only unseen articles, marked as seen.
    """
    new_articles: List[NewsArticle] = []
    duplicates = 0

    for article in response.articles:
        key = _article_key(article)
        if key in _seen:
            duplicates += 1
            logger.debug(
                "Duplicate article skipped: %s", article.headline[:60]
            )
        else:
            _seen.add(key)
            new_articles.append(article)

    if duplicates:
        logger.info(
            "%s: %d duplicate articles skipped, %d new",
            response.ticker, duplicates, len(new_articles)
        )

    return NewsResponse(
        ticker=response.ticker,
        articles=new_articles,
        total_fetched=response.total_fetched,
        total_valid=len(new_articles),
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def seen_count() -> int:
    """Total unique keys seen (prices + articles combined)."""
    return len(_seen)


def reset() -> None:
    """Clear the seen set. Useful for testing."""
    _seen.clear()