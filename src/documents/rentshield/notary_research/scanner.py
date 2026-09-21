# Runs the notary-provider research scan: fetches every URL in
# targets.py via Scrapfly, checks for API_SIGNAL_KEYWORDS, and diffs
# against the previous scan's snapshot so callers only need to act on
# what's actually NEW -- not re-read the same "no API" result every day.
# Called by documents.tasks.run_notary_provider_scan_task (the scheduled
# job) and by manage.py scan_notary_providers (manual/on-demand runs,
# also how this was verified without a real Scrapfly key -- see that
# command's own docstring).
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from documents.rentshield.notary_research.scrapfly_client import fetch_page_text
from documents.rentshield.notary_research.targets import API_SIGNAL_KEYWORDS
from documents.rentshield.notary_research.targets import TARGETS

logger = logging.getLogger("paperless.rentshield")


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _snapshot_dir() -> Path:
    from django.conf import settings

    path = Path(settings.DATA_DIR) / "notary_research"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _found_keywords(page_text: str) -> list[str]:
    lowered = page_text.lower()
    return [kw for kw in API_SIGNAL_KEYWORDS if kw in lowered]


def scan_all_targets() -> dict:
    """Returns {"scanned": [...], "errors": [...], "new_signals": [...]}.
    Each scanned entry: {name, url, found_keywords, is_new_signal}.
    Writes this run's per-target keyword findings to
    DATA_DIR/notary_research/<slug>.json so the next run can diff
    against it -- deliberately just a JSON snapshot on disk, not a new
    database model, since this is exploratory research data, not
    product data (see the notarization-automation plan in the README
    for why MonitoredProperty/Subscription, by contrast, will need a
    real model when that work happens)."""
    snapshot_dir = _snapshot_dir()
    scanned = []
    errors = []
    new_signals = []

    for target in TARGETS:
        slug = _slug(target["name"])
        snapshot_path = snapshot_dir / f"{slug}.json"
        previous_keywords: list[str] = []
        if snapshot_path.exists():
            try:
                previous_keywords = json.loads(snapshot_path.read_text()).get("found_keywords", [])
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("notary_research: could not read previous snapshot for %s: %s", target["name"], exc)

        try:
            page_text = fetch_page_text(target["url"])
        except Exception as exc:  # noqa: BLE001 - one bad target must not stop the scan
            logger.warning("notary_research: fetch failed for %s (%s): %s", target["name"], target["url"], exc)
            errors.append({"name": target["name"], "url": target["url"], "error": str(exc)})
            continue

        found = _found_keywords(page_text)
        newly_found = sorted(set(found) - set(previous_keywords))
        entry = {
            "name": target["name"],
            "url": target["url"],
            "found_keywords": found,
            "new_keywords": newly_found,
        }
        scanned.append(entry)
        if newly_found:
            new_signals.append(entry)

        snapshot_path.write_text(json.dumps({"found_keywords": found}, indent=2))

    return {"scanned": scanned, "errors": errors, "new_signals": new_signals}
