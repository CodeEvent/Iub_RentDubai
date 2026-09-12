from __future__ import annotations

from django.conf import settings
from django.db import models


class IdentityVerification(models.Model):
    """One property owner's passport/ID verification via a self-hosted
    Idswyft instance (documents/rentshield_identity/idswyft_client.py) --
    camera capture + liveness + face match against the document photo,
    not NFC chip reading (see the 2026-09-12 README section on why: NFC
    needs a native app or a PC/SC reader, neither of which this project
    has). One row per user, created the first time they start
    verification; `status` is updated either by polling Idswyft's status
    endpoint or by its webhook, whichever lands first."""

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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status} ({self.provider})"
