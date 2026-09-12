# Property-owner identity verification -- self-hosted Idswyft (camera
# capture + liveness + face match against the passport photo, see
# idswyft_client.py's header comment for why this and not NFC chip
# reading). Mounted under the same documents/ URL namespace as every
# other RentShield endpoint (paperless/urls.py), matching this
# project's existing convention.
from __future__ import annotations

import logging
import mimetypes
from pathlib import Path

from django.core.files.base import ContentFile
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield_identity import idswyft_client
from documents.rentshield_identity.models import IdentityVerification

logger = logging.getLogger("paperless.rentshield")


def _save_geolocation(record: IdentityVerification, post_data) -> None:
    """Optional browser Geolocation API reading, sent alongside either
    upload (see identity-verification.component.ts) -- evidence for a
    reviewer of where verification happened, never a gate on the result
    itself. Silently does nothing if absent (permission denied/unset) or
    malformed, matching this project's usual "optional evidence, never a
    hard failure" pattern for this kind of field."""
    try:
        lat = post_data.get("latitude")
        lng = post_data.get("longitude")
        if lat is None or lng is None:
            return
        record.latitude = float(lat)
        record.longitude = float(lng)
        accuracy = post_data.get("location_accuracy_m")
        record.location_accuracy_m = float(accuracy) if accuracy is not None else None
    except (TypeError, ValueError):
        logger.warning("Ignoring malformed geolocation in upload for user %s", record.user_id)


def _filename_for_content_type(name: str, content_type: str) -> str:
    """normalize_image_for_idswyft() can change the actual bytes' format
    (e.g. JPEG2000 -> JPEG) without this view knowing the original
    filename's extension -- if the stored filename keeps saying ".jp2"
    while the bytes are now a JPEG, django.views.static.serve guesses the
    wrong Content-Type from the extension and the admin review page's
    <img> tag refuses to render it, even though the bytes are fine."""
    guessed_ext = mimetypes.guess_extension(content_type)
    if not guessed_ext:
        return name
    return Path(name).stem + guessed_ext


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def start_verification_view(request):
    """POST /api/documents/identity/verify/start/ -- starts a new Idswyft
    session for the current user. The frontend then captures the passport
    photo and selfie itself and posts them to upload_front_document_view/
    upload_live_capture_view below -- the property owner never leaves
    RentShield's own page or sees Idswyft's branding (that hosted page
    can't be white-labeled without their paid enterprise plan)."""
    existing = IdentityVerification.objects.filter(user=request.user).first()
    if existing and existing.status == IdentityVerification.Status.VERIFIED:
        return Response({"status": existing.status})

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
        session = idswyft_client.create_verification_session(request.user.id)
    except Exception:
        logger.exception("Failed to start Idswyft verification session for user %s", request.user.id)
        return Response({"error": "Could not start identity verification -- try again shortly."}, status=502)

    record.verification_id = session["verification_id"]
    record.hosted_url = session["hosted_url"]
    record.status = IdentityVerification.Status.PENDING
    record.save(update_fields=["verification_id", "hosted_url", "status", "updated_at"])
    # "identity" mode's flow always starts here -- see
    # idswyft_client.create_verification_session()'s header comment.
    return Response({"status": record.status, "step": "AWAITING_FRONT"})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def verification_status_view(request):
    """GET /api/documents/identity/verify/status/ -- the frontend polls
    this while a session is pending, and also calls it once on load to
    resume at the right capture step after a reload (`step`). Actively
    re-checks with Idswyft for the outcome (not just returning the
    last-known DB value) the same way
    documents.rentshield.service.check_notarization_status() polls the
    e-signature provider -- a webhook can be slow/dropped, so this is
    the reliable path, not just a nice-to-have."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"status": None, "step": None})

    step = None
    if record.status == IdentityVerification.Status.PENDING and record.verification_id and idswyft_client.is_configured():
        try:
            live = idswyft_client.get_verification_status(record.verification_id)
        except Exception:
            logger.exception("Failed to poll Idswyft status for verification %s", record.verification_id)
        else:
            step = live["step"]
            # None means "still in progress" (Idswyft's own final_result
            # is null until the session completes) -- not a status value
            # to write, and never mistake it for the string "None" landing
            # in the field.
            if live["final_result"] is not None and live["final_result"] != record.status:
                record.status = live["final_result"]
                record.save(update_fields=["status", "updated_at"])

    return Response({"status": record.status, "step": step})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_front_document_view(request):
    """POST /api/documents/identity/verify/front-document/ -- the
    passport photo, captured right inside RentShield's own page (see
    identity-verification.component.ts). Forwarded to Idswyft's engine
    for real OCR extraction, which can take a few seconds -- the
    frontend shows a spinner for this call, not just the polling loop."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"error": "No verification in progress -- start one first."}, status=400)

    uploaded = request.FILES.get("document")
    if not uploaded:
        return Response({"error": "A photo of your passport is required."}, status=400)

    # Read once, reuse the same bytes for RentShield's own copy (for the
    # admin review page -- see admin_views.py) and for the Idswyft
    # forward -- the upload stream can only be consumed once. Normalized
    # to a format Idswyft actually accepts *before* either use -- a
    # passport/CIE chip photo can arrive as JPEG2000, which Idswyft 502s
    # on and browsers can't render for the admin thumbnail either (see
    # idswyft_client.normalize_image_for_idswyft's comment).
    file_bytes, content_type = idswyft_client.normalize_image_for_idswyft(uploaded.read(), uploaded.content_type)
    record.passport_photo.save(_filename_for_content_type(uploaded.name, content_type), ContentFile(file_bytes), save=False)
    _save_geolocation(record, request.POST)
    record.save(update_fields=["passport_photo", "latitude", "longitude", "location_accuracy_m", "updated_at"])

    try:
        result = idswyft_client.upload_front_document(
            record.verification_id, file_bytes, uploaded.name, content_type,
        )
    except Exception:
        logger.exception("Front-document upload failed for verification %s", record.verification_id)
        return Response({"error": "Could not process that photo -- try again."}, status=502)

    # A bad/unreadable document can hard-reject right here, before any
    # selfie is ever uploaded -- without this check the record stays
    # "pending" forever with no terminal outcome, the exact "stuck
    # spinner" bug already fixed once for the resume-on-reload case.
    final_result = result.get("final_result")
    if final_result is not None and final_result != record.status:
        record.status = final_result
        record.save(update_fields=["status", "updated_at"])

    return Response({"step": result.get("status"), "status": record.status})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_live_capture_view(request):
    """POST /api/documents/identity/verify/live-capture/ -- the live
    selfie. Idswyft runs liveness + face-match synchronously in this same
    request and returns the final outcome directly, so this updates the
    stored status immediately rather than waiting for the next poll."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"error": "No verification in progress -- start one first."}, status=400)

    uploaded = request.FILES.get("selfie")
    if not uploaded:
        return Response({"error": "A selfie is required."}, status=400)

    file_bytes, content_type = idswyft_client.normalize_image_for_idswyft(uploaded.read(), uploaded.content_type)
    record.selfie_photo.save(_filename_for_content_type(uploaded.name, content_type), ContentFile(file_bytes), save=False)
    _save_geolocation(record, request.POST)
    record.save(update_fields=["selfie_photo", "latitude", "longitude", "location_accuracy_m", "updated_at"])

    try:
        result = idswyft_client.upload_live_capture(
            record.verification_id, file_bytes, uploaded.name, content_type,
        )
    except Exception:
        logger.exception("Live-capture upload failed for verification %s", record.verification_id)
        return Response({"error": "Could not process that selfie -- try again."}, status=502)

    final_result = result.get("final_result")
    if final_result is not None and final_result != record.status:
        record.status = final_result
        record.save(update_fields=["status", "updated_at"])

    return Response({"step": result.get("status"), "status": record.status})


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
