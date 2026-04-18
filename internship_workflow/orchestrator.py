"""
Internship Workflow Orchestrator — coordinates scrape → store → apply → record.

Phases:
  1. SEARCH   — 30 min of scraping LinkedIn/Indeed/Handshake/Google
  2. FILTER   — deduplicate, cross-check against already-applied
  3. APPLY    — Playwright auto-fill for each new listing
  4. RECORD   — write applied internships to Google Sheets

Emits real-time status events via status_cb(phase, message, count).
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .scraper import run_search
from .storage import InternshipStorage
from .applicator import apply_to_internships

log = logging.getLogger(__name__)

_BASE = Path(__file__).parent
_RUN_LOG = _BASE / "run_log.json"

SEARCH_DURATION_MINUTES = 30


# ── Run Log ────────────────────────────────────────────────────────────────────

def _load_run_log() -> dict:
    if _RUN_LOG.exists():
        try:
            return json.loads(_RUN_LOG.read_text())
        except Exception:
            pass
    return {"runs": []}


def _append_run(entry: dict):
    log_data = _load_run_log()
    log_data["runs"].append(entry)
    _RUN_LOG.write_text(json.dumps(log_data, indent=2))


# ── Orchestrator ──────────────────────────────────────────────────────────────

class WorkflowOrchestrator:
    """
    Usage:
        orch = WorkflowOrchestrator(status_cb=my_callback)
        result = orch.run()
    """

    def __init__(self, status_cb: Callable | None = None):
        self._cb = status_cb
        self._storage = InternshipStorage(status_cb=status_cb)
        self._start_time = None
        self._run_result = {
            "started_at": None,
            "finished_at": None,
            "found_count": 0,
            "new_count": 0,
            "applied_count": 0,
            "applied_listings": [],
            "error": None,
        }

    def _emit(self, phase: str, msg: str, count: int = 0):
        log.info(f"[{phase.upper()}] {msg}")
        if self._cb:
            self._cb(phase, msg, count)

    # ── Phase 1: Search ────────────────────────────────────────────────────────

    def _phase_search(self) -> list[dict]:
        self._emit("search", f"Phase 1: Searching for internships ({SEARCH_DURATION_MINUTES} min)...")
        listings = run_search(
            status_cb=self._cb,
            duration_minutes=SEARCH_DURATION_MINUTES,
        )
        self._run_result["found_count"] = len(listings)
        self._emit("search", f"Found {len(listings)} internship listings.", len(listings))
        return listings

    # ── Phase 2: Filter ────────────────────────────────────────────────────────

    def _phase_filter(self, listings: list[dict]) -> list[dict]:
        self._emit("filter", "Phase 2: Saving found internships and filtering duplicates...")

        # Save all found to Sheets
        new_saved = self._storage.save_found(listings)
        self._emit("filter", f"Saved {new_saved} new listings to Google Sheets.")

        # Filter out already-applied
        unapplied = self._storage.get_unapplied(listings)
        self._run_result["new_count"] = len(unapplied)
        self._emit(
            "filter",
            f"{len(unapplied)} listings not yet applied to (skipping {len(listings) - len(unapplied)} already applied).",
            len(unapplied),
        )
        return unapplied

    # ── Phase 3: Apply ─────────────────────────────────────────────────────────

    async def _phase_apply(self, listings: list[dict]) -> list[dict]:
        if not listings:
            self._emit("apply", "No new internships to apply to.")
            return []

        self._emit("apply", f"Phase 3: Applying to {len(listings)} internships...")
        applied = await apply_to_internships(listings, status_cb=self._cb)
        self._run_result["applied_count"] = len(applied)
        self._emit("apply", f"Applied to {len(applied)} internships.", len(applied))
        return applied

    # ── Phase 4: Record ────────────────────────────────────────────────────────

    def _phase_record(self, applied: list[dict]):
        self._emit("record", f"Phase 4: Recording {len(applied)} applied internships...")
        for listing in applied:
            self._storage.mark_applied(listing, notes="auto-applied by HUBERT")
        self._run_result["applied_listings"] = applied
        self._emit("record", "All applied internships recorded to Google Sheets.", len(applied))

    # ── Main Run ───────────────────────────────────────────────────────────────

    def run(self) -> dict:
        """Synchronous entry point — runs the full async workflow."""
        return asyncio.run(self._run_async())

    async def _run_async(self) -> dict:
        self._start_time = time.time()
        self._run_result["started_at"] = datetime.now().isoformat()

        self._emit("start", "HUBERT Internship Workflow starting...", 0)

        try:
            # Phase 1: Search
            listings = self._phase_search()

            # Phase 2: Filter
            unapplied = self._phase_filter(listings)

            # Phase 3: Apply
            applied = await self._phase_apply(unapplied)

            # Phase 4: Record
            self._phase_record(applied)

            self._run_result["finished_at"] = datetime.now().isoformat()
            elapsed = round(time.time() - self._start_time)
            self._emit(
                "done",
                f"Workflow complete in {elapsed}s. Applied to {len(applied)} internships.",
                len(applied),
            )

        except Exception as e:
            log.exception("Orchestrator error")
            self._run_result["error"] = str(e)
            self._run_result["finished_at"] = datetime.now().isoformat()
            self._emit("error", f"Workflow error: {e}", 0)

        _append_run(self._run_result)
        return self._run_result


# ── CLI Entry ──────────────────────────────────────────────────────────────────

def run_workflow(status_cb: Callable | None = None) -> dict:
    """Public function — call this to run the full workflow."""
    orch = WorkflowOrchestrator(status_cb=status_cb)
    return orch.run()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    def cb(phase, msg, count):
        print(f"  [{phase:8}] {msg}")

    result = run_workflow(status_cb=cb)
    print("\n=== Run Summary ===")
    print(f"  Found:   {result['found_count']}")
    print(f"  New:     {result['new_count']}")
    print(f"  Applied: {result['applied_count']}")
    if result.get("applied_listings"):
        print("\n  Applied to:")
        for item in result["applied_listings"]:
            print(f"    • {item['title']} @ {item['company']} ({item['location']})")
