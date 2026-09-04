# Orchestration for RentShield notices, now that they are real
# paperless-ngx Documents (see custom_fields.py) instead of rows in a
# separate rentshield_notice table. Every function here operates on
# plain dicts of notice fields and/or a Document id -- there is no
# Notice model anymore. Ported from the old rentshield/services.py,
# same behavior, different storage.
from __future__ import annotations

import tempfile
from datetime import datetime
from pathlib import Path
from time import mktime

import pathvalidate
from django.conf import settings
from documents.data_models import ConsumableDocument
from documents.data_models import DocumentMetadataOverrides
from documents.data_models import DocumentSource
from documents.models import CustomField
from documents.models import CustomFieldInstance
from documents.models import Document
from documents.models import Tag
from documents.rentshield.constants import ALL_REASONS
from documents.rentshield.constants import notice_period_days
from documents.rentshield.custom_fields import RENTSHIELD_TAG_NAME
from documents.rentshield.custom_fields import key_to_id_map
from documents.rentshield.notice_builder import build_notice
from documents.rentshield.pdf import render_notice_pdf
from documents.rentshield.pricing import calculate_total
from documents.tasks import consume_file


def notice_to_builder_input(fields: dict) -> dict:
    return {
        "landlord_name": fields.get("landlord_name"),
        "tenant_name": fields.get("tenant_name"),
        "property_type": fields.get("property_type"),
        "unit_no": fields.get("unit_no"),
        "building_name": fields.get("building_name"),
        "plot_number": fields.get("plot_number"),
        "ejari_number": fields.get("ejari_number"),
        "notice_date": fields.get("notice_date"),
        "reason": fields.get("reason"),
    }


def _custom_fields_payload(fields: dict) -> dict[int, object]:
    """Maps short field keys (landlord_name, reason, ...) to
    {CustomField.id: value}, skipping any key whose CustomField
    definition isn't found (shouldn't happen once the bootstrap
    migration has run, but this keeps a stale/edited field from
    hard-failing notice creation)."""
    ids = key_to_id_map()
    payload: dict[int, object] = {}
    for key, value in fields.items():
        field_id = ids.get(key)
        if field_id is not None and value is not None:
            payload[field_id] = value
    return payload


def generate_and_consume(
    fields: dict,
    owner_id: int | None = None,
    synchronous: bool = False,
) -> str | Document:
    """Renders `fields` to a real bilingual PDF and hands it to
    paperless-ngx's own consumption pipeline (the same consume_file task
    its stock upload API uses), with every notice field attached as a
    paperless-ngx CustomField value and the "RentShield Notice" tag
    applied -- so the created Document is fully self-describing and
    filterable via paperless's own stock APIs, with no separate
    rentshield table.

    By default (synchronous=False, the API view's behavior) this
    dispatches consumption via Celery and returns the task id; poll it
    via paperless-ngx's own GET /api/tasks/?task_id=... to learn the
    resulting Document id. Management commands that need the Document
    immediately (demo-data seeding, tests) can pass synchronous=True to
    call consume_file in-process instead and get the Document back
    directly -- no Celery worker required.
    """
    reason = fields["reason"]
    period_days = notice_period_days(reason)
    total_price_aed = calculate_total(
        {"notarization": bool(fields.get("add_notarization")), "ai_review": bool(fields.get("add_ai_review"))},
    )

    document_data = build_notice(notice_to_builder_input(fields))
    pdf_bytes = render_notice_pdf(document_data)

    reason_meta = ALL_REASONS.get(reason)
    reason_label = reason_meta["label"] if reason_meta else reason
    # Sanitize once and reuse everywhere -- reason labels like "Personal
    # Use / Recovery" contain characters (e.g. "/") that are unsafe as a
    # path segment; a previous version of this code only sanitized the
    # temp file's own name and passed the raw string through to
    # DocumentMetadataOverrides.filename, which paperless-ngx's consumer
    # uses to build its own working-copy path -- causing a
    # FileNotFoundError the moment a reason label contained a "/".
    doc_name = pathvalidate.sanitize_filename(f"Notice of {reason_label} - {fields.get('tenant_name')}.pdf")

    settings.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=settings.SCRATCH_DIR))
    temp_file_path = temp_dir / doc_name
    temp_file_path.write_bytes(pdf_bytes)

    t = int(mktime(datetime.now().timetuple()))
    import os

    os.utime(temp_file_path, times=(t, t))

    custom_fields_for_document = {
        **fields,
        "notice_period_days": period_days,
        "total_price_aed": total_price_aed,
    }

    tag, _ = Tag.objects.get_or_create(name=RENTSHIELD_TAG_NAME, defaults={"color": "#10b981"})

    input_doc = ConsumableDocument(
        source=DocumentSource.ApiUpload,
        original_file=temp_file_path,
    )
    overrides = DocumentMetadataOverrides(
        filename=doc_name,
        title=doc_name.removesuffix(".pdf"),
        owner_id=owner_id,
        tag_ids=[tag.id],
        custom_fields=_custom_fields_payload(custom_fields_for_document),
    )

    if synchronous:
        result = consume_file(input_doc, overrides)
        document_id = result.get("document_id") if isinstance(result, dict) else None
        if document_id is None:
            msg = f"consume_file did not produce a document (synchronous demo/test path): {result!r}"
            raise RuntimeError(msg)
        return Document.objects.get(id=document_id)

    async_task = consume_file.apply_async(
        kwargs={"input_doc": input_doc, "overrides": overrides},
    )
    return async_task.id


def _set_custom_field_value(document: Document, key: str, value: object) -> None:
    """Writes `value` onto the CustomFieldInstance for short field `key`
    on `document`, using that CustomField's own declared data_type to
    pick the correct storage column -- never assume/hardcode it, since
    e.g. esign_signing_url is a URL field, not a string field."""
    field_id = key_to_id_map().get(key)
    if field_id is None:
        return
    custom_field = CustomField.objects.get(id=field_id)
    value_field_name = CustomFieldInstance.get_value_field_name(data_type=custom_field.data_type)
    CustomFieldInstance.objects.update_or_create(
        document=document,
        field_id=field_id,
        defaults={value_field_name: value},
    )


def run_ai_review(document: Document, use_deepseek_ocr: bool = False) -> dict:
    """Runs the AI compliance-review pipeline against `document`'s own
    file: extracts text (docling-service, or deepseek-ocr-service for a
    hard scan), builds the Article-25 citation graph against it
    (documents.rentshield.citation_graph), and writes the result back
    onto that same Document's own CustomFieldInstance rows -- a
    human-readable summary plus a findings count -- then swaps its
    "Needs AI Review" tag for "AI-Reviewed".

    Runs synchronously; callers on a request/response path (e.g. a
    Workflow webhook, which paperless-ngx gives only 5 seconds) must
    dispatch this via a Celery task instead of calling it directly --
    see documents.tasks.run_ai_review_task.
    """
    from documents.rentshield.custom_fields import AI_REVIEWED_TAG_NAME
    from documents.rentshield.custom_fields import NEEDS_AI_REVIEW_TAG_NAME
    from documents.rentshield.document_analysis import analyze_document
    from documents.rentshield.citation_graph import build_citation_graph

    content = document.source_path.read_bytes()
    result = analyze_document(
        document.original_filename or document.filename or "document",
        content,
        document.mime_type,
        use_deepseek_ocr=use_deepseek_ocr,
    )
    graph = build_citation_graph(result.get("text"))

    findings = [edge for edge in graph["edges"] if edge["relation"] in ("satisfies", "violates")]
    if findings:
        lines = [
            f"{'✓' if edge['relation'] == 'satisfies' else '✗'} {edge.get('note', edge['to'])}"
            for edge in findings
        ]
        summary = "\n".join(lines)
    else:
        summary = "No notice-period or service-method clauses were detected in this document."
    if graph.get("ejari_number"):
        summary += f"\n\nEjari No. found: {graph['ejari_number']}"

    _set_custom_field_value(document, "ai_review_summary", summary)
    _set_custom_field_value(document, "ai_review_findings_count", graph["violation_count"])

    needs_review_tag = Tag.objects.filter(name=NEEDS_AI_REVIEW_TAG_NAME).first()
    if needs_review_tag:
        document.tags.remove(needs_review_tag)
    reviewed_tag, _ = Tag.objects.get_or_create(
        name=AI_REVIEWED_TAG_NAME,
        defaults={"color": "#059669"},
    )
    document.tags.add(reviewed_tag)

    return {
        "summary": summary,
        "violation_count": graph["violation_count"],
        "has_violation": graph["has_violation"],
    }


def read_notice_fields(document: Document) -> dict:
    """Reads a Document's RentShield CustomFieldInstance values back into
    a plain dict keyed by the same short field names generate_and_consume()
    accepts -- the inverse of _custom_fields_payload()."""
    id_to_key = {v: k for k, v in key_to_id_map().items()}
    fields: dict = {}
    for instance in CustomFieldInstance.objects.filter(document=document, field_id__in=id_to_key.keys()):
        fields[id_to_key[instance.field_id]] = instance.value
    return fields


def request_notarization(document: Document) -> dict:
    """Routes the notice on `document` through a real e-signature
    workflow (DocuSeal primary, OpenSign fallback) via
    documents.rentshield.esign.orchestrator, then writes the result back
    onto that Document's own CustomFieldInstance rows -- no separate
    Notice row to update. Requires the notarization add-on to have been
    selected and a landlord email to route the signing request to.
    """
    fields = read_notice_fields(document)
    if not fields.get("add_notarization"):
        raise ValueError("Notarization add-on was not selected for this notice")
    if not fields.get("landlord_email"):
        raise ValueError("A landlord email is required to route the notarization request")

    from documents.rentshield.esign.orchestrator import request_signing

    document_data = build_notice(notice_to_builder_input(fields))
    reason_meta = ALL_REASONS.get(fields.get("reason"))
    reason_label = reason_meta["label"] if reason_meta else fields.get("reason")

    result = request_signing(
        document_data,
        {
            "landlord_name": fields.get("landlord_name"),
            "landlord_email": fields.get("landlord_email"),
            "tenant_name": fields.get("tenant_name"),
            "reason_label": reason_label,
        },
    )

    for key, value in {
        "esign_provider": result["provider"],
        "esign_external_id": result["external_id"],
        "esign_signing_url": result["signing_url"],
        "esign_status": result["status"],
    }.items():
        _set_custom_field_value(document, key, value)
    return result


def check_notarization_status(document: Document) -> dict:
    """Polls whichever e-signature provider originally handled the
    request for `document` and refreshes its e-sign CustomFieldInstance
    values."""
    fields = read_notice_fields(document)
    provider = fields.get("esign_provider")
    external_id = fields.get("esign_external_id")
    if not provider or not external_id:
        raise ValueError("No notarization request has been made for this notice yet")

    from documents.rentshield.esign.orchestrator import check_signing_status

    status = check_signing_status(provider, external_id)

    updates = {"esign_status": status["status"]}
    if status.get("signed_document_url"):
        updates["esign_signed_document_url"] = status["signed_document_url"]
    for key, value in updates.items():
        _set_custom_field_value(document, key, value)
    return {
        "provider": provider,
        "status": status["status"],
        "signed_document_url": status.get("signed_document_url"),
    }
