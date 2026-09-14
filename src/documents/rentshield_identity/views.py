# Property-owner identity verification -- self-hosted Idswyft (camera
# capture + liveness + face match against the passport photo, see
# idswyft_client.py's header comment for why this and not NFC chip
# reading). Mounted under the same documents/ URL namespace as every
# other RentShield endpoint (paperless/urls.py), matching this
# project's existing convention.
from __future__ import annotations

import logging
import mimetypes
import re
from itertools import combinations
from pathlib import Path

from dateutil import parser as dateutil_parser
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.mail import send_mail
from django.db.models import Q
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield.roles import NOTARY_PUBLIC_GROUP_NAME
from documents.rentshield.roles import IsNotaryPublic
from documents.rentshield.roles import IsRentshieldAdmin
from documents.rentshield_identity import face_match
from documents.rentshield_identity import idswyft_client
from documents.rentshield_identity.models import IdentityVerification
from documents.rentshield_identity.models import IdentityVerificationAuditLog
from documents.rentshield_identity.models import IdentityVerificationCall

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


def _looks_like_a_name(value: str) -> bool:
    """Real bug found live: Idswyft's OCR occasionally returns
    implausible garbage for the name field specifically -- confirmed
    directly in its own logs, on real photographed documents, at HIGH
    reported confidence (0.87-0.95): "A", "ET", "E Y E", and "∞".
    Confidence alone can't be trusted to filter these out. A plausible
    human name has at least two actual letters; anything short of that
    is treated as "OCR couldn't read this" rather than a comparable
    value -- otherwise a confidently-wrong OCR read produces a false
    "name mismatch" alarm for the Notary, and (via
    _update_user_profile_from_ocr below) could silently overwrite the
    property owner's own account name with a single symbol."""
    return len(re.findall(r"[A-Za-z]", value)) >= 2


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


def _pairwise_mismatches(field_label: str, raw: dict[str, str], normalized: dict[str, str | None]) -> list[str]:
    """Every pair of non-empty sources that disagree, as one note each
    -- generalizes the old two-source (card OCR vs chip) check to three
    (declared vs card OCR vs chip) without three near-duplicate
    functions. Compares on `normalized` (so format differences like
    DD/MM/YYYY vs YYYY-MM-DD don't read as a mismatch) but displays the
    `raw` value -- a Notary needs to see what was actually typed/read,
    not a normalized stand-in for it."""
    notes = []
    present = [label for label, value in normalized.items() if value]
    for label_a, label_b in combinations(present, 2):
        if normalized[label_a] != normalized[label_b]:
            notes.append(f'{field_label} mismatch: {label_a} says "{raw[label_a]}", {label_b} says "{raw[label_b]}".')
    return notes


def _check_identity_mismatch(record: IdentityVerification) -> str:
    """Never a hard gate -- OCR/MRZ misreads happen on any side of these
    comparisons, and a typo is still possible even on the web's own
    declare-a-document step -- just something surfaced for the Notary
    reviewer (admin_views.py) to see and weigh alongside everything
    else. Three independent sources where available: what the user
    typed on the web before ever touching the app (declared_*), Idswyft's
    OCR of the photographed card (card_ocr_*), and the NFC chip's own
    signed data (chip_*) -- a disagreement between any two is real
    signal, not just OCR-vs-chip like before declared_* existed."""
    notes = []

    names = {
        "card photo OCR": record.card_ocr_full_name,
        "chip": record.chip_full_name,
    }
    normalized_names = {label: _normalize_name_tokens(value) if value else None for label, value in names.items()}
    for label_a, label_b in combinations([label for label, value in normalized_names.items() if value], 2):
        if normalized_names[label_a] != normalized_names[label_b]:
            notes.append(f'Name mismatch: {label_a} read "{names[label_a]}", {label_b} read "{names[label_b]}".')

    dobs = {
        "declared": record.declared_date_of_birth,
        "card photo OCR": record.card_ocr_date_of_birth,
        "chip": record.chip_date_of_birth,
    }
    notes += _pairwise_mismatches(
        "Date of birth", dobs, {label: _normalize_dob(value) if value else None for label, value in dobs.items()},
    )

    # The document number the chip unlocked itself with a key that's
    # NOT this number (see chip_document_number's own field comment) --
    # this only ever runs after a successful PACE/BAC handshake, so a
    # mismatch here means one of the three sources misread/mistyped the
    # printed number, not that the wrong document was scanned.
    doc_numbers = {
        "declared": record.declared_document_number,
        "card photo OCR": record.card_ocr_document_number,
        "chip": record.chip_document_number,
    }
    notes += _pairwise_mismatches(
        "Document number",
        doc_numbers,
        {label: value.strip().upper().replace(" ", "") if value else None for label, value in doc_numbers.items()},
    )

    return " ".join(notes)


def _run_chip_selfie_match(chip_photo_bytes: bytes, selfie_bytes: bytes) -> float | None:
    """Independent second face match (face_match.py), alongside
    Idswyft's own card-photo-vs-selfie match -- never a hard gate here
    either, same reasoning as _check_identity_mismatch(): a failed
    detection just means "couldn't compare", left for the Notary
    reviewer to see and weigh, not a verification failure."""
    try:
        return face_match.compare_faces(chip_photo_bytes, selfie_bytes)
    except face_match.NoFaceDetectedError:
        logger.warning("Chip-vs-selfie face match: no face detected in one of the images")
        return None
    except Exception:
        logger.exception("Chip-vs-selfie face match failed unexpectedly")
        return None


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

    latest_call = record.video_calls.first()
    return Response(
        {
            "status": record.status,
            "step": step,
            "notary_notes": record.notary_notes,
            "video_call": latest_call.to_dict() if latest_call else None,
        },
    )


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
        ocr_name = (ocr_data.get("name") or "").strip()
        record.card_ocr_full_name = ocr_name[:255] if _looks_like_a_name(ocr_name) else ""
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

    response_data = {"step": result.get("status"), "status": record.status}
    # Real gap, reported: the Android app treated any HTTP 200 here as
    # "proceed to NFC scan", even when the body said status="failed" --
    # by the time that surfaced, it looked like an unrelated failure
    # several steps later. Passing Idswyft's own rejection_detail through
    # lets the client show an explanation immediately instead of a bare
    # "failed" (e.g. "OCR confidence 0.23 is below minimum 0.6").
    if final_result == IdentityVerification.Status.FAILED and result.get("rejection_detail"):
        response_data["detail"] = result["rejection_detail"]
    return Response(response_data)


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
    update_fields = ["selfie_photo", "latitude", "longitude", "location_accuracy_m"]
    if record.chip_photo:
        record.chip_selfie_match_score = _run_chip_selfie_match(record.chip_photo.read(), file_bytes)
        update_fields.append("chip_selfie_match_score")
    record.save(update_fields=[*update_fields, "updated_at"])

    try:
        result = idswyft_client.upload_live_capture(
            record.verification_id, file_bytes, uploaded.name, content_type,
        )
    except Exception as exc:
        logger.exception("Live-capture upload failed for verification %s", record.verification_id)
        # Idswyft's own error text (e.g. "Verification was already
        # rejected in a previous step") is genuinely more actionable than
        # a generic "try again" -- real gap found live: a card photo that
        # already hard-rejected always throws exactly this when the
        # selfie is attempted anyway, which used to surface as an
        # unrelated-looking, unexplained selfie failure.
        return Response({"error": str(exc) or "Could not process that selfie -- try again."}, status=502)

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

    # Real gap found live (2026-09-14): unlike upload_front_document_view,
    # this never passed through Idswyft's own rejection_detail (e.g.
    # "Liveness score 0.31 -- anti-spoofing check failed" or "No face
    # detected... confidence: 0.42, threshold: 0.5") -- a rejected
    # selfie only ever showed a bare "Verification failed." with
    # nothing actionable, on both the web and the app.
    response_data = {"step": result.get("status"), "status": record.status}
    if final_result == IdentityVerification.Status.FAILED and result.get("rejection_detail"):
        response_data["detail"] = result["rejection_detail"]
    return Response(response_data)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def submit_chip_data_view(request):
    """POST /api/documents/identity/verify/chip-data/ -- the name/date
    of birth read directly off the NFC chip's DG1 (MRZ) by the native
    Android/iOS app, sent as multipart form data: `full_name`/
    `date_of_birth`/`document_number` as text fields (already extracted
    client-side by NfcChipReader.kt/PassportNFCService.swift), plus an
    optional `chip_photo` file -- the chip's own DG2 photo, used for an
    independent second face match against the selfie (face_match.py),
    separate from Idswyft's own card-photo-vs-selfie match. Text fields
    are cross-checked against Idswyft's own OCR of the photographed card
    (card_ocr_*, set by upload_front_document_view above) -- see
    _check_identity_mismatch()'s comment on why a disagreement is
    surfaced for the Notary reviewer rather than treated as a hard
    failure."""
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
    update_fields = ["chip_full_name", "chip_date_of_birth", "chip_document_number", "identity_mismatch_notes"]

    chip_photo = request.FILES.get("chip_photo")
    if chip_photo:
        file_bytes, content_type = idswyft_client.normalize_image_for_idswyft(chip_photo.read(), chip_photo.content_type)
        record.chip_photo.save(_filename_for_content_type(chip_photo.name, content_type), ContentFile(file_bytes), save=False)
        update_fields.append("chip_photo")

    record.save(update_fields=[*update_fields, "updated_at"])
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
    _log_verification_action(record, IdentityVerificationAuditLog.Action.SUBMITTED_FOR_REVIEW, actor=request.user)

    from documents.tasks import run_identity_prescreen_task

    run_identity_prescreen_task.delay(record.id)
    _notify_notary_queue(record)

    return Response({"status": record.status})


def _notify_notary_queue(record: IdentityVerification) -> None:
    """Fire-and-forget email to every real Notary Public (Group members
    plus staff, matching roles.is_notary_public()'s own definition of
    who that is) the moment a verification actually needs their
    attention -- requested explicitly so a Notary doesn't have to keep
    polling the dashboard to find out something is waiting. Sent
    individually to each recipient's own address (not one email with
    everyone in To:) so Notaries don't see each other's addresses.
    Same "log and swallow, never block the real action" pattern as
    _notify_identity_verification_result below."""
    User = get_user_model()
    recipients = (
        User.objects.filter(Q(is_staff=True) | Q(groups__name=NOTARY_PUBLIC_GROUP_NAME))
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
    if not recipients:
        logger.debug("Verification %s reached AWAITING_NOTARY_REVIEW but no Notary has an email on file.", record.id)
        return

    subject = "RentShield: A new identity verification needs your review"
    message = (
        f"{record.user.username} has finished the verification steps -- "
        "a Notary Public needs to watch their confirmation video and "
        "decide.\n\n"
        "Open the Identity Verification Admin page to review it."
    )
    for recipient in recipients:
        try:
            send_mail(subject=subject, message=message, from_email=None, recipient_list=[recipient], fail_silently=False)
        except Exception:
            logger.exception("Failed to send Notary queue notification email to %r", recipient)


# Which additional-document type is disallowed for a given primary
# declared_document_type -- the additional document must never be the
# same kind as the primary one (requested explicitly: "the second one
# must not be the passport" when the primary already is one). CIE's
# analog is "national_id": a CIE is functionally a national ID card, so
# submitting "National ID Card" as the additional document alongside a
# CIE primary would be the same redundancy in different words.
_DISALLOWED_ADDITIONAL_FOR_PRIMARY = {
    "passport": IdentityVerification.AdditionalIdType.SECOND_PASSPORT,
    "cie": IdentityVerification.AdditionalIdType.NATIONAL_ID,
}


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def upload_additional_id_view(request):
    """POST /api/documents/identity/verify/additional-id/ -- a second,
    independent ID document (driving licence, national ID, ...) as a
    MANDATORY pipeline step (2026-09-13, superseding the earlier
    optional web upload) -- front AND back, never the same document
    type as the primary. App-only: enforced here by requiring the NFC
    chip read to have already succeeded (chip_full_name is only ever
    set by submit_chip_data_view), the exact point in the pipeline this
    step now belongs right after -- there is no way to reach this from
    the web any more, since the web has no NFC step to sequence
    after."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"error": "Start identity verification first."}, status=400)

    if not record.chip_full_name:
        return Response({"error": "Tap your primary document for the NFC read first."}, status=400)

    id_type = (request.data.get("id_type") or "").strip()
    valid_types = dict(IdentityVerification.AdditionalIdType.choices)
    if id_type not in valid_types:
        return Response({"error": "Choose a valid document type."}, status=400)
    if id_type == _DISALLOWED_ADDITIONAL_FOR_PRIMARY.get(record.declared_document_type):
        return Response({"error": "Your additional document can't be the same type as your primary document."}, status=400)

    front = request.FILES.get("photo_front")
    back = request.FILES.get("photo_back")
    if not front or not back:
        return Response({"error": "Photos of both the front and back of the document are required."}, status=400)

    front_bytes, front_content_type = idswyft_client.normalize_image_for_idswyft(front.read(), front.content_type)
    back_bytes, back_content_type = idswyft_client.normalize_image_for_idswyft(back.read(), back.content_type)
    record.additional_id_photo_front.save(
        _filename_for_content_type(front.name, front_content_type), ContentFile(front_bytes), save=False,
    )
    record.additional_id_photo_back.save(
        _filename_for_content_type(back.name, back_content_type), ContentFile(back_bytes), save=False,
    )
    record.additional_id_type = id_type
    record.save(
        update_fields=["additional_id_photo_front", "additional_id_photo_back", "additional_id_type", "updated_at"],
    )
    return Response({"status": "ok"})


# The only fields a Notary can correct on the review page -- the OCR/
# chip text RentShield itself already populated, never `status` or any
# photo/video (those come from the pipeline, not a reviewer's own
# input). Posted as `edit_<field>` so they can't collide with `notes`.
_NOTARY_EDITABLE_FIELDS = (
    "card_ocr_full_name", "card_ocr_date_of_birth", "card_ocr_document_number",
    "chip_full_name", "chip_date_of_birth", "chip_document_number",
)


def _log_verification_action(record: IdentityVerification, action: str, actor, notes: str = "") -> None:
    """Writes one IdentityVerificationAuditLog row -- see that model's
    own docstring for why it's a denormalized snapshot (plain
    verification_id + copied username) rather than a real FK to the
    verification: it has to survive admin_delete_verification_view
    deleting the row it's about. Called with the record still very much
    alive in every case (including right before it's deleted), so
    record.user.username is always safe to read here."""
    IdentityVerificationAuditLog.objects.create(
        verification_id=record.id,
        username=record.user.username,
        action=action,
        actor=actor,
        notes=notes[:2000],
    )


def _apply_notary_edits(record: IdentityVerification, data) -> list[str]:
    """Lets the Notary fix an OCR/chip misread right on the review page
    before deciding, instead of confirming/rejecting a record she can
    see is wrong with no way to correct it. Recomputes
    identity_mismatch_notes afterward since an edit can resolve (or
    introduce) a mismatch."""
    changed = []
    for field in _NOTARY_EDITABLE_FIELDS:
        key = f"edit_{field}"
        if key not in data:
            continue
        max_length = record._meta.get_field(field).max_length
        setattr(record, field, (data.get(key) or "").strip()[:max_length])
        changed.append(field)
    if changed:
        record.identity_mismatch_notes = _check_identity_mismatch(record)
        changed.append("identity_mismatch_notes")
    return changed


def _notify_identity_verification_result(record: IdentityVerification) -> None:
    """Fire-and-forget email to the property owner once the Notary
    Public reaches a final decision -- same "log and swallow, never
    block the real action" pattern as
    documents.rentshield.service._notify_notice_served. Deliberately
    silent no-op when the account has no email on file."""
    recipient = record.user.email
    if not recipient:
        logger.debug(
            "Verification %s reached a final decision but user %s has no "
            "email on file -- skipping notification.",
            record.id, record.user_id,
        )
        return

    if record.status == IdentityVerification.Status.VERIFIED:
        subject = "RentShield: Your identity has been verified"
        message = (
            "Good news -- a Notary Public has reviewed your identity "
            "verification and confirmed it. Your account is now marked "
            "as verified.\n\n"
        )
    elif record.status == IdentityVerification.Status.NEEDS_MORE_INFO:
        subject = "RentShield: Your identity verification needs another look"
        message = (
            "A Notary Public reviewed your identity verification and needs "
            "a bit more from you before it can be approved -- nothing you've "
            "already submitted has been deleted. Open RentShield and "
            "continue your verification to address this.\n\n"
        )
    else:
        subject = "RentShield: Your identity verification was not approved"
        message = (
            "A Notary Public has reviewed your identity verification and "
            "could not approve it. You can start a new verification from "
            "your account and try again.\n\n"
        )
    if record.notary_notes:
        message += f"Notes from the reviewer: {record.notary_notes}\n"

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,  # falls back to settings.DEFAULT_FROM_EMAIL
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send identity verification result email to %r", recipient)


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
    record = _get_reviewable_record_or_error(verification_id, request.user)
    if isinstance(record, Response):
        return record
    edited_fields = _apply_notary_edits(record, request.data)
    record.status = IdentityVerification.Status.VERIFIED
    record.notary_reviewed_by = request.user
    record.notary_reviewed_at = timezone.now()
    record.notary_notes = (request.data.get("notes") or "")[:2000]
    # A decision has been made -- whatever claim was on this record is
    # now stale (nothing left here for the claim to protect). Leaving
    # it would show a confusing "Claimed by X" on an already-verified/
    # failed record indefinitely.
    record.claimed_by = None
    record.claimed_at = None
    record.save(
        update_fields=[
            *edited_fields, "status", "notary_reviewed_by", "notary_reviewed_at", "notary_notes",
            "claimed_by", "claimed_at", "updated_at",
        ],
    )
    _log_verification_action(record, IdentityVerificationAuditLog.Action.CONFIRMED, actor=request.user, notes=record.notary_notes)
    _notify_identity_verification_result(record)
    return Response({"status": record.status})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def notary_reject_view(request, verification_id):
    """POST /api/documents/identity/verify/notary/<id>/reject/ -- the
    Notary Public reviewer rejects the video (doesn't match, low
    quality, wrong person, ...). `notes` should say why -- shown back to
    whoever looks at this record afterward, there's no other record of
    the reviewer's reasoning."""
    record = _get_reviewable_record_or_error(verification_id, request.user)
    if isinstance(record, Response):
        return record
    edited_fields = _apply_notary_edits(record, request.data)
    record.status = IdentityVerification.Status.FAILED
    record.notary_reviewed_by = request.user
    record.notary_reviewed_at = timezone.now()
    record.notary_notes = (request.data.get("notes") or "")[:2000]
    # A decision has been made -- whatever claim was on this record is
    # now stale (nothing left here for the claim to protect). Leaving
    # it would show a confusing "Claimed by X" on an already-verified/
    # failed record indefinitely.
    record.claimed_by = None
    record.claimed_at = None
    record.save(
        update_fields=[
            *edited_fields, "status", "notary_reviewed_by", "notary_reviewed_at", "notary_notes",
            "claimed_by", "claimed_at", "updated_at",
        ],
    )
    _log_verification_action(record, IdentityVerificationAuditLog.Action.REJECTED, actor=request.user, notes=record.notary_notes)
    _notify_identity_verification_result(record)
    return Response({"status": record.status})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def notary_request_more_info_view(request, verification_id):
    """POST /api/documents/identity/verify/notary/<id>/request-more-info/
    -- a third outcome alongside confirm/reject: the video/photos are
    mostly fine but something specific needs redoing (blurry video,
    wrong document photographed, a chip read that didn't take, ...).
    Unlike notary_reject_view this is NOT a final decision -- it sends
    the record back to PENDING so the user's own app picks the pipeline
    back up (same non-destructive resume path start_verification_view
    already gives a FAILED record), and unlike
    admin_reset_verification_view it deletes nothing: whatever was
    already good stays on the record for the next reviewer to see.
    `notes` is required here (optional on confirm/reject) -- without it
    the user has no idea what to actually redo."""
    record = _get_reviewable_record_or_error(verification_id, request.user)
    if isinstance(record, Response):
        return record
    notes = (request.data.get("notes") or "").strip()
    if not notes:
        return Response({"error": "Say what the user needs to redo -- notes are required for this."}, status=400)
    edited_fields = _apply_notary_edits(record, request.data)
    record.status = IdentityVerification.Status.NEEDS_MORE_INFO
    record.notary_reviewed_by = request.user
    record.notary_reviewed_at = timezone.now()
    record.notary_notes = notes[:2000]
    # See notary_confirm_view's own comment: a fresh resubmission
    # deserves a fresh claim state, not the previous round's stale one.
    record.claimed_by = None
    record.claimed_at = None
    record.save(
        update_fields=[
            *edited_fields, "status", "notary_reviewed_by", "notary_reviewed_at", "notary_notes",
            "claimed_by", "claimed_at", "updated_at",
        ],
    )
    _log_verification_action(record, IdentityVerificationAuditLog.Action.REQUESTED_MORE_INFO, actor=request.user, notes=notes)
    _notify_identity_verification_result(record)
    return Response({"status": record.status})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def claim_verification_view(request, verification_id):
    """POST /api/documents/identity/verify/notary/<id>/claim/ -- an
    advisory lock (IdentityVerification.claim_conflict) a Notary takes
    before working on a record, so a second Notary triaging the same
    queue sees it's already being handled instead of confirming/
    rejecting the same record moments later with no warning. Refuses to
    steal a live claim from someone else; claiming your own
    already-claimed record just refreshes claimed_at (harmless, and
    saves the frontend from having to know the difference)."""
    try:
        record = IdentityVerification.objects.select_related("claimed_by").get(pk=verification_id)
    except (IdentityVerification.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such verification."}, status=404)
    conflict = _claim_conflict_response(record, request.user)
    if conflict:
        return conflict
    record.claimed_by = request.user
    record.claimed_at = timezone.now()
    record.save(update_fields=["claimed_by", "claimed_at", "updated_at"])
    return Response({"claimed_by": request.user.username, "claimed_at": record.claimed_at})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def release_verification_view(request, verification_id):
    """POST /api/documents/identity/verify/notary/<id>/release/ --
    voluntarily gives up a claim (done reviewing, or claimed it by
    mistake). Silently a no-op on someone else's claim or no claim at
    all -- releasing is never itself a conflict worth surfacing as an
    error."""
    try:
        record = IdentityVerification.objects.get(pk=verification_id)
    except (IdentityVerification.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such verification."}, status=404)
    if record.claimed_by_id == request.user.id:
        record.claimed_by = None
        record.claimed_at = None
        record.save(update_fields=["claimed_by", "claimed_at", "updated_at"])
    return Response({"claimed_by": None})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def schedule_video_call_view(request, verification_id):
    """POST /api/documents/identity/verify/notary/<id>/schedule-call/
    {scheduled_at} -- proposes a live video call (see
    IdentityVerificationCall's own docstring for why this exists
    alongside the async pipeline). Same reviewable gate as confirm/
    reject/request-more-info: only meaningful once there's actually
    something to talk through. Creates the row PROPOSED, not
    CONFIRMED -- the user still has to agree to the time
    (confirm_video_call_view) or ask for another one
    (request_video_call_reschedule_view)."""
    record = _get_reviewable_record_or_error(verification_id, request.user)
    if isinstance(record, Response):
        return record
    raw = request.data.get("scheduled_at")
    if not raw:
        return Response({"error": "A date/time is required."}, status=400)
    try:
        scheduled_at = dateutil_parser.parse(raw)
    except (ValueError, OverflowError):
        return Response({"error": "Could not understand that date/time."}, status=400)
    if timezone.is_naive(scheduled_at):
        scheduled_at = timezone.make_aware(scheduled_at)
    if scheduled_at <= timezone.now():
        return Response({"error": "Pick a time in the future."}, status=400)

    # Real bug caught in testing: without this, a Notary proposing a
    # new time left the OLD row still PROPOSED/CONFIRMED, so two "active"
    # calls could exist for the same record at once -- and since
    # to_dict() consumers just take the most-recently-scheduled one,
    # whichever had the LATER scheduled_at would win even if it was the
    # stale one. Proposing again always supersedes whatever was pending.
    record.video_calls.filter(
        status__in=[
            IdentityVerificationCall.Status.PROPOSED,
            IdentityVerificationCall.Status.CONFIRMED,
            IdentityVerificationCall.Status.RESCHEDULE_REQUESTED,
        ],
    ).update(status=IdentityVerificationCall.Status.CANCELLED)

    call = IdentityVerificationCall.objects.create(
        identity_verification=record,
        scheduled_at=scheduled_at,
        proposed_by=request.user,
    )
    _log_verification_action(
        record, IdentityVerificationAuditLog.Action.CALL_SCHEDULED, actor=request.user,
        notes=f"Proposed for {scheduled_at:%Y-%m-%d %H:%M %Z}",
    )
    _notify_video_call_proposed(call)
    return Response({"call": call.to_dict()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def confirm_video_call_view(request, call_id):
    """POST /api/documents/identity/verify/call/<call_id>/confirm/ --
    the property owner agrees to the proposed time. Only the user the
    call is actually about can confirm it -- there's no other access
    control on this row otherwise (unlike the Notary-only endpoints
    above, this one's identity check is "is this your own
    verification", not a role)."""
    call = _get_own_call_or_error(request.user, call_id)
    if isinstance(call, Response):
        return call
    if call.status != IdentityVerificationCall.Status.PROPOSED:
        return Response({"error": f"This call isn't waiting on your confirmation (status: {call.status})."}, status=400)
    call.status = IdentityVerificationCall.Status.CONFIRMED
    call.save(update_fields=["status", "updated_at"])
    _log_verification_action(call.identity_verification, IdentityVerificationAuditLog.Action.CALL_CONFIRMED, actor=request.user)
    _notify_video_call_confirmed(call)
    return Response({"call": call.to_dict()})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def request_video_call_reschedule_view(request, call_id):
    """POST /api/documents/identity/verify/call/<call_id>/request-reschedule/
    {reason} -- the proposed time doesn't work for the user. Doesn't
    let them pick a new time themselves (that's still the Notary's
    call to propose, via schedule_video_call_view again once they've
    seen why) -- just flags it back to the queue, same "notify, don't
    self-serve" pattern as the rest of this review relationship."""
    call = _get_own_call_or_error(request.user, call_id)
    if isinstance(call, Response):
        return call
    if call.status not in (IdentityVerificationCall.Status.PROPOSED, IdentityVerificationCall.Status.CONFIRMED):
        return Response({"error": f"This call can't be rescheduled anymore (status: {call.status})."}, status=400)
    call.status = IdentityVerificationCall.Status.RESCHEDULE_REQUESTED
    reason = (request.data.get("reason") or "").strip()[:2000]
    call.save(update_fields=["status", "updated_at"])
    _log_verification_action(
        call.identity_verification, IdentityVerificationAuditLog.Action.CALL_RESCHEDULE_REQUESTED,
        actor=request.user, notes=reason,
    )
    _notify_video_call_reschedule_requested(call, reason)
    return Response({"call": call.to_dict()})


@api_view(["POST"])
@permission_classes([IsNotaryPublic])
def complete_video_call_view(request, verification_id, call_id):
    """POST /api/documents/identity/verify/notary/<id>/calls/<call_id>/complete/
    {notes, no_show} -- the Notary's own record of what happened on the
    call, independent of Confirm/Reject/Send-back-for-more-info on the
    verification itself: the call is evidence feeding that eventual
    decision, not a decision in its own right."""
    try:
        call = IdentityVerificationCall.objects.select_related("identity_verification__user").get(
            pk=call_id, identity_verification_id=verification_id,
        )
    except (IdentityVerificationCall.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such call."}, status=404)
    no_show = bool(request.data.get("no_show"))
    call.status = IdentityVerificationCall.Status.NO_SHOW if no_show else IdentityVerificationCall.Status.COMPLETED
    call.notary_call_notes = (request.data.get("notes") or "")[:2000]
    call.save(update_fields=["status", "notary_call_notes", "updated_at"])
    _log_verification_action(
        call.identity_verification,
        IdentityVerificationAuditLog.Action.CALL_NO_SHOW if no_show else IdentityVerificationAuditLog.Action.CALL_COMPLETED,
        actor=request.user, notes=call.notary_call_notes,
    )
    return Response({"call": call.to_dict()})


def _get_own_call_or_error(user, call_id):
    try:
        call = IdentityVerificationCall.objects.select_related("identity_verification").get(pk=call_id)
    except (IdentityVerificationCall.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such call."}, status=404)
    if call.identity_verification.user_id != user.id:
        return Response({"error": "Not your verification."}, status=403)
    return call


def _notify_video_call_proposed(call: IdentityVerificationCall) -> None:
    """Fire-and-forget email to the property owner the moment a Notary
    proposes a time -- same silent-no-op-without-an-email pattern as
    _notify_identity_verification_result."""
    recipient = call.identity_verification.user.email
    if not recipient:
        return
    try:
        send_mail(
            subject="RentShield: A Notary Public proposed a video call",
            message=(
                f"A Notary Public would like a short video call with you on "
                f"{call.scheduled_at:%Y-%m-%d %H:%M %Z} to verify your identity in "
                "person. Open RentShield to confirm this time or ask for another "
                "one.\n"
            ),
            from_email=None,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send video call proposal email for call %s", call.id)


def _notify_video_call_confirmed(call: IdentityVerificationCall) -> None:
    """Fire-and-forget email to the Notary who proposed it -- confirms
    the property owner has actually agreed to the time."""
    recipient = call.proposed_by.email if call.proposed_by else ""
    if not recipient:
        return
    try:
        send_mail(
            subject="RentShield: Your proposed video call was confirmed",
            message=(
                f"{call.identity_verification.user.username} confirmed the video "
                f"call for {call.scheduled_at:%Y-%m-%d %H:%M %Z}. It'll show up in "
                "your review queue with a Join button once it's close to that "
                "time.\n"
            ),
            from_email=None,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Failed to send video call confirmation email for call %s", call.id)


def _notify_video_call_reschedule_requested(call: IdentityVerificationCall, reason: str) -> None:
    """Fire-and-forget email to every Notary/staff (same recipient list
    as _notify_notary_queue) -- the proposed time doesn't work, someone
    needs to propose a new one."""
    User = get_user_model()
    recipients = (
        User.objects.filter(Q(is_staff=True) | Q(groups__name=NOTARY_PUBLIC_GROUP_NAME))
        .exclude(email="")
        .values_list("email", flat=True)
        .distinct()
    )
    if not recipients:
        return
    subject = "RentShield: A property owner asked to reschedule their video call"
    message = (
        f"{call.identity_verification.user.username} can't make the video call "
        f"proposed for {call.scheduled_at:%Y-%m-%d %H:%M %Z} -- propose a new time "
        "from the Identity Verification Admin page.\n"
    )
    if reason:
        message += f"\nTheir reason: {reason}\n"
    for recipient in recipients:
        try:
            send_mail(subject=subject, message=message, from_email=None, recipient_list=[recipient], fail_silently=False)
        except Exception:
            logger.exception("Failed to send reschedule-request email to %r", recipient)


def _get_reviewable_record_or_error(verification_id, user):
    """Real bug caught in testing: without this check, a Notary could
    "confirm" or "reject" a record that never even reached the video
    step (e.g. one the automated pipeline had already hard-failed),
    silently overwriting a legitimate outcome. Reviewing is only
    meaningful once there's actually a video to watch.

    Also refuses when someone else holds a live claim on this record
    (2026-09-14, IdentityVerification.claim_conflict) -- claiming is
    optional, but if a Notary DID claim it, a different Notary deciding
    here is exactly the double-action race claiming exists to prevent."""
    try:
        record = IdentityVerification.objects.select_related("claimed_by").get(pk=verification_id)
    except (IdentityVerification.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such verification."}, status=404)
    if record.status != IdentityVerification.Status.AWAITING_NOTARY_REVIEW:
        return Response(
            {"error": f"This verification isn't awaiting review (current status: {record.status})."},
            status=400,
        )
    conflict = _claim_conflict_response(record, user)
    if conflict:
        return conflict
    return record


def _claim_conflict_response(record: IdentityVerification, user) -> Response | None:
    """Shared by every mutating action a Notary/Admin can take on a
    record -- see IdentityVerification.claim_conflict for what counts
    as a live conflicting claim."""
    if record.claim_conflict(user):
        return Response(
            {"error": f"Currently claimed by {record.claimed_by.username} -- ask them to release it, or wait for the claim to expire."},
            status=409,
        )
    return None


def _delete_verification_evidence_files(record: IdentityVerification) -> None:
    """Every FileField on IdentityVerification itself (not its video
    calls' recordings -- see admin_delete_verification_view for those).
    Shared by _reset_verification (keeps the row) and
    admin_delete_verification_view (removes it entirely): Django never
    deletes a FileField's actual file from storage on its own, whether
    the row is updated or deleted outright, so both paths need this."""
    for field in (
        record.passport_photo, record.selfie_photo, record.chip_photo, record.video,
        record.additional_id_photo_front, record.additional_id_photo_back,
    ):
        if field:
            field.delete(save=False)


def _reset_verification(record: IdentityVerification) -> None:
    """Wipes a verification back to a clean slate so the user can redo
    the whole pipeline from scratch -- every uploaded file, every OCR/
    chip/declared field, the mismatch notes, the AI summary, and any
    Notary review decision. Keeps the row itself, unlike
    admin_delete_verification_view below -- this is for a real user
    whose evidence needs redoing, that one is for a record that
    shouldn't exist in the list at all. Also clears any pending/claimed
    DevicePairingCode rows for the same user -- a stale one would
    otherwise let a resumed session skip straight past the fresh QR
    this reset is meant to force."""
    from documents.rentshield_identity.models import DevicePairingCode

    _delete_verification_evidence_files(record)

    record.verification_id = ""
    record.hosted_url = ""
    record.status = IdentityVerification.Status.PENDING
    record.latitude = None
    record.longitude = None
    record.location_accuracy_m = None
    record.declared_document_type = ""
    record.declared_document_number = ""
    record.declared_date_of_birth = ""
    record.declared_expiry_date = ""
    record.declared_can = ""
    record.card_ocr_full_name = ""
    record.card_ocr_date_of_birth = ""
    record.card_ocr_document_number = ""
    record.chip_full_name = ""
    record.chip_date_of_birth = ""
    record.chip_document_number = ""
    record.chip_selfie_match_score = None
    record.identity_mismatch_notes = ""
    record.automated_result = ""
    record.notary_reviewed_by = None
    record.notary_reviewed_at = None
    record.notary_notes = ""
    record.ai_prescreen_summary = ""
    record.additional_id_type = ""
    record.claimed_by = None
    record.claimed_at = None
    record.save()

    DevicePairingCode.objects.filter(user=record.user).delete()


@api_view(["POST"])
@permission_classes([IsRentshieldAdmin | IsNotaryPublic])
def admin_reset_verification_view(request, verification_id):
    """POST /api/documents/identity/verify/admin/<id>/reset/ -- wipes a
    user's whole identity verification back to a clean slate (every
    uploaded photo/video, every OCR/chip/declared field) and lets them
    start over -- for a case genuinely too broken to send back with
    notary_request_more_info_view (wrong account entirely, corrupted
    upload, testing, ...). Opened up to Notary Public as well as Admin
    (2026-09-14, explicitly requested) -- previously admin-only on the
    theory that deleting evidence was a heavier action than review, but
    a Notary triaging the queue is exactly who runs into a record worth
    throwing away, and gating it behind a separate admin request added
    friction without adding safety (the frontend already confirms this
    destructive action before calling it)."""
    try:
        record = IdentityVerification.objects.select_related("claimed_by", "user").get(pk=verification_id)
    except (IdentityVerification.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such verification."}, status=404)
    conflict = _claim_conflict_response(record, request.user)
    if conflict:
        return conflict
    _log_verification_action(record, IdentityVerificationAuditLog.Action.RESET, actor=request.user)
    _reset_verification(record)
    return Response({"status": record.status})


@api_view(["POST"])
@permission_classes([IsRentshieldAdmin | IsNotaryPublic])
def admin_delete_verification_view(request, verification_id):
    """POST /api/documents/identity/verify/admin/<id>/delete/ --
    permanently removes the whole IdentityVerification row, not just its
    evidence (see admin_reset_verification_view above for the "keep the
    row, let them redo it" version). No status gate -- pending,
    awaiting review, verified, failed, needs-more-info, any of them can
    be deleted; this is for getting a record out of the list entirely
    (a spam signup, a duplicate/wrong account, test data), not for
    correcting a real one still in progress. Available to Admin or
    Notary Public, same reasoning as reset above. IdentityVerificationCall
    rows cascade-delete with the parent (on_delete=CASCADE), but their
    recording files still need explicit cleanup first -- a cascade
    delete touches the database, never file storage."""
    try:
        record = IdentityVerification.objects.select_related("user", "claimed_by").prefetch_related("video_calls").get(
            pk=verification_id,
        )
    except (IdentityVerification.DoesNotExist, ValueError, TypeError):
        return Response({"error": "No such verification."}, status=404)
    conflict = _claim_conflict_response(record, request.user)
    if conflict:
        return conflict

    from documents.rentshield_identity.models import DevicePairingCode

    # Logged before the row itself is destroyed -- this and every prior
    # entry for the same verification_id are the only record it ever
    # existed once record.delete() below runs (see
    # IdentityVerificationAuditLog's own docstring on why it isn't a
    # real FK to the row it's about).
    _log_verification_action(record, IdentityVerificationAuditLog.Action.DELETED, actor=request.user)
    _delete_verification_evidence_files(record)
    for call in record.video_calls.all():
        if call.recording_file:
            call.recording_file.delete(save=False)
    DevicePairingCode.objects.filter(user=record.user).delete()
    record.delete()
    return Response({"deleted": True})


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
