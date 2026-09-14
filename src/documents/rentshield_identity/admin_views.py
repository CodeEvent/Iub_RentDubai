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

import datetime
from collections import defaultdict

from django.db.models import Q
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield.roles import IsNotaryPublic
from documents.rentshield.roles import IsRentshieldAdmin
from documents.rentshield.roles import is_notary_public
from documents.rentshield_identity.models import IdentityVerification
from documents.rentshield_identity.models import IdentityVerificationAuditLog


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


def _parse_date_or_none(raw: str | None) -> datetime.date | None:
    if not raw:
        return None
    try:
        return datetime.date.fromisoformat(raw)
    except ValueError:
        return None


def _filtered_records(request):
    """Shared by admin_list_verifications_view and
    admin_export_verifications_view (2026-09-14) -- the CSV export is
    meant to export "whatever the Notary is currently looking at", so
    it needs the exact same q/filter_status/date_from/date_to/status
    handling as the list view, not a second copy of it."""
    records = (
        IdentityVerification.objects.select_related("user", "notary_reviewed_by", "claimed_by")
        .prefetch_related("video_calls")
        .order_by("-updated_at")
    )

    q = (request.GET.get("q") or "").strip()
    if q:
        records = records.filter(Q(user__username__icontains=q) | Q(user__email__icontains=q))
    filter_status = request.GET.get("filter_status") or ""
    if filter_status in dict(IdentityVerification.Status.choices):
        records = records.filter(status=filter_status)
    date_from = _parse_date_or_none(request.GET.get("date_from"))
    if date_from:
        records = records.filter(created_at__date__gte=date_from)
    date_to = _parse_date_or_none(request.GET.get("date_to"))
    if date_to:
        records = records.filter(created_at__date__lte=date_to)

    if request.GET.get("status") != "all":
        records = records.filter(status=IdentityVerification.Status.AWAITING_NOTARY_REVIEW)
        records = sorted(records, key=lambda record: (-_risk_score(record), -record.updated_at.timestamp()))
    else:
        records = list(records)
    return records


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
    URLs elsewhere in this app.

    Optional filters (2026-09-14, meant for the ?status=all history view
    once it has more than a handful of rows, but applied regardless of
    which mode is active -- see _filtered_records): `q` (username/email
    substring), `filter_status` (exact IdentityVerification.Status
    value), `date_from`/`date_to` (YYYY-MM-DD, against created_at)."""
    records = _filtered_records(request)

    # One bulk query for every listed record's audit trail instead of
    # one query per record (this view can return the whole history) --
    # verification_id is a plain int here, not a real FK (see
    # IdentityVerificationAuditLog's own docstring), so this is a
    # straightforward IN-filter grouped in Python, not a
    # prefetch_related.
    audit_by_verification: dict[int, list[IdentityVerificationAuditLog]] = defaultdict(list)
    for entry in IdentityVerificationAuditLog.objects.filter(verification_id__in=[r.id for r in records]):
        audit_by_verification[entry.verification_id].append(entry)

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
                    "claimed_by": record.claimed_by.username if record.claimed_by else None,
                    "claimed_at": record.claimed_at,
                    "claim_conflict": record.claim_conflict(request.user),
                    "audit_log": [entry.to_dict() for entry in audit_by_verification.get(record.id, [])],
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ],
        },
    )


@api_view(["GET"])
@permission_classes([IsRentshieldAdmin | IsNotaryPublic])
def admin_export_verifications_view(request):
    """GET /api/documents/identity/verify/admin/export/ -- a CSV of
    whatever admin_list_verifications_view is currently showing (same
    q/filter_status/date_from/date_to/status query params via
    _filtered_records) for compliance record-keeping: who was verified,
    when, and by whom. Core identity/decision fields only, not every
    column the review page itself shows -- evidence photo URLs and the
    AI pre-screen summary aren't the kind of thing a compliance export
    needs, and would make the file harder to actually read."""
    import csv

    from django.http import HttpResponse

    records = _filtered_records(request)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="rentshield-identity-verifications.csv"'
    writer = csv.writer(response)
    writer.writerow(
        [
            "id", "username", "email", "status", "declared_document_type", "declared_document_number",
            "card_ocr_full_name", "chip_full_name", "automated_result", "notary_reviewed_by",
            "notary_reviewed_at", "notary_notes", "created_at", "updated_at",
        ],
    )
    for record in records:
        writer.writerow(
            [
                record.id,
                record.user.username,
                record.user.email,
                record.status,
                record.declared_document_type,
                record.declared_document_number,
                record.card_ocr_full_name,
                record.chip_full_name,
                record.automated_result,
                record.notary_reviewed_by.username if record.notary_reviewed_by else "",
                record.notary_reviewed_at.isoformat() if record.notary_reviewed_at else "",
                record.notary_notes,
                record.created_at.isoformat(),
                record.updated_at.isoformat(),
            ],
        )
    return response
