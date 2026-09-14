# Review page for property-owner identity verifications -- every user
# who has gone through the flow, their submitted passport photo and
# selfie side by side (the "mapping" between them is simply that they
# belong to the same IdentityVerification row -- one user, one document
# pair, one result), the OCR/chip cross-check, the confirmation video,
# and where it was performed. A separate module from views.py (which the
# property owner's own browser calls) since this is a distinct audience.
#
# Viewable by RentShield Admin (is_staff) OR the Notary Public group --
# whichever of the two, a viewer sees the same full record: a Notary
# needs the OCR/chip/mismatch/automated-result context to make sense of
# the video, not just the video in isolation.
from __future__ import annotations

from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield.roles import IsNotaryPublic
from documents.rentshield.roles import IsRentshieldAdmin
from documents.rentshield.roles import is_notary_public
from documents.rentshield_identity.models import IdentityVerification


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notary_status_view(request):
    """GET /api/documents/identity/verify/notary-status/ -- lets the
    frontend show the "Identity Verification Admin" nav link to a
    Notary Public account, not just is_staff admins. Real gap this
    closes: is_notary_public() is a plain Group-membership check with
    no equivalent exposed anywhere in what the frontend already gets
    about the logged-in user (is_staff/is_superuser only), and every
    seeded Notary account used to also happen to be is_staff -- masking
    this -- until the notary account was correctly stripped down to
    non-staff (2026-09-13), at which point it could no longer even find
    its way to the review page it has real backend access to."""
    return Response({"is_notary_public": is_notary_public(request.user)})


def _risk_score(record: IdentityVerification) -> int:
    """Higher first: a Notary triaging a real queue should see the
    records most likely to need a closer look before the clean ones,
    not whichever happened to update most recently. Two independent
    risk signals, since either can exist without the other (the
    automated cross-check is plain string comparison; Claude's own read
    of the same fields can disagree with it -- see ai_prescreen.py's
    system prompt on why it's told not to just trust that automated
    note)."""
    summary = (record.ai_prescreen_summary or "").lower()
    if record.identity_mismatch_notes or "significant inconsistency" in summary:
        return 2
    if "minor inconsistency" in summary:
        return 1
    return 0


@api_view(["GET"])
@permission_classes([IsRentshieldAdmin | IsNotaryPublic])
def admin_list_verifications_view(request):
    """GET /api/documents/identity/verify/admin/list/ -- by default only
    the records actually needing a Notary's attention (status
    AWAITING_NOTARY_REVIEW), riskiest first (see _risk_score) so a
    Notary triaging several at once sees the ones most likely to need a
    closer look before the clean ones -- showing every record
    regardless of status made the queue useless once more than a
    handful of users had verified/failed already. Pass ?status=all to
    see the full history instead (e.g. to look back at a past
    decision) -- that view stays newest-first, plain chronological
    order being what you actually want when browsing decisions already
    made. File URLs are relative (MEDIA_URL-based, same as any other
    Django FileField) -- the frontend resolves them against the API
    host, same as it does for paperless-ngx's own document thumbnail
    URLs elsewhere in this app."""
    records = (
        IdentityVerification.objects.select_related("user", "notary_reviewed_by")
        .prefetch_related("video_calls")
        .order_by("-updated_at")
    )
    if request.GET.get("status") != "all":
        records = records.filter(status=IdentityVerification.Status.AWAITING_NOTARY_REVIEW)
        records = sorted(records, key=lambda record: (-_risk_score(record), -record.updated_at.timestamp()))
    return Response(
        {
            "results": [
                {
                    "id": record.id,
                    "username": record.user.username,
                    "email": record.user.email,
                    "status": record.status,
                    "provider": record.provider,
                    "verification_id": record.verification_id,
                    "passport_photo_url": record.passport_photo.url if record.passport_photo else None,
                    "selfie_photo_url": record.selfie_photo.url if record.selfie_photo else None,
                    "video_url": record.video.url if record.video else None,
                    "chip_photo_url": record.chip_photo.url if record.chip_photo else None,
                    "additional_id_type": record.additional_id_type,
                    "additional_id_type_label": record.get_additional_id_type_display() if record.additional_id_type else "",
                    "additional_id_photo_front_url": (
                        record.additional_id_photo_front.url if record.additional_id_photo_front else None
                    ),
                    "additional_id_photo_back_url": (
                        record.additional_id_photo_back.url if record.additional_id_photo_back else None
                    ),
                    "chip_selfie_match_score": record.chip_selfie_match_score,
                    "latitude": record.latitude,
                    "longitude": record.longitude,
                    "location_accuracy_m": record.location_accuracy_m,
                    "declared_document_type": record.declared_document_type,
                    "declared_document_number": record.declared_document_number,
                    "declared_date_of_birth": record.declared_date_of_birth,
                    "card_ocr_full_name": record.card_ocr_full_name,
                    "card_ocr_date_of_birth": record.card_ocr_date_of_birth,
                    "card_ocr_document_number": record.card_ocr_document_number,
                    "chip_full_name": record.chip_full_name,
                    "chip_date_of_birth": record.chip_date_of_birth,
                    "chip_document_number": record.chip_document_number,
                    "identity_mismatch_notes": record.identity_mismatch_notes,
                    "automated_result": record.automated_result,
                    "notary_reviewed_by": record.notary_reviewed_by.username if record.notary_reviewed_by else None,
                    "notary_reviewed_at": record.notary_reviewed_at,
                    "notary_notes": record.notary_notes,
                    "ai_prescreen_summary": record.ai_prescreen_summary,
                    "video_call": calls[0].to_dict() if (calls := list(record.video_calls.all())) else None,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ],
        },
    )
