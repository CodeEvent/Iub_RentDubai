from __future__ import annotations

from django.conf import settings
from django.db import models


class Order(models.Model):
    """One payment for one notice-generation request. Created BEFORE the
    notice exists (pending payment), and generate_and_consume() only
    ever fires once this row's status flips to PAID/DEMO_PAID -- see
    documents/rentshield_billing/views.py and
    documents.tasks.finalize_paid_notice_task. `fields` is the exact
    payload create_notice_view already validates, snapshotted here so
    the notice generated after payment matches exactly what was quoted
    and paid for, not whatever the form happens to hold by the time
    payment confirms."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID = "paid", "Paid"
        DEMO_PAID = "demo_paid", "Paid (demo)"
        FAILED = "failed", "Failed"
        CANCELED = "canceled", "Canceled"

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="rentshield_orders",
    )
    fields = models.JSONField(help_text="Notice-creation payload this order is for.")
    amount_aed = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, default="")
    # Nullable FK to documents.Document -- no direct model import to
    # avoid a rentshield_billing <-> documents circular import at
    # module load time (documents already imports plenty from
    # documents.rentshield; this app should stay a one-way dependency:
    # rentshield_billing can be imported by documents code, not the
    # other way around).
    document_id = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"Order #{self.pk} ({self.status}, AED {self.amount_aed})"
