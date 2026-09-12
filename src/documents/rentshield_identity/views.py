# Property-owner identity verification -- self-hosted Idswyft (camera
# capture + liveness + face match against the passport photo, see
# idswyft_client.py's header comment for why this and not NFC chip
# reading). Mounted under the same documents/ URL namespace as every
# other RentShield endpoint (paperless/urls.py), matching this
# project's existing convention.
from __future__ import annotations

import logging

from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield_identity import idswyft_client
from documents.rentshield_identity.models import IdentityVerification

logger = logging.getLogger("paperless.rentshield")


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_verification_view(request):
    """POST /api/documents/identity/verify/start/ -- starts a new Idswyft
    session for the current user and returns its hosted page URL. The
    frontend either redirects to it directly (same device) or renders it
    as a QR code for the user to scan with their phone -- Idswyft's own
    hosted page does the actual capture, this backend never sees the
    photo or selfie."""
    existing = IdentityVerification.objects.filter(user=request.user).first()
    if existing and existing.status == IdentityVerification.Status.VERIFIED:
        return Response({"status": existing.status, "hosted_url": existing.hosted_url})

    if not idswyft_client.is_configured():
        # No DB write here on purpose: a "pending" row created for a
        # request that never actually reached Idswyft would show as
        # stuck in progress forever, not as the "try again later" it
        # actually is.
        return Response(
            {"error": "Identity verification is not configured in this environment."},
            status=503,
        )

    record, _ = IdentityVerification.objects.get_or_create(user=request.user)
    try:
        session = idswyft_client.create_verification_session()
    except Exception:
        logger.exception("Failed to start Idswyft verification session for user %s", request.user.id)
        return Response({"error": "Could not start identity verification -- try again shortly."}, status=502)

    record.verification_id = session["verification_id"]
    record.hosted_url = session["hosted_url"]
    record.status = IdentityVerification.Status.PENDING
    record.save(update_fields=["verification_id", "hosted_url", "status", "updated_at"])
    return Response({"status": record.status, "hosted_url": record.hosted_url})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def verification_status_view(request):
    """GET /api/documents/identity/verify/status/ -- the frontend polls
    this while a session is pending. Actively re-checks with Idswyft
    (not just returning the last-known DB value) the same way
    documents.rentshield.service.check_notarization_status() polls the
    e-signature provider -- a webhook can be slow/dropped, so this is
    the reliable path, not just a nice-to-have."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"status": None})

    if record.status == IdentityVerification.Status.PENDING and record.verification_id and idswyft_client.is_configured():
        try:
            live_status = idswyft_client.get_verification_status(record.verification_id)
        except Exception:
            logger.exception("Failed to poll Idswyft status for verification %s", record.verification_id)
        else:
            if live_status != record.status:
                record.status = live_status
                record.save(update_fields=["status", "updated_at"])

    return Response({"status": record.status})


@api_view(["POST"])
@permission_classes([AllowAny])
def idswyft_webhook_view(request):
    """POST /api/documents/identity/verify/webhook/ -- Idswyft's
    community README documents retry-on-failure webhooks but not their
    exact payload shape or signature scheme (not published anywhere as
    of 2026-09-12), so this reads defensively (`verification_id`/`id`,
    `status`/`event`) and never trusts an unrecognized payload rather
    than guessing a signature check that might not match the real one.
    verification_status_view's polling is the authoritative path this
    feature actually relies on; this is a latency optimization on top of
    it, not the only way status gets updated."""
    verification_id = request.data.get("verification_id") or request.data.get("id")
    status = request.data.get("status") or request.data.get("event")
    if not verification_id or status not in dict(IdentityVerification.Status.choices):
        logger.warning("Idswyft webhook: ignoring unrecognized payload %r", request.data)
        return Response({"ok": False}, status=400)

    updated = IdentityVerification.objects.filter(verification_id=verification_id).update(status=status)
    if not updated:
        logger.warning("Idswyft webhook: no IdentityVerification found for %r", verification_id)
    return Response({"ok": True})
