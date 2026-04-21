"""
color_rows.py — Color applied rows green and failed rows red in the Internships sheet.
"""

import json
from pathlib import Path

BASE = Path(__file__).parent
TOKEN_FILE = BASE.parent / ".secrets" / "google_token.json"
CREDS_FILE = BASE.parent / ".secrets" / "google_client_secret.json"
SHEET_ID = "1sPoDGQNeg3I-APvuoBGGujarIzG_O0qprij7byXlIOY"
SHEET_NAME = "Listings"


def get_sheets_service():
    import google.oauth2.credentials
    import google.auth.transport.requests
    from googleapiclient.discovery import build

    token_data = json.loads(TOKEN_FILE.read_text())
    creds_info = json.loads(CREDS_FILE.read_text())
    installed = creds_info.get("installed") or creds_info.get("web", {})

    creds = google.oauth2.credentials.Credentials(
        token=token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=installed.get("client_id"),
        client_secret=installed.get("client_secret"),
        scopes=token_data.get("scopes", []),
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(google.auth.transport.requests.Request())
        token_data["token"] = creds.token
        TOKEN_FILE.write_text(json.dumps(token_data))
    return build("sheets", "v4", credentials=creds)


def color_row(svc, sheet_gid: int, row_index: int, color: dict):
    """Set background color for an entire row (0-based row_index, 0 = header)."""
    svc.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={
            "requests": [{
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_gid,
                        "startRowIndex": row_index,
                        "endRowIndex": row_index + 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": color
                        }
                    },
                    "fields": "userEnteredFormat.backgroundColor"
                }
            }]
        }
    ).execute()


def main():
    svc = get_sheets_service()

    # Get the sheet GID for the "Listings" tab
    meta = svc.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
    sheet_gid = None
    for s in meta["sheets"]:
        if s["properties"]["title"] == SHEET_NAME:
            sheet_gid = s["properties"]["sheetId"]
            break
    if sheet_gid is None:
        print(f"Sheet tab '{SHEET_NAME}' not found!")
        return

    # Read status column (G) from the sheet
    result = svc.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!G:G"
    ).execute()
    rows = result.get("values", [])

    GREEN = {"red": 0.714, "green": 0.843, "blue": 0.659}   # light green
    RED   = {"red": 0.957, "green": 0.694, "blue": 0.694}   # light red
    WHITE = {"red": 1.0,   "green": 1.0,   "blue": 1.0}

    requests = []
    applied_count = 0
    failed_count = 0

    for i, row in enumerate(rows):
        if i == 0:
            continue  # skip header
        status = row[0].strip() if row else ""
        if status == "Applied":
            color = GREEN
            applied_count += 1
        elif status == "Failed":
            color = RED
            failed_count += 1
        else:
            color = WHITE

        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_gid,
                    "startRowIndex": i,
                    "endRowIndex": i + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": color
                    }
                },
                "fields": "userEnteredFormat.backgroundColor"
            }
        })

    if not requests:
        print("No rows to update.")
        return

    # Send in batches of 100
    batch_size = 100
    for start in range(0, len(requests), batch_size):
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={"requests": requests[start:start + batch_size]}
        ).execute()

    print(f"Done. Colored {applied_count} rows green (Applied), {failed_count} rows red (Failed).")


if __name__ == "__main__":
    main()
