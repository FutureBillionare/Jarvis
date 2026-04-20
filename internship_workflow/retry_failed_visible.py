"""
retry_failed_visible.py — Retry all failed LinkedIn listings using a VISIBLE browser.

Key differences from run_with_sheet_sync.py:
  • headless=False  → real browser window, bypasses LinkedIn bot detection
  • Slower, randomized delays between actions to mimic human behavior
  • Skips international (non-US/remote) jobs that won't be relevant
  • Focuses exclusively on LinkedIn Easy Apply flow with better modal handling
  • Updates internships_found.json and Google Sheet in real time

Run: python retry_failed_visible.py
"""

import asyncio
import io
import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

BASE = Path(__file__).parent
LISTINGS_FILE = BASE / "internships_found.json"
TOKEN_FILE = BASE.parent / ".secrets" / "google_token.json"
CREDS_FILE = BASE.parent / ".secrets" / "google_client_secret.json"
SHEET_ID = "1sPoDGQNeg3I-APvuoBGGujarIzG_O0qprij7byXlIOY"
SHEET_NAME = "Listings"

LINKEDIN_EMAIL = "jakegoncalves2002@gmail.com"
LINKEDIN_PASSWORD = "Browneyes2007!"

# International subdomains to skip (non-US jobs not worth pursuing)
SKIP_SUBDOMAINS = {"uk.linkedin.com", "nl.linkedin.com", "sg.linkedin.com",
                   "tr.linkedin.com", "id.linkedin.com", "au.linkedin.com",
                   "de.linkedin.com", "fr.linkedin.com", "ca.linkedin.com"}

PROFILE = json.loads((BASE / "profile.json").read_text())
P = PROFILE["personal"]
E = PROFILE["education"]
RESUME_PATH = PROFILE.get("documents", {}).get("resume_path", "")


# ── Google Sheets ─────────────────────────────────────────────────────────────

def _get_sheets_service():
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


def _update_sheet(sheets_svc, row_index: int, status: str, notes: str = ""):
    sheet_row = row_index + 2
    date_str = datetime.now().strftime("%Y-%m-%d") if status == "Applied" else ""
    try:
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"{SHEET_NAME}!G{sheet_row}:I{sheet_row}",
            valueInputOption="RAW",
            body={"values": [[status, date_str, notes]]},
        ).execute()
    except Exception as e:
        log.warning(f"  Sheet update error: {e}")


def _save_status(listing_id: str, status: str):
    listings = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
    for item in listings:
        if item.get("id") == listing_id:
            item["status"] = status
            if status == "applied":
                item["applied_at"] = datetime.now().isoformat()
    LISTINGS_FILE.write_text(json.dumps(listings, indent=2), encoding="utf-8")


# ── Human-like helpers ────────────────────────────────────────────────────────

async def _human_delay(min_ms=800, max_ms=2500):
    await asyncio.sleep(random.uniform(min_ms, max_ms) / 1000)


async def _fill_field(page, selector: str, value: str):
    try:
        el = page.locator(selector).first
        if await el.count():
            await el.click()
            await _human_delay(200, 500)
            await el.fill(value)
            return True
    except Exception:
        pass
    return False


# ── LinkedIn Login ────────────────────────────────────────────────────────────

async def linkedin_login(context):
    log.info("Logging into LinkedIn (visible browser)...")
    page = await context.new_page()
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
    await _human_delay(1500, 3000)

    try:
        await page.wait_for_selector("#username", timeout=15000)
    except Exception:
        log.warning("Login page slow to load.")

    await page.fill("#username", LINKEDIN_EMAIL)
    await _human_delay(400, 900)
    await page.fill("#password", LINKEDIN_PASSWORD)
    await _human_delay(500, 1200)
    await page.click("button[type='submit']")
    await _human_delay(3000, 5000)

    if "checkpoint" in page.url or "challenge" in page.url:
        log.warning("⚠ 2FA / CAPTCHA required — waiting up to 90s for manual completion...")
        for _ in range(90):
            await asyncio.sleep(1)
            if "checkpoint" not in page.url and "challenge" not in page.url:
                break

    log.info(f"LinkedIn login done. Current URL: {page.url}")
    return page


# ── Easy Apply handler ────────────────────────────────────────────────────────

async def _try_easy_apply(page, listing: dict) -> bool:
    """Navigate to listing and attempt LinkedIn Easy Apply with robust modal handling."""
    await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
    await _human_delay(2000, 4000)

    # Look for Easy Apply button (multiple selectors)
    easy_selectors = [
        ".jobs-apply-button--top-card",
        "button.jobs-apply-button",
        "[data-control-name='jobdetails_topcard_inapply']",
        "button:has-text('Easy Apply')",
        "a:has-text('Easy Apply')",
    ]
    easy_btn = None
    for sel in easy_selectors:
        candidate = page.locator(sel).first
        if await candidate.count():
            easy_btn = candidate
            break

    if not easy_btn:
        log.info("  No Easy Apply button found.")
        return False

    await easy_btn.click()
    await _human_delay(2000, 3500)

    # Wait for modal to appear
    modal_sel = ".jobs-easy-apply-content, .jobs-easy-apply-modal, [data-test-modal], .artdeco-modal__content"
    try:
        await page.wait_for_selector(modal_sel, timeout=8000)
    except Exception:
        log.warning("  Modal did not appear after Easy Apply click.")

    modal = page.locator(modal_sel).first
    ctx = modal if await modal.count() else page

    for step in range(12):
        # Fill basic fields visible in this step
        for sel, val in [
            ("input[id*='firstName'], input[name*='firstName'], input[aria-label*='First name']", P["first_name"]),
            ("input[id*='lastName'], input[name*='lastName'], input[aria-label*='Last name']", P["last_name"]),
            ("input[type='email'], input[id*='email']", P["email"]),
            ("input[type='tel'], input[id*='phone'], input[aria-label*='Phone']", P["phone"]),
            ("input[id*='city'], input[aria-label*='City'], input[id*='location']", P["city"]),
        ]:
            await _fill_field(ctx, sel, val)

        # Upload resume if file input visible
        try:
            fi = ctx.locator("input[type='file']").first
            if await fi.count() and RESUME_PATH:
                await fi.set_input_files(RESUME_PATH)
                await _human_delay(1000, 2000)
        except Exception:
            pass

        # Handle common yes/no radio questions (work authorization, etc.)
        try:
            yes_radios = ctx.locator("label:has-text('Yes'), input[type='radio'][value='Yes']")
            count = await yes_radios.count()
            for i in range(min(count, 5)):
                try:
                    await yes_radios.nth(i).click()
                    await _human_delay(200, 400)
                except Exception:
                    pass
        except Exception:
            pass

        # Check for Submit button
        submit = ctx.locator(
            "button[aria-label='Submit application'], "
            "button:has-text('Submit application'), "
            "button:has-text('Submit')"
        ).first
        if await submit.count():
            await submit.click()
            await _human_delay(2000, 3000)
            log.info("  Submitted!")
            return True

        # Check for Next / Review / Continue
        next_btn = ctx.locator(
            "button[aria-label='Continue to next step']:not([disabled]), "
            "button[data-easy-apply-next-button]:not([disabled]), "
            "button:has-text('Review'):not([disabled]), "
            "footer button:has-text('Next'):not([disabled]), "
            "button:has-text('Continue'):not([disabled])"
        ).first
        if await next_btn.count():
            await next_btn.click()
            await _human_delay(1500, 2500)
        else:
            log.info(f"  No next/submit at step {step+1} — stopping.")
            break

    return False


# ── External link fallback ────────────────────────────────────────────────────

async def _try_external_apply(page, listing: dict) -> bool:
    """For LinkedIn jobs that redirect to an external ATS."""
    await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
    await _human_delay(1500, 3000)

    apply_btn = page.locator("a:has-text('Apply'), button:has-text('Apply')").first
    if not await apply_btn.count():
        return False

    href = await apply_btn.get_attribute("href")
    if not href:
        return False

    # Decode LinkedIn safety redirect
    if "linkedin.com/safety/go" in href:
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        href = unquote(qs.get("url", [href])[0])

    if not href.startswith("http") or "linkedin.com" in href:
        return False

    ext_page = await page.context.new_page()
    try:
        await ext_page.goto(href, wait_until="domcontentloaded", timeout=25000)
        await _human_delay(2000, 3500)

        # Fill common fields
        for sel, val in [
            ("input[name*='first'], input[id*='first'], input[aria-label*='First']", P["first_name"]),
            ("input[name*='last'], input[id*='last'], input[aria-label*='Last']", P["last_name"]),
            ("input[type='email'], input[name*='email']", P["email"]),
            ("input[type='tel'], input[name*='phone']", P["phone"]),
            ("input[name*='city'], input[id*='city']", P["city"]),
            ("input[name*='state'], input[id*='state']", P["state"]),
        ]:
            await _fill_field(ext_page, sel, val)

        # Upload resume
        try:
            fi = ext_page.locator("input[type='file']").first
            if await fi.count() and RESUME_PATH:
                await fi.set_input_files(RESUME_PATH)
                await _human_delay(1000, 2000)
        except Exception:
            pass

        # Submit
        submit = ext_page.locator(
            "button[type='submit'], input[type='submit'], "
            "button:has-text('Submit'), button:has-text('Apply')"
        ).first
        if await submit.count():
            await submit.click()
            await _human_delay(3000, 4000)
            await ext_page.close()
            return True

        await ext_page.close()
    except Exception as e:
        log.error(f"  External apply error: {e}")
        try:
            await ext_page.close()
        except Exception:
            pass

    return False


# ── Main loop ─────────────────────────────────────────────────────────────────

async def retry_failed(listings: list, sheets_svc):
    from playwright.async_api import async_playwright

    applied, failed, skipped = [], [], []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,   # ← VISIBLE BROWSER: defeats LinkedIn bot detection
            slow_mo=50,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport=None,   # use window size
            locale="en-US",
            timezone_id="America/Chicago",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        linkedin_page = await linkedin_login(context)

        for i, listing in enumerate(listings):
            domain = urlparse(listing["url"]).netloc
            if domain in SKIP_SUBDOMAINS:
                log.info(f"[{i+1}/{len(listings)}] SKIP (international): {listing['title']} @ {listing['company']}")
                skipped.append(listing)
                continue

            log.info(f"[{i+1}/{len(listings)}] {listing['title']} @ {listing['company']}")

            success = False
            notes = ""
            try:
                # Try Easy Apply first, then external fallback
                success = await _try_easy_apply(linkedin_page, listing)
                if not success:
                    log.info("  Easy Apply failed — trying external apply link...")
                    success = await _try_external_apply(linkedin_page, listing)
            except Exception as e:
                notes = f"Error: {str(e)[:80]}"
                log.error(f"  Exception: {e}")

            status = "Applied" if success else "Failed"
            log.info(f"  → {status}")

            # Get the row index in the qualified list (for sheet sync)
            # Load all qualified listings to find this one's position
            all_listings = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
            qualified = [x for x in all_listings if x.get("qualified")]
            row_idx = next((j for j, x in enumerate(qualified) if x.get("id") == listing.get("id")), i)

            _update_sheet(sheets_svc, row_idx, status, notes)
            _save_status(listing.get("id", ""), "applied" if success else "failed")

            if success:
                applied.append(listing)
            else:
                failed.append(listing)

            # Human-like pause between jobs
            await _human_delay(4000, 8000)

        await browser.close()

    return applied, failed, skipped


def main():
    listings = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
    to_retry = [x for x in listings if x.get("qualified") and x.get("status") == "failed"]
    log.info(f"Retrying {len(to_retry)} failed LinkedIn listings with VISIBLE browser...")

    try:
        sheets_svc = _get_sheets_service()
        log.info("Google Sheets connected.")
    except Exception as e:
        log.warning(f"Could not connect to Google Sheets: {e} — continuing without sheet sync")
        sheets_svc = None

    class _NoopSheets:
        def spreadsheets(self): return self
        def values(self): return self
        def update(self, **kwargs): return self
        def execute(self): pass

    if not sheets_svc:
        sheets_svc = _NoopSheets()

    applied, failed, skipped = asyncio.run(retry_failed(to_retry, sheets_svc))

    log.info("\n=== RETRY RESULTS ===")
    log.info(f"  Applied:  {len(applied)}")
    log.info(f"  Failed:   {len(failed)}")
    log.info(f"  Skipped:  {len(skipped)} (international)")

    if applied:
        log.info("\n  Successfully applied to:")
        for l in applied:
            log.info(f"    + {l['title']} @ {l['company']}")

    if failed:
        log.info("\n  Still failed:")
        for l in failed:
            log.info(f"    - {l['title']} @ {l['company']}")


if __name__ == "__main__":
    main()
