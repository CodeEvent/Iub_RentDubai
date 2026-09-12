# Client for a self-hosted Idswyft instance
# (https://github.com/team-idswyft/idswyft-community) -- same
# "self-hosted service, plain requests, env-var base URL + key" shape as
# documents/rentshield/esign/docuseal_client.py. Idswyft does the actual
# document capture + liveness + face-match itself on its own hosted
# page (or via its JS SDK) -- our backend only ever starts a session and
# polls/receives its result, it never touches the passport photo or
# selfie directly.
#
# Endpoint paths and the X-API-Key header are taken from idswyft-
# community's own README; the exact key name for the hosted verification
# page URL in the initialize response isn't documented anywhere public
# as of 2026-09-12, so `_hosted_url()` below checks the field names that
# would make sense and falls back to a constructed URL -- confirm this
# against a real deployed instance's actual response before relying on
# it in production.
from __future__ import annotations

import os

import requests

IDSWYFT_BASE_URL = os.environ.get("IDSWYFT_BASE_URL", "")
IDSWYFT_API_KEY = os.environ.get("IDSWYFT_API_KEY", "")


def is_configured() -> bool:
    return bool(IDSWYFT_BASE_URL and IDSWYFT_API_KEY)


def _fetch(path: str, method: str = "GET", json: dict | None = None) -> dict:
    res = requests.request(
        method,
        f"{IDSWYFT_BASE_URL}{path}",
        json=json,
        headers={"Content-Type": "application/json", "X-API-Key": IDSWYFT_API_KEY},
        timeout=30,
    )
    body = res.json() if res.content else {}
    if not res.ok:
        raise RuntimeError(body.get("error") or f"Idswyft API returned {res.status_code}")
    return body


def _hosted_url(verification_id: str, body: dict) -> str:
    return (
        body.get("hosted_url")
        or body.get("verification_url")
        or body.get("redirect_url")
        or f"{IDSWYFT_BASE_URL}/verify/{verification_id}"
    )


def create_verification_session(document_type: str = "passport") -> dict:
    """Starts a new verification session and returns the hosted page URL
    to send the user to (redirect on the same device, or show as a QR
    code for them to scan with their phone -- see
    rentshield_identity/views.py's start_verification_view)."""
    body = _fetch("/api/v2/verify/initialize", method="POST", json={"document_type": document_type})
    verification_id = body["verification_id"]
    return {"verification_id": verification_id, "hosted_url": _hosted_url(verification_id, body)}


def get_verification_status(verification_id: str) -> str:
    """Returns one of "pending" / "verified" / "failed" / "manual_review"
    -- the exact strings idswyft-community's README documents for this
    endpoint, which line up 1:1 with IdentityVerification.Status."""
    body = _fetch(f"/api/v2/verify/{verification_id}/status")
    return body["status"]
