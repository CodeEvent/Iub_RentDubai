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
#   - `verification_mode` defaults to "full", which expects a back-page
#     document upload -- fine for a national ID, wrong for a passport
#     (single-sided). "identity" mode's flow (front document -> live
#     capture -> face match -> complete) is the one that actually fits a
#     passport, so create_verification_session() always requests it.
#   - POST .../front-document takes the photo as multipart field
#     "document"; POST .../live-capture takes the selfie as multipart
#     field "selfie". Both are plain single-image uploads -- no
#     multi-frame liveness challenge is required (that's optional
#     metadata the "identity" mode flow doesn't need).
from __future__ import annotations

import os
import uuid
from io import BytesIO

import requests
from PIL import Image

IDSWYFT_BASE_URL = os.environ.get("IDSWYFT_BASE_URL", "")
IDSWYFT_API_KEY = os.environ.get("IDSWYFT_API_KEY", "")

# Idswyft's own upload validation, hit for real (2026-09-13): "File type
# 'image/jp2' not in allowed types: image/jpeg, image/png,
# application/pdf". A passport/CIE chip photo (DG2, read by the
# Android/iOS native NFC apps) commonly arrives as JPEG2000 -- neither
# platform's own stock image APIs can decode that format either (see
# those apps' own NfcChipReader.kt/PassportNFCService.swift comments),
# so this can't be pushed onto the client; converted here once instead,
# which also fixes the admin review page's thumbnail (browsers can't
# render image/jp2 any better than Idswyft can).
_IDSWYFT_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}


def normalize_image_for_idswyft(file_bytes: bytes, content_type: str | None) -> tuple[bytes, str]:
    if content_type in _IDSWYFT_ALLOWED_CONTENT_TYPES:
        return file_bytes, content_type
    image = Image.open(BytesIO(file_bytes)).convert("RGB")
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue(), "image/jpeg"

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
    """Starts a new verification session. The actual capture (photo +
    selfie) happens inside RentShield's own UI via upload_front_document()/
    upload_live_capture() below -- not Idswyft's hosted page -- see
    rentshield_identity/views.py's start_verification_view."""
    body = _fetch(
        "/api/v2/verify/initialize",
        method="POST",
        json={
            "user_id": rentshield_user_uuid(django_user_id),
            "document_type": document_type,
            "verification_mode": "identity",
        },
    )
    verification_id = body["verification_id"]
    return {"verification_id": verification_id, "hosted_url": _hosted_url(verification_id, body)}


def _upload(path: str, field_name: str, file_bytes: bytes, filename: str, content_type: str) -> dict:
    res = requests.post(
        f"{IDSWYFT_BASE_URL}{path}",
        files={field_name: (filename, file_bytes, content_type)},
        headers={"X-API-Key": IDSWYFT_API_KEY},
        timeout=60,
    )
    body = res.json() if res.content else {}
    if not res.ok:
        raise RuntimeError(body.get("message") or body.get("error") or f"Idswyft API returned {res.status_code}")
    return body


def upload_front_document(verification_id: str, file_bytes: bytes, filename: str, content_type: str) -> dict:
    """Uploads the passport photo -- triggers real OCR extraction
    synchronously on Idswyft's engine (~1.5GB ML inference spike per
    idswyft-community's own README), so this call can take a while."""
    return _upload(f"/api/v2/verify/{verification_id}/front-document", "document", file_bytes, filename, content_type)


def upload_live_capture(verification_id: str, file_bytes: bytes, filename: str, content_type: str) -> dict:
    """Uploads the live selfie -- triggers real liveness + face-match
    inference synchronously, same resource note as upload_front_document()."""
    return _upload(f"/api/v2/verify/{verification_id}/live-capture", "selfie", file_bytes, filename, content_type)


def get_verification_status(verification_id: str) -> dict:
    """Returns {"step": ..., "final_result": ...}. `step` is Idswyft's
    granular session step (AWAITING_FRONT, AWAITING_LIVE, FACE_MATCHING,
    COMPLETE, ...) -- the frontend uses this to resume at the right
    capture stage after a reload. `final_result` stays None until the
    session reaches a terminal state, then becomes exactly "verified" /
    "failed" / "manual_review" -- callers should treat None as "still in
    progress", never overwrite a stored status with it."""
    body = _fetch(f"/api/v2/verify/{verification_id}/status")
    return {"step": body.get("status"), "final_result": body.get("final_result")}
