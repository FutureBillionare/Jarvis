"""
Storage layer — Google Sheets + local JSON cache.

Manages two sheets inside the 'Internships Applied' Google Spreadsheet:
  • "Found"   — all discovered internships
  • "Applied" — internships that were actually applied to

Falls back to local JSON if Sheets auth fails.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Callable

log = logging.getLogger(__name__)

_BASE = Path(__file__).parent.parent
_SECRETS = _BASE / ".secrets" / "google_token.json"
_LOCAL_FOUND = Path(__file__).parent / "internships_found.json"
_LOCAL_APPLIED = Path(__file__).parent / "internships_applied.json"

SPREADSHEET_NAME = "Internships Applied"
SHEET_FOUND = "Found"
SHEET_APPLIED = "Applied"

FOUND_HEADERS = ["ID", "Title", "Company", "Location", "URL", "Source", "Found At", "Status"]
APPLIED_HEADERS = ["ID", "Title", "Company", "Location", "URL", "Applied At", "Status", "Notes"]


# ── Google Auth ───────────────────────────────────────────────────────────────

def _get_creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request

    scopes = [
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/calendar",
        "https://www.googleapis.com/auth/webmasters",
        "https://www.googleapis.com/auth/analytics.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "openid",
    ]

    creds = Credentials.from_authorized_user_file(str(_SECRETS), scopes)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds


def _sheets_service():
    from googleapiclient.discovery import build
    return build("sheets", "v4", credentials=_get_creds())


def _drive_service():
    from googleapiclient.discovery import build
    return build("drive", "v3", credentials=_get_creds())


# ── Spreadsheet Bootstrap ─────────────────────────────────────────────────────

def _find_or_create_spreadsheet() -> str:
    """Return the spreadsheet ID, creating it if it doesn't exist."""
    drive = _drive_service()
    sheets = _sheets_service()

    # Search for existing spreadsheet
    query = f"name='{SPREADSHEET_NAME}' and mimeType='application/vnd.google-apps.spreadsheet'"
    result = drive.files().list(q=query, fields="files(id, name)").execute()
    files = result.get("files", [])

    if files:
        return files[0]["id"]

    # Create new spreadsheet with two sheets
    body = {
        "properties": {"title": SPREADSHEET_NAME},
        "sheets": [
            {"properties": {"title": SHEET_FOUND}},
            {"properties": {"title": SHEET_APPLIED}},
        ],
    }
    spreadsheet = sheets.spreadsheets().create(body=body).execute()
    sid = spreadsheet["spreadsheetId"]

    # Write headers
    sheets.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"{SHEET_FOUND}!A1",
        valueInputOption="RAW",
        body={"values": [FOUND_HEADERS]},
    ).execute()
    sheets.spreadsheets().values().update(
        spreadsheetId=sid,
        range=f"{SHEET_APPLIED}!A1",
        valueInputOption="RAW",
        body={"values": [APPLIED_HEADERS]},
    ).execute()

    log.info(f"Created spreadsheet '{SPREADSHEET_NAME}' id={sid}")
    return sid


# ── Local JSON Cache ──────────────────────────────────────────────────────────

def _load_local(path: Path) -> list[dict]:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            return []
    return []


def _save_local(path: Path, data: list[dict]):
    path.write_text(json.dumps(data, indent=2))


# ── Public API ────────────────────────────────────────────────────────────────

class InternshipStorage:
    def __init__(self, status_cb: Callable | None = None):
        self._cb = status_cb
        self._sid: str | None = None
        self._sheets = None
        self._use_sheets = False
        self._init_sheets()

    def _emit(self, msg: str):
        log.info(msg)
        if self._cb:
            self._cb("storage", msg, 0)

    def _init_sheets(self):
        try:
            self._sid = _find_or_create_spreadsheet()
            self._sheets = _sheets_service()
            self._use_sheets = True
            self._emit(f"Connected to Google Sheets: {SPREADSHEET_NAME}")
        except Exception as e:
            log.warning(f"Google Sheets unavailable: {e}. Using local JSON.")
            self._use_sheets = False

    # ── Found Internships ──────────────────────────────────────────────────────

    def get_found_ids(self) -> set[str]:
        """Return set of IDs already in the Found sheet."""
        if self._use_sheets:
            try:
                result = self._sheets.spreadsheets().values().get(
                    spreadsheetId=self._sid,
                    range=f"{SHEET_FOUND}!A2:A",
                ).execute()
                values = result.get("values", [])
                return {row[0] for row in values if row}
            except Exception as e:
                log.warning(f"Sheets read error: {e}")

        local = _load_local(_LOCAL_FOUND)
        return {item["id"] for item in local}

    def save_found(self, listings: list[dict]):
        """Append new listings to Found sheet (skips duplicates)."""
        existing_ids = self.get_found_ids()
        new_listings = [l for l in listings if l["id"] not in existing_ids]

        if not new_listings:
            self._emit("No new internships to save.")
            return 0

        rows = []
        for l in new_listings:
            rows.append([
                l.get("id", ""),
                l.get("title", ""),
                l.get("company", ""),
                l.get("location", ""),
                l.get("url", ""),
                l.get("source", ""),
                l.get("found_at", ""),
                "new",
            ])

        if self._use_sheets:
            try:
                self._sheets.spreadsheets().values().append(
                    spreadsheetId=self._sid,
                    range=f"{SHEET_FOUND}!A1",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": rows},
                ).execute()
                self._emit(f"Saved {len(new_listings)} new internships to Google Sheets.")
            except Exception as e:
                log.warning(f"Sheets write error: {e}. Saving locally.")
                self._use_sheets = False

        if not self._use_sheets:
            local = _load_local(_LOCAL_FOUND)
            local.extend(new_listings)
            _save_local(_LOCAL_FOUND, local)
            self._emit(f"Saved {len(new_listings)} new internships locally.")

        return len(new_listings)

    # ── Applied Internships ────────────────────────────────────────────────────

    def get_applied_ids(self) -> set[str]:
        """Return set of IDs already applied to."""
        if self._use_sheets:
            try:
                result = self._sheets.spreadsheets().values().get(
                    spreadsheetId=self._sid,
                    range=f"{SHEET_APPLIED}!A2:A",
                ).execute()
                values = result.get("values", [])
                return {row[0] for row in values if row}
            except Exception as e:
                log.warning(f"Sheets read error: {e}")

        local = _load_local(_LOCAL_APPLIED)
        return {item["id"] for item in local}

    def mark_applied(self, listing: dict, notes: str = ""):
        """Record a successfully applied internship."""
        row = [
            listing.get("id", ""),
            listing.get("title", ""),
            listing.get("company", ""),
            listing.get("location", ""),
            listing.get("url", ""),
            datetime.now().isoformat(),
            "applied",
            notes,
        ]

        if self._use_sheets:
            try:
                self._sheets.spreadsheets().values().append(
                    spreadsheetId=self._sid,
                    range=f"{SHEET_APPLIED}!A1",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": [row]},
                ).execute()
                self._emit(f"Recorded applied: {listing['title']} @ {listing['company']}")
                return
            except Exception as e:
                log.warning(f"Sheets write error: {e}")

        local = _load_local(_LOCAL_APPLIED)
        applied_entry = dict(listing)
        applied_entry.update({"applied_at": datetime.now().isoformat(), "notes": notes})
        local.append(applied_entry)
        _save_local(_LOCAL_APPLIED, local)
        self._emit(f"Recorded applied (local): {listing['title']} @ {listing['company']}")

    def get_unapplied(self, listings: list[dict]) -> list[dict]:
        """Return listings that haven't been applied to yet."""
        applied_ids = self.get_applied_ids()
        return [l for l in listings if l["id"] not in applied_ids]

    def get_all_applied(self) -> list[dict]:
        """Return all applied internships."""
        if self._use_sheets:
            try:
                result = self._sheets.spreadsheets().values().get(
                    spreadsheetId=self._sid,
                    range=f"{SHEET_APPLIED}!A2:H",
                ).execute()
                values = result.get("values", [])
                return [
                    dict(zip(APPLIED_HEADERS, row))
                    for row in values if row
                ]
            except Exception as e:
                log.warning(f"Sheets read error: {e}")

        return _load_local(_LOCAL_APPLIED)
