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
from rest_framework.response import Response

from documents.rentshield.roles import IsNotaryPublic
from documents.rentshield.roles import IsRentshieldAdmin
from documents.rentshield_identity.models import IdentityVerification


@api_view(["GET"])
@permission_classes([IsRentshieldAdmin | IsNotaryPublic])
def admin_list_verifications_view(request):
    """GET /api/documents/identity/verify/admin/list/ -- by default only
    the records actually needing a Notary's attention (status
    AWAITING_NOTARY_REVIEW), newest first -- showing every record
    regardless of status made the queue useless once more than a
    handful of users had verified/failed already. Pass ?status=all to
    see the full history instead (e.g. to look back at a past
    decision). File URLs are relative (MEDIA_URL-based, same as any
    other Django FileField) -- the frontend resolves them against the
    API host, same as it does for paperless-ngx's own document
    thumbnail URLs elsewhere in this app."""
    records = IdentityVerification.objects.select_related("user", "notary_reviewed_by").order_by("-updated_at")
    if request.GET.get("status") != "all":
        records = records.filter(status=IdentityVerification.Status.AWAITING_NOTARY_REVIEW)
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
                    "chip_selfie_match_score": record.chip_selfie_match_score,
                    "latitude": record.latitude,
                    "longitude": record.longitude,
                    "location_accuracy_m": record.location_accuracy_m,
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
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ],
        },
    )
