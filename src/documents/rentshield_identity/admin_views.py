# Admin-only review page for property-owner identity verifications --
# every user who has gone through the flow, their submitted passport
# photo and selfie side by side (the "mapping" between them is simply
# that they belong to the same IdentityVerification row -- one user, one
# document pair, one result), the outcome, and where it was performed.
# A separate module from views.py (which the property owner's own
# browser calls) since this is a distinct audience with a different
# permission (IsRentshieldAdmin, not "is this my own verification").
from __future__ import annotations

from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.response import Response

from documents.rentshield.roles import IsRentshieldAdmin
from documents.rentshield_identity.models import IdentityVerification


@api_view(["GET"])
@permission_classes([IsRentshieldAdmin])
def admin_list_verifications_view(request):
    """GET /api/documents/identity/verify/admin/list/ -- every
    verification record, newest first. Photo URLs are relative
    (MEDIA_URL-based, same as any other Django FileField) -- the
    frontend resolves them against the API host, same as it does for
    paperless-ngx's own document thumbnail URLs elsewhere in this app."""
    records = IdentityVerification.objects.select_related("user").order_by("-updated_at")
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
                    "latitude": record.latitude,
                    "longitude": record.longitude,
                    "location_accuracy_m": record.location_accuracy_m,
                    "created_at": record.created_at,
                    "updated_at": record.updated_at,
                }
                for record in records
            ],
        },
    )
