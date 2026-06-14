import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from validator import LTPResponse

logger = logging.getLogger(__name__)

SUCCESS_DIR = Path("storage/local_success")
SUCCESS_DIR.mkdir(parents=True, exist_ok=True)


def _write_success_entry(filename: str, payload: Any) -> None:
    try:
        file_path = SUCCESS_DIR / filename
        file_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        logger.error("Failed to write success file %s: %s", filename, e)


def save_price_success(ticker: str, validated_response: "LTPResponse") -> None:
    """Save only this ticker's price data to a separate file.
    
    Args:
        ticker: Trading symbol (e.g., 'RELIANCE')
        validated_response: Validated LTPResponse with all tickers' data
    """
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"price_{ticker}_{ts_str}.json"
    
    # Extract only this ticker's quote from the response
    key = f"NSE_EQ:{ticker}"
    if key not in validated_response.data:
        logger.warning("Ticker %s not found in response", ticker)
        return
    
    # Create payload with just this ticker's data
    payload = {
        "status": validated_response.status,
        "data": {
            key: validated_response.data[key].model_dump()
        }
    }
    _write_success_entry(filename, payload)


def save_news_success(ticker: str, payload: Any) -> None:
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    filename = f"news_{ticker}_{ts_str}.json"
    _write_success_entry(filename, payload)
