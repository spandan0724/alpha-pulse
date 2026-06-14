# ingestion/upstox_client/instruments.py
"""Instrument registry for NSE-listed stocks.

Single source of truth for Upstox instrument keys and company names.
To add a new ticker, just append to INSTRUMENTS — nothing else needs changing.

Structure:
    INSTRUMENTS: Dict[trading_symbol -> {instrument_key, name}]

Usage:
    from upstox_client.instruments import get_instrument_key, get_company_name
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
INSTRUMENTS_FILE = ROOT_DIR / "instruments.json"

# ---------------------------------------------------------------------------
# Default registry values used only if instruments.json is missing or invalid.
# ---------------------------------------------------------------------------
DEFAULT_INSTRUMENTS: Dict[str, dict] = {
    "ADANIENT": {
        "instrument_key": "NSE_EQ|INE423A01024",
        "name": "ADANI ENTERPRISES LIMITED",
    },
    "ABCAPITAL": {
        "instrument_key": "NSE_EQ|INE674K01013",
        "name": "ADITYA BIRLA CAPITAL LTD.",
    },
}


def _load_instruments() -> Dict[str, dict]:
    if not INSTRUMENTS_FILE.exists():
        logger.warning(
            "instruments.json not found at %s — falling back to default registry",
            INSTRUMENTS_FILE,
        )
        return DEFAULT_INSTRUMENTS

    try:
        with INSTRUMENTS_FILE.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)

        instruments: Dict[str, dict] = {}
        for item in raw:
            symbol = str(item.get("trading_symbol", "")).upper().strip()
            if not symbol:
                logger.warning("Skipping instrument entry with missing trading_symbol: %s", item)
                continue
            if "instrument_key" not in item or "name" not in item:
                logger.warning("Skipping incomplete instrument entry: %s", item)
                continue
            instruments[symbol] = {
                "instrument_key": item["instrument_key"],
                "name": item["name"],
            }
        if not instruments:
            raise ValueError("No valid instruments loaded from instruments.json")
        return instruments
    except Exception as exc:
        logger.warning(
            "Failed to load instruments.json (%s) — falling back to default registry",
            exc,
        )
        return DEFAULT_INSTRUMENTS


INSTRUMENTS: Dict[str, dict] = _load_instruments()

# Reverse map: instrument_key -> trading_symbol
# Built once at module load — used when parsing batch API responses
KEY_TO_TICKER: Dict[str, str] = {
    info["instrument_key"]: ticker
    for ticker, info in INSTRUMENTS.items()
}

# Ticker -> company name map for NewsAPI queries
TICKER_COMPANY_MAP: Dict[str, str] = {
    ticker: info["name"]
    for ticker, info in INSTRUMENTS.items()
}

# Active tickers used by the current ingestion run.
# Keep only these two symbols for now.
DEFAULT_ACTIVE_TICKERS = ["RELIANCE", "ADANIENT"]


def get_instrument_key(ticker: str) -> str:
    """Resolve a trading symbol to its Upstox instrument key.

    Args:
        ticker: NSE trading symbol (e.g. 'ADANIENT').

    Returns:
        Upstox instrument key string (e.g. 'NSE_EQ|INE423A01024').

    Raises:
        KeyError: If ticker is not registered in INSTRUMENTS.
    """
    ticker = ticker.upper().strip()
    if ticker not in INSTRUMENTS:
        raise KeyError(
            f"Ticker '{ticker}' not in registry. "
            f"Add it to INSTRUMENTS in instruments.py."
        )
    return INSTRUMENTS[ticker]["instrument_key"]


def get_company_name(ticker: str) -> str:
    """Return the full company name for a ticker.

    Used by the news client to build NewsAPI search queries.
    Requires the ticker to be registered in instruments.json.

    Args:
        ticker: NSE trading symbol.

    Returns:
        Full company name string.

    Raises:
        KeyError: If the ticker is not registered in instruments.json.
    """
    ticker = ticker.upper().strip()
    if ticker not in TICKER_COMPANY_MAP:
        raise KeyError(
            f"Ticker '{ticker}' is not registered in instruments.json. "
            "Add it there with a company name before using NewsAPI."
        )
    return TICKER_COMPANY_MAP[ticker]


def build_keys_string(tickers: List[str]) -> str:
    """Build a comma-separated instrument key string for Upstox batch requests.

    Skips tickers that are not in the registry with a warning rather than
    raising — allows partial batch fetches when some tickers are misconfigured.

    Args:
        tickers: List of NSE trading symbols.

    Returns:
        Comma-separated instrument keys string.
    """
    keys: List[str] = []
    for ticker in tickers:
        try:
            keys.append(get_instrument_key(ticker))
        except KeyError:
            logger.warning("Skipping unregistered ticker: %s", ticker)
    return ",".join(keys)


def resolve_ticker(instrument_key: str) -> Optional[str]:
    """Reverse-lookup: instrument key -> trading symbol.

    Used when parsing batch API responses where Upstox returns instrument
    keys rather than trading symbols.

    Args:
        instrument_key: Upstox instrument key string.

    Returns:
        Trading symbol string, or None if not found.
    """
    return KEY_TO_TICKER.get(instrument_key)


def all_tickers() -> List[str]:
    """Return a sorted list of active trading symbols for this run."""
    tickers = [t for t in DEFAULT_ACTIVE_TICKERS if t in INSTRUMENTS]
    if not tickers:
        return sorted(INSTRUMENTS.keys())
    return tickers