import logging

from fastapi import APIRouter, Form, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.config import (
    BUSINESS_NAME,
    CLOSING_MESSAGE,
    FALLBACK_PHONE,
    PUBLIC_BASE_URL,
    TWILIO_WEBHOOK_AUTH_TOKEN,
)
from app.services.openai_extract import extract_field
from app.services.sheets import append_lead
from app.services.state import clear_session, get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

MAX_RETRIES = 2

PROMPTS = {
    "name": f"Thank you for calling {BUSINESS_NAME}. I'm your virtual assistant. May I have your name, please?",
    "event_type": "Thanks! What type of event are you planning?",
    "date": "Great. What date are you looking for?",
}


def _xml_response(twiml: VoiceResponse) -> Response:
    return Response(content=str(twiml), media_type="application/xml")


def _phone_for_speech(phone: str) -> str:
    """Speak each digit separately: 4, 8, 0, 5, 7, 7, 3, 0, 9, 0"""
    digits = "".join(c for c in phone if c.isdigit())
    if not digits:
        return phone
    return ", ".join(digits)


def build_error_twiml(call_sid: str | None = None) -> Response:
    if call_sid:
        clear_session(call_sid)
    spoken = _phone_for_speech(FALLBACK_PHONE)
    response = VoiceResponse()
    response.say(
        "We're sorry, something went wrong with our phone system. "
        f"Please call us directly at {spoken}. Goodbye."
    )
    response.hangup()
    return _xml_response(response)


def _validate_twilio(request: Request, form: dict) -> bool:
    if not TWILIO_WEBHOOK_AUTH_TOKEN:
        return True
    signature = request.headers.get("X-Twilio-Signature", "")
    url = str(request.url)
    validator = RequestValidator(TWILIO_WEBHOOK_AUTH_TOKEN)
    return validator.validate(url, form, signature)


def _gather_speech(action_path: str, prompt: str) -> Gather:
    return Gather(
        input="speech",
        action=f"{PUBLIC_BASE_URL}{action_path}",
        method="POST",
        speech_timeout="auto",
        speech_model="phone_call",
        language="en-US",
        timeout=5,
    )


def _retry_count(session, step: str) -> int:
    return session.retries.get(step, 0)


def _increment_retry(session, step: str) -> None:
    session.retries[step] = _retry_count(session, step) + 1


def _ask_step(response: VoiceResponse, step: str) -> None:
    gather = _gather_speech("/voice/handle", PROMPTS[step])
    gather.say(PROMPTS[step])
    response.append(gather)
    response.say("I didn't catch that. Let me try again.")
    response.redirect(f"{PUBLIC_BASE_URL}/voice/handle", method="POST")


def _advance_or_retry(
    call_sid: str,
    session,
    step: str,
    value: str,
    response: VoiceResponse,
) -> bool:
    """Returns True if step was captured and we should continue."""
    if value:
        return True

    if _retry_count(session, step) >= MAX_RETRIES:
        response.say(
            "I'm having trouble hearing you. Please call back when you're ready, "
            "or leave a message with your name, event type, and preferred date. Goodbye."
        )
        response.hangup()
        clear_session(call_sid)
        return False

    _increment_retry(session, step)
    _ask_step(response, step)
    return False


@router.post("/fallback")
@router.post("/error")
async def voice_fallback(request: Request):
    """Twilio 'primary handler fails' URL — same message as other errors."""
    return build_error_twiml()


@router.post("/incoming")
async def incoming_call(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(default=""),
):
    try:
        form = dict(await request.form())
        if not _validate_twilio(request, form):
            logger.warning("Invalid Twilio signature on /incoming")
            return build_error_twiml(CallSid)

        if not PUBLIC_BASE_URL:
            logger.error("PUBLIC_BASE_URL is not set")
            return build_error_twiml(CallSid)

        clear_session(CallSid)
        session = get_session(CallSid, caller_phone=From)

        response = VoiceResponse()
        _ask_step(response, session.step)
        return _xml_response(response)
    except Exception:
        logger.exception("Error in /voice/incoming")
        return build_error_twiml(CallSid)


@router.post("/handle")
async def handle_speech(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(default=""),
    SpeechResult: str = Form(default=""),
):
    try:
        form = dict(await request.form())
        if not _validate_twilio(request, form):
            logger.warning("Invalid Twilio signature on /handle")
            return build_error_twiml(CallSid)

        if not PUBLIC_BASE_URL:
            logger.error("PUBLIC_BASE_URL is not set")
            return build_error_twiml(CallSid)

        session = get_session(CallSid, caller_phone=From)
        response = VoiceResponse()
        speech = (SpeechResult or "").strip()

        if session.step == "name":
            value = extract_field("name", speech)
            if not _advance_or_retry(CallSid, session, "name", value, response):
                return _xml_response(response)
            session.caller_name = value
            session.step = "event_type"
            _ask_step(response, "event_type")
            return _xml_response(response)

        if session.step == "event_type":
            value = extract_field("event_type", speech)
            if not _advance_or_retry(CallSid, session, "event_type", value, response):
                return _xml_response(response)
            session.event_type = value
            session.step = "date"
            _ask_step(response, "date")
            return _xml_response(response)

        if session.step == "date":
            value = extract_field("date", speech)
            if not _advance_or_retry(CallSid, session, "date", value, response):
                return _xml_response(response)
            session.event_date = value
            session.step = "done"

            try:
                append_lead(
                    caller_phone=session.caller_phone or From,
                    caller_name=session.caller_name,
                    event_type=session.event_type,
                    event_date=session.event_date,
                )
            except Exception:
                logger.exception("Failed to save lead to Google Sheets")
                response.say(
                    "I have your details, but I had trouble saving them. "
                    "Our team will still follow up with you shortly."
                )
            else:
                response.say(CLOSING_MESSAGE)

            clear_session(CallSid)
            response.hangup()
            return _xml_response(response)

        logger.warning("Unexpected call state for CallSid=%s step=%s", CallSid, session.step)
        return build_error_twiml(CallSid)
    except Exception:
        logger.exception("Error in /voice/handle")
        return build_error_twiml(CallSid)
