# Thin client for Scrapfly (https://scrapfly.io) -- a scraping-as-a-
# service API that handles anti-bot/JS-rendering, which the UAE
# government notary portals in targets.py are reasonably likely to have.
# Same shape as documents/rentshield/esign/docuseal_client.py: a bare
# `requests` call against the documented REST endpoint, no SDK
# dependency added for one endpoint. Scrapfly's own API docs:
# https://scrapfly.io/docs/scrape-api/getting-started
from __future__ import annotations

import os

import requests

SCRAPFLY_API_URL = "https://api.scrapfly.io/scrape"


def fetch_page_text(url: str, *, render_js: bool = True, timeout: int = 45) -> str:
    """Fetches `url` through Scrapfly and returns its rendered page text
    (not raw HTML -- callers here only care about visible copy, e.g.
    scanning for "API"/"developer" mentions). Raises RuntimeError with
    Scrapfly's own error message on any failure; raises immediately,
    without an HTTP call, if SCRAPFLY_API_KEY isn't configured, so a
    caller can catch exactly one exception type either way.
    """
    from django.conf import settings

    api_key = settings.SCRAPFLY_API_KEY
    if not api_key:
        msg = "SCRAPFLY_API_KEY is not configured"
        raise RuntimeError(msg)

    response = requests.get(
        SCRAPFLY_API_URL,
        params={
            "key": api_key,
            "url": url,
            "render_js": "true" if render_js else "false",
            "asp": "true",  # Scrapfly's anti-scrape-protection bypass
            "format": "text",
        },
        timeout=timeout,
    )
    body = response.json() if response.content else {}
    if not response.ok:
        error = (body.get("result") or {}).get("error") or body.get("message") or f"Scrapfly returned {response.status_code}"
        msg = f"Scrapfly fetch failed for {url}: {error}"
        raise RuntimeError(msg)

    result = body.get("result") or {}
    content = result.get("content")
    if content is None:
        msg = f"Scrapfly returned no content for {url}"
        raise RuntimeError(msg)
    return content
