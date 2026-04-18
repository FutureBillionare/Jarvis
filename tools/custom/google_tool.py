"""
Tool: google_tool
Description: Full Google account control for HUBERT — Gmail, Drive, Calendar,
Search Console, and Analytics. First run opens a browser for OAuth login.
"""

import os, json, base64, mimetypes
from pathlib import Path
from datetime import datetime, timezone

# ── Paths ─────────────────────────────────────────────────────────────────────

_BASE       = Path(__file__).parent.parent.parent
_SECRET     = _BASE / ".secrets" / "google_client_secret.json"
_TOKEN      = _BASE / ".secrets" / "google_token.json"

_SCOPES = [
    "https://mail.google.com/",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/webmasters",
    "https://www.googleapis.com/auth/analytics.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

# ── Auth ──────────────────────────────────────────────────────────────────────

def _get_creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if _TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN), _SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(_SECRET), _SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)
        _TOKEN.parent.mkdir(parents=True, exist_ok=True)
        _TOKEN.write_text(creds.to_json())

    return creds

def _service(name, version):
    from googleapiclient.discovery import build
    return build(name, version, credentials=_get_creds())

# ── Gmail ─────────────────────────────────────────────────────────────────────

def run_gmail_send(params):
    import email.mime.text, email.mime.multipart
    from googleapiclient.errors import HttpError

    to      = params["to"]
    subject = params["subject"]
    body    = params["body"]

    msg = email.mime.multipart.MIMEMultipart()
    msg["to"]      = to
    msg["subject"] = subject
    msg.attach(email.mime.text.MIMEText(body, "plain"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    svc = _service("gmail", "v1")
    svc.users().messages().send(userId="me", body={"raw": raw}).execute()
    return f"Email sent to {to} — subject: {subject}"

def run_gmail_read(params):
    count  = int(params.get("count", 10))
    query  = params.get("query", "")
    svc    = _service("gmail", "v1")
    result = svc.users().messages().list(userId="me", q=query, maxResults=count).execute()
    msgs   = result.get("messages", [])
    if not msgs:
        return "No messages found."

    lines = []
    for m in msgs:
        detail = svc.users().messages().get(
            userId="me", id=m["id"], format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        lines.append(f"[{headers.get('Date','')}] {headers.get('From','')} — {headers.get('Subject','(no subject)')}")

    return "\n".join(lines)

def run_gmail_get_message(params):
    msg_id = params["message_id"]
    svc    = _service("gmail", "v1")
    detail = svc.users().messages().get(userId="me", id=msg_id, format="full").execute()

    headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
    body = ""
    parts = detail["payload"].get("parts", [])
    if parts:
        for p in parts:
            if p.get("mimeType") == "text/plain":
                data = p["body"].get("data", "")
                body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
                break
    else:
        data = detail["payload"]["body"].get("data", "")
        body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    return f"From: {headers.get('From')}\nDate: {headers.get('Date')}\nSubject: {headers.get('Subject')}\n\n{body[:3000]}"

# ── Google Drive ──────────────────────────────────────────────────────────────

def run_gdrive_list(params):
    folder  = params.get("folder", "root")
    count   = int(params.get("count", 20))
    svc     = _service("drive", "v3")
    query   = f"'{folder}' in parents and trashed=false" if folder != "root" else "trashed=false"
    result  = svc.files().list(
        q=query, pageSize=count,
        fields="files(id,name,mimeType,modifiedTime,size)"
    ).execute()
    files = result.get("files", [])
    if not files:
        return "No files found."
    lines = []
    for f in files:
        size = f.get("size", "—")
        lines.append(f"{f['name']}  [{f['mimeType'].split('.')[-1]}]  {f['modifiedTime'][:10]}  id:{f['id']}")
    return "\n".join(lines)

def run_gdrive_upload(params):
    from googleapiclient.http import MediaFileUpload
    file_path = params["file_path"]
    folder_id = params.get("folder_id")

    path     = Path(file_path)
    mime, _  = mimetypes.guess_type(str(path))
    mime     = mime or "application/octet-stream"

    meta = {"name": path.name}
    if folder_id:
        meta["parents"] = [folder_id]

    svc   = _service("drive", "v3")
    media = MediaFileUpload(str(path), mimetype=mime, resumable=True)
    f     = svc.files().create(body=meta, media_body=media, fields="id,name,webViewLink").execute()
    return f"Uploaded: {f['name']}  id:{f['id']}  link:{f.get('webViewLink','')}"

def run_gdrive_share(params):
    file_id = params["file_id"]
    email   = params.get("email")
    role    = params.get("role", "reader")  # reader / writer / owner
    svc     = _service("drive", "v3")

    perm = {"type": "anyone", "role": role} if not email else \
           {"type": "user", "role": role, "emailAddress": email}
    svc.permissions().create(fileId=file_id, body=perm).execute()

    target = email or "anyone with the link"
    return f"Shared file {file_id} with {target} as {role}"

# ── Google Calendar ───────────────────────────────────────────────────────────

def run_gcal_list(params):
    count  = int(params.get("count", 10))
    svc    = _service("calendar", "v3")
    now    = datetime.now(timezone.utc).isoformat()
    result = svc.events().list(
        calendarId="primary", timeMin=now,
        maxResults=count, singleEvents=True, orderBy="startTime"
    ).execute()
    events = result.get("items", [])
    if not events:
        return "No upcoming events."
    lines = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date"))
        lines.append(f"{start[:16]}  {e.get('summary','(no title)')}")
    return "\n".join(lines)

def run_gcal_create(params):
    title    = params["title"]
    start    = params["start"]   # ISO format: 2026-04-18T14:00:00
    end      = params["end"]
    desc     = params.get("description", "")
    tz       = params.get("timezone", "America/Chicago")

    svc   = _service("calendar", "v3")
    event = {
        "summary": title,
        "description": desc,
        "start": {"dateTime": start, "timeZone": tz},
        "end":   {"dateTime": end,   "timeZone": tz},
    }
    e = svc.events().insert(calendarId="primary", body=event).execute()
    return f"Event created: {e.get('summary')}  link:{e.get('htmlLink')}"

def run_gcal_delete(params):
    event_id = params["event_id"]
    svc      = _service("calendar", "v3")
    svc.events().delete(calendarId="primary", eventId=event_id).execute()
    return f"Event {event_id} deleted."

# ── Google Search Console ─────────────────────────────────────────────────────

def run_search_console(params):
    site       = params["site_url"]        # e.g. "https://example.com/"
    start_date = params.get("start_date", "2026-01-01")
    end_date   = params.get("end_date",   datetime.now().strftime("%Y-%m-%d"))
    dimension  = params.get("dimension",  "query")
    count      = int(params.get("count",  10))

    svc    = _service("searchconsole", "v1")
    result = svc.searchanalytics().query(
        siteUrl=site,
        body={
            "startDate": start_date,
            "endDate":   end_date,
            "dimensions": [dimension],
            "rowLimit":  count,
        }
    ).execute()

    rows = result.get("rows", [])
    if not rows:
        return "No search console data found."
    lines = [f"{'Query':<40} Clicks  Impressions  CTR     Position"]
    for r in rows:
        keys  = ", ".join(r.get("keys", []))
        lines.append(f"{keys:<40} {r['clicks']:<7} {r['impressions']:<12} {r['ctr']*100:.1f}%   {r['position']:.1f}")
    return "\n".join(lines)

# ── Google Analytics ──────────────────────────────────────────────────────────

def run_analytics(params):
    property_id = params["property_id"]   # e.g. "properties/123456789"
    start_date  = params.get("start_date", "30daysAgo")
    end_date    = params.get("end_date",   "today")
    metric      = params.get("metric",     "activeUsers")

    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import RunReportRequest, DateRange, Dimension, Metric

    client = BetaAnalyticsDataClient(credentials=_get_creds())
    request = RunReportRequest(
        property=property_id,
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name=metric)],
        date_ranges=[DateRange(start_date=start_date, end_date=end_date)],
        limit=int(params.get("count", 10)),
    )
    response = client.run_report(request)
    lines = [f"{'Page':<50} {metric}"]
    for row in response.rows:
        lines.append(f"{row.dimension_values[0].value:<50} {row.metric_values[0].value}")
    return "\n".join(lines)

# ── Auth helper ───────────────────────────────────────────────────────────────

def run_google_auth(params):
    """Trigger OAuth flow and return connected account info."""
    from googleapiclient.discovery import build
    creds = _get_creds()
    svc   = build("oauth2", "v2", credentials=creds)
    info  = svc.userinfo().get().execute()
    return f"Connected as: {info.get('email')}  name:{info.get('name')}  id:{info.get('id')}"

# ── Tool definitions ──────────────────────────────────────────────────────────

TOOLS = [
    ({"name": "google_auth",
      "description": "Connect HUBERT to Google account via OAuth. Run this first to log in.",
      "input_schema": {"type": "object", "properties": {}, "required": []}},
     run_google_auth),

    ({"name": "gmail_send",
      "description": "Send an email from HUBERT's Google account.",
      "input_schema": {"type": "object",
        "properties": {
            "to":      {"type": "string", "description": "Recipient email"},
            "subject": {"type": "string", "description": "Email subject"},
            "body":    {"type": "string", "description": "Email body (plain text)"},
        }, "required": ["to", "subject", "body"]}},
     run_gmail_send),

    ({"name": "gmail_read",
      "description": "Read recent emails. Optionally filter with a Gmail search query.",
      "input_schema": {"type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of emails to fetch (default 10)"},
            "query": {"type": "string",  "description": "Gmail search query e.g. 'from:someone@gmail.com is:unread'"},
        }, "required": []}},
     run_gmail_read),

    ({"name": "gmail_get_message",
      "description": "Read the full body of a specific email by message ID.",
      "input_schema": {"type": "object",
        "properties": {
            "message_id": {"type": "string", "description": "Gmail message ID from gmail_read"},
        }, "required": ["message_id"]}},
     run_gmail_get_message),

    ({"name": "gdrive_list",
      "description": "List files in Google Drive.",
      "input_schema": {"type": "object",
        "properties": {
            "folder": {"type": "string", "description": "Folder ID or 'root' (default)"},
            "count":  {"type": "integer", "description": "Max files to return (default 20)"},
        }, "required": []}},
     run_gdrive_list),

    ({"name": "gdrive_upload",
      "description": "Upload a file to Google Drive.",
      "input_schema": {"type": "object",
        "properties": {
            "file_path":  {"type": "string", "description": "Local path to the file"},
            "folder_id":  {"type": "string", "description": "Drive folder ID to upload into (optional)"},
        }, "required": ["file_path"]}},
     run_gdrive_upload),

    ({"name": "gdrive_share",
      "description": "Share a Google Drive file.",
      "input_schema": {"type": "object",
        "properties": {
            "file_id": {"type": "string", "description": "Drive file ID"},
            "email":   {"type": "string", "description": "Email to share with (omit for public link)"},
            "role":    {"type": "string", "description": "reader, writer, or owner (default: reader)"},
        }, "required": ["file_id"]}},
     run_gdrive_share),

    ({"name": "gcal_list",
      "description": "List upcoming Google Calendar events.",
      "input_schema": {"type": "object",
        "properties": {
            "count": {"type": "integer", "description": "Number of events (default 10)"},
        }, "required": []}},
     run_gcal_list),

    ({"name": "gcal_create",
      "description": "Create a Google Calendar event.",
      "input_schema": {"type": "object",
        "properties": {
            "title":       {"type": "string", "description": "Event title"},
            "start":       {"type": "string", "description": "Start time ISO format e.g. 2026-04-18T14:00:00"},
            "end":         {"type": "string", "description": "End time ISO format"},
            "description": {"type": "string", "description": "Event description (optional)"},
            "timezone":    {"type": "string", "description": "Timezone (default: America/Chicago)"},
        }, "required": ["title", "start", "end"]}},
     run_gcal_create),

    ({"name": "gcal_delete",
      "description": "Delete a Google Calendar event by ID.",
      "input_schema": {"type": "object",
        "properties": {
            "event_id": {"type": "string", "description": "Calendar event ID"},
        }, "required": ["event_id"]}},
     run_gcal_delete),

    ({"name": "search_console",
      "description": "Query Google Search Console for SEO data — clicks, impressions, CTR, position.",
      "input_schema": {"type": "object",
        "properties": {
            "site_url":   {"type": "string", "description": "Site URL e.g. https://example.com/"},
            "start_date": {"type": "string", "description": "Start date YYYY-MM-DD (default 2026-01-01)"},
            "end_date":   {"type": "string", "description": "End date YYYY-MM-DD (default today)"},
            "dimension":  {"type": "string", "description": "query, page, country, device (default: query)"},
            "count":      {"type": "integer", "description": "Rows to return (default 10)"},
        }, "required": ["site_url"]}},
     run_search_console),

    ({"name": "analytics",
      "description": "Query Google Analytics 4 — traffic, page views, active users.",
      "input_schema": {"type": "object",
        "properties": {
            "property_id": {"type": "string", "description": "GA4 property ID e.g. properties/123456789"},
            "start_date":  {"type": "string", "description": "Start date or '30daysAgo' (default)"},
            "end_date":    {"type": "string", "description": "End date or 'today' (default)"},
            "metric":      {"type": "string", "description": "activeUsers, sessions, screenPageViews (default: activeUsers)"},
            "count":       {"type": "integer", "description": "Rows to return (default 10)"},
        }, "required": ["property_id"]}},
     run_analytics),
]
