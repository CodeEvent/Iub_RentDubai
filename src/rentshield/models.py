from django.db import models

from rentshield.constants import REASON_CHOICES


class Notice(models.Model):
    """A generated Dubai tenancy notice.

    Mirrors the `notices` table from legacy-v1/api/src/db.js field for
    field, plus a link to the real paperless-ngx Document created for it
    (see rentshield/services.py) — this FK is the actual payoff of
    rebasing onto paperless-ngx: every generated notice is OCR'd, full-
    text searchable, and taggable through paperless's own machinery
    instead of being a bespoke file on disk.
    """

    PROPERTY_TYPE_CHOICES = [
        ("Apartment", "Apartment"),
        ("Villa", "Villa"),
        ("Townhouse", "Townhouse"),
        ("Office", "Office"),
        ("Retail", "Retail"),
    ]

    landlord_name = models.CharField(max_length=255)
    landlord_email = models.EmailField(blank=True, null=True)
    tenant_name = models.CharField(max_length=255)
    property_type = models.CharField(max_length=32, choices=PROPERTY_TYPE_CHOICES, default="Apartment")
    unit_no = models.CharField(max_length=64, blank=True, null=True)
    building_name = models.CharField(max_length=255, blank=True, null=True)
    plot_number = models.CharField(max_length=64, blank=True, null=True)
    ejari_number = models.CharField(max_length=64, blank=True, null=True)
    notice_date = models.DateField()
    reason = models.CharField(max_length=32, choices=REASON_CHOICES)

    add_notarization = models.BooleanField(default=False)
    add_ai_review = models.BooleanField(default=False)

    # Populated by rentshield.esign.orchestrator.request_signing() when
    # add_notarization is set — see services.py's request_notarization()
    # / check_notarization_status().
    esign_provider = models.CharField(max_length=16, blank=True, null=True)
    esign_external_id = models.CharField(max_length=255, blank=True, null=True)
    esign_signing_url = models.URLField(blank=True, null=True, max_length=1024)
    esign_status = models.CharField(max_length=32, blank=True, null=True)
    esign_signed_document_url = models.URLField(blank=True, null=True, max_length=1024)

    # Populated once rentshield.services.generate_and_consume() hands the
    # rendered PDF to paperless-ngx's consume_file task.
    consume_task_id = models.CharField(max_length=72, blank=True, null=True)
    document = models.ForeignKey(
        "documents.Document",
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="rentshield_notices",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Notice({self.landlord_name} -> {self.tenant_name}, {self.reason})"
