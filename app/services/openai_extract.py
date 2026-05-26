import json
import re
from datetime import datetime

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


def parse_spelled_name(speech: str) -> str:
    """Turn letter-by-letter spelling into a readable name (only source used for caller name)."""
    speech = (speech or "").strip()
    if not speech:
        return ""

    text = re.sub(
        r"^(my name is|it is|it's|i spell it|spelled|that is|that's)\s*",
        "",
        speech,
        flags=re.IGNORECASE,
    )
    text = text.replace("-", " ").replace(".", " ").replace(",", " ")

    letter_run: list[str] = []
    name_parts: list[str] = []

    for word in text.split():
        letters_only = re.sub(r"[^a-zA-Z]", "", word)
        if not letters_only:
            continue
        if letters_only.lower() in ("space", "and", "dot"):
            if letter_run:
                name_parts.append("".join(letter_run))
                letter_run = []
            continue
        if len(letters_only) == 1:
            letter_run.append(letters_only.lower())
        else:
            if letter_run:
                name_parts.append("".join(letter_run))
                letter_run = []
            name_parts.append(letters_only.lower())

    if letter_run:
        name_parts.append("".join(letter_run))

    if name_parts:
        return " ".join(part.capitalize() for part in name_parts)

    return text.strip().title()


def apply_default_year(date_text: str) -> str:
    """If caller did not say a year, assume the current calendar year."""
    text = (date_text or "").strip()
    if not text:
        return ""
    if re.search(r"\b(19|20)\d{2}\b", text):
        return text
    return f"{text}, {datetime.now().year}"


_MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def _parse_calendar_date(text: str) -> datetime | None:
    """Return datetime if text is a real calendar date, else None."""
    text = text.strip()
    if not text:
        return None

    year_match = re.search(r"\b(19|20)\d{2}\b", text)
    year = int(year_match.group()) if year_match else datetime.now().year
    lower = text.lower()

    month: int | None = None
    day: int | None = None

    for name, num in _MONTH_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", lower):
            month = num
            break

    if month is not None:
        day_match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\b", lower)
        if day_match:
            day = int(day_match.group(1))
    else:
        numeric = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})(?:[/\-.](\d{2,4}))?\b", text)
        if numeric:
            month = int(numeric.group(1))
            day = int(numeric.group(2))
            if numeric.group(3):
                y = int(numeric.group(3))
                year = y if y > 99 else 2000 + y

    if month is None or day is None:
        return None

    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None

    try:
        return datetime(year, month, day)
    except ValueError:
        return None


def format_valid_date(dt: datetime) -> str:
    return f"{dt.strftime('%B')} {dt.day}, {dt.year}"


def validate_event_date(date_text: str) -> str:
    """
    Apply default year, verify the date exists on the calendar, and return
    a normalized string — or '' if invalid (e.g. June 59th).
    """
    with_year = apply_default_year(date_text)
    if not with_year:
        return ""

    parsed = _parse_calendar_date(with_year)
    if parsed is None:
        return ""

    return format_valid_date(parsed)


def extract_field(field: str, speech: str) -> str:
    """Normalize spoken answers into clean spreadsheet values."""
    speech = (speech or "").strip()
    if not speech:
        return ""

    # Spelled first/last names are parsed locally (letter-by-letter only)
    if field in ("name_first", "name_last"):
        return parse_spelled_name(speech)

    client = _get_client()
    if client is None:
        value = _fallback_extract(field, speech)
        if field == "date":
            return validate_event_date(value)
        return value

    prompts = {
        "name": "Extract only the caller's full name from what they said. Return JSON: {\"value\": \"...\"}",
        "event_type": "Extract only the type of event (wedding, birthday, corporate, etc.). Return JSON: {\"value\": \"...\"}",
        "date": (
            "Extract only the requested event date as a real calendar date "
            "(month and day; year optional). Reject impossible dates like June 59. "
            'Return JSON: {"value": "..."}'
        ),
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
        value = value or _fallback_extract(field, speech)
        if field == "date":
            return validate_event_date(value)
        return value
    except Exception:
        value = _fallback_extract(field, speech)
        if field == "date":
            return validate_event_date(value)
        return value
