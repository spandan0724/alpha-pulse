# ingestion/upstox_client/__init__.py
"""Upstox client package for AlphaPulse ingestion pipeline.

Public API — import from here, not from submodules directly.

Example:
    from upstox_client import fetch_quotes_batch, parse_quote, fetch_news
    from upstox_client import get_instrument_key, all_tickers
"""

from .auth import get_headers
from .instruments import (
    get_instrument_key,
    get_company_name,
    build_keys_string,
    resolve_ticker,
    all_tickers,
    INSTRUMENTS,
)
from .quotes import fetch_quote, fetch_quotes_batch, fetch_ltp, parse_quote
from .news import fetch_news

__all__ = [
    # auth
    "get_headers",
    # instruments
    "get_instrument_key",
    "get_company_name",
    "build_keys_string",
    "resolve_ticker",
    "all_tickers",
    "INSTRUMENTS",
    # quotes
    "fetch_quote",
    "fetch_quotes_batch",
    "parse_quote",
    # news
    "fetch_news",
]