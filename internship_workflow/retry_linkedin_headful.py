"""
retry_linkedin_headful.py — Retry all failed LinkedIn applications in headed (visible) browser.

KEY DIFFERENCE vs run_with_sheet_sync.py:
  - headless=False  → visible Chromium, bypasses LinkedIn bot detection
  - Only processes listings with status == 'failed'
  - Preserves correct sheet row indices for updates

Run: python retry_linkedin_headful.py
"""

import asyncio
import io
import json
import logging
import random
import sys
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

# Import helpers from the main runner
sys.path.insert(0, str(BASE))
from run_with_sheet_sync import (
    _get_sheets_service,
    update_sheet_row_status,
    save_listing_status,
    _apply_linkedin,
    LINKEDIN_EMAIL,
    LINKEDIN_PASSWORD,
)


async def linkedin_login_smart(context):
    """Login to LinkedIn, or skip if already logged in."""
    log.info("Navigating to LinkedIn...")
    page = await context.new_page()
    await page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(2000)

    # If we're on the feed, already logged in
    if "/feed" in page.url or "/in/" in page.url:
        log.info("Already logged in to LinkedIn.")
        return page

    # Otherwise go to login page
    await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=30000)
    username_visible = False
    try:
        await page.wait_for_selector("#username", timeout=10000)
        username_visible = True
    except Exception:
        log.warning("Login form not found — may already be logged in.")

    if username_visible:
        await page.wait_for_timeout(1000)
        await page.fill("#username", LINKEDIN_EMAIL)
        await page.wait_for_timeout(500)
        await page.fill("#password", LINKEDIN_PASSWORD)
        await page.wait_for_timeout(500)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(4000)

        if "checkpoint" in page.url or "challenge" in page.url:
            log.warning("2FA/CAPTCHA required — waiting up to 60s for manual completion...")
            for _ in range(60):
                await page.wait_for_timeout(1000)
                if "checkpoint" not in page.url and "challenge" not in page.url:
                    break

    log.info(f"LinkedIn ready. URL: {page.url}")
    return page


async def retry_failed(listings_with_indices: list[tuple[int, dict]], sheets_svc):
    from playwright.async_api import async_playwright

    results = {"applied": [], "failed": []}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=False,  # VISIBLE browser — bypasses bot detection
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1366,768",
                "--start-maximized",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1366, "height": 768},
            locale="en-US",
            timezone_id="America/Chicago",
        )
        await context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        log.info("Logging into LinkedIn (headed mode)...")
        linkedin_page = await linkedin_login_smart(context)
        log.info("LinkedIn login complete. Starting retry run...")

        total = len(listings_with_indices)
        for attempt, (sheet_row_idx, listing) in enumerate(listings_with_indices):
            log.info(
                f"[{attempt+1}/{total}] {listing['title']} @ {listing['company']}"
            )

            success = False
            notes = ""
            try:
                success = await _apply_linkedin(linkedin_page, listing)
            except Exception as e:
                notes = f"Error: {str(e)[:100]}"
                log.error(f"  Error: {e}")

            status = "Applied" if success else "Failed"
            log.info(f"  -> {status}")

            # Update Google Sheet at the correct row
            try:
                update_sheet_row_status(sheets_svc, sheet_row_idx, status, notes)
            except Exception as e:
                log.warning(f"  Sheet update failed: {e}")

            # Update JSON
            save_listing_status(listing.get("id", ""), "applied" if success else "failed")

            if success:
                results["applied"].append(listing)
            else:
                results["failed"].append(listing)

            # Human-like delay between applications
            delay = random.uniform(4, 8)
            await asyncio.sleep(delay)

        log.info("Closing browser...")
        await browser.close()

    return results


def main():
    # Load all listings and find qualified failed ones with their sheet row indices
    all_listings = json.loads(LISTINGS_FILE.read_text(encoding="utf-8"))
    qualified = [x for x in all_listings if x.get("qualified")]

    # Build (sheet_row_index, listing) pairs for failed ones
    # sheet_row_index is the 0-based index in the qualified list (row = index + 2 in sheet)
    failed_with_indices = [
        (i, listing)
        for i, listing in enumerate(qualified)
        if listing.get("status") in ("failed", "Failed")
    ]

    log.info(f"Found {len(failed_with_indices)} failed LinkedIn applications to retry")

    sheets_svc = _get_sheets_service()
    log.info("Google Sheets connected.")

    results = asyncio.run(retry_failed(failed_with_indices, sheets_svc))

    log.info("\n=== RETRY RESULTS ===")
    log.info(f"  Applied:  {len(results['applied'])}")
    log.info(f"  Failed:   {len(results['failed'])}")

    if results["applied"]:
        log.info("\n  Successfully applied to:")
        for l in results["applied"]:
            log.info(f"    + {l['title']} @ {l['company']}")

    if results["failed"]:
        log.info(f"\n  Still failed ({len(results['failed'])}):")
        for l in results["failed"][:10]:
            log.info(f"    x {l['title']} @ {l['company']}")
        if len(results["failed"]) > 10:
            log.info(f"    ... and {len(results['failed']) - 10} more")


if __name__ == "__main__":
    main()
