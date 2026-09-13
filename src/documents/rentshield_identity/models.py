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
    `verification_id`, unrelated to Django storage.

    Full pipeline (2026-09-13): photograph the card -> Idswyft OCRs it
    (card_ocr_*) and RentShield auto-updates the user's first/last name
    from that -> NFC chip read (chip_*) cross-checked against the OCR
    fields -> selfie face-match against the card photo -> a short
    recorded video -> a human (Notary Public role) reviews everything
    and is the one who actually sets `status` to VERIFIED. Idswyft's own
    automated result (`automated_result`) only ever short-circuits to
    FAILED on a hard reject -- anything else reaches the Notary queue,
    per this project's explicit choice to keep human review as the
    final word rather than trust the automated match alone."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        AWAITING_NOTARY_REVIEW = "awaiting_notary_review", "Awaiting Notary Public review"
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
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)

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

    # Idswyft's own OCR read of the photographed card (from `ocr_data` in
    # its front-document response -- MRZ-backfilled and checksum-scored
    # when the document has one, per idswyft's own newVerification.ts).
    # Stored as text, not a DateField: OCR dates arrive in whatever
    # format the source document/MRZ used, and a failed strict parse
    # would silently lose real evidence a reviewer could still read.
    card_ocr_full_name = models.CharField(max_length=255, blank=True, default="")
    card_ocr_date_of_birth = models.CharField(max_length=32, blank=True, default="")
    card_ocr_document_number = models.CharField(max_length=64, blank=True, default="")

    # The same fields as read directly off the NFC chip (DG1/MRZ) by the
    # native Android/iOS apps -- independent of Idswyft's OCR, so
    # disagreement between the two is real signal, not noise.
    chip_full_name = models.CharField(max_length=255, blank=True, default="")
    chip_date_of_birth = models.CharField(max_length=32, blank=True, default="")
    # The chip's OWN copy of the card's printed ID/serial number -- the
    # real "does the card number match the chip" check some users
    # expect, done *after* unlocking the chip with its actual PACE key
    # (the CAN), never by using the serial number as that key itself
    # (the chip's firmware doesn't accept it as one -- see
    # MainActivity.kt's onScanClicked() comment on the Android side).
    chip_document_number = models.CharField(max_length=64, blank=True, default="")

    # The chip's own DG2 photo (read straight off the passport/CIE chip,
    # cryptographically signed) -- kept separately from passport_photo
    # (the photographed card, used for OCR/Idswyft's own face match) so
    # a second, independent face comparison against the selfie can run
    # (documents/rentshield_identity/face_match.py) alongside Idswyft's.
    chip_photo = models.FileField(upload_to="rentshield_identity/chip_photos/", blank=True, null=True)
    # Cosine similarity from that comparison, or null if either photo
    # had no detectable face -- never an automatic pass/fail (see
    # face_match.py's SAME_PERSON_THRESHOLD comment), just more context
    # alongside Idswyft's own card-photo-vs-selfie result
    # (automated_result below) for the Notary reviewer to weigh.
    chip_selfie_match_score = models.FloatField(null=True, blank=True)

    # Set once the two sources above are both present -- never a hard
    # gate (OCR misreads happen), just something the Notary reviewer
    # below needs to see and weigh.
    identity_mismatch_notes = models.TextField(blank=True, default="")

    # Idswyft's own final_result (verified/failed/manual_review) --
    # kept as reference context for the Notary reviewer, distinct from
    # `status` above, which now tracks the whole pipeline including
    # their review, not just the automated result.
    automated_result = models.CharField(max_length=16, blank=True, default="")

    # A short user-recorded confirmation clip, reviewed by a real person
    # (Notary Public role) within 24h before `status` can ever become
    # VERIFIED -- see roles.py's IsNotaryPublic and admin_views.py's
    # notary_confirm_view/notary_reject_view.
    video = models.FileField(upload_to="rentshield_identity/videos/", blank=True, null=True)
    notary_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rentshield_notary_reviews",
    )
    notary_reviewed_at = models.DateTimeField(null=True, blank=True)
    notary_notes = models.TextField(blank=True, default="")

    # Claude-generated summary of the automated evidence, produced once
    # a verification reaches AWAITING_NOTARY_REVIEW (ai_prescreen.py) --
    # always shown labeled as AI-generated, never a decision: the Notary
    # remains the only one who can set VERIFIED. Blank until the
    # background task runs, and stays blank (not an error) if
    # ANTHROPIC_API_KEY isn't configured -- see ai_prescreen.py.
    ai_prescreen_summary = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status} ({self.provider})"
