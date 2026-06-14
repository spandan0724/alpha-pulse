# ingestion/dlq.py
"""Unified Dead Letter Queue for both price and news failures.

Routes failed payloads to storage/local_dlq/ with a type prefix
in the filename so price and news failures are easy to distinguish:
  storage/local_dlq/price_20240115_143000.json
  storage/local_dlq/news_ADANIENT_20240115_143000.json

In GCP both publish to the same Pub/Sub DLQ topic with a
"data_type" field in the message so consumers can filter.

Never raises — DLQ failure must never crash the main pipeline.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal

logger = logging.getLogger(__name__)

DLQ_DIR = Path("storage/local_dlq")

# Shared in-memory DLQ — both price and news failures go here
_dlq: List[dict] = []


def _write_entry(entry: dict, filename: str) -> None:
    """Write a DLQ entry to disk. Never raises."""
    try:
        DLQ_DIR.mkdir(parents=True, exist_ok=True)
        file_path = DLQ_DIR / filename
        file_path.write_text(json.dumps(entry, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error("Failed to write DLQ file %s: %s", filename, e)


def send_to_dlq(
    data_type: Literal["price", "news"],
    payload: dict,
    error: Exception,
    ticker: str = "UNKNOWN",
) -> None:
    """Route any failed payload to the unified DLQ.

    Works for both price and news failures — the data_type field
    distinguishes them in the queue and in the filename.

    Args:
        data_type : "price" or "news"
        payload   : The raw payload that failed (dict)
        error     : The exception that caused the failure
        ticker    : NSE symbol (used in filename for news failures)
    """
    ts = datetime.now(timezone.utc)

    entry = {
        "data_type": data_type,
        "ticker": ticker,
        "payload": payload,
        "error": str(error),
        "error_type": type(error).__name__,
        "failed_at": ts.isoformat(),
    }

    _dlq.append(entry)

    # Build a descriptive filename
    ts_str = ts.strftime("%Y%m%d_%H%M%S_%f")
    if data_type == "news":
        filename = f"news_{ticker}_{ts_str}.json"
    else:
        filename = f"price_{ts_str}.json"

    _write_entry(entry, filename)

    logger.warning(
        "[DLQ] %s failure for %s — %s: %s",
        data_type.upper(), ticker, type(error).__name__, error
    )


# ---------------------------------------------------------------------------
# Convenience wrappers — keep call sites readable
# ---------------------------------------------------------------------------

def send_price_to_dlq(payload: dict, error: Exception) -> None:
    """Shorthand for routing a price ingestion failure to DLQ."""
    send_to_dlq("price", payload, error, ticker="ALL")


def send_news_to_dlq(
    ticker: str, payload: dict, error: Exception
) -> None:
    """Shorthand for routing a news fetch failure to DLQ."""
    send_to_dlq("news", payload, error, ticker=ticker)


# ---------------------------------------------------------------------------
# Inspection helpers
# ---------------------------------------------------------------------------

def get_dlq_messages(data_type: str = None) -> List[dict]:
    """Return DLQ messages, optionally filtered by data_type.

    Args:
        data_type: "price", "news", or None for all.

    Returns:
        List of DLQ entry dicts.
    """
    if data_type:
        return [m for m in _dlq if m["data_type"] == data_type]
    return list(_dlq)


def dlq_count(data_type: str = None) -> int:
    """Return count of DLQ messages, optionally filtered by type."""
    return len(get_dlq_messages(data_type))