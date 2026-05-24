import logging

import httpx

from bot.config import APPS_SCRIPT_URL

logger = logging.getLogger(__name__)


async def save_lead(
    *,
    source: str,
    contact: str,
    name: str,
    event_type: str,
    event_date: str,
) -> bool:
    if not APPS_SCRIPT_URL:
        logger.error("APPS_SCRIPT_URL is not set in .env")
        return False

    payload = {
        "source": source,
        "contact": contact,
        "name": name,
        "eventType": event_type,
        "date": event_date,
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(APPS_SCRIPT_URL, json=payload)
            response.raise_for_status()
        return True
    except Exception:
        logger.exception("Failed to save lead to Google Sheets")
        return False
