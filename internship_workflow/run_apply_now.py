"""
run_apply_now.py — Score internships_found.json, log into LinkedIn headlessly,
and apply to all qualifying listings (score >= 6).

Run with: python run_apply_now.py
"""

import asyncio
import io
import json
import logging
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows so checkmark/cross chars don't crash
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
PROFILE_FILE = BASE / "profile.json"

LINKEDIN_EMAIL = "jakegoncalves2002@gmail.com"
LINKEDIN_PASSWORD = "Browneyes2007!"

# ── Scoring ────────────────────────────────────────────────────────────────────

US_KEYWORDS = [
    "united states", "usa", "u.s.", "texas", "remote", "california",
    "new york", "washington", "virginia", "colorado", "florida",
    "illinois", "massachusetts", "georgia", "arizona", "ohio",
    "nationwide", "anywhere", "hybrid",
]

SKILL_KEYWORDS = [
    "python", "ai", "ml", "machine learning", "software", "engineering",
    "mechanical", "aerospace", "robotics", "computer science", "research",
    "electrical", "field", "autocad", "data", "systems", "automation",
    "manufacturing", "operations", "general",
]

NEGATIVE_KEYWORDS = [
    "malaysia", "india", "canada", "uk", "australia", "germany",
    "france", "singapore", "nigeria", "pakistan", "international",
    "abroad", "overseas",
]


def score_listing(listing: dict) -> int:
    title = listing.get("title", "").lower()
    company = listing.get("company", "").lower()
    location = listing.get("location", "").lower()

    # Hard reject international
    for neg in NEGATIVE_KEYWORDS:
        if neg in location:
            return 0

    score = 5  # base

    # Prefer US / remote
    for kw in US_KEYWORDS:
        if kw in location:
            score += 2
            break

    # Skill keyword match in title
    for kw in SKILL_KEYWORDS:
        if kw in title:
            score += 1
            break

    # Known good companies (boost)
    top_companies = [
        "spacex", "lockheed", "boeing", "raytheon", "anduril",
        "northrop", "l3harris", "general dynamics", "nasa", "tesla",
        "blue origin", "rocket lab", "textron", "honeywell",
    ]
    for co in top_companies:
        if co in company:
            score += 2
            break

    return min(score, 10)


# ── LinkedIn Login ─────────────────────────────────────────────────────────────

async def linkedin_login(context):
    log.info("Logging into LinkedIn...")
    page = await context.new_page()
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
    # Wait explicitly for the username field
    try:
        await page.wait_for_selector("#username", timeout=15000)
    except Exception:
        await page.screenshot(path=str(BASE / "debug_login.png"))
        log.warning(f"Login page did not load properly — screenshot saved. URL: {page.url}")
    await page.wait_for_timeout(1500)

    await page.fill("#username", LINKEDIN_EMAIL)
    await page.wait_for_timeout(500)
    await page.fill("#password", LINKEDIN_PASSWORD)
    await page.wait_for_timeout(500)
    await page.click("button[type='submit']")
    await page.wait_for_timeout(4000)

    url = page.url
    if "checkpoint" in url or "challenge" in url or "verification" in url:
        log.warning("Two-step verification required! Waiting up to 60s for you to approve...")
        # Wait for redirect away from checkpoint
        for _ in range(60):
            await page.wait_for_timeout(1000)
            if "checkpoint" not in page.url and "challenge" not in page.url:
                break
        log.info(f"Post-2FA URL: {page.url}")

    if "feed" in page.url or "mynetwork" in page.url or "jobs" in page.url:
        log.info("LinkedIn login successful.")
        return page
    else:
        log.warning(f"Login may have failed — current URL: {page.url}")
        return page


# ── Apply Loop ─────────────────────────────────────────────────────────────────

async def apply_all(listings: list[dict]):
    from playwright.async_api import async_playwright

    applied = []
    failed = []

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
        # Remove webdriver flag
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Log into LinkedIn once
        linkedin_page = await linkedin_login(context)

        for i, listing in enumerate(listings, 1):
            url = listing.get("url", "")
            title = listing["title"]
            company = listing["company"]
            log.info(f"[{i}/{len(listings)}] {title} @ {company}")


            try:
                source = listing.get("source", "").lower()
                ats = _detect_ats(url)

                if ats == "linkedin":
                    success = await _apply_linkedin(linkedin_page, listing)
                elif ats == "greenhouse":
                    success = await _apply_greenhouse(context, listing)
                elif ats == "lever":
                    success = await _apply_lever(context, listing)
                else:
                    success = await _apply_generic(context, listing)

                if success:
                    applied.append(listing)
                    log.info(f"  ✓ Applied")
                else:
                    failed.append(listing)
                    log.info(f"  ✗ Skipped (no submit found)")

            except Exception as e:
                failed.append(listing)
                log.error(f"  ✗ Error: {e}")

            time.sleep(3)

        await browser.close()

    return applied, failed


# ── ATS Detection ──────────────────────────────────────────────────────────────

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


# ── Per-ATS Apply Helpers ──────────────────────────────────────────────────────

PROFILE = json.loads(PROFILE_FILE.read_text())
P = PROFILE["personal"]
E = PROFILE["education"]
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
        f"Thank you,\n{P['full_name']}\n{P['email']} | {P['phone']}"
    )


async def _fill_common(page):
    fields = [
        ("input[name*='first'], input[id*='first']", P["first_name"]),
        ("input[name*='last'], input[id*='last']", P["last_name"]),
        ("input[name*='full'], input[id*='full']", P["full_name"]),
        ("input[type='email'], input[name*='email']", P["email"]),
        ("input[type='tel'], input[name*='phone']", P["phone"]),
        ("input[name*='city'], input[id*='city']", P["city"]),
        ("input[name*='state'], input[id*='state']", P["state"]),
        ("input[name*='zip'], input[name*='postal']", P["zip"]),
    ]
    for sel, val in fields:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                await el.fill(str(val))
        except Exception:
            pass


async def _upload_resume(page):
    try:
        fi = page.locator("input[type='file']").first
        if await fi.count() > 0 and RESUME_PATH:
            await fi.set_input_files(RESUME_PATH)
            await page.wait_for_timeout(1000)
    except Exception:
        pass


async def _apply_linkedin(page, listing):
    await page.goto(listing["url"], wait_until="domcontentloaded", timeout=30000)
    # Wait for LinkedIn React to render apply links (up to 8s)
    try:
        await page.wait_for_selector(
            "a:has-text('Easy Apply'), button:has-text('Easy Apply'), "
            "a:has-text('Apply'), button:has-text('Apply')",
            timeout=8000,
        )
    except Exception:
        pass
    await page.wait_for_timeout(1000)

    # LinkedIn renders buttons as <a> tags. Check Easy Apply first.
    easy = page.locator("a:has-text('Easy Apply'), button:has-text('Easy Apply')").first
    if await easy.count():
        # Get href if it's a link, otherwise click
        href = await easy.get_attribute("href")
        if href and href.startswith("http"):
            await page.goto(href, wait_until="domcontentloaded", timeout=30000)
        else:
            await easy.click()
        await page.wait_for_timeout(2000)

        # Wait for the Easy Apply modal to appear
        try:
            await page.wait_for_selector(
                ".jobs-easy-apply-content, .jobs-easy-apply-modal, [data-test-modal]",
                timeout=8000
            )
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        # Scope all interactions to the Easy Apply modal
        modal = page.locator(
            ".jobs-easy-apply-content, .jobs-easy-apply-modal, "
            "[data-test-modal], .artdeco-modal"
        ).first
        # Fall back to full page if no modal found
        ctx = modal if await modal.count() else page

        for _ in range(10):
            await _fill_common(ctx)
            await _upload_resume(ctx)

            # Submit button — scoped to modal footer area
            submit = ctx.locator(
                "button:has-text('Submit application'), "
                "button[aria-label='Submit application'], "
                "button[data-easy-apply-next-button]:has-text('Submit')"
            ).first
            # Next button — scoped to modal, exclude disabled and wrong-context buttons
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

    # No Easy Apply — look for external Apply link
    apply_link = page.locator("a:has-text('Apply'), button:has-text('Apply')").first
    if not await apply_link.count():
        return False

    href = await apply_link.get_attribute("href")
    if href and href.startswith("http") and "linkedin.com" not in href:
        # External ATS — navigate directly (skip new tab)
        ext_page = await page.context.new_page()
        try:
            await ext_page.goto(href, wait_until="domcontentloaded", timeout=20000)
            await ext_page.wait_for_timeout(2000)
            await _fill_common(ext_page)
            await _upload_resume(ext_page)
            try:
                await ext_page.fill(
                    "textarea[id*='cover'], textarea[name*='cover'], textarea[name='comments']",
                    _cover_letter(listing)
                )
            except Exception:
                pass
            submit = ext_page.locator(
                "button[type='submit'], input[type='submit'], "
                "button:has-text('Submit'), button:has-text('Apply')"
            ).first
            if await submit.count():
                await submit.click()
                await ext_page.wait_for_timeout(3000)
                await ext_page.close()
                return True
            await ext_page.close()
        except Exception:
            try:
                await ext_page.close()
            except Exception:
                pass
    else:
        # LinkedIn-hosted apply page or no usable href — click and handle in same page
        context = page.context
        try:
            async with context.expect_page(timeout=5000) as new_page_info:
                await apply_link.click()
            ext_page = await new_page_info.value
            await ext_page.wait_for_load_state("domcontentloaded", timeout=15000)
            await ext_page.wait_for_timeout(2000)
            await _fill_common(ext_page)
            await _upload_resume(ext_page)
            submit = ext_page.locator(
                "button[type='submit'], input[type='submit'], button:has-text('Submit')"
            ).first
            if await submit.count():
                await submit.click()
                await ext_page.wait_for_timeout(3000)
                await ext_page.close()
                return True
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


# ── Google Sheets Recording ────────────────────────────────────────────────────

def record_to_sheets(applied: list[dict]):
    try:
        import os, sys
        sys.path.insert(0, str(BASE.parent))
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token_file = BASE.parent / ".secrets" / "google_token.json"
        if not token_file.exists():
            log.warning("No Google token found — skipping Sheets recording.")
            return

        creds = Credentials.from_authorized_user_file(
            str(token_file),
            scopes=["https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive"]
        )

        service = build("sheets", "v4", credentials=creds)
        drive = build("drive", "v3", credentials=creds)

        # Find "Internships Applied" sheet
        results = drive.files().list(
            q="name='Internships Applied' and mimeType='application/vnd.google-apps.spreadsheet'",
            fields="files(id, name)"
        ).execute()
        files = results.get("files", [])
        if not files:
            log.warning("'Internships Applied' sheet not found — skipping recording.")
            return

        sheet_id = files[0]["id"]
        rows = []
        for l in applied:
            rows.append([l["title"], l["company"], l["location"], l["url"], "Applied", l.get("found_at", "")])

        service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range="Sheet1!A:F",
            valueInputOption="RAW",
            body={"values": rows}
        ).execute()
        log.info(f"Recorded {len(rows)} applied internships to Google Sheets.")
    except Exception as e:
        log.error(f"Sheets recording error: {e}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    listings = json.loads(LISTINGS_FILE.read_text())
    log.info(f"Loaded {len(listings)} listings from internships_found.json")

    # Score and filter
    qualifying = []
    for l in listings:
        s = score_listing(l)
        l["score"] = s
        if s >= 6:
            qualifying.append(l)

    qualifying.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"{len(qualifying)} qualifying listings (score >= 6), skipping {len(listings) - len(qualifying)}")

    for l in qualifying[:5]:
        log.info(f"  Top: {l['score']}/10 — {l['title']} @ {l['company']} ({l['location']})")

    # Apply
    applied, failed = asyncio.run(apply_all(qualifying))

    log.info(f"\n=== RESULTS ===")
    log.info(f"  Applied:  {len(applied)}")
    log.info(f"  Skipped:  {len(failed)}")

    if applied:
        log.info("\n  Applied to:")
        for l in applied:
            log.info(f"    • {l['title']} @ {l['company']}")

    # Record to Sheets
    if applied:
        record_to_sheets(applied)

    return applied


if __name__ == "__main__":
    main()
