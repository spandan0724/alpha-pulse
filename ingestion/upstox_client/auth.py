# ingestion/upstox_client/auth.py
"""Upstox auth — reads access token from environment.

IMPORTANT: Never hardcode the access token in code.
           Store it in .env and load via python-dotenv.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


def get_access_token() -> str:
    """Read Upstox Bearer token from environment.

    Raises:
        RuntimeError: If UPSTOX_ACCESS_TOKEN is not set.
    """
    token = os.getenv("UPSTOX_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "UPSTOX_ACCESS_TOKEN is not set.\n"
            "Add it to your .env file:\n"
            "UPSTOX_ACCESS_TOKEN=your_token_here"
        )
    return token


def get_headers() -> dict:
    """Return Authorization headers for Upstox API requests."""
    return {
        "Accept": "application/json",
        "Authorization": f"Bearer {get_access_token()}",
    }