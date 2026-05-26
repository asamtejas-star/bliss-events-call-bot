import logging
import re

from fastapi import APIRouter, Form, Request, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import Gather, VoiceResponse

from app.config import (
    BUSINESS_NAME,
    CLOSING_MESSAGE,
    FALLBACK_PHONE,
    PUBLIC_BASE_URL,
    TWILIO_VOICE,
    TWILIO_WEBHOOK_AUTH_TOKEN,
)
from app.services.openai_extract import extract_field
from app.services.sheets import append_lead
from app.services.state import VALID_STEPS, clear_session, get_session

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/voice", tags=["voice"])

MAX_RETRIES = 2

PROMPTS = {
    "name_first": (
        f"Thank you for calling {BUSINESS_NAME}. I'm your virtual assistant. "
        "Please spell your first name, letter by letter."
    ),
    "name_last": "Thank you. Now please spell your last name, letter by letter.",
    "event_type": "Thanks! What type of event are you planning?",
    "date": "Great. What date are you looking for?",
}

# Brief noises Twilio sometimes transcribes — do not count as an answer
_NOISE_UTTERANCES = frozenset(
    {"uh", "um", "umm", "hmm", "hm", "ah", "oh", "yeah", "yes", "no", "ok", "okay"}
)


def _xml_response(twiml: VoiceResponse) -> Response:
    return Response(content=str(twiml), media_type="application/xml")


def _say(target, message: str) -> None:
    """Twilio free basic voice (man or woman — no Polly/neural charges)."""
    voice = TWILIO_VOICE if TWILIO_VOICE in ("man", "woman") else "woman"
    target.say(message, voice=voice, language="en-US")


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
    _say(
        response,
        "We're sorry, something went wrong with our phone system. "
        f"Please call us directly at {spoken}. Goodbye.",
    )
    response.hangup()
    return _xml_response(response)


def _normalize_base_url(url: str) -> str:
    """Strip trailing /health or slashes — common mistake when copying from browser."""
    url = url.rstrip("/")
    if url.endswith("/health"):
        url = url[: -len("/health")]
    return url.rstrip("/")


def _public_base_url(request: Request) -> str:
    """App URL for TwiML callbacks — env var or Render/proxy headers."""
    if PUBLIC_BASE_URL:
        return _normalize_base_url(PUBLIC_BASE_URL)
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
    proto = request.headers.get("X-Forwarded-Proto", "https")
    if host:
        return f"{proto}://{host}".rstrip("/")
    return ""


def _validation_url_candidates(request: Request) -> list[str]:
    """URLs Twilio may have signed (proxy-aware)."""
    path = request.url.path
    query = request.url.query
    suffix = f"{path}?{query}" if query else path

    candidates: list[str] = []
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host")
    proto = request.headers.get("X-Forwarded-Proto", "https")

    if host:
        candidates.append(f"{proto}://{host}{suffix}")

    if PUBLIC_BASE_URL:
        candidates.append(f"{PUBLIC_BASE_URL.rstrip('/')}{suffix}")

    return list(dict.fromkeys(candidates))


def _validate_twilio(request: Request, form: dict) -> bool:
    if not TWILIO_WEBHOOK_AUTH_TOKEN:
        return True

    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        logger.warning("Missing X-Twilio-Signature header")
        return False

    validator = RequestValidator(TWILIO_WEBHOOK_AUTH_TOKEN)
    for url in _validation_url_candidates(request):
        if validator.validate(url, form, signature):
            return True

    logger.warning(
        "Invalid Twilio signature. Tried URLs: %s. "
        "Ensure TWILIO_WEBHOOK_AUTH_TOKEN matches your Twilio Auth Token exactly.",
        _validation_url_candidates(request),
    )
    return False


def _handle_action_url(base_url: str, step: str) -> str:
    return f"{base_url}/voice/handle?step={step}"


def _listen_url(base_url: str, step: str) -> str:
    return f"{base_url}/voice/listen?step={step}"


def _gather_speech(base_url: str, step: str, *, spelling: bool = False) -> Gather:
    # barge_in=False: background noise won't interrupt the question
    # Longer silence window when spelling so pauses between letters are OK
    return Gather(
        input="speech",
        action=_handle_action_url(base_url, step),
        method="POST",
        barge_in=False,
        speech_timeout="4" if spelling else "auto",
        speech_model="phone_call",
        language="en-US",
        timeout=12 if spelling else 10,
    )


def _accept_answer(step: str, value: str) -> bool:
    if not value or not value.strip():
        return False
    if value.strip().lower() in _NOISE_UTTERANCES:
        return False
    if step in ("name_first", "name_last"):
        return len(re.sub(r"[^a-zA-Z]", "", value)) >= 2
    return len(value.strip()) >= 2


def _retry_count(session, step: str) -> int:
    return session.retries.get(step, 0)


def _increment_retry(session, step: str) -> None:
    session.retries[step] = _retry_count(session, step) + 1


def _ask_step(response: VoiceResponse, step: str, base_url: str) -> None:
    """Play the question to completion, then start listening on a separate request."""
    _say(response, PROMPTS[step])
    response.redirect(_listen_url(base_url, step), method="POST")


def _start_listening(response: VoiceResponse, step: str, base_url: str) -> None:
    """Gather only — used after the question has fully finished playing."""
    spelling = step in ("name_first", "name_last")
    gather = _gather_speech(base_url, step, spelling=spelling)
    response.append(gather)
    _say(response, "I didn't catch that. Let me try again.")
    response.redirect(_handle_action_url(base_url, step), method="POST")


def _advance_or_retry(
    call_sid: str,
    session,
    step: str,
    value: str,
    response: VoiceResponse,
    base_url: str,
) -> bool:
    """Returns True if step was captured and we should continue."""
    if _accept_answer(step, value):
        return True

    if _retry_count(session, step) >= MAX_RETRIES:
        _say(
            response,
            "I'm having trouble hearing you. Please call back when you're ready, "
            "or leave a message with your name, event type, and preferred date. Goodbye.",
        )
        response.hangup()
        clear_session(call_sid)
        return False

    _increment_retry(session, step)
    _ask_step(response, step, base_url)
    return False


@router.post("/fallback")
@router.post("/error")
async def voice_fallback(request: Request):
    """Twilio 'primary handler fails' URL — same message as other errors."""
    return build_error_twiml()


@router.post("/listen")
async def listen_for_answer(
    request: Request,
    CallSid: str = Form(...),
):
    """Start speech recognition only after the prompt has finished playing."""
    try:
        form = dict(await request.form())
        base_url = _public_base_url(request)

        if not _validate_twilio(request, form):
            return build_error_twiml(CallSid)

        if not base_url:
            logger.error("Cannot determine public URL — set PUBLIC_BASE_URL on Render")
            return build_error_twiml(CallSid)

        step = request.query_params.get("step")
        if step not in VALID_STEPS:
            logger.warning("Invalid listen step: %s", step)
            return build_error_twiml(CallSid)

        response = VoiceResponse()
        _start_listening(response, step, base_url)
        logger.info("Listening CallSid=%s step=%s", CallSid, step)
        return _xml_response(response)
    except Exception:
        logger.exception("Error in /voice/listen")
        return build_error_twiml(CallSid)


@router.post("/incoming")
async def incoming_call(
    request: Request,
    CallSid: str = Form(...),
    From: str = Form(default=""),
):
    try:
        form = dict(await request.form())
        base_url = _public_base_url(request)

        if not _validate_twilio(request, form):
            return build_error_twiml(CallSid)

        if not base_url:
            logger.error("Cannot determine public URL — set PUBLIC_BASE_URL on Render")
            return build_error_twiml(CallSid)

        clear_session(CallSid)
        session = get_session(CallSid, caller_phone=From)

        response = VoiceResponse()
        _ask_step(response, session.step, base_url)
        logger.info("Incoming call CallSid=%s base_url=%s", CallSid, base_url)
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
        base_url = _public_base_url(request)

        if not _validate_twilio(request, form):
            return build_error_twiml(CallSid)

        if not base_url:
            logger.error("Cannot determine public URL — set PUBLIC_BASE_URL on Render")
            return build_error_twiml(CallSid)

        session = get_session(CallSid, caller_phone=From)
        step_param = request.query_params.get("step")
        if step_param in VALID_STEPS:
            session.step = step_param  # type: ignore[assignment]

        response = VoiceResponse()
        speech = (SpeechResult or "").strip()
        logger.info(
            "CallSid=%s step=%s speech=%r",
            CallSid,
            session.step,
            speech[:80] if speech else "",
        )

        if session.step == "name_first":
            value = extract_field("name_first", speech)
            if not _advance_or_retry(CallSid, session, "name_first", value, response, base_url):
                return _xml_response(response)
            session.first_name = value
            session.step = "name_last"
            _ask_step(response, "name_last", base_url)
            return _xml_response(response)

        if session.step == "name_last":
            value = extract_field("name_last", speech)
            if not _advance_or_retry(CallSid, session, "name_last", value, response, base_url):
                return _xml_response(response)
            session.last_name = value
            session.update_full_name()
            session.step = "event_type"
            _ask_step(response, "event_type", base_url)
            return _xml_response(response)

        if session.step == "event_type":
            value = extract_field("event_type", speech)
            if not _advance_or_retry(CallSid, session, "event_type", value, response, base_url):
                return _xml_response(response)
            session.event_type = value
            session.step = "date"
            _ask_step(response, "date", base_url)
            return _xml_response(response)

        if session.step == "date":
            value = extract_field("date", speech)
            if not _advance_or_retry(CallSid, session, "date", value, response, base_url):
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
                _say(
                    response,
                    "I have your details, but I had trouble saving them. "
                    "Our team will still follow up with you shortly.",
                )
            else:
                _say(response, CLOSING_MESSAGE)

            clear_session(CallSid)
            response.hangup()
            return _xml_response(response)

        logger.warning("Unexpected call state for CallSid=%s step=%s", CallSid, session.step)
        return build_error_twiml(CallSid)
    except Exception:
        logger.exception("Error in /voice/handle")
        return build_error_twiml(CallSid)
