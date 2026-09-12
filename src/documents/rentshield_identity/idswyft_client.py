# Client for a self-hosted Idswyft instance
# (https://github.com/team-idswyft/idswyft-community) -- same
# "self-hosted service, plain requests, env-var base URL + key" shape as
# documents/rentshield/esign/docuseal_client.py. Idswyft does the actual
# document capture + liveness + face-match itself on its own hosted
# page (or via its JS SDK) -- our backend only ever starts a session and
# polls/receives its result, it never touches the passport photo or
# selfie directly.
#
# Endpoint paths/payloads verified 2026-09-12 against a real running
# instance's own backend source (backend/src/routes/newVerification.ts),
# not just the README, which turned out to document an incomplete
# picture of the real contract:
#   - POST /api/v2/verify/initialize requires `user_id` as a UUID -- not
#     mentioned in the README at all. Idswyft has no concept of "this is
#     the same RentShield user come back again" otherwise, so
#     views.py derives a stable uuid5 from the Django user's id.
#   - The initialize response's URL field is `verification_url`, not
#     `hosted_url` -- _hosted_url() below checks both, `verification_url`
#     first, so this keeps working either way.
#   - GET /api/v2/verify/{id}/status's `status` field is the granular
#     session step (AWAITING_FRONT, FACE_MATCHING, COMPLETE, ...), not a
#     simple outcome -- the field that actually maps onto
#     IdentityVerification.Status is `final_result`, which is null until
#     the session reaches COMPLETE/HARD_REJECTED, then becomes exactly
#     "verified" / "failed" / "manual_review".
from __future__ import annotations

import os
import uuid

import requests

IDSWYFT_BASE_URL = os.environ.get("IDSWYFT_BASE_URL", "")
IDSWYFT_API_KEY = os.environ.get("IDSWYFT_API_KEY", "")

# Namespace for deriving a stable per-user UUID -- Idswyft requires a
# UUID `user_id`; Django's own user ids are plain integers. uuid5 is
# deterministic (same Django user always maps to the same Idswyft
# user_id) without needing a stored field for it. Fixed, arbitrary
# constant -- only needs to be stable, not secret.
_USER_ID_NAMESPACE = uuid.UUID("0fe723ca-3c0c-4177-aa16-82434b43314c")


def rentshield_user_uuid(django_user_id: int) -> str:
    return str(uuid.uuid5(_USER_ID_NAMESPACE, f"rentshield-user-{django_user_id}"))


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
        body.get("verification_url")
        or body.get("hosted_url")
        or body.get("redirect_url")
        or f"{IDSWYFT_BASE_URL}/verify/{verification_id}"
    )


def create_verification_session(django_user_id: int, document_type: str = "passport") -> dict:
    """Starts a new verification session and returns the hosted page URL
    to send the user to (redirect on the same device, or show as a QR
    code for them to scan with their phone -- see
    rentshield_identity/views.py's start_verification_view)."""
    body = _fetch(
        "/api/v2/verify/initialize",
        method="POST",
        json={"user_id": rentshield_user_uuid(django_user_id), "document_type": document_type},
    )
    verification_id = body["verification_id"]
    return {"verification_id": verification_id, "hosted_url": _hosted_url(verification_id, body)}


def get_verification_status(verification_id: str) -> str | None:
    """Returns "verified" / "failed" / "manual_review" once the session
    reaches a terminal state, or None while still in progress (Idswyft's
    own `final_result` is null until then) -- callers should treat None
    as "still pending", not overwrite an existing pending record with
    it."""
    body = _fetch(f"/api/v2/verify/{verification_id}/status")
    return body.get("final_result")
