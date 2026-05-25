import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.config import (
    BUSINESS_NAME,
    FALLBACK_PHONE,
    GOOGLE_SHEET_ID,
    OPENAI_API_KEY,
    OPENAI_MODEL,
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


@app.exception_handler(RequestValidationError)
async def voice_validation_error(request: Request, exc: RequestValidationError):
    if request.url.path.startswith("/voice"):
        logger.warning("Validation error on voice route: %s", exc)
        from app.routes.voice import build_error_twiml

        return build_error_twiml()
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


@app.exception_handler(Exception)
async def unhandled_exception(request: Request, exc: Exception):
    if request.url.path.startswith("/voice"):
        logger.exception("Unhandled error on voice route: %s", exc)
        from app.routes.voice import build_error_twiml

        return build_error_twiml()
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health")
def health():
    return {
        "status": "ok",
        "business": BUSINESS_NAME,
        "webhook_base_url": PUBLIC_BASE_URL or "(not set)",
        "fallback_phone": FALLBACK_PHONE,
        "openai_enabled": bool(OPENAI_API_KEY),
        "openai_model": OPENAI_MODEL if OPENAI_API_KEY else None,
    }
