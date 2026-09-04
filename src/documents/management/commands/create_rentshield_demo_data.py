# Idempotently seeds realistic (fictitious) RentShield notices and
# tenancy contracts so a new user -- or a prospective one clicking
# through the self-guided tour -- sees a platform that already has data
# in it, not an empty shell. Every document is created through the same
# real code paths the app itself uses (documents.rentshield.service, the
# stock paperless-ngx consumption pipeline) -- there is no seed-only
# shortcut that writes rows directly, so the demo data exercises exactly
# what a real notice/contract upload exercises, including the Workflow
# engine's DOCUMENT_ADDED triggers.
from __future__ import annotations

import os
import tempfile
from datetime import date
from datetime import timedelta
from pathlib import Path
from time import mktime

import pathvalidate
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from documents.data_models import ConsumableDocument
from documents.data_models import DocumentMetadataOverrides
from documents.data_models import DocumentSource
from documents.models import Document
from documents.models import Tag
from documents.rentshield.custom_fields import DEMO_DATA_TAG_NAME
from documents.rentshield.custom_fields import TENANCY_CONTRACT_TAG_NAME
from documents.rentshield.document_analysis import DocumentAnalysisError
from documents.rentshield.service import generate_and_consume
from documents.rentshield.service import run_ai_review
from documents.tasks import consume_file

User = get_user_model()

TODAY = date.today()


def _d(days_ago: int) -> str:
    return (TODAY - timedelta(days=days_ago)).isoformat()


# 8 notices covering every statutory + breach reason, with a realistic
# spread of the notarization and AI-review add-ons so "Notarization
# Pending" and "Needs AI Review" aren't empty on a fresh install. Names,
# buildings, and Ejari numbers are all fictitious.
DEMO_NOTICES = [
    {
        "landlord_name": "Ahmed Al Maktoum",
        "tenant_name": "Sarah Mitchell",
        "property_type": "Apartment",
        "unit_no": "1204",
        "building_name": "Marina Heights Tower",
        "ejari_number": "204938271",
        "notice_date": _d(20),
        "reason": "sale",
    },
    {
        "landlord_name": "Fatima Al Suwaidi",
        "landlord_email": "fatima.demo@example.com",
        "tenant_name": "David Chen",
        "property_type": "Villa",
        "plot_number": "3311-0921",
        "building_name": "Al Barsha Villa 12",
        "ejari_number": "119284736",
        "notice_date": _d(25),
        "reason": "personal",
        "add_notarization": True,
    },
    {
        "landlord_name": "Mohammed Al Rashid",
        "tenant_name": "Jessica Park",
        "property_type": "Office",
        "unit_no": "1502",
        "building_name": "Business Bay Tower B",
        "ejari_number": "556677889",
        "notice_date": _d(34),
        "reason": "demolition",
        "add_ai_review": True,
    },
    {
        "landlord_name": "Aisha Al Qassimi",
        "tenant_name": "Michael Brown",
        "property_type": "Retail",
        "unit_no": "G-14",
        "building_name": "JBR The Walk",
        "ejari_number": "998877665",
        "notice_date": _d(38),
        "reason": "renovation",
    },
    {
        "landlord_name": "Omar Sharif",
        "tenant_name": "Linda Davis",
        "property_type": "Apartment",
        "unit_no": "802",
        "building_name": "Downtown Views",
        "ejari_number": "334455667",
        "notice_date": _d(10),
        "reason": "nonpayment",
    },
    {
        "landlord_name": "Layla Hassan",
        "landlord_email": "layla.demo@example.com",
        "tenant_name": "Robert Wilson",
        "property_type": "Apartment",
        "unit_no": "45B",
        "building_name": "Discovery Gardens",
        "ejari_number": "112233445",
        "notice_date": _d(14),
        "reason": "sublease",
        "add_notarization": True,
    },
    {
        "landlord_name": "Khalid Al Falasi",
        "landlord_email": "khalid.demo@example.com",
        "tenant_name": "Emma Taylor",
        "property_type": "Villa",
        "plot_number": "AR-0456",
        "building_name": "Arabian Ranches Villa 7",
        "ejari_number": "667788990",
        "notice_date": _d(30),
        "reason": "sale",
        "add_notarization": True,
        "add_ai_review": True,
    },
    {
        "landlord_name": "Noura Al Marri",
        "tenant_name": "James Anderson",
        "property_type": "Townhouse",
        "unit_no": "12",
        "building_name": "Jumeirah Village Circle - JVC08",
        "ejari_number": "223344556",
        "notice_date": _d(45),
        "reason": "personal",
    },
]

# 3 uploaded tenancy contracts -- one that will fail AI review (short
# notice-period clause + an invalid service method), one that will pass
# cleanly, and one deliberately left un-reviewed so "Contracts Under
# Review" isn't always empty on a fresh install.
DEMO_CONTRACTS = [
    {
        "title": "Tenancy Contract - Golden Sands Building",
        "filename": "Tenancy Contract - Golden Sands Building.txt",
        "tag_at_upload": True,
        "run_ai_review": True,
        "text": (
            "TENANCY CONTRACT\n\n"
            "This Agreement is made between the Landlord and the Tenant for the "
            "lease of Unit 903, Golden Sands Building, Al Nahda, Dubai. "
            "Ejari No. 5544332211.\n\n"
            "Term: This Agreement may be terminated by either party upon 7 days "
            "written notice to the other party.\n\n"
            "Service of Notice: The Landlord may serve notice verbally to the "
            "Tenant, or by any other means the Landlord considers reasonable.\n\n"
            "Rent: AED 85,000 per annum, payable in 4 cheques.\n"
        ),
    },
    {
        "title": "Tenancy Contract - Marina View Tower",
        "filename": "Tenancy Contract - Marina View Tower.txt",
        "tag_at_upload": True,
        "run_ai_review": True,
        "text": (
            "TENANCY CONTRACT\n\n"
            "This Agreement is made between the Landlord and the Tenant for the "
            "lease of Unit 2210, Marina View Tower, Dubai Marina, Dubai. "
            "Ejari No. 9988776655.\n\n"
            "Term: Either party may terminate this Agreement upon 365 days "
            "written notice to the other party, in accordance with Law No. (33) "
            "of 2008.\n\n"
            "Service of Notice: Notice shall be served via registered mail with "
            "acknowledgment of receipt, or through a Notary Public.\n\n"
            "Rent: AED 145,000 per annum, payable in 2 cheques.\n"
        ),
    },
    {
        # Filename deliberately avoids "contract" and the tag is applied
        # only after consumption (see handle()) so neither of the
        # AI-review-on-upload workflows' DOCUMENT_ADDED triggers catch
        # it -- this one is meant to stay genuinely pending, to
        # illustrate "Contracts Under Review" on a fresh install.
        "title": "Tenancy Contract - Al Wasl Residence",
        "filename": "Al Wasl Residence - Lease Agreement.txt",
        "tag_at_upload": False,
        "run_ai_review": False,
        "text": (
            "TENANCY CONTRACT\n\n"
            "This Agreement is made between the Landlord and the Tenant for the "
            "lease of Villa 4, Al Wasl Residence, Al Wasl Road, Dubai. "
            "Ejari No. 1122334455.\n\n"
            "Term: This Agreement is for a fixed term of one (1) year, renewable "
            "by mutual written agreement of both parties.\n\n"
            "Rent: AED 210,000 per annum, payable in 1 cheque.\n"
        ),
    },
]


class Command(BaseCommand):
    help = (
        "Idempotently seeds 8 realistic (fictitious) RentShield notices and "
        "3 uploaded tenancy contracts, through the same code paths real "
        "usage goes through (documents.rentshield.service, paperless-ngx's "
        "own consumption pipeline) -- so every dashboard widget and "
        "workflow has real, visible data on a fresh install. Safe to "
        "re-run: skipped entirely if any document already carries the "
        "'Demo Data' tag."
    )

    def handle(self, *args, **options):
        if Tag.objects.filter(name=DEMO_DATA_TAG_NAME).exists():
            self.stdout.write(
                self.style.WARNING(
                    f"Skipping: a '{DEMO_DATA_TAG_NAME}' tag already exists, which "
                    "means this command has already run. To reset, delete every "
                    f"document tagged '{DEMO_DATA_TAG_NAME}' in paperless-ngx "
                    "(Documents > filter by that tag > select all > delete), then "
                    "re-run this command.",
                ),
            )
            return

        demo_tag = Tag.objects.create(name=DEMO_DATA_TAG_NAME, color="#94a3b8")
        owner = User.objects.filter(is_superuser=True).order_by("id").first()
        owner_id = owner.id if owner else None

        created_notices = 0
        for fields in DEMO_NOTICES:
            document = generate_and_consume(fields, owner_id=owner_id, synchronous=True)
            document.tags.add(demo_tag)
            created_notices += 1
            self.stdout.write(self.style.SUCCESS(f"Created notice: {document.title}"))

        created_contracts = 0
        reviewed_contracts = 0
        for contract in DEMO_CONTRACTS:
            document = self._consume_contract(
                contract["title"],
                contract["filename"],
                contract["text"],
                owner_id,
                tag_at_upload=contract["tag_at_upload"],
            )
            document.tags.add(demo_tag)
            if not contract["tag_at_upload"]:
                tenancy_tag, _ = Tag.objects.get_or_create(
                    name=TENANCY_CONTRACT_TAG_NAME,
                    defaults={"color": "#6366f1"},
                )
                document.tags.add(tenancy_tag)
            created_contracts += 1
            self.stdout.write(self.style.SUCCESS(f"Created contract: {document.title}"))

            if contract["run_ai_review"]:
                try:
                    result = run_ai_review(document)
                except DocumentAnalysisError as exc:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  AI review skipped for {document.title!r} -- "
                            f"docling-service isn't reachable ({exc}). It'll show "
                            "up under 'Contracts Under Review' until reviewed "
                            "manually or docling-service is running.",
                        ),
                    )
                else:
                    reviewed_contracts += 1
                    verdict = "non-compliant" if result["has_violation"] else "compliant"
                    self.stdout.write(f"  AI-reviewed: {verdict} ({result['violation_count']} finding(s))")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDemo data created: {created_notices} notices, "
                f"{created_contracts} contracts ({reviewed_contracts} AI-reviewed).",
            ),
        )
        self.stdout.write(
            "All demo documents are tagged "
            f"'{DEMO_DATA_TAG_NAME}' -- filter by that tag to find or bulk-delete "
            "them later. If a Celery worker is running, its "
            "DOCUMENT_ADDED workflows (storage path, document type, "
            "notarization-pending webhook, etc.) will also have fired on "
            "these documents, same as any real upload.",
        )

    def _consume_contract(
        self,
        title: str,
        filename: str,
        text: str,
        owner_id: int | None,
        *,
        tag_at_upload: bool,
    ) -> Document:
        safe_filename = pathvalidate.sanitize_filename(filename)
        settings.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
        temp_dir = Path(tempfile.mkdtemp(dir=settings.SCRATCH_DIR))
        temp_file_path = temp_dir / safe_filename
        temp_file_path.write_text(text, encoding="utf-8")

        t = int(mktime(date.today().timetuple()))
        os.utime(temp_file_path, times=(t, t))

        tag_ids = []
        if tag_at_upload:
            tag, _ = Tag.objects.get_or_create(
                name=TENANCY_CONTRACT_TAG_NAME,
                defaults={"color": "#6366f1"},
            )
            tag_ids = [tag.id]

        input_doc = ConsumableDocument(
            source=DocumentSource.ApiUpload,
            original_file=temp_file_path,
        )
        overrides = DocumentMetadataOverrides(
            filename=safe_filename,
            title=title,
            owner_id=owner_id,
            tag_ids=tag_ids,
        )
        result = consume_file(input_doc, overrides)
        document_id = result.get("document_id") if isinstance(result, dict) else None
        if document_id is None:
            msg = f"consume_file did not produce a document for {title!r}: {result!r}"
            raise RuntimeError(msg)
        return Document.objects.get(id=document_id)
