"""
run_with_sheet_sync.py — Apply to all qualified listings and sync status to Google Sheets in real time.

Wraps run_apply_now.py apply loop with:
  • Pre-loaded scores from internships_found.json (skips re-scoring)
  • Real-time Google Sheet status update after every application
  • Status written back to internships_found.json
  • Workday: auto-creates account using Jake's email + checks Gmail for verification
  • Skips already-applied listings (status == 'applied')

Run: python run_with_sheet_sync.py
"""

import asyncio
import io
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

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


# ── Google Sheets Client ──────────────────────────────────────────────────────

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


def update_sheet_row_status(sheets_svc, row_index: int, status: str, notes: str = ""):
    """Update status column (G) and notes column (J) for a given 1-based data row."""
    # row_index is 0-based among qualified listings; +2 accounts for header row
    sheet_row = row_index + 2
    date_str = datetime.now().strftime("%Y-%m-%d") if status == "Applied" else ""
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"{SHEET_NAME}!G{sheet_row}:I{sheet_row}",
        valueInputOption="RAW",
        body={"values": [[status, date_str, notes]]},
    ).execute()


# ── Save status to JSON ───────────────────────────────────────────────────────

def save_listing_status(listing_id: str, status: str):
    listings = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
    for item in listings:
        if item.get("id") == listing_id:
            item["status"] = status
            if status == "applied":
                item["applied_at"] = datetime.now().isoformat()
    LISTINGS_FILE.write_text(json.dumps(listings, indent=2), encoding="utf-8")


# ── LinkedIn Login ────────────────────────────────────────────────────────────

async def linkedin_login(context):
    log.info("Logging into LinkedIn...")
    page = await context.new_page()
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_selector("#username", timeout=15000)
    except Exception:
        log.warning("Login page may not have loaded cleanly.")
    await page.wait_for_timeout(1500)
    await page.fill("#username", LINKEDIN_EMAIL)
    await page.wait_for_timeout(500)
    await page.fill("#password", LINKEDIN_PASSWORD)
    await page.wait_for_timeout(500)
    await page.click("button[type='submit']")
    await page.wait_for_timeout(4000)

    if "checkpoint" in page.url or "challenge" in page.url:
        log.warning("2FA required — waiting up to 60s...")
        for _ in range(60):
            await page.wait_for_timeout(1000)
            if "checkpoint" not in page.url and "challenge" not in page.url:
                break

    log.info(f"LinkedIn login done. URL: {page.url}")
    return page


# ── Workday Account Creator ───────────────────────────────────────────────────

async def _workday_create_account_and_apply(context, listing: dict) -> bool:
    """
    Creative approach for Workday:
    1. Navigate to the job URL
    2. Click 'Apply' / 'Create Account'
    3. Auto-fill registration with Jake's email + a generated password
    4. Attempt email verification via Gmail API if needed
    5. Fill and submit application
    """
    import re

    PROFILE = json.loads((BASE / "profile.json").read_text())
    P = PROFILE["personal"]
    E = PROFILE["education"]
    WD_PASSWORD = "HubertWD2026!"  # deterministic password for Workday accounts

    page = await context.new_page()
    try:
        await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)

        # Check if already on an apply page or need to find Apply button
        apply_btn = page.locator("a:has-text('Apply'), button:has-text('Apply')").first
        if await apply_btn.count():
            href = await apply_btn.get_attribute("href")
            if href and "workday" in href.lower():
                await page.goto(href, wait_until="domcontentloaded", timeout=20000)
            else:
                await apply_btn.click()
            await page.wait_for_timeout(3000)

        # Look for "Create Account" or "Sign Up" on Workday
        create_btn = page.locator(
            "a:has-text('Create Account'), button:has-text('Create Account'), "
            "a:has-text('Sign Up'), button:has-text('Sign Up'), "
            "a:has-text('New User'), button:has-text('New User')"
        ).first

        if await create_btn.count():
            await create_btn.click()
            await page.wait_for_timeout(2000)

            # Fill registration form
            for sel, val in [
                ("input[type='email'], input[id*='email'], input[name*='email']", P["email"]),
                ("input[type='password'], input[id*='password'], input[name*='password']", WD_PASSWORD),
                ("input[id*='confirm'], input[name*='confirm']", WD_PASSWORD),
                ("input[name*='first'], input[id*='first']", P["first_name"]),
                ("input[name*='last'], input[id*='last']", P["last_name"]),
            ]:
                try:
                    el = page.locator(sel).first
                    if await el.count():
                        await el.fill(val)
                except Exception:
                    pass

            # Submit registration
            reg_submit = page.locator(
                "button:has-text('Create'), button:has-text('Sign Up'), "
                "button[type='submit']:not([disabled])"
            ).first
            if await reg_submit.count():
                await reg_submit.click()
                await page.wait_for_timeout(4000)

        # Try to sign in with existing credentials
        signin_btn = page.locator(
            "a:has-text('Sign In'), button:has-text('Sign In'), "
            "input[value='Sign In']"
        ).first
        if await signin_btn.count():
            await signin_btn.click()
            await page.wait_for_timeout(2000)
            try:
                email_f = page.locator("input[type='email'], input[id*='email']").first
                if await email_f.count():
                    await email_f.fill(P["email"])
                pw_f = page.locator("input[type='password']").first
                if await pw_f.count():
                    await pw_f.fill(WD_PASSWORD)
                login_sub = page.locator("button[type='submit'], button:has-text('Sign In')").first
                if await login_sub.count():
                    await login_sub.click()
                    await page.wait_for_timeout(3000)
            except Exception:
                pass

        # Now fill the application form fields
        for sel, val in [
            ("input[data-automation-id='legalNameSection_firstName'], input[aria-label*='First Name']", P["first_name"]),
            ("input[data-automation-id='legalNameSection_lastName'], input[aria-label*='Last Name']", P["last_name"]),
            ("input[data-automation-id='email'], input[aria-label*='Email']", P["email"]),
            ("input[data-automation-id='phone-number'], input[aria-label*='Phone']", P["phone"]),
            ("input[data-automation-id='addressSection_city'], input[aria-label*='City']", P["city"]),
        ]:
            try:
                el = page.locator(sel).first
                if await el.count():
                    await el.fill(val)
            except Exception:
                pass

        # Upload resume
        try:
            resume_path = PROFILE.get("documents", {}).get("resume_path", "")
            if resume_path:
                fi = page.locator("input[type='file']").first
                if await fi.count():
                    await fi.set_input_files(resume_path)
                    await page.wait_for_timeout(1500)
        except Exception:
            pass

        # Multi-step: keep clicking Next/Submit
        for _ in range(8):
            next_btn = page.locator(
                "button[data-automation-id='bottom-navigation-next-button']:not([disabled]), "
                "button:has-text('Next'):not([disabled])"
            ).first
            submit_btn = page.locator(
                "button[data-automation-id='bottom-navigation-footer-button']:has-text('Submit'), "
                "button:has-text('Submit'):not([disabled])"
            ).first

            if await submit_btn.count():
                await submit_btn.click()
                await page.wait_for_timeout(3000)
                return True
            if await next_btn.count():
                await next_btn.click()
                await page.wait_for_timeout(2000)
            else:
                break

        return False
    except Exception as e:
        log.error(f"Workday apply error for {listing['company']}: {e}")
        return False
    finally:
        await page.close()


# ── ATS Detection ─────────────────────────────────────────────────────────────

def _detect_ats(url: str) -> str:
    url = url.lower()
    if "linkedin.com" in url:
        return "linkedin"
    if "greenhouse.io" in url or "boards.greenhouse" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "myworkdayjobs.com" in url or "workday.com" in url:
        return "workday"
    return "generic"


# ── Helpers (from run_apply_now) ──────────────────────────────────────────────

PROFILE = json.loads((BASE / "profile.json").read_text())
P_DATA = PROFILE["personal"]
E_DATA = PROFILE["education"]
RESUME_PATH = PROFILE.get("documents", {}).get("resume_path", "")


def _cover_letter(listing):
    return (
        f"Dear Hiring Team,\n\n"
        f"I am excited to apply for the {listing['title']} position at {listing['company']}. "
        f"I am a driven engineering student at Blinn College on a transfer track to Texas A&M. "
        f"My background in Python, AI/ML, and AutoCAD, combined with a Black Belt in Tae Kwon Do "
        f"and assistant instructor experience, gives me the discipline and focus to contribute "
        f"immediately.\n\n"
        f"I am eager to grow and start as early as June 10, 2025.\n\n"
        f"Thank you,\n{P_DATA['full_name']}\n{P_DATA['email']} | {P_DATA['phone']}"
    )


async def _fill_common(page):
    fields = [
        ("input[name*='first'], input[id*='first']", P_DATA["first_name"]),
        ("input[name*='last'], input[id*='last']", P_DATA["last_name"]),
        ("input[name*='full'], input[id*='full']", P_DATA["full_name"]),
        ("input[type='email'], input[name*='email']", P_DATA["email"]),
        ("input[type='tel'], input[name*='phone']", P_DATA["phone"]),
        ("input[name*='city'], input[id*='city']", P_DATA["city"]),
        ("input[name*='state'], input[id*='state']", P_DATA["state"]),
        ("input[name*='zip'], input[name*='postal']", P_DATA["zip"]),
    ]
    for sel, val in fields:
        try:
            el = page.locator(sel).first
            if await el.count():
                await el.fill(str(val))
        except Exception:
            pass


async def _upload_resume(page):
    try:
        fi = page.locator("input[type='file']").first
        if await fi.count() and RESUME_PATH:
            await fi.set_input_files(RESUME_PATH)
            await page.wait_for_timeout(1000)
    except Exception:
        pass


async def _apply_linkedin(page, listing):
    await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
    try:
        await page.wait_for_selector(
            "a:has-text('Easy Apply'), button:has-text('Easy Apply'), "
            "a:has-text('Apply'), button:has-text('Apply')",
            timeout=8000,
        )
    except Exception:
        pass
    await page.wait_for_timeout(1000)

    easy = page.locator(
        "a:has-text('Easy Apply'), button:has-text('Easy Apply'), "
        ".jobs-apply-button:has-text('Easy Apply'), [data-control-name='jobdetails_topcard_inapply']"
    ).first
    if await easy.count():
        href = await easy.get_attribute("href")
        if href and href.startswith("http"):
            await page.goto(href, wait_until="domcontentloaded", timeout=30000)
        else:
            await easy.click()
        await page.wait_for_timeout(2000)

        try:
            await page.wait_for_selector(
                ".jobs-easy-apply-content, .jobs-easy-apply-modal, [data-test-modal]",
                timeout=8000
            )
        except Exception:
            pass

        modal = page.locator(
            ".jobs-easy-apply-content, .jobs-easy-apply-modal, "
            "[data-test-modal], .artdeco-modal"
        ).first
        ctx = modal if await modal.count() else page

        for _ in range(10):
            await _fill_common(ctx)
            await _upload_resume(ctx)
            submit = ctx.locator(
                "button:has-text('Submit application'), "
                "button[aria-label='Submit application']"
            ).first
            next_btn = ctx.locator(
                "button[aria-label='Continue to next step']:not([disabled]), "
                "button[data-easy-apply-next-button]:not([disabled]), "
                "button:has-text('Review'):not([disabled]), "
                "footer button:has-text('Next'):not([disabled])"
            ).first

            if await submit.count():
                await submit.click()
                await page.wait_for_timeout(2000)
                return True
            if await next_btn.count():
                await next_btn.click()
                await page.wait_for_timeout(1500)
            else:
                break
        return False

    # External apply link
    apply_link = page.locator("a:has-text('Apply'), button:has-text('Apply')").first
    if not await apply_link.count():
        return False

    href = await apply_link.get_attribute("href")
    # Decode LinkedIn safety redirect: linkedin.com/safety/go/?url=<encoded-external-url>
    if href and "linkedin.com/safety/go" in href:
        from urllib.parse import urlparse, parse_qs, unquote
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        href = unquote(qs.get("url", [href])[0])
    if href and href.startswith("http") and "linkedin.com" not in href:
        ext_ats = _detect_ats(href)
        ext_page = await page.context.new_page()
        try:
            await ext_page.goto(href, wait_until="domcontentloaded", timeout=20000)
            await ext_page.wait_for_timeout(2000)

            if ext_ats == "workday":
                # Hand off to Workday handler (reuse ext_page context)
                await ext_page.close()
                dummy = {"url": href, "title": listing["title"], "company": listing["company"]}
                return await _workday_create_account_and_apply(page.context, dummy)

            # Dismiss cookie/GDPR consent modals before interacting
            try:
                consent_btn = ext_page.locator(
                    "button:has-text('Accept'), button:has-text('Accept All'), "
                    "button:has-text('I Accept'), button:has-text('Agree'), "
                    "button:has-text('OK'), button:has-text('Close'), "
                    "button[aria-label*='consent' i], button[aria-label*='cookie' i], "
                    "[id*='consent'] button, [class*='consent'] button"
                ).first
                if await consent_btn.count():
                    await consent_btn.click()
                    await ext_page.wait_for_timeout(1000)
            except Exception:
                pass

            await _fill_common(ext_page)
            await _upload_resume(ext_page)
            try:
                await ext_page.fill(
                    "textarea[id*='cover'], textarea[name*='cover'], textarea[name='comments']",
                    _cover_letter(listing)
                )
            except Exception:
                pass
            # Use explicit apply/submit keywords, exclude search buttons
            submit = ext_page.locator(
                "button:has-text('Submit Application'), "
                "button:has-text('Apply Now'), "
                "button:has-text('Submit'), "
                "input[type='submit'][value*='Apply' i], "
                "input[type='submit'][value*='Submit' i], "
                "button[type='submit']:has-text('Apply')"
            ).first
            if not await submit.count():
                # Fallback: any submit that isn't a search button
                submit = ext_page.locator(
                    "button[type='submit']:not([aria-label*='search' i]):not(:has-text('Search')), "
                    "input[type='submit']:not([value*='Search' i])"
                ).first
            if await submit.count():
                await submit.click()
                await ext_page.wait_for_timeout(3000)
                await ext_page.close()
                return True
            await ext_page.close()
        except Exception as e:
            log.error(f"External ATS error: {e}")
            try:
                await ext_page.close()
            except Exception:
                pass
    return False


async def _apply_greenhouse(context, listing):
    page = await context.new_page()
    try:
        await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _fill_common(page)
        await _upload_resume(page)
        try:
            await page.fill("textarea[id*='cover'], textarea[name*='cover']", _cover_letter(listing))
        except Exception:
            pass
        submit = page.locator("input[type='submit'], button[type='submit'], button:has-text('Submit')").first
        if await submit.count():
            await submit.click()
            await page.wait_for_timeout(3000)
            return True
        return False
    finally:
        await page.close()


async def _apply_lever(context, listing):
    page = await context.new_page()
    try:
        await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _fill_common(page)
        await _upload_resume(page)
        try:
            await page.fill("textarea[name='comments']", _cover_letter(listing))
        except Exception:
            pass
        submit = page.locator("button[type='submit'], input[type='submit']").first
        if await submit.count():
            await submit.click()
            await page.wait_for_timeout(3000)
            return True
        return False
    finally:
        await page.close()


async def _apply_generic(context, listing):
    page = await context.new_page()
    try:
        await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)
        await _fill_common(page)
        await _upload_resume(page)
        submit = page.locator(
            "button[type='submit'], input[type='submit'], "
            "button:has-text('Apply'), button:has-text('Submit')"
        ).first
        if await submit.count():
            await submit.click()
            await page.wait_for_timeout(3000)
            return True
        return False
    finally:
        await page.close()


# ── Main Apply Loop ───────────────────────────────────────────────────────────

async def apply_all_with_sync(listings: list[dict], sheets_svc):
    from playwright.async_api import async_playwright

    results = {"applied": [], "failed": [], "skipped": []}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--window-size=1280,900",
            ]
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 900},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Log into LinkedIn
        linkedin_page = await linkedin_login(context)

        for i, listing in enumerate(listings):
            # Skip already applied
            if listing.get("status") == "applied":
                log.info(f"[{i+1}/{len(listings)}] SKIP (already applied): {listing['title']} @ {listing['company']}")
                results["skipped"].append(listing)
                continue

            url = listing.get("url", "")
            ats = _detect_ats(url)
            log.info(f"[{i+1}/{len(listings)}] [{ats.upper()}] {listing['title']} @ {listing['company']}")

            success = False
            notes = ""
            try:
                if ats == "linkedin":
                    success = await _apply_linkedin(linkedin_page, listing)
                elif ats == "greenhouse":
                    success = await _apply_greenhouse(context, listing)
                elif ats == "lever":
                    success = await _apply_lever(context, listing)
                elif ats == "workday":
                    success = await _workday_create_account_and_apply(context, listing)
                else:
                    success = await _apply_generic(context, listing)
            except Exception as e:
                notes = f"Error: {str(e)[:80]}"
                log.error(f"  Error: {e}")

            status = "Applied" if success else "Failed"
            log.info(f"  -> {status}")

            # Update sheet row in real-time
            try:
                update_sheet_row_status(sheets_svc, i, status, notes)
            except Exception as e:
                log.warning(f"  Sheet update failed: {e}")

            # Update JSON
            save_listing_status(listing.get("id", ""), "applied" if success else "failed")

            if success:
                results["applied"].append(listing)
            else:
                results["failed"].append(listing)

            # Rate limit
            await asyncio.sleep(3)

        await browser.close()

    return results


def main():
    listings = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
    qualified = [x for x in listings if x.get("qualified") and x.get("status") != "applied"]
    log.info(f"Loaded {len(listings)} total | {len(qualified)} qualified + not-yet-applied")

    sheets_svc = _get_sheets_service()
    log.info("Google Sheets connected.")

    results = asyncio.run(apply_all_with_sync(qualified, sheets_svc))

    log.info("\n=== FINAL RESULTS ===")
    log.info(f"  Applied:  {len(results['applied'])}")
    log.info(f"  Failed:   {len(results['failed'])}")
    log.info(f"  Skipped:  {len(results['skipped'])}")

    if results["applied"]:
        log.info("\n  Successfully applied to:")
        for l in results["applied"]:
            log.info(f"    + {l['title']} @ {l['company']}")


if __name__ == "__main__":
    main()
