import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import (
    BUSINESS_NAME,
    GOOGLE_SHEET_ID,
    PUBLIC_BASE_URL,
    TWILIO_ACCOUNT_SID,
)
from app.routes import voice

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    missing = []
    if not PUBLIC_BASE_URL:
        missing.append("PUBLIC_BASE_URL")
    if not TWILIO_ACCOUNT_SID:
        missing.append("TWILIO_ACCOUNT_SID")
    if not GOOGLE_SHEET_ID:
        missing.append("GOOGLE_SHEET_ID")
    if missing:
        logger.warning(
            "Missing .env values: %s — phone calls will not work until these are set.",
            ", ".join(missing),
        )
    else:
        logger.info("Phone bot ready. Twilio webhook: %s/voice/incoming", PUBLIC_BASE_URL)
    yield


app = FastAPI(title="Bliss AI Call Bot", version="1.0.0", lifespan=lifespan)
app.include_router(voice.router)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "business": BUSINESS_NAME,
        "webhook_base_url": PUBLIC_BASE_URL or "(not set)",
    }
