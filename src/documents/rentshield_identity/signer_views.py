# Public, token-gated views for a notice's SIGNER (landlord) to prove
# their identity before documents.rentshield.esign.orchestrator ever
# emails them an actual DocuSeal/OpenSign signing link -- see
# NoticeSignerVerification's own docstring in models.py and
# documents.rentshield.service.request_notarization()/
# _send_signer_verification_email() for how a row here gets created and
# emailed in the first place. The signer has no RentShield account, so
# every view here is AllowAny and authenticates purely via the signed
# token in the URL (django.core.signing, same salted-token shape as
# rentshield_views.py's invite-accept link) -- there is no session to
# check permissions against.
from __future__ import annotations

import logging

from django.core.files.base import ContentFile
from django.core.signing import BadSignature
from django.core.signing import SignatureExpired
from django.core.signing import loads
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.decorators import parser_classes
from rest_framework.decorators import permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from documents.rentshield_identity import idswyft_client
from documents.rentshield_identity.models import NoticeSignerVerification
from documents.rentshield_identity.views import _filename_for_content_type

logger = logging.getLogger("paperless.rentshield")


def _load_verification(token: str):
    """Decodes a capture-link token back into its NoticeSignerVerification
    row, or (None, an error Response) if it's malformed/expired."""
    from documents.rentshield.service import SIGNER_TOKEN_MAX_AGE_SECONDS
    from documents.rentshield.service import SIGNER_TOKEN_SALT

    try:
        payload = loads(token, salt=SIGNER_TOKEN_SALT, max_age=SIGNER_TOKEN_MAX_AGE_SECONDS)
    except SignatureExpired:
        return None, Response({"error": "This verification link has expired."}, status=400)
    except BadSignature:
        return None, Response({"error": "Invalid verification link."}, status=400)

    verification = get_object_or_404(NoticeSignerVerification, id=payload["verification_id"])
    return verification, None


def _names_roughly_match(a: str, b: str) -> bool:
    """Loose, not exact -- OCR'd vs. typed spelling of the same name
    routinely differs (middle names, diacritics, word order). Every word
    in the shorter name has to appear in the longer one; catches
    "different person entirely" without false-flagging e.g. "Mohammed Al
    Futtaim" vs. "Mohammed A. Al Futtaim"."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return True  # nothing to compare against isn't evidence of a mismatch
    shorter, longer = (words_a, words_b) if len(words_a) <= len(words_b) else (words_b, words_a)
    return shorter.issubset(longer)


def notice_signer_verify_page_view(request):
    """GET /sign-verify/?token=... -- the actual page a signer lands on
    from _send_signer_verification_email()'s link. A plain Django
    template (documents/templates/rentshield/signer_verify.html), NOT an
    Angular route: Angular's entire index.html is served behind
    login_required (see paperless/urls.py's catch-all comment), and this
    signer has no RentShield account to log in with -- same reasoning as
    every other public page in this codebase (landing_view, the /login/
    signup wizard, rentshield_invite_accept_view), registered the same
    way, before that catch-all. The page's own JS
    (static/rentshield/signer-verify.js) drives the token-gated JSON
    views below via plain fetch()."""
    token = request.GET.get("token", "")
    verification, error = _load_verification(token)
    if error is not None:
        return render(request, "rentshield/signer_verify.html", {"error": error.data["error"]})
    return render(
        request,
        "rentshield/signer_verify.html",
        {"token": token, "signer_name": verification.signer_name},
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def signer_status_view(request, token):
    """GET /api/documents/notice-signer/<token>/status/ -- polled by the
    signer capture page, same shape as identity/verify/status/'s
    verification_status_view (no Notary-review branch here -- see
    NoticeSignerVerification's docstring for why there isn't one)."""
    verification, error = _load_verification(token)
    if error:
        return error

    step = None
    if (
        verification.status == NoticeSignerVerification.Status.PENDING
        and verification.verification_id
        and idswyft_client.is_configured()
    ):
        try:
            live = idswyft_client.get_verification_status(verification.verification_id)
        except Exception:
            logger.exception("Failed to poll Idswyft status for signer verification %s", verification.id)
        else:
            step = live["step"]
            if live["final_result"] is not None and live["final_result"] != verification.status:
                verification.status = live["final_result"]
                verification.save(update_fields=["status", "updated_at"])

    return Response(
        {
            "status": verification.status,
            "step": step,
            "signer_name": verification.signer_name,
            "name_mismatch": verification.name_mismatch,
        },
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def signer_start_view(request, token):
    """POST /api/documents/notice-signer/<token>/start/ -- same shape as
    identity/verify/start/'s start_verification_view."""
    verification, error = _load_verification(token)
    if error:
        return error

    if verification.status == NoticeSignerVerification.Status.VERIFIED:
        return Response({"status": verification.status})

    if not idswyft_client.is_configured():
        return Response(
            {"error": "Identity verification is not configured in this environment."},
            status=503,
        )

    try:
        session = idswyft_client.create_verification_session_for_signer(verification.id)
    except Exception:
        logger.exception("Failed to start Idswyft session for signer verification %s", verification.id)
        return Response({"error": "Could not start identity verification -- try again shortly."}, status=502)

    verification.verification_id = session["verification_id"]
    verification.status = NoticeSignerVerification.Status.PENDING
    verification.save(update_fields=["verification_id", "status", "updated_at"])
    return Response({"status": verification.status, "step": "AWAITING_FRONT"})


@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser])
def signer_upload_front_view(request, token):
    """POST /api/documents/notice-signer/<token>/front-document/ -- same
    shape as identity/verify/front-document/'s upload_front_document_view."""
    verification, error = _load_verification(token)
    if error:
        return error
    if not verification.verification_id:
        return Response({"error": "No verification in progress -- start one first."}, status=400)

    uploaded = request.FILES.get("document")
    if not uploaded:
        return Response({"error": "A photo of your ID is required."}, status=400)

    file_bytes, content_type = idswyft_client.normalize_image_for_idswyft(uploaded.read(), uploaded.content_type)
    verification.passport_photo.save(
        _filename_for_content_type(uploaded.name, content_type), ContentFile(file_bytes), save=False,
    )

    try:
        result = idswyft_client.upload_front_document(
            verification.verification_id, file_bytes, uploaded.name, content_type,
        )
    except Exception:
        logger.exception("Front-document upload failed for signer verification %s", verification.id)
        verification.save(update_fields=["passport_photo", "updated_at"])
        return Response({"error": "Could not process that photo -- try again."}, status=502)

    final_result = result.get("final_result")
    if final_result == NoticeSignerVerification.Status.FAILED:
        verification.status = final_result
    elif verification.status == NoticeSignerVerification.Status.FAILED:
        verification.status = NoticeSignerVerification.Status.PENDING

    ocr_data = result.get("ocr_data") or {}
    ocr_name = (ocr_data.get("name") or "").strip()
    if ocr_name:
        verification.ocr_full_name = ocr_name[:255]
        verification.name_mismatch = not _names_roughly_match(ocr_name, verification.signer_name)

    verification.save(update_fields=["passport_photo", "status", "ocr_full_name", "name_mismatch", "updated_at"])

    response_data = {"step": result.get("status"), "status": verification.status}
    if final_result == NoticeSignerVerification.Status.FAILED and result.get("rejection_detail"):
        response_data["detail"] = result["rejection_detail"]
    return Response(response_data)


@api_view(["POST"])
@permission_classes([AllowAny])
@parser_classes([MultiPartParser])
def signer_upload_selfie_view(request, token):
    """POST /api/documents/notice-signer/<token>/live-capture/ -- same
    shape as identity/verify/live-capture/'s upload_live_capture_view.
    The one place that actually clears a signer to be routed to real
    DocuSeal/OpenSign signing: on a VERIFIED result (and no name
    mismatch against what this notice names as its signer), it queues
    fire_signing_after_verification_task rather than calling the
    provider inline, matching every other e-sign dispatch in this
    codebase (documents.tasks.run_notarization_task)."""
    verification, error = _load_verification(token)
    if error:
        return error
    if not verification.verification_id:
        return Response({"error": "No verification in progress -- start one first."}, status=400)

    uploaded = request.FILES.get("selfie")
    if not uploaded:
        return Response({"error": "A selfie is required."}, status=400)

    file_bytes, content_type = idswyft_client.normalize_image_for_idswyft(uploaded.read(), uploaded.content_type)
    verification.selfie_photo.save(
        _filename_for_content_type(uploaded.name, content_type), ContentFile(file_bytes), save=False,
    )

    try:
        result = idswyft_client.upload_live_capture(
            verification.verification_id, file_bytes, uploaded.name, content_type,
        )
    except Exception:
        logger.exception("Live-capture upload failed for signer verification %s", verification.id)
        verification.save(update_fields=["selfie_photo", "updated_at"])
        return Response({"error": "Could not process that photo -- try again."}, status=502)

    final_result = result.get("final_result")
    if final_result:
        verification.status = final_result
    if verification.status == NoticeSignerVerification.Status.VERIFIED and verification.name_mismatch:
        # Idswyft's own face-match passed, but the OCR'd document name
        # doesn't match this notice's declared signer -- real signal a
        # human should weigh, downgraded so request_notarization() never
        # treats it as cleared to sign.
        verification.status = NoticeSignerVerification.Status.MANUAL_REVIEW
    verification.save(update_fields=["selfie_photo", "status", "updated_at"])

    if verification.status == NoticeSignerVerification.Status.VERIFIED:
        from documents.tasks import fire_signing_after_verification_task

        fire_signing_after_verification_task.delay(verification.document_id)

    response_data = {"step": result.get("status"), "status": verification.status}
    if result.get("rejection_detail"):
        response_data["detail"] = result["rejection_detail"]
    return Response(response_data)
