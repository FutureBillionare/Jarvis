"""Debug: navigate to first listing and dump the apply button HTML."""
import asyncio
import json
from pathlib import Path

BASE = Path(__file__).parent
LISTINGS = json.loads((BASE / "internships_found.json").read_text())

EMAIL = "jakegoncalves2002@gmail.com"
PASSWORD = "Browneyes2007!"

async def main():
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ))
        page = await context.new_page()

        # Login
        await page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        await page.fill("#username", EMAIL)
        await page.fill("#password", PASSWORD)
        await page.click("button[type='submit']")
        await page.wait_for_timeout(4000)
        print(f"After login: {page.url}")

        # Navigate to first listing
        url = LISTINGS[0]["url"]
        print(f"\nNavigating to: {url}")
        await page.goto(url, wait_until="domcontentloaded")
        await page.wait_for_timeout(5000)

        # Dump apply-related elements
        html = await page.evaluate("""() => {
            const els = document.querySelectorAll(
                'button, a[href]'
            );
            return Array.from(els)
                .filter(el => {
                    const t = (el.textContent || '').toLowerCase();
                    const h = (el.getAttribute('href') || '').toLowerCase();
                    return t.includes('apply') || h.includes('apply') || h.includes('job');
                })
                .slice(0, 15)
                .map(el => ({
                    tag: el.tagName,
                    text: el.textContent.trim().slice(0, 80),
                    href: el.getAttribute('href'),
                    cls: el.className,
                    'aria-label': el.getAttribute('aria-label'),
                    'data-job-id': el.getAttribute('data-job-id'),
                }));
        }""")
        print("\nApply-related elements:")
        for el in html:
            print(f"  {el['tag']} | text={el['text']!r} | href={el['href']!r} | cls={el['cls']!r}")

        # Also check for any offsite apply links
        offsite = await page.evaluate("""() => {
            const links = document.querySelectorAll('a[href]');
            return Array.from(links)
                .filter(a => {
                    const h = a.getAttribute('href') || '';
                    return !h.includes('linkedin.com') && h.startsWith('http');
                })
                .slice(0, 10)
                .map(a => ({href: a.href, text: a.textContent.trim().slice(0, 60)}));
        }""")
        print("\nOff-site links on page:")
        for l in offsite:
            print(f"  {l['href']} | {l['text']!r}")

        # Screenshot
        await page.screenshot(path=str(BASE / "debug2.png"))
        print("\nScreenshot saved to debug2.png")

        await browser.close()

asyncio.run(main())
