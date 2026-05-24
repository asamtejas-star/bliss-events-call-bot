import os

from dotenv import load_dotenv

load_dotenv()

BUSINESS_NAME = os.getenv("BUSINESS_NAME", "our business")
APPS_SCRIPT_URL = os.getenv("APPS_SCRIPT_URL", "").strip()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()

CLOSING_MESSAGE = (
    "Perfect! Our team will call you back soon to finalize payment and other details. "
    "Thank you, and have a wonderful day!"
)
