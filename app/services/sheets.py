import json
from datetime import datetime, timezone

from google.oauth2 import service_account
from googleapiclient.discovery import build

from app.config import (
    GOOGLE_SHEET_ID,
    GOOGLE_SHEET_TAB,
    GOOGLE_SERVICE_ACCOUNT_JSON,
    GOOGLE_SHEETS_CREDENTIALS_FILE,
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = [
    "Timestamp",
    "Caller Phone",
    "Caller Name",
    "Event Type",
    "Requested Date",
]


def _load_credentials():
    if GOOGLE_SERVICE_ACCOUNT_JSON.strip():
        info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
        return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return service_account.Credentials.from_service_account_file(
        GOOGLE_SHEETS_CREDENTIALS_FILE,
        scopes=SCOPES,
    )


def _get_service():
    credentials = _load_credentials()
    return build("sheets", "v4", credentials=credentials)


def ensure_headers() -> None:
    if not GOOGLE_SHEET_ID:
        raise ValueError("GOOGLE_SHEET_ID is not set in .env")

    service = _get_service()
    sheet = service.spreadsheets()
    range_name = f"{GOOGLE_SHEET_TAB}!A1:E1"
    result = sheet.values().get(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=range_name,
    ).execute()
    existing = result.get("values", [])

    if not existing or existing[0] != HEADERS:
        sheet.values().update(
            spreadsheetId=GOOGLE_SHEET_ID,
            range=range_name,
            valueInputOption="RAW",
            body={"values": [HEADERS]},
        ).execute()


def append_lead(
    *,
    caller_phone: str,
    caller_name: str,
    event_type: str,
    event_date: str,
) -> None:
    ensure_headers()
    service = _get_service()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    row = [timestamp, caller_phone, caller_name, event_type, event_date]

    service.spreadsheets().values().append(
        spreadsheetId=GOOGLE_SHEET_ID,
        range=f"{GOOGLE_SHEET_TAB}!A:E",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()
