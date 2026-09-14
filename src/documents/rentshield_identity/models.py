from __future__ import annotations

import uuid
from datetime import timedelta

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
        # Distinct from FAILED (2026-09-14): a Notary who just needs a
        # redo -- blurry video, wrong document photographed, chip read
        # didn't take -- previously had no way to say that without using
        # Reject, which reads as a hard "you did not pass" to the user
        # and to anyone auditing the record afterward. This sends the
        # record back to the user's own pipeline without deleting any
        # evidence (see notary_request_more_info_view) -- unlike
        # admin_reset_verification_view, which does.
        NEEDS_MORE_INFO = "needs_more_info", "Needs more from you"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rentshield_identity_verification",
    )
    provider = models.CharField(max_length=32, default="idswyft")
    verification_id = models.CharField(max_length=255, blank=True, default="")
    hosted_url = models.URLField(blank=True, default="")
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)

    # What the user typed on the WEB page's "declare your document" step
    # (identity-verification.component.ts), before ever scanning the QR
    # -- typed on a real keyboard, not a phone's, specifically to cut
    # down the CAN/document-number typos that kept happening when this
    # was only ever typed on the app's own small screen. Carried to the
    # app via pair_claim_view's response so the app can pre-fill (still
    # editable, never blindly trusted) instead of asking from scratch,
    # and cross-checked against card_ocr_*/chip_* below (see
    # views.py's _check_identity_mismatch) as a third independent
    # source, not just OCR-vs-chip. declared_expiry_date/declared_can
    # are only ever used to build the app's own PACE/BAC key -- neither
    # is echoed back by the chip, so neither has anything to cross-check
    # against.
    declared_document_type = models.CharField(max_length=16, blank=True, default="")
    declared_document_number = models.CharField(max_length=64, blank=True, default="")
    declared_date_of_birth = models.CharField(max_length=32, blank=True, default="")
    declared_expiry_date = models.CharField(max_length=32, blank=True, default="")
    declared_can = models.CharField(max_length=16, blank=True, default="")

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

    class AdditionalIdType(models.TextChoices):
        DRIVING_LICENCE = "driving_licence", "Driving Licence"
        NATIONAL_ID = "national_id", "National ID Card"
        RESIDENCE_VISA = "residence_visa", "Residence Visa"
        SECOND_PASSPORT = "second_passport", "Second Passport"
        OTHER = "other", "Other ID document"

    # A second, independent ID document (e.g. a driving licence) --
    # requested explicitly as a MANDATORY pipeline step (2026-09-13,
    # superseding the earlier optional web upload), never the same
    # document type as the primary one above (pairing_views.py's
    # _validate_declared_document already establishes that), and always
    # front AND back -- a single photo isn't enough evidence for a
    # document this project has no OCR/NFC pipeline for. App-only: there
    # is no web UI for this any more, since it has to happen at a
    # specific point in the app's own pipeline (right after the NFC
    # read -- see views.py's upload_additional_id_view), not whenever a
    # browser happens to be open.
    additional_id_type = models.CharField(max_length=32, choices=AdditionalIdType.choices, blank=True, default="")
    additional_id_photo_front = models.FileField(upload_to="rentshield_identity/additional_ids/", blank=True, null=True)
    additional_id_photo_back = models.FileField(upload_to="rentshield_identity/additional_ids/", blank=True, null=True)

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

    # Advisory lock (2026-09-14, explicitly requested): once there's
    # more than one Notary account, two Notaries could otherwise act on
    # the same record at once with no warning. A Notary claims a record
    # explicitly (claim_verification_view) before working on it;
    # confirm/reject/request-more-info/reset/delete then refuse a
    # conflicting actor while someone else's claim is still fresh (see
    # CLAIM_STALE_AFTER below) -- an abandoned claim (closed tab,
    # forgot to release) ages out on its own instead of locking the
    # record forever.
    claimed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rentshield_claimed_verifications",
    )
    claimed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    CLAIM_STALE_AFTER = timedelta(minutes=15)

    def claim_conflict(self, user) -> bool:
        """True if this record is claimed by someone OTHER than `user`
        and that claim hasn't gone stale yet."""
        from django.utils import timezone

        if not self.claimed_by_id or self.claimed_by_id == user.id:
            return False
        return timezone.now() < self.claimed_at + self.CLAIM_STALE_AFTER

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status} ({self.provider})"


class IdentityVerificationCall(models.Model):
    """A scheduled, self-hosted Jitsi video call between a Notary Public
    and the property owner -- the one live, synchronous moment in an
    otherwise fully async pipeline, closing the biggest real gap
    against how an actual Dubai Notary Public appointment works (in-
    person presence confirmation + a legal-capacity judgment call, per
    notarypublicdubai.com's own description -- neither of which a
    recorded video can substitute for). A FK, not a one-to-one: a
    no-show or a reschedule creates a new row rather than overwriting
    history, so a Notary reviewing a record later can still see that an
    earlier attempt happened.

    Deliberately simple room security (2026-09-14): `room_name` is
    unguessable (a full uuid4) but Jitsi's own auth/lobby isn't
    configured -- same trust model as any "anyone with the link" video
    tool. Recording is started manually by the Notary clicking Jitsi's
    own toolbar button (they're the moderator, being first to
    schedule/join) rather than orchestrated via Jibri's REST/XMPP API --
    ponytail: add prosody JWT auth + a lobby, and/or programmatic
    recording control, if this ever needs hardening."""

    class Status(models.TextChoices):
        PROPOSED = "proposed", "Proposed -- waiting on the user"
        CONFIRMED = "confirmed", "Confirmed"
        RESCHEDULE_REQUESTED = "reschedule_requested", "User asked for a different time"
        COMPLETED = "completed", "Completed"
        NO_SHOW = "no_show", "No-show"
        CANCELLED = "cancelled", "Cancelled"

    identity_verification = models.ForeignKey(
        IdentityVerification,
        on_delete=models.CASCADE,
        related_name="video_calls",
    )
    room_name = models.CharField(max_length=64, unique=True, default=uuid.uuid4, editable=False)
    scheduled_at = models.DateTimeField()
    proposed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="rentshield_proposed_video_calls",
    )
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PROPOSED)
    notary_call_notes = models.TextField(blank=True, default="")

    # Filled in by run_video_call_recording_ingest_task once Jibri's
    # finished recording is found in the shared volume and matched to
    # this call by room_name -- see that task's own docstring for why a
    # periodic scan instead of a Jibri finalize-script webhook.
    recording_file = models.FileField(
        upload_to="rentshield_identity/call_recordings/",
        blank=True,
        null=True,
    )

    # Null until run_video_call_reminder_task actually sends one --
    # never re-sent for the same call once set, same "log a stamp so a
    # periodic task can't double-fire" pattern DevicePairingCode's own
    # single-use `claimed_at` uses.
    reminder_sent_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # -created_at, not -scheduled_at: every consumer that reads
        # `.first()`/`calls[0]` wants "the current/most-recently-
        # proposed call", and a superseded call can easily have a
        # LATER scheduled_at than the new one that replaced it (see
        # schedule_video_call_view's own cancel-the-old-ones comment) --
        # ordering by scheduled_at would then surface the stale one.
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.identity_verification_id}: {self.status} @ {self.scheduled_at}"

    # 10 minutes early -- long enough that neither side is stuck
    # refreshing right at the scheduled second, short enough that
    # "Join call" isn't just sitting there for hours beforehand. No
    # forced close on the other end: the Notary marking the call
    # COMPLETED/NO_SHOW is what actually ends the window, not a timer.
    JOIN_WINDOW_BEFORE = timedelta(minutes=10)

    def join_open(self) -> bool:
        from django.utils import timezone

        return self.status == self.Status.CONFIRMED and timezone.now() >= self.scheduled_at - self.JOIN_WINDOW_BEFORE

    def to_dict(self) -> dict:
        """Shared serialization for both the property owner's own status
        endpoint (verification_status_view) and the Notary's review list
        (admin_list_verifications_view) -- one shape, not two independently
        maintained ones. Carries `jitsi_base_url` itself (same pattern
        pairing_views.py's `_apk_download_url()` already uses for
        `apk_url`) so the frontend never needs its own separate copy of
        that config -- it talks to Jitsi directly, not through Django,
        but still gets the URL from the one place that already knows it."""
        from django.conf import settings

        return {
            "id": self.id,
            "status": self.status,
            "scheduled_at": self.scheduled_at,
            "room_name": self.room_name,
            "join_open": self.join_open(),
            "notary_call_notes": self.notary_call_notes,
            "recording_url": self.recording_file.url if self.recording_file else None,
            "jitsi_base_url": settings.RENTSHIELD_JITSI_BASE_URL,
        }


class IdentityVerificationAuditLog(models.Model):
    """One row per action taken on an IdentityVerification -- confirm,
    reject, request-more-info, reset, delete, and every video-call
    state change. Added (2026-09-14) because those actions all used to
    share a single notary_reviewed_by/at/notes slot on the record
    itself: a second "send back for more info" silently overwrote the
    first, and there was no way to see that it had even happened.

    Deliberately NOT a ForeignKey to IdentityVerification (or to the
    acting User for the row's own identity) -- a real audit trail has
    to outlive admin_delete_verification_view deleting the record it's
    about, otherwise "add a real audit trail" and "add the ability to
    delete a verification" would cancel each other out. `verification_id`
    and `username` are a plain int and a copy taken at write time, not
    a live relation; `actor` is still a real FK (SET_NULL) since losing
    who-did-it is a smaller loss than losing the whole row would be,
    and Users aren't deleted anywhere near as often as verifications
    are reset/deleted in this feature area."""

    class Action(models.TextChoices):
        SUBMITTED_FOR_REVIEW = "submitted_for_review", "Submitted for Notary review"
        CONFIRMED = "confirmed", "Confirmed"
        REJECTED = "rejected", "Rejected"
        REQUESTED_MORE_INFO = "requested_more_info", "Sent back for more info"
        RESET = "reset", "Reset (evidence wiped)"
        DELETED = "deleted", "Deleted"
        CALL_SCHEDULED = "call_scheduled", "Video call scheduled"
        CALL_CONFIRMED = "call_confirmed", "Video call confirmed"
        CALL_RESCHEDULE_REQUESTED = "call_reschedule_requested", "Video call reschedule requested"
        CALL_COMPLETED = "call_completed", "Video call completed"
        CALL_NO_SHOW = "call_no_show", "Video call no-show"

    verification_id = models.PositiveIntegerField(db_index=True)
    username = models.CharField(max_length=255, blank=True, default="")
    action = models.CharField(max_length=32, choices=Action.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rentshield_verification_audit_entries",
    )
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"verification {self.verification_id}: {self.action}"

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "action_label": self.get_action_display(),
            "actor": self.actor.username if self.actor else None,
            "notes": self.notes,
            "created_at": self.created_at,
        }


class DevicePairingCode(models.Model):
    """A short-lived, single-use code that lets the native Android/iOS
    app sign a user in by scanning a QR code shown on this web app's
    identity-verification page, instead of typing a username/password
    on the phone -- the same "scan to sign in" pattern as WhatsApp Web
    or the GitHub CLI's device flow. See
    rentshield_identity/pairing_views.py for the full start/status/claim
    flow; safety here rests entirely on the code itself (192 bits of
    entropy via secrets.token_urlsafe, single-use, PAIRING_CODE_TTL
    expiry) since the claim step has to be reachable with no auth at
    all -- the phone genuinely has no account yet at that point.

    Claiming one only ever grants the same DRF auth Token a normal
    password login already would (see pairing_views.py's
    pair_claim_view) -- this is a different way to obtain that token,
    not a higher-privileged one."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        CLAIMED = "claimed", "Claimed"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rentshield_pairing_codes",
    )
    code = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    claimed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status}"
