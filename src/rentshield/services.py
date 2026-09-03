from __future__ import annotations

import tempfile
from pathlib import Path
from time import mktime
from datetime import datetime

import pathvalidate
from django.conf import settings
from documents.data_models import ConsumableDocument
from documents.data_models import DocumentMetadataOverrides
from documents.data_models import DocumentSource
from documents.tasks import consume_file

from rentshield.constants import ALL_REASONS
from rentshield.models import Notice
from rentshield.notice_builder import build_notice
from rentshield.pdf import render_notice_pdf


def notice_to_builder_input(notice: Notice) -> dict:
    return {
        "landlord_name": notice.landlord_name,
        "tenant_name": notice.tenant_name,
        "property_type": notice.property_type,
        "unit_no": notice.unit_no,
        "building_name": notice.building_name,
        "plot_number": notice.plot_number,
        "ejari_number": notice.ejari_number,
        "notice_date": notice.notice_date,
        "reason": notice.reason,
    }


def generate_and_consume(notice: Notice, owner_id: int | None = None) -> str:
    """Renders `notice` to a real PDF and hands it to paperless-ngx's own
    consumption pipeline (the same `consume_file` task its own upload API
    uses — see documents/views.py PostDocumentView) so it becomes a real,
    OCR'd, searchable Document rather than a bespoke file this app manages
    itself. Returns the Celery task id; `notice.consume_task_id` is set to
    it so callers can poll `check_consume_status()`.
    """
    document_data = build_notice(notice_to_builder_input(notice))
    pdf_bytes = render_notice_pdf(document_data)

    reason = ALL_REASONS.get(notice.reason)
    reason_label = reason["label"] if reason else notice.reason
    doc_name = f"Notice of {reason_label} - {notice.tenant_name}.pdf"

    settings.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=settings.SCRATCH_DIR))
    temp_file_path = temp_dir / pathvalidate.sanitize_filename(doc_name)
    temp_file_path.write_bytes(pdf_bytes)

    t = int(mktime(datetime.now().timetuple()))
    import os

    os.utime(temp_file_path, times=(t, t))

    input_doc = ConsumableDocument(
        source=DocumentSource.ApiUpload,
        original_file=temp_file_path,
    )
    overrides = DocumentMetadataOverrides(
        filename=doc_name,
        title=doc_name.removesuffix(".pdf"),
        owner_id=owner_id,
    )

    async_task = consume_file.apply_async(
        kwargs={"input_doc": input_doc, "overrides": overrides},
    )

    notice.consume_task_id = async_task.id
    notice.save(update_fields=["consume_task_id"])
    return async_task.id


def check_consume_status(notice: Notice) -> dict:
    """Polls paperless-ngx's own PaperlessTask row for the consumption
    task started by generate_and_consume(), and links `notice.document`
    once the Document has actually been created — the same
    poll-until-resolved shape used for the DocuSeal/OpenSign notarization
    status checks in legacy-v1.
    """
    from documents.models import PaperlessTask

    if not notice.consume_task_id:
        return {"status": "not_requested"}

    try:
        task = PaperlessTask.objects.get(task_id=notice.consume_task_id)
    except PaperlessTask.DoesNotExist:
        return {"status": "pending"}

    if task.status == PaperlessTask.Status.SUCCESS and not notice.document_id:
        doc_ids = task.related_document_ids
        if doc_ids:
            notice.document_id = doc_ids[0]
            notice.save(update_fields=["document"])

    return {
        "status": task.status,
        "document_id": notice.document_id,
        "result": task.result_data,
    }


def request_notarization(notice: Notice) -> dict:
    """Routes `notice` through a real e-signature workflow (DocuSeal
    primary, OpenSign fallback) via rentshield.esign.orchestrator —
    ported 1:1 from legacy-v1's POST /api/notices/:id/notarize. Requires
    the notarization add-on to have been selected and a landlord email
    to route the signing request to.
    """
    if not notice.add_notarization:
        raise ValueError("Notarization add-on was not selected for this notice")
    if not notice.landlord_email:
        raise ValueError("A landlord email is required to route the notarization request")

    from rentshield.esign.orchestrator import request_signing

    document_data = build_notice(notice_to_builder_input(notice))
    reason = ALL_REASONS.get(notice.reason)
    reason_label = reason["label"] if reason else notice.reason

    result = request_signing(document_data, {
        "landlord_name": notice.landlord_name,
        "landlord_email": notice.landlord_email,
        "tenant_name": notice.tenant_name,
        "reason_label": reason_label,
    })

    notice.esign_provider = result["provider"]
    notice.esign_external_id = result["external_id"]
    notice.esign_signing_url = result["signing_url"]
    notice.esign_status = result["status"]
    notice.save(update_fields=["esign_provider", "esign_external_id", "esign_signing_url", "esign_status"])
    return result


def check_notarization_status(notice: Notice) -> dict:
    """Polls whichever e-signature provider originally handled the
    request — ported 1:1 from legacy-v1's GET /api/notices/:id/notarize/status.
    """
    if not notice.esign_provider or not notice.esign_external_id:
        raise ValueError("No notarization request has been made for this notice yet")

    from rentshield.esign.orchestrator import check_signing_status

    status = check_signing_status(notice.esign_provider, notice.esign_external_id)

    notice.esign_status = status["status"]
    notice.esign_signed_document_url = status.get("signed_document_url")
    notice.save(update_fields=["esign_status", "esign_signed_document_url"])
    return {
        "provider": notice.esign_provider,
        "status": status["status"],
        "signed_document_url": status.get("signed_document_url"),
    }
