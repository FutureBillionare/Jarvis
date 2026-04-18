"""
Internship Scraper — searches LinkedIn, Google Jobs, Indeed, Handshake, and
Glassdoor for engineering internships matching Jake's profile.
"""

import json
import time
import random
import hashlib
import logging
from pathlib import Path
from datetime import datetime
from typing import Callable

import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

_BASE = Path(__file__).parent
_PROFILE = json.loads((_BASE / "profile.json").read_text())

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

SEARCH_CONFIG = _PROFILE["internship_search"]
KEYWORDS = SEARCH_CONFIG["job_titles"]
LOCATIONS = SEARCH_CONFIG["locations"]


# ── Utilities ─────────────────────────────────────────────────────────────────

def _uid(company: str, title: str, url: str) -> str:
    raw = f"{company.lower().strip()}{title.lower().strip()}{url}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def _pause(lo=1.5, hi=3.5):
    time.sleep(random.uniform(lo, hi))


def _get(url: str, **kwargs) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15, **kwargs)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"GET failed {url}: {e}")
        return None


# ── Google Jobs Search ────────────────────────────────────────────────────────

def _search_google_jobs(query: str, status_cb: Callable | None = None) -> list[dict]:
    results = []
    url = (
        f"https://www.google.com/search?q={requests.utils.quote(query)}"
        "&ibp=htl;jobs&hl=en&gl=us"
    )
    r = _get(url)
    if not r:
        return results

    soup = BeautifulSoup(r.text, "html.parser")
    for card in soup.select("li.iFjolb")[:10]:
        try:
            title_el = card.select_one(".QJPWVe")
            company_el = card.select_one(".vNEEBe")
            loc_el = card.select_one(".Qk80Jf")
            link_el = card.select_one("a")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location = loc_el.get_text(strip=True) if loc_el else "Unknown"
            apply_url = link_el["href"] if link_el else ""

            entry = {
                "id": _uid(company, title, apply_url),
                "title": title,
                "company": company,
                "location": location,
                "url": apply_url,
                "source": "Google Jobs",
                "found_at": datetime.now().isoformat(),
            }
            results.append(entry)
        except Exception:
            continue

    return results


# ── LinkedIn Public Jobs Search ───────────────────────────────────────────────

def _search_linkedin(keyword: str, location: str, status_cb: Callable | None = None) -> list[dict]:
    results = []
    encoded_kw = requests.utils.quote(keyword)
    encoded_loc = requests.utils.quote(location)
    url = (
        f"https://www.linkedin.com/jobs/search/?keywords={encoded_kw}"
        f"&location={encoded_loc}&f_JT=I&f_TP=1%2C2&sortBy=DD"
    )
    r = _get(url)
    if not r:
        return results

    soup = BeautifulSoup(r.text, "html.parser")
    cards = soup.select("div.base-card")[:15]

    for card in cards:
        try:
            title_el = card.select_one("h3.base-search-card__title")
            company_el = card.select_one("h4.base-search-card__subtitle")
            loc_el = card.select_one("span.job-search-card__location")
            link_el = card.select_one("a.base-card__full-link")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location_str = loc_el.get_text(strip=True) if loc_el else "Unknown"
            apply_url = link_el["href"].split("?")[0] if link_el else ""

            entry = {
                "id": _uid(company, title, apply_url),
                "title": title,
                "company": company,
                "location": location_str,
                "url": apply_url,
                "source": "LinkedIn",
                "found_at": datetime.now().isoformat(),
            }
            results.append(entry)
        except Exception:
            continue

    return results


# ── Indeed Search ─────────────────────────────────────────────────────────────

def _search_indeed(keyword: str, location: str, status_cb: Callable | None = None) -> list[dict]:
    results = []
    encoded_kw = requests.utils.quote(keyword)
    encoded_loc = requests.utils.quote(location)
    url = (
        f"https://www.indeed.com/jobs?q={encoded_kw}&l={encoded_loc}"
        "&jt=internship&fromage=7"
    )
    r = _get(url)
    if not r:
        return results

    soup = BeautifulSoup(r.text, "html.parser")
    for card in soup.select("div.job_seen_beacon")[:15]:
        try:
            title_el = card.select_one("h2.jobTitle span")
            company_el = card.select_one("span.companyName")
            loc_el = card.select_one("div.companyLocation")
            link_el = card.select_one("a.jcs-JobTitle")

            if not title_el:
                continue

            title = title_el.get_text(strip=True)
            company = company_el.get_text(strip=True) if company_el else "Unknown"
            location_str = loc_el.get_text(strip=True) if loc_el else "Unknown"
            job_id = link_el.get("data-jk", "") if link_el else ""
            apply_url = f"https://www.indeed.com/viewjob?jk={job_id}" if job_id else ""

            entry = {
                "id": _uid(company, title, apply_url),
                "title": title,
                "company": company,
                "location": location_str,
                "url": apply_url,
                "source": "Indeed",
                "found_at": datetime.now().isoformat(),
            }
            results.append(entry)
        except Exception:
            continue

    return results


# ── Handshake (public listings via Google) ────────────────────────────────────

def _search_handshake(keyword: str, status_cb: Callable | None = None) -> list[dict]:
    """Search Handshake internships via Google site: search."""
    query = f'site:joinhandshake.com "{keyword}" internship summer 2025'
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num=10"
    r = _get(url)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for result in soup.select("div.g")[:10]:
        try:
            title_el = result.select_one("h3")
            link_el = result.select_one("a")
            snippet_el = result.select_one("div.VwiC3b")

            if not title_el or not link_el:
                continue

            title = title_el.get_text(strip=True)
            href = link_el["href"]
            snippet = snippet_el.get_text(strip=True) if snippet_el else ""

            # Extract company from title (format: "Title at Company | Handshake")
            company = "Unknown"
            if " at " in title:
                parts = title.split(" at ")
                title = parts[0].strip()
                company = parts[1].split("|")[0].strip()
            elif "|" in title:
                parts = title.split("|")
                title = parts[0].strip()
                company = parts[1].strip() if len(parts) > 1 else "Unknown"

            entry = {
                "id": _uid(company, title, href),
                "title": title,
                "company": company,
                "location": "See listing",
                "url": href,
                "source": "Handshake",
                "description": snippet,
                "found_at": datetime.now().isoformat(),
            }
            results.append(entry)
        except Exception:
            continue

    return results


# ── Glassdoor Search ──────────────────────────────────────────────────────────

def _search_glassdoor(keyword: str, status_cb: Callable | None = None) -> list[dict]:
    query = f'site:glassdoor.com "{keyword}" internship summer 2025'
    url = f"https://www.google.com/search?q={requests.utils.quote(query)}&num=10"
    r = _get(url)
    if not r:
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for result in soup.select("div.g")[:10]:
        try:
            title_el = result.select_one("h3")
            link_el = result.select_one("a")
            if not title_el or not link_el:
                continue

            raw_title = title_el.get_text(strip=True)
            href = link_el["href"]

            # Parse "Title - Company - Glassdoor" format
            parts = raw_title.replace(" - Glassdoor", "").split(" - ")
            title = parts[0].strip()
            company = parts[1].strip() if len(parts) > 1 else "Unknown"

            entry = {
                "id": _uid(company, title, href),
                "title": title,
                "company": company,
                "location": "See listing",
                "url": href,
                "source": "Glassdoor",
                "found_at": datetime.now().isoformat(),
            }
            results.append(entry)
        except Exception:
            continue

    return results


# ── Deduplication ─────────────────────────────────────────────────────────────

def _dedup(listings: list[dict]) -> list[dict]:
    seen = set()
    unique = []
    for item in listings:
        key = item["id"]
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# ── Main Search Entry Point ────────────────────────────────────────────────────

def run_search(
    status_cb: Callable | None = None,
    duration_minutes: int = 30,
) -> list[dict]:
    """
    Run the full internship search for `duration_minutes`.
    Calls status_cb(phase, message, count) during execution.
    Returns deduplicated list of internship listings.
    """

    def emit(phase: str, msg: str, count: int = 0):
        log.info(f"[{phase}] {msg}")
        if status_cb:
            status_cb(phase, msg, count)

    all_results = []
    start = time.time()
    deadline = start + (duration_minutes * 60)

    emit("search", "Starting internship search...", 0)

    # Rotate through keywords and locations
    search_pairs = [
        (kw, loc)
        for kw in KEYWORDS[:4]          # top 4 keywords
        for loc in LOCATIONS[:3]         # top 3 locations
    ]
    random.shuffle(search_pairs)

    for i, (keyword, location) in enumerate(search_pairs):
        if time.time() >= deadline:
            emit("search", "Research time limit reached.", len(all_results))
            break

        emit("search", f"Searching: '{keyword}' in {location}...", len(all_results))

        # LinkedIn
        try:
            results = _search_linkedin(keyword, location, status_cb)
            all_results.extend(results)
            emit("search", f"LinkedIn: +{len(results)} results", len(all_results))
        except Exception as e:
            log.warning(f"LinkedIn search error: {e}")
        _pause()

        if time.time() >= deadline:
            break

        # Indeed
        try:
            results = _search_indeed(keyword, location, status_cb)
            all_results.extend(results)
            emit("search", f"Indeed: +{len(results)} results", len(all_results))
        except Exception as e:
            log.warning(f"Indeed search error: {e}")
        _pause()

        if time.time() >= deadline:
            break

    # Handshake (college-specific)
    emit("search", "Searching Handshake (college internships)...", len(all_results))
    for kw in KEYWORDS[:3]:
        if time.time() >= deadline:
            break
        try:
            results = _search_handshake(kw, status_cb)
            all_results.extend(results)
            emit("search", f"Handshake: +{len(results)} for '{kw}'", len(all_results))
        except Exception as e:
            log.warning(f"Handshake search error: {e}")
        _pause(2, 4)

    # Google Jobs
    emit("search", "Searching Google Jobs...", len(all_results))
    for kw in KEYWORDS[:3]:
        if time.time() >= deadline:
            break
        query = f"{kw} summer 2025 internship Texas"
        try:
            results = _search_google_jobs(query, status_cb)
            all_results.extend(results)
            emit("search", f"Google Jobs: +{len(results)} for '{kw}'", len(all_results))
        except Exception as e:
            log.warning(f"Google Jobs search error: {e}")
        _pause(2, 4)

    # Deduplicate
    unique = _dedup(all_results)
    emit("search", f"Search complete. Found {len(unique)} unique listings.", len(unique))
    return unique


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    listings = run_search(duration_minutes=5)
    print(f"\n=== Found {len(listings)} internships ===")
    for item in listings[:10]:
        print(f"  [{item['source']}] {item['title']} @ {item['company']} — {item['location']}")
