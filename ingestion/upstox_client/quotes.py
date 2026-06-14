# ingestion/upstox_client/quotes.py
"""Upstox market quote fetching and parsing.

Handles single and batch quote requests against the Upstox v2 API.
Parsing is kept here so the pipeline never touches raw Upstox response
shapes — only the flat StockPrice-compatible dict leaves this module.

Usage:
    from upstox_client.quotes import fetch_quote, fetch_quotes_batch, parse_quote
"""

import logging
from typing import Dict, List

import requests

from .auth import get_headers
from .instruments import build_keys_string, resolve_ticker

logger = logging.getLogger(__name__)

BASE_URL = "https://api.upstox.com/v2"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _handle_response_errors(resp: requests.Response, context: str) -> None:
    """Raise a descriptive RuntimeError for non-200 Upstox responses.

    Args:
        resp: The HTTP response object.
        context: Short string describing what was being fetched (for logging).

    Raises:
        RuntimeError: With a clear message depending on status code.
    """
    if resp.status_code == 401:
        raise RuntimeError(
            f"Upstox token expired or invalid while fetching {context}. "
            "Re-run auth.py to get a new token."
        )
    if resp.status_code == 429:
        raise RuntimeError(
            f"Upstox rate limit hit while fetching {context}. "
            "Wait before retrying."
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"Upstox API error [{resp.status_code}] fetching {context}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# Quote fetching
# ---------------------------------------------------------------------------

def fetch_quote(ticker: str, instrument_key: str) -> dict:
    """Fetch the latest market quote for a single ticker.

    Prefer fetch_quotes_batch() when fetching multiple tickers —
    it uses one API call instead of N.

    Args:
        ticker: NSE trading symbol (e.g. 'ADANIENT') — used for logging only.
        instrument_key: Upstox instrument key (e.g. 'NSE_EQ|INE423A01024').

    Returns:
        Raw quote dict from Upstox 'data' field.

    Raises:
        RuntimeError: On API errors or empty response.
    """
    url = f"{BASE_URL}/market-quote/quotes"
    resp = requests.get(
        url,
        headers=get_headers(),
        params={"instrument_key": instrument_key},
        timeout=30,
    )

    _handle_response_errors(resp, ticker)

    data = resp.json().get("data", {})
    quote = data.get(instrument_key)
    if not quote:
        raise RuntimeError(
            f"Empty quote data returned for {ticker} ({instrument_key})"
        )

    logger.info("Fetched quote for %s: ₹%s", ticker, quote.get("last_price"))
    return quote


V3_BASE_URL = "https://api.upstox.com/v3"


def fetch_ltp(instrument_keys: List[str]) -> dict:
    """Fetch LTP quotes for multiple instrument keys from Upstox.

    Args:
        instrument_keys: List of Upstox instrument keys.

    Returns:
        Raw Upstox JSON response with status and data fields.
    """
    keys_str = ",".join(instrument_keys)
    if not keys_str:
        logger.error("No instrument keys provided for fetch_ltp")
        return {"status": "success", "data": {}}

    url = f"{V3_BASE_URL}/market-quote/ltp"
    resp = requests.get(
        url,
        headers=get_headers(),
        params={"instrument_key": keys_str},
        timeout=30,
    )

    _handle_response_errors(resp, f"ltp batch {instrument_keys}")
    return resp.json()


def fetch_quotes_batch(tickers: List[str]) -> Dict[str, dict]:
    """Fetch quotes for multiple tickers in a SINGLE Upstox API call.

    Upstox supports comma-separated instrument keys in one request —
    far more efficient than one call per ticker.

    Args:
        tickers: List of NSE trading symbols.

    Returns:
        Dict mapping trading_symbol -> raw quote dict.
        Tickers that failed instrument key lookup are silently skipped
        (already warned in build_keys_string).
    """
    keys_str = build_keys_string(tickers)
    if not keys_str:
        logger.error("No valid instrument keys for tickers: %s", tickers)
        return {}

    url = f"{BASE_URL}/market-quote/quotes"
    resp = requests.get(
        url,
        headers=get_headers(),
        params={"instrument_key": keys_str},
        timeout=30,
    )

    _handle_response_errors(resp, f"batch {tickers}")

    raw_data = resp.json().get("data", {})

    # Upstox returns instrument keys as dict keys — reverse-map to tickers
    results: Dict[str, dict] = {}
    for instrument_key, quote in raw_data.items():
        ticker = resolve_ticker(instrument_key)
        if ticker:
            results[ticker] = quote
        else:
            logger.warning(
                "Instrument key in response not in registry: %s", instrument_key
            )

    logger.info(
        "Batch fetch complete: %d/%d tickers returned data",
        len(results), len(tickers),
    )
    return results


# ---------------------------------------------------------------------------
# Quote parsing
# ---------------------------------------------------------------------------

def parse_quote(ticker: str, quote: dict) -> dict:
    """Flatten a raw Upstox quote into a StockPrice-compatible dict.

    Upstox returns a nested structure (ohlc, depth, ltpc). This function
    extracts only the fields needed by the StockPrice Pydantic model so
    the rest of the pipeline is decoupled from Upstox response shapes.

    Args:
        ticker: NSE trading symbol.
        quote: Raw quote dict from Upstox API.

    Returns:
        Flat dict ready for StockPrice(**result) instantiation.
        event_ts is intentionally omitted — the Pydantic default_factory
        fills it with datetime.now(timezone.utc) automatically.
    """
    ohlc = quote.get("ohlc", {})

    def _safe_float(value) -> float | None:
        """Convert to float, returning None for zero or missing values."""
        try:
            f = float(value)
            return f if f != 0.0 else None
        except (TypeError, ValueError):
            return None

    return {
        "ticker": ticker.upper(),
        "price": float(quote.get("last_price", 0)),   # LTP — Live Traded Price
        "volume": int(quote.get("volume", 0)),
        "open_price": _safe_float(ohlc.get("open")),
        "high_price": _safe_float(ohlc.get("high")),
        "low_price": _safe_float(ohlc.get("low")),
        "close_price": _safe_float(ohlc.get("close")),
    }