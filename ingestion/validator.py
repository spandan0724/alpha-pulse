# ingestion/validator.py
"""Unified Pydantic V2 models for all AlphaPulse data.

Covers:
  - Quote        : single instrument LTP from Upstox
  - LTPResponse  : full Upstox API response (status + data dict)
  - NewsArticle  : single article from NewsAPI
  - NewsResponse : collection of validated articles for one ticker

Price validation is strict — bad price = hard failure.
News validation is lenient — bad article = skip and continue.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, field_validator, model_validator

from summarizer import summarize_article

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Price models
# ---------------------------------------------------------------------------

class Quote(BaseModel):
    last_price: float
    instrument_token: str
    ltq: Optional[int] = None
    volume: int
    cp: Optional[float] = None

    @field_validator("last_price")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v < 0:
            raise ValueError(f"Price cannot be negative: {v}")
        return round(v, 4)

    @field_validator("cp")
    @classmethod
    def cp_must_be_positive(cls, v: Optional[float]) -> Optional[float]:
        if v is None:
            return None
        if v < 0:
            raise ValueError(f"Price change cannot be negative: {v}")
        return round(v, 4)

    @field_validator("volume")
    @classmethod
    def volume_must_be_non_negative(cls, v: int) -> int:
        if v < 0:
            raise ValueError(f"Value cannot be negative: {v}")
        return v

    @field_validator("ltq")
    @classmethod
    def ltq_must_be_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        if v < 0:
            raise ValueError(f"Value cannot be negative: {v}")
        return v


class LTPResponse(BaseModel):
    status: str
    data: Dict[str, Quote]

    @field_validator("status")
    @classmethod
    def status_must_be_success(cls, v: str) -> str:
        if v.lower() != "success":
            raise ValueError(f"Unexpected Upstox status: {v}")
        return v


# ---------------------------------------------------------------------------
# News models
# ---------------------------------------------------------------------------

class NewsArticle(BaseModel):
    ticker: str
    headline: str
    source: str
    url: Optional[str] = None
    published_at: Optional[datetime] = None
    fetched_at: Optional[datetime] = None
    summary: Optional[str] = None

    @field_validator("ticker")
    @classmethod
    def ticker_uppercase(cls, v: str) -> str:
        return v.upper().strip()

    @field_validator("headline")
    @classmethod
    def headline_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v or v == "[Removed]":
            raise ValueError("Headline is empty or removed")
        return v

    @field_validator("source")
    @classmethod
    def source_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Source cannot be empty")
        return v

    @field_validator("url")
    @classmethod
    def url_cleanup(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        return v if v.startswith("http") else None

    @field_validator("summary")
    @classmethod
    def summary_cleanup(cls, v: Optional[str]) -> Optional[str]:
        if not v:
            return None
        v = v.strip()
        return v if v else None

    @model_validator(mode="after")
    def set_fetched_at(self) -> "NewsArticle":
        if self.fetched_at is None:
            self.fetched_at = datetime.now(timezone.utc)
        return self


class NewsResponse(BaseModel):
    ticker: str
    articles: List[NewsArticle]
    total_fetched: int
    total_valid: int
    fetched_at: Optional[datetime] = None

    @model_validator(mode="after")
    def set_fetched_at(self) -> "NewsResponse":
        if self.fetched_at is None:
            self.fetched_at = datetime.now(timezone.utc)
        return self


# ---------------------------------------------------------------------------
# Validation functions
# ---------------------------------------------------------------------------

def _normalize_ltp_response(raw: dict) -> dict:
    """Normalize raw Upstox LTP payloads before validation."""
    normalized: dict[str, Any] = dict(raw)

    status = normalized.get("status")
    if isinstance(status, str) and status.lower() in {"ok", "success"}:
        normalized["status"] = "success"

    data = normalized.get("data")
    if isinstance(data, dict):
        normalized_data: dict[str, Any] = {}
        for key, quote in data.items():
            if not isinstance(quote, dict):
                normalized_data[key] = quote
                continue

            quote_norm = dict(quote)
            if "instrument_token" not in quote_norm:
                quote_norm["instrument_token"] = quote_norm.get(
                    "instrument_key",
                    quote_norm.get("token", key),
                )

            if "ltq" not in quote_norm:
                quote_norm["ltq"] = None
            if "cp" not in quote_norm:
                quote_norm["cp"] = None

            if "volume" in quote_norm and quote_norm["volume"] == "":
                quote_norm["volume"] = 0
            if "last_price" in quote_norm and quote_norm["last_price"] == "":
                quote_norm["last_price"] = 0.0

            normalized_data[key] = quote_norm
        normalized["data"] = normalized_data

    return normalized


def validate_ltp_response(raw: dict) -> LTPResponse:
    """Validate a raw Upstox LTP API response.

    Args:
        raw: Raw JSON dict from Upstox API.

    Returns:
        Validated LTPResponse object.

    Raises:
        ValidationError: If response shape or values are invalid.
    """
    normalized = _normalize_ltp_response(raw)
    return LTPResponse.model_validate(normalized)


def validate_articles(ticker: str, raw_articles: List[dict]) -> NewsResponse:
    """Validate a list of raw NewsAPI articles for a ticker.

    Lenient — invalid articles are skipped with a warning,
    not pipeline-breaking. Adds AI summarization.
    Returns a NewsResponse with only articles that passed all validators.

    Args:
        ticker: NSE trading symbol.
        raw_articles: Raw article list from NewsAPI.

    Returns:
        NewsResponse containing only valid articles with summaries.
    """
    valid: List[NewsArticle] = []
    skipped = 0

    for i, raw in enumerate(raw_articles):
        try:
            # Summarize article description
            description = raw.get("description", "") or raw.get("title", "")
            logger.info("Article %d: description length %d chars", i, len(description))
            summary = summarize_article(description)
            logger.info("Article %d: summary result length %d chars", i, len(summary) if summary else 0)
            
            article = NewsArticle(
                ticker=ticker,
                headline=raw.get("title", ""),
                source=(raw.get("source") or {}).get("name", ""),
                url=raw.get("url"),
                published_at=raw.get("publishedAt"),
                summary=summary,
            )
            valid.append(article)
        except Exception as e:
            skipped += 1
            logger.warning(
                "Article %d for %s skipped — %s", i, ticker, e
            )

    logger.info(
        "%s: %d valid articles, %d skipped out of %d",
        ticker, len(valid), skipped, len(raw_articles)
    )

    return NewsResponse(
        ticker=ticker,
        articles=valid,
        total_fetched=len(raw_articles),
        total_valid=len(valid),
    )