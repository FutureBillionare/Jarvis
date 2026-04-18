"""
Application Filler — uses Playwright to auto-fill internship applications.

Supports:
  • LinkedIn Easy Apply
  • Greenhouse ATS  (greenhouse.io)
  • Lever ATS       (lever.co)
  • Workday         (myworkdayjobs.com)
  • Generic form filler (best-effort)
"""

import json
import logging
import time
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_BASE = Path(__file__).parent
_PROFILE = json.loads((_BASE / "profile.json").read_text())
_RESUME_PATH = _PROFILE.get("documents", {}).get(
    "resume_path",
    str(Path.home() / "Downloads" / "Resume V1 - Google Docs.pdf"),
)

P = _PROFILE["personal"]
E = _PROFILE["education"]


# ── ATS Detection ─────────────────────────────────────────────────────────────

def _detect_ats(url: str) -> str:
    url = url.lower()
    if "linkedin.com/jobs" in url or "linkedin.com/comm" in url:
        return "linkedin"
    if "greenhouse.io" in url or "boards.greenhouse" in url:
        return "greenhouse"
    if "lever.co" in url:
        return "lever"
    if "myworkdayjobs.com" in url or "workday.com" in url:
        return "workday"
    if "taleo" in url:
        return "taleo"
    if "smartrecruiters" in url:
        return "smartrecruiters"
    return "generic"


# ── Playwright Helpers ────────────────────────────────────────────────────────

async def _fill_if_exists(page, selector: str, value: str):
    try:
        el = page.locator(selector).first
        if await el.count() > 0:
            await el.fill(str(value))
    except Exception:
        pass


async def _click_if_exists(page, selector: str):
    try:
        el = page.locator(selector).first
        if await el.count() > 0:
            await el.click()
            await page.wait_for_timeout(800)
    except Exception:
        pass


async def _fill_common_fields(page):
    """Fill fields that appear across most ATS platforms."""
    mappings = [
        # First name
        ("input[name*='first'], input[id*='first'], input[placeholder*='First']", P["first_name"]),
        # Last name
        ("input[name*='last'], input[id*='last'], input[placeholder*='Last']", P["last_name"]),
        # Full name
        ("input[name*='full_name'], input[id*='full'], input[placeholder*='Full Name']", P["full_name"]),
        # Email
        ("input[type='email'], input[name*='email'], input[id*='email']", P["email"]),
        # Phone
        ("input[type='tel'], input[name*='phone'], input[id*='phone']", P["phone"]),
        # Address
        ("input[name*='address'], input[id*='address'], input[placeholder*='Address']", P["address"]),
        # City
        ("input[name*='city'], input[id*='city'], input[placeholder*='City']", P["city"]),
        # State
        ("input[name*='state'], input[id*='state']", P["state"]),
        # Zip
        ("input[name*='zip'], input[name*='postal'], input[id*='zip']", P["zip"]),
        # School
        ("input[name*='school'], input[name*='university'], input[id*='school']", E["school"]),
        # Degree
        ("input[name*='degree'], input[id*='degree']", E["degree"]),
        # Major
        ("input[name*='major'], input[id*='major']", E["major"]),
        # Graduation year
        ("input[name*='graduation'], input[id*='graduation']", E["graduation_year"]),
        # LinkedIn URL
        ("input[name*='linkedin'], input[id*='linkedin']", P.get("linkedin", "")),
        # Work authorization
        ("input[name*='authorized'], input[id*='authorized']", "Yes"),
        # Relocate
        ("input[name*='relocat'], input[id*='relocat']", "Yes"),
        # Start date
        ("input[name*='start'], input[id*='start_date'], input[placeholder*='start']",
         _PROFILE["personal"].get("earliest_start_date", "June 10, 2025")),
    ]
    for selector, value in mappings:
        if value:
            await _fill_if_exists(page, selector, value)


# ── LinkedIn Easy Apply ───────────────────────────────────────────────────────

async def _apply_linkedin(page, listing: dict, status_cb: Callable | None) -> bool:
    def emit(msg):
        log.info(msg)
        if status_cb:
            status_cb("apply", msg, 0)

    emit(f"LinkedIn Easy Apply: {listing['title']} @ {listing['company']}")

    try:
        await page.goto(listing["url"], wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Click "Easy Apply" button
        easy_apply = page.locator("button.jobs-apply-button, button:has-text('Easy Apply')").first
        if not await easy_apply.count():
            emit("No Easy Apply button found — skipping")
            return False

        await easy_apply.click()
        await page.wait_for_timeout(2000)

        # Multi-step form loop (up to 10 steps)
        for step in range(10):
            await _fill_common_fields(page)

            # Upload resume if file input present
            try:
                file_input = page.locator("input[type='file']").first
                if await file_input.count() > 0:
                    await file_input.set_input_files(_RESUME_PATH)
                    await page.wait_for_timeout(1000)
            except Exception:
                pass

            # Check for "Next" or "Submit" button
            next_btn = page.locator("button:has-text('Next'), button[aria-label*='Continue']").first
            submit_btn = page.locator("button:has-text('Submit application'), button[aria-label*='Submit']").first

            if await submit_btn.count() > 0:
                await submit_btn.click()
                await page.wait_for_timeout(2000)
                emit(f"Submitted LinkedIn Easy Apply for {listing['company']}")
                return True

            if await next_btn.count() > 0:
                await next_btn.click()
                await page.wait_for_timeout(1500)
                continue

            break

        return False

    except Exception as e:
        emit(f"LinkedIn apply error: {e}")
        return False


# ── Greenhouse ATS ────────────────────────────────────────────────────────────

async def _apply_greenhouse(page, listing: dict, status_cb: Callable | None) -> bool:
    def emit(msg):
        log.info(msg)
        if status_cb:
            status_cb("apply", msg, 0)

    emit(f"Greenhouse apply: {listing['title']} @ {listing['company']}")

    try:
        await page.goto(listing["url"], wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        # Greenhouse standard fields
        await _fill_if_exists(page, "#first_name", P["first_name"])
        await _fill_if_exists(page, "#last_name", P["last_name"])
        await _fill_if_exists(page, "#email", P["email"])
        await _fill_if_exists(page, "#phone", P["phone"])

        # Resume upload
        try:
            resume_input = page.locator("input[type='file'][id*='resume']").first
            if await resume_input.count() > 0:
                await resume_input.set_input_files(_RESUME_PATH)
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        # Cover letter (brief auto-generated)
        await _fill_if_exists(
            page,
            "textarea[id*='cover'], textarea[name*='cover']",
            _generate_cover_letter(listing),
        )

        await _fill_common_fields(page)
        await _fill_salary_fields(page, listing)

        # Submit
        submit = page.locator("input[type='submit'], button[type='submit'], button:has-text('Submit')").first
        if await submit.count() > 0:
            await submit.click()
            await page.wait_for_timeout(3000)
            emit(f"Submitted Greenhouse for {listing['company']}")
            return True

        return False

    except Exception as e:
        emit(f"Greenhouse apply error: {e}")
        return False


# ── Lever ATS ─────────────────────────────────────────────────────────────────

async def _apply_lever(page, listing: dict, status_cb: Callable | None) -> bool:
    def emit(msg):
        log.info(msg)
        if status_cb:
            status_cb("apply", msg, 0)

    emit(f"Lever apply: {listing['title']} @ {listing['company']}")

    try:
        await page.goto(listing["url"], wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)

        await _fill_if_exists(page, "input[name='name']", P["full_name"])
        await _fill_if_exists(page, "input[name='email']", P["email"])
        await _fill_if_exists(page, "input[name='phone']", P["phone"])
        await _fill_if_exists(page, "input[name='org']", E["school"])
        await _fill_if_exists(page, "input[name='urls[LinkedIn]']", P.get("linkedin", ""))

        # Resume upload
        try:
            file_input = page.locator("input[type='file']").first
            if await file_input.count() > 0:
                await file_input.set_input_files(_RESUME_PATH)
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        await _fill_if_exists(
            page,
            "textarea[name='comments']",
            _generate_cover_letter(listing),
        )
        await _fill_salary_fields(page, listing)

        submit = page.locator("button[type='submit'], input[type='submit']").first
        if await submit.count() > 0:
            await submit.click()
            await page.wait_for_timeout(3000)
            emit(f"Submitted Lever for {listing['company']}")
            return True

        return False

    except Exception as e:
        emit(f"Lever apply error: {e}")
        return False


# ── Generic Form Filler ───────────────────────────────────────────────────────

async def _fill_salary_fields(page, listing: dict):
    """Fill salary fields with industry-average-plus-10% estimate."""
    salary_text = _estimate_salary(listing)
    # Extract just the numeric dollar amount for numeric fields
    import re
    match = re.search(r"\$(\d+)", salary_text)
    numeric_val = match.group(1) if match else "20"
    selectors = [
        "input[name*='salary'], input[id*='salary'], input[placeholder*='salary']",
        "input[name*='compensation'], input[id*='compensation']",
        "input[name*='pay'], input[id*='pay_rate']",
        "textarea[name*='salary'], textarea[id*='salary']",
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() > 0:
                tag = await el.evaluate("el => el.tagName.toLowerCase()")
                if tag == "textarea":
                    await el.fill(salary_text)
                else:
                    await el.fill(numeric_val)
        except Exception:
            pass


async def _apply_generic(page, listing: dict, status_cb: Callable | None) -> bool:
    def emit(msg):
        log.info(msg)
        if status_cb:
            status_cb("apply", msg, 0)

    emit(f"Generic form apply: {listing['title']} @ {listing['company']}")

    try:
        await page.goto(listing["url"], wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(2000)
        await _fill_common_fields(page)
        await _fill_salary_fields(page, listing)

        # Try resume upload
        try:
            file_input = page.locator("input[type='file']").first
            if await file_input.count() > 0:
                await file_input.set_input_files(_RESUME_PATH)
                await page.wait_for_timeout(1000)
        except Exception:
            pass

        submit = page.locator("button[type='submit'], input[type='submit'], button:has-text('Apply'), button:has-text('Submit')").first
        if await submit.count() > 0:
            await submit.click()
            await page.wait_for_timeout(3000)
            emit(f"Submitted generic form for {listing['company']}")
            return True

        emit(f"Could not find submit button for {listing['company']}")
        return False

    except Exception as e:
        emit(f"Generic apply error: {e}")
        return False


# ── Cover Letter Generator ────────────────────────────────────────────────────

def _estimate_salary(listing: dict) -> str:
    """Return a salary ask 10% above estimated industry average for the role."""
    title = listing.get("title", "").lower()
    # Rough industry averages for intern hourly rates (annualized for salaried fields)
    if any(k in title for k in ["software", "ml", "ai", "data", "computer"]):
        avg = 25  # $/hr
    elif any(k in title for k in ["mechanical", "aerospace", "civil", "chemical"]):
        avg = 20
    else:
        avg = 18
    ask = round(avg * 1.10, 2)
    return (
        f"${ask:.0f}/hr — based on industry average of ~${avg}/hr for this role type. "
        f"I understand the value of the skills and discipline I bring to the table and believe "
        f"this reflects fair compensation."
    )


def _generate_cover_letter(listing: dict) -> str:
    aa = _PROFILE.get("application_answers", {})
    return (
        f"Dear Hiring Team,\n\n"
        f"I am excited to apply for the {listing['title']} position at {listing['company']}. "
        f"I am a driven and hard-working individual currently studying at Blinn College on an engineering "
        f"transfer track toward Texas A&M University. My coursework, combined with hands-on projects in "
        f"Python, AI, and machine learning, has given me a strong technical foundation I am eager to apply "
        f"in a real-world setting.\n\n"
        f"Beyond academics, I hold a Black Belt in Tae Kwon Do and have served as an assistant instructor "
        f"for youth programs — experiences that have instilled in me the discipline, focus, and leadership "
        f"I bring to every endeavor. I graduated from Southlake Carroll Senior High School with honors "
        f"(weighted GPA 4.2) and hold an AutoCAD certification.\n\n"
        f"{aa.get('why_this_role', 'I am looking for hard, honest work and a chance to grow.')}\n\n"
        f"I would welcome the opportunity to contribute to {listing['company']} "
        f"starting as early as June 10, 2025.\n\n"
        f"Thank you for your consideration,\n{P['full_name']}\n{P['email']} | {P['phone']}"
    )


# ── Main Entry Point ──────────────────────────────────────────────────────────

async def apply_to_internships(
    listings: list[dict],
    status_cb: Callable | None = None,
) -> list[dict]:
    """
    Attempt to apply to each listing via Playwright.
    Returns list of successfully applied listings.
    """
    from playwright.async_api import async_playwright

    def emit(msg):
        log.info(msg)
        if status_cb:
            status_cb("apply", msg, 0)

    applied = []
    emit(f"Starting applications for {len(listings)} internships...")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()

        for listing in listings:
            emit(f"Applying: {listing['title']} @ {listing['company']}")
            ats = _detect_ats(listing.get("url", ""))
            success = False

            try:
                if ats == "linkedin":
                    success = await _apply_linkedin(page, listing, status_cb)
                elif ats == "greenhouse":
                    success = await _apply_greenhouse(page, listing, status_cb)
                elif ats == "lever":
                    success = await _apply_lever(page, listing, status_cb)
                else:
                    success = await _apply_generic(page, listing, status_cb)
            except Exception as e:
                emit(f"Error applying to {listing['company']}: {e}")
                success = False

            if success:
                applied.append(listing)
                emit(f"✓ Applied: {listing['title']} @ {listing['company']}")
            else:
                emit(f"✗ Skipped: {listing['title']} @ {listing['company']}")

            # Rate limit between applications
            time.sleep(3)

        await browser.close()

    emit(f"Applications complete. Submitted {len(applied)}/{len(listings)}.")
    return applied
