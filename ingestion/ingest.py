# ingestion/ingest.py
"""Main ingestion entry point for AlphaPulse.

Orchestrates:
  1. Load tickers from instruments.json
  2. Fetch + validate + deduplicate LTP prices  (Upstox)
  3. Fetch + validate + deduplicate news        (NewsAPI)
  4. Route any failures to unified DLQ

Works as a local script and as a Cloud Function HTTP trigger.
"""

import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from upstox_client.instruments import all_tickers, build_keys_string
from upstox_client.quotes import fetch_ltp
from upstox_client.news import run_news_pipeline
from validator import validate_ltp_response
from idempotency import process_price_idempotent, filter_new_articles
from dlq import send_price_to_dlq, send_news_to_dlq, dlq_count
from storage import save_price_success, save_news_success

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_price_ingestion(tickers: list, instrument_keys: list) -> dict:
    """Fetch, validate, and deduplicate LTP price data.

    Args:
        tickers: List of NSE trading symbols (e.g., ['RELIANCE', 'ADANIENT']).
        instrument_keys: List of Upstox instrument key strings.

    Returns:
        Dict summarising price ingestion result.
    """
    raw = {}
    try:
        raw = fetch_ltp(instrument_keys)
        validated = validate_ltp_response(raw)
        result = process_price_idempotent(validated)
        # Save each ticker's price data separately
        for ticker in tickers:
            save_price_success(ticker, validated)
        logger.info("Prices OK — %d quotes", len(validated.data))
        return {"status": "ok", "quote_count": len(validated.data)}
    except Exception as e:
        send_price_to_dlq(raw, e)
        logger.error("Price ingestion failed: %s", e)
        return {"status": "failed", "error": str(e), "quote_count": 0}


def run_news_ingestion(tickers: list) -> dict:
    """Fetch, validate, and deduplicate news for all tickers.

    Args:
        tickers: List of NSE trading symbols.

    Returns:
        Dict summarising news ingestion result.
    """
    total_articles = 0
    failed_tickers = []

    for ticker in tickers:
        try:
            response = run_news_pipeline(ticker, page_size=10)
            save_news_success(ticker, response.model_dump())
            total_articles += response.total_valid
        except Exception as e:
            send_news_to_dlq(ticker, {}, e)
            failed_tickers.append(ticker)
            logger.error("News failed for %s: %s", ticker, e)

    status = "ok" if not failed_tickers else "partial"
    logger.info("News %s — %d articles total", status, total_articles)
    return {
        "status": status,
        "total_articles": total_articles,
        "failed_tickers": failed_tickers,
    }


def run_ingestion() -> dict:
    """Run one full ingestion cycle — prices + news."""
    started_at = datetime.now(timezone.utc).isoformat()
    logger.info("=== AlphaPulse ingestion started %s ===", started_at)

    tickers = all_tickers()
    if not tickers:
        return {"status": "failed", "error": "No tickers in instruments.json"}

    keys = build_keys_string(tickers).split(",")

    price_result = run_price_ingestion(tickers, keys)
    news_result  = run_news_ingestion(tickers)

    summary = {
        "status": "ok" if price_result["status"] == "ok" else "failed",
        "started_at": started_at,
        "tickers": tickers,
        "prices": price_result,
        "news": news_result,
        "dlq": {
            "price": dlq_count("price"),
            "news":  dlq_count("news"),
            "total": dlq_count(),
        },
    }

    logger.info("=== Ingestion complete: %s ===", summary["status"])
    return summary


# Cloud Function entry point
def main(request=None):
    result = run_ingestion()
    return result, (200 if result["status"] == "ok" else 500)


# Local entry point
if __name__ == "__main__":
    result = run_ingestion()
    print("\n=== AlphaPulse Ingestion Result ===")
    print(f"  Status         : {result['status']}")
    print(f"  Tickers        : {result['tickers']}")
    print(f"  Quotes         : {result['prices']['quote_count']}")
    print(f"  Articles       : {result['news']['total_articles']}")
    print(f"  DLQ (price)    : {result['dlq']['price']}")
    print(f"  DLQ (news)     : {result['dlq']['news']}")
    if result['news']['failed_tickers']:
        print(f"  News failures  : {result['news']['failed_tickers']}")
    if result['prices'].get('error'):
        print(f"  Price error    : {result['prices']['error']}")