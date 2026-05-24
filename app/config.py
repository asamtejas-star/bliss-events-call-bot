import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "our business")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WEBHOOK_AUTH_TOKEN = os.getenv("TWILIO_WEBHOOK_AUTH_TOKEN", "")

GOOGLE_SHEETS_CREDENTIALS_FILE = os.getenv(
    "GOOGLE_SHEETS_CREDENTIALS_FILE",
    str(BASE_DIR / "credentials" / "google-service-account.json"),
)
# For cloud hosts (Render, Railway, etc.): paste full service account JSON here
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "")
PORT = int(os.getenv("PORT", "8000"))
GOOGLE_SHEET_TAB = os.getenv("GOOGLE_SHEET_TAB", "Leads")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

CLOSING_MESSAGE = (
    "Perfect! Our team will call you back soon to finalize payment and other details. "
    "Thank you for calling, and have a wonderful day!"
)
