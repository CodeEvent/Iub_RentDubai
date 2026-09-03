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
