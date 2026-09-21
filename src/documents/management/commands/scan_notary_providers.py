# Manual/on-demand entry point for the notary-provider research scan
# (documents/rentshield/notary_research/) -- the same scanner the daily
# Celery Beat task (documents.tasks.run_notary_provider_scan_task) runs
# on a schedule. Useful for running it right now instead of waiting for
# the schedule, and for verifying the pipeline works without needing to
# wait on/trigger Celery.
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = (
        "Runs the notary-provider research scan once, right now, and prints "
        "the results -- fetches every URL in documents/rentshield/"
        "notary_research/targets.py via Scrapfly and reports which ones "
        "show a new api/developer/integration signal since the last scan. "
        "Requires PAPERLESS_SCRAPFLY_API_KEY; prints a clear message and "
        "exits cleanly (not an error) if it isn't set."
    )

    def handle(self, *args, **options):
        if not settings.SCRAPFLY_API_KEY:
            self.stdout.write(
                self.style.WARNING(
                    "SCRAPFLY_API_KEY is not configured (PAPERLESS_SCRAPFLY_API_KEY) "
                    "-- nothing to scan. Set it and re-run.",
                ),
            )
            return

        from documents.rentshield.notary_research.scanner import scan_all_targets

        result = scan_all_targets()

        for entry in result["scanned"]:
            marker = "NEW SIGNAL" if entry["new_keywords"] else "no change"
            self.stdout.write(f"[{marker}] {entry['name']} ({entry['url']})")
            if entry["found_keywords"]:
                self.stdout.write(f"    keywords found: {', '.join(entry['found_keywords'])}")
            if entry["new_keywords"]:
                self.stdout.write(self.style.SUCCESS(f"    NEW since last scan: {', '.join(entry['new_keywords'])}"))

        for err in result["errors"]:
            self.stdout.write(self.style.ERROR(f"[ERROR] {err['name']} ({err['url']}): {err['error']}"))

        self.stdout.write(
            self.style.SUCCESS(
                f"\nScanned {len(result['scanned'])}, {len(result['errors'])} error(s), "
                f"{len(result['new_signals'])} new signal(s).",
            ),
        )
