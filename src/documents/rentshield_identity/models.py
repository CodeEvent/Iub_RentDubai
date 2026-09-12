from __future__ import annotations

from django.conf import settings
from django.db import models


class IdentityVerification(models.Model):
    """One property owner's passport/ID verification via a self-hosted
    Idswyft instance (documents/rentshield_identity/idswyft_client.py) --
    camera capture + liveness + face match against the document photo,
    not NFC chip reading (see that file's header comment for why: NFC
    needs a native app or a PC/SC reader, neither of which this web app
    has). One row per user, created the first time they start
    verification; `status` is updated either by polling Idswyft's status
    endpoint or by its webhook, whichever lands first.

    `passport_photo`/`selfie_photo` are RentShield's own copies of what
    the user uploaded (saved before forwarding to Idswyft) -- Idswyft
    never returns these once processed, and the admin review page
    (rentshield_identity/admin_views.py) needs something to actually
    show a reviewer. Idswyft's own IDs/session tokens stay in
    `verification_id`, unrelated to Django storage."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"
        MANUAL_REVIEW = "manual_review", "Needs manual review"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rentshield_identity_verification",
    )
    provider = models.CharField(max_length=32, default="idswyft")
    verification_id = models.CharField(max_length=255, blank=True, default="")
    hosted_url = models.URLField(blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)

    passport_photo = models.FileField(upload_to="rentshield_identity/passports/", blank=True, null=True)
    selfie_photo = models.FileField(upload_to="rentshield_identity/selfies/", blank=True, null=True)

    # Captured client-side via the browser's Geolocation API at upload
    # time (see identity-verification.component.ts) -- where the
    # verification was actually performed, not the user's address.
    # Null when the browser permission was denied/unavailable; this is
    # evidence for a reviewer, never a hard gate on verification itself.
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    location_accuracy_m = models.FloatField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status} ({self.provider})"
