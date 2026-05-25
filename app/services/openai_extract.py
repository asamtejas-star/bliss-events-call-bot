import json
import re

from openai import OpenAI

from app.config import OPENAI_API_KEY, OPENAI_MODEL

_client: OpenAI | None = None


def _get_client() -> OpenAI | None:
    global _client
    if not OPENAI_API_KEY:
        return None
    if _client is None:
        _client = OpenAI(api_key=OPENAI_API_KEY, timeout=8.0)
    return _client


def _fallback_extract(field: str, speech: str) -> str:
    text = speech.strip()
    if field == "name":
        text = re.sub(
            r"^(my name is|i am|i'm|this is|it's|it is)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
    elif field == "event_type":
        text = re.sub(
            r"^(i need|i want|looking for|it's|it is|a|an)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
    elif field == "date":
        text = re.sub(
            r"^(on|for|around|about|the date is|date is)\s+",
            "",
            text,
            flags=re.IGNORECASE,
        )
    return text.strip().title() if field == "name" else text.strip()


def extract_field(field: str, speech: str) -> str:
    """Normalize spoken answers into clean spreadsheet values."""
    speech = (speech or "").strip()
    if not speech:
        return ""

    # Names: skip OpenAI so Twilio webhooks respond quickly and reliably
    if field == "name":
        return _fallback_extract("name", speech)

    client = _get_client()
    if client is None:
        return _fallback_extract(field, speech)

    prompts = {
        "name": "Extract only the caller's full name from what they said. Return JSON: {\"value\": \"...\"}",
        "event_type": "Extract only the type of event (wedding, birthday, corporate, etc.). Return JSON: {\"value\": \"...\"}",
        "date": "Extract only the requested event date. Keep their wording (e.g. June 15th 2026). Return JSON: {\"value\": \"...\"}",
    }

    try:
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": "You extract structured data from phone call transcripts. Return only valid JSON.",
                },
                {"role": "user", "content": f"{prompts[field]}\n\nCaller said: {speech}"},
            ],
        )
        data = json.loads(response.choices[0].message.content or "{}")
        value = str(data.get("value", "")).strip()
        return value or _fallback_extract(field, speech)
    except Exception:
        return _fallback_extract(field, speech)
