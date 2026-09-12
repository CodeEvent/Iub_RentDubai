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

from dateutil import parser as dateutil_parser
from django.core.files.base import ContentFile
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield.roles import IsNotaryPublic
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


def _update_user_profile_from_ocr(user, full_name: str) -> None:
    """Auto-updates the account's name from the ID card's own OCR read,
    requested explicitly rather than left for the user to type
    separately. Naive first-token/rest split -- good enough for the
    common case, and this only ever runs once the identity pipeline has
    real document evidence behind the name, so an imperfect split is
    cosmetic, not a correctness problem."""
    full_name = full_name.strip()
    if not full_name:
        return
    parts = full_name.split(None, 1)
    user.first_name = parts[0][:150]
    user.last_name = parts[1][:150] if len(parts) > 1 else ""
    user.save(update_fields=["first_name", "last_name"])


def _normalize_name_tokens(name: str) -> set[str]:
    """MRZ-style names are SURNAME<<GIVEN<NAMES (filler '<' for spaces)
    and can list surname before given names, while a chip reader's own
    firstName/lastName join is given-name-first -- comparing as a token
    set instead of an exact string avoids false "mismatches" that are
    really just word order."""
    return {token.upper() for token in name.replace("<", " ").split() if token}


def _normalize_dob(value: str) -> str | None:
    """Card OCR and chip MRZ data can each report a date of birth in a
    different format (ISO, DD/MM/YYYY, bare MRZ YYMMDD, ...) -- parsed
    leniently and compared as dates, not strings. Returns None on a
    failed parse rather than raising: an unparsable date on either side
    means "can't compare", not "mismatch" -- the raw values are still
    shown to the Notary reviewer either way."""
    try:
        return dateutil_parser.parse(value, fuzzy=True).date().isoformat()
    except (ValueError, OverflowError, TypeError):
        return None


def _check_identity_mismatch(record: IdentityVerification) -> str:
    """Never a hard gate -- OCR/MRZ misreads happen on both sides of
    this comparison -- just something surfaced for the Notary reviewer
    (admin_views.py) to see and weigh alongside everything else."""
    notes = []
    if record.card_ocr_full_name and record.chip_full_name:
        if _normalize_name_tokens(record.card_ocr_full_name) != _normalize_name_tokens(record.chip_full_name):
            notes.append(
                f'Name mismatch: card photo OCR read "{record.card_ocr_full_name}", '
                f'chip read "{record.chip_full_name}".',
            )
    if record.card_ocr_date_of_birth and record.chip_date_of_birth:
        card_dob = _normalize_dob(record.card_ocr_date_of_birth)
        chip_dob = _normalize_dob(record.chip_date_of_birth)
        if card_dob and chip_dob and card_dob != chip_dob:
            notes.append(
                f'Date of birth mismatch: card photo OCR read "{record.card_ocr_date_of_birth}", '
                f'chip read "{record.chip_date_of_birth}".',
            )
    if record.card_ocr_document_number and record.chip_document_number:
        # The document number the chip unlocked itself with a key that's
        # NOT this number (see chip_document_number's own field comment)
        # -- this only ever runs after a successful PACE/BAC handshake,
        # so a mismatch here means the OCR misread the printed number,
        # not that the wrong document was scanned.
        card_doc_number = record.card_ocr_document_number.strip().upper().replace(" ", "")
        chip_doc_number = record.chip_document_number.strip().upper().replace(" ", "")
        if card_doc_number != chip_doc_number:
            notes.append(
                f'Document number mismatch: card photo OCR read "{record.card_ocr_document_number}", '
                f'chip read "{record.chip_document_number}".',
            )
    return " ".join(notes)


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
    if final_result == IdentityVerification.Status.FAILED:
        record.status = final_result
        record.save(update_fields=["status", "updated_at"])

    ocr_data = result.get("ocr_data") or {}
    if ocr_data:
        record.card_ocr_full_name = (ocr_data.get("name") or "")[:255]
        record.card_ocr_date_of_birth = (ocr_data.get("date_of_birth") or "")[:32]
        record.card_ocr_document_number = (ocr_data.get("document_number") or "")[:64]
        record.identity_mismatch_notes = _check_identity_mismatch(record)
        record.save(
            update_fields=[
                "card_ocr_full_name", "card_ocr_date_of_birth", "card_ocr_document_number",
                "identity_mismatch_notes", "updated_at",
            ],
        )
        _update_user_profile_from_ocr(request.user, record.card_ocr_full_name)

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

    # Idswyft's own automated result is no longer the last word (see
    # models.py's docstring): a hard "failed" still short-circuits
    # immediately, same reasoning as upload_front_document_view above,
    # but "verified"/"manual_review" now only park in `automated_result`
    # as context for the Notary reviewer -- `status` stays PENDING until
    # the video step (upload_video_view) reaches AWAITING_NOTARY_REVIEW,
    # and only a human sets it to VERIFIED from there.
    final_result = result.get("final_result")
    if final_result is not None and final_result != record.automated_result:
        record.automated_result = final_result
        update_fields = ["automated_result", "updated_at"]
        if final_result == IdentityVerification.Status.FAILED:
            record.status = final_result
            update_fields.append("status")
        record.save(update_fields=update_fields)

    return Response({"step": result.get("status"), "status": record.status})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_chip_data_view(request):
    """POST /api/documents/identity/verify/chip-data/ -- the name/date
    of birth read directly off the NFC chip's DG1 (MRZ) by the native
    Android/iOS app, sent as plain JSON text (already extracted
    client-side by NfcChipReader.kt/PassportNFCService.swift -- no file
    upload here). Cross-checked against Idswyft's own OCR of the
    photographed card (card_ocr_*, set by upload_front_document_view
    above) -- see _check_identity_mismatch()'s comment on why a
    disagreement is surfaced for the Notary reviewer rather than
    treated as a hard failure."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"error": "No verification in progress -- start one first."}, status=400)

    full_name = (request.data.get("full_name") or "").strip()
    if not full_name:
        return Response({"error": "Chip full name is required."}, status=400)

    record.chip_full_name = full_name[:255]
    record.chip_date_of_birth = (request.data.get("date_of_birth") or "").strip()[:32]
    record.chip_document_number = (request.data.get("document_number") or "").strip()[:64]
    record.identity_mismatch_notes = _check_identity_mismatch(record)
    record.save(
        update_fields=[
            "chip_full_name", "chip_date_of_birth", "chip_document_number",
            "identity_mismatch_notes", "updated_at",
        ],
    )
    return Response({"status": record.status, "mismatch": bool(record.identity_mismatch_notes)})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_video_view(request):
    """POST /api/documents/identity/verify/video/ -- the short recorded
    confirmation clip. Not sent to Idswyft at all (it has no video-review
    API) -- this is purely for the Notary Public queue below. Advances
    `status` to AWAITING_NOTARY_REVIEW unless the automated pipeline
    already hard-failed, in which case there's nothing left to review."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"error": "No verification in progress -- start one first."}, status=400)

    if record.status == IdentityVerification.Status.FAILED:
        return Response({"error": "This verification already failed -- start a new one."}, status=400)

    uploaded = request.FILES.get("video")
    if not uploaded:
        return Response({"error": "A short confirmation video is required."}, status=400)

    record.video.save(uploaded.name, ContentFile(uploaded.read()), save=False)
    record.status = IdentityVerification.Status.AWAITING_NOTARY_REVIEW
    record.save(update_fields=["video", "status", "updated_at"])
    return Response({"status": record.status})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def notary_confirm_view(request, verification_id):
    """POST /api/documents/identity/verify/notary/<id>/confirm/ -- the
    Notary Public reviewer has watched the video (and can see the OCR/
    chip/mismatch/automated-result context alongside it, all returned by
    admin_views.py's list endpoint) and confirms this is really the
    account holder. This is the only path that ever sets VERIFIED --
    see models.py's docstring on why the automated result alone no
    longer does."""
    record = _get_reviewable_record_or_error(verification_id)
    if isinstance(record, Response):
        return record
    record.status = IdentityVerification.Status.VERIFIED
    record.notary_reviewed_by = request.user
    record.notary_reviewed_at = timezone.now()
    record.notary_notes = (request.data.get("notes") or "")[:2000]
    record.save(update_fields=["status", "notary_reviewed_by", "notary_reviewed_at", "notary_notes", "updated_at"])
    return Response({"status": record.status})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def notary_reject_view(request, verification_id):
    """POST /api/documents/identity/verify/notary/<id>/reject/ -- the
    Notary Public reviewer rejects the video (doesn't match, low
    quality, wrong person, ...). `notes` should say why -- shown back to
    whoever looks at this record afterward, there's no other record of
    the reviewer's reasoning."""
    record = _get_reviewable_record_or_error(verification_id)
    if isinstance(record, Response):
        return record
    record.status = IdentityVerification.Status.FAILED
    record.notary_reviewed_by = request.user
    record.notary_reviewed_at = timezone.now()
    record.notary_notes = (request.data.get("notes") or "")[:2000]
    record.save(update_fields=["status", "notary_reviewed_by", "notary_reviewed_at", "notary_notes", "updated_at"])
    return Response({"status": record.status})


def _get_reviewable_record_or_error(verification_id):
    """Real bug caught in testing: without this check, a Notary could
    "confirm" or "reject" a record that never even reached the video
    step (e.g. one the automated pipeline had already hard-failed),
    silently overwriting a legitimate outcome. Reviewing is only
    meaningful once there's actually a video to watch."""
    try:
        record = IdentityVerification.objects.get(pk=verification_id)
    except (IdentityVerification.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such verification."}, status=404)
    if record.status != IdentityVerification.Status.AWAITING_NOTARY_REVIEW:
        return Response(
            {"error": f"This verification isn't awaiting review (current status: {record.status})."},
            status=400,
        )
    return record


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
