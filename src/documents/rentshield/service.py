# Orchestration for RentShield notices, now that they are real
# paperless-ngx Documents (see custom_fields.py) instead of rows in a
# separate rentshield_notice table. Every function here operates on
# plain dicts of notice fields and/or a Document id -- there is no
# Notice model anymore. Ported from the old rentshield/services.py,
# same behavior, different storage.
from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from time import mktime

import pathvalidate
from django.conf import settings
from django.core.mail import send_mail
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

logger = logging.getLogger("paperless.rentshield")


def _notify_legal_review_requested(fields: dict) -> None:
    """Fire-and-forget email to settings.RENTSHIELD_LEGAL_REVIEW_NOTIFY_EMAIL
    when a notice requests the Legal Review add-on -- fulfillment is
    operational (an admin reads this, filters Documents by the "Legal
    Review Requested" tag, and loops in counsel outside the app), not a
    login role or object-permission grant. Reuses paperless-ngx's own
    configured EMAIL_BACKEND -- no separate email setup. Deliberately
    silent no-op when the setting is unset (a real, expected local-dev/
    not-yet-configured state, not an error), and never lets a mail
    failure fail notice creation -- logged and swallowed instead."""
    recipient = settings.RENTSHIELD_LEGAL_REVIEW_NOTIFY_EMAIL
    if not recipient:
        logger.debug(
            "Legal Review requested but RENTSHIELD_LEGAL_REVIEW_NOTIFY_EMAIL "
            "is unset -- skipping notification email.",
        )
        return
    try:
        send_mail(
            subject="RentShield: Legal Review requested",
            message=(
                f"A notice has requested Legal Review.\n\n"
                f"Landlord: {fields.get('landlord_name')}\n"
                f"Tenant: {fields.get('tenant_name')}\n"
                f"Reason: {fields.get('reason')}\n"
                f"Notice date: {fields.get('notice_date')}\n\n"
                "Filter Documents by the \"Legal Review Requested\" tag "
                "in paperless-ngx to find it."
            ),
            from_email=None,  # falls back to settings.DEFAULT_FROM_EMAIL
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send Legal Review notification email to %r",
            recipient,
        )


def _notify_notary_fulfillment_requested(fields: dict) -> None:
    """Fire-and-forget email to
    settings.RENTSHIELD_NOTARY_FULFILLMENT_NOTIFY_EMAIL when a notice
    requests the Real Notary Public add-on -- exact same pattern as
    _notify_legal_review_requested() above: this is manual, human
    fulfillment (a real notary-services contact reads this email, then
    processes the notice through her own real-world notarization
    process, same as before this feature existed), not an API dispatch.
    She completes it using paperless-ngx's own document editor (see
    documents/rentshield/custom_fields.py's comment above
    AWAITING_NOTARY_PUBLIC_TAG_NAME), not a reply to this email or any
    bespoke UI -- this just tells her a new one is waiting. Deliberately
    silent no-op when the setting is unset, and never lets a mail
    failure fail notice creation -- logged and swallowed instead."""
    recipient = settings.RENTSHIELD_NOTARY_FULFILLMENT_NOTIFY_EMAIL
    if not recipient:
        logger.debug(
            "Real Notary Public requested but "
            "RENTSHIELD_NOTARY_FULFILLMENT_NOTIFY_EMAIL is unset -- "
            "skipping notification email.",
        )
        return
    try:
        send_mail(
            subject="RentShield: Real Notary Public requested",
            message=(
                f"A notice needs physical notarization.\n\n"
                f"Landlord: {fields.get('landlord_name')}\n"
                f"Tenant: {fields.get('tenant_name')}\n"
                f"Reason: {fields.get('reason')}\n"
                f"Notice date: {fields.get('notice_date')}\n\n"
                "Filter Documents by the \"Awaiting Notary Public\" tag "
                "in paperless-ngx to find it, or open the \"RentShield: "
                "Notary Public Queue\" saved view. Once notarized, "
                "upload the scanned/stamped copy as a normal document, "
                "then on the original notice: link it via the "
                "\"RentShield: Notarized Copy\" field, fill in "
                "\"RentShield: Notary Reference No.\", set \"RentShield: "
                "Notary Public Status\" to \"completed\", and swap the "
                "\"Awaiting Notary Public\" tag for \"Notary Public "
                "Completed\" (or \"Notary Public Rejected\" with a note "
                "in \"RentShield: Notary Notes\" if it can't be done)."
            ),
            from_email=None,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send Real Notary Public notification email to %r",
            recipient,
        )


def _notify_notice_served(document: Document) -> None:
    """Fire-and-forget email to the notice's own "RentShield: Landlord
    Email" (not a fixed settings.-level address like the two notify
    functions above -- this one has to reach a different landlord per
    notice) once documents.rentshield.signals detects the Real Notary
    Public fulfiller's manual "Notary Public Status" edit transition
    into "completed" or "rejected" -- that transition is itself the
    legal service event under Article 25(3) (see custom_fields.py's
    comment above AWAITING_NOTARY_PUBLIC_TAG_NAME), so this is the other
    half of _notify_notary_fulfillment_requested() above: that one told
    the fulfiller a request came in, this one tells the landlord it's
    done. Deliberately silent no-op when there's no landlord_email on
    this notice, and never lets a mail failure propagate -- logged and
    swallowed, same as the other two notify functions."""
    fields = read_notice_fields(document)
    recipient = fields.get("landlord_email")
    if not recipient:
        logger.debug(
            "Notice %s reached a Notary Public completion state but has "
            "no landlord_email on file -- skipping notification email.",
            document.id,
        )
        return

    status = fields.get("notary_status")
    if status == "completed":
        subject = "RentShield: Your notice has been served"
        message = (
            f"Your notice for {fields.get('tenant_name')} has been notarized "
            "and legally served on the tenant via Notary Public -- one of "
            "the recognized service methods under Article 25(3) of Law "
            "No. (33) of 2008.\n\n"
            f"Reference number: {fields.get('notary_reference_no') or '(not recorded)'}\n"
            f"Served date: {fields.get('served_date') or '(not recorded)'}\n\n"
            "The notarized copy is attached to your notice in RentShield."
        )
    else:
        subject = "RentShield: Your notice could not be notarized"
        message = (
            f"Your notice for {fields.get('tenant_name')} could not be "
            "notarized and was not served.\n\n"
            f"Notes from the notary-services contact: {fields.get('notary_notes') or '(none provided)'}\n\n"
            "Please review and resubmit if needed."
        )

    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=None,
            recipient_list=[recipient],
            fail_silently=False,
        )
    except Exception:
        logger.exception(
            "Failed to send notice-served notification email to %r for document %s",
            recipient,
            document.id,
        )


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


def write_and_consume(
    content: bytes | str,
    filename: str,
    *,
    title: str | None = None,
    owner_id: int | None = None,
    tag_ids: list[int] | None = None,
    custom_fields: dict[int, object] | None = None,
    synchronous: bool = False,
) -> str | Document:
    """Writes `content` to a sanitized temp file under settings.SCRATCH_DIR
    and hands it to paperless-ngx's own consumption pipeline (the same
    consume_file task its stock upload API uses) -- shared plumbing for
    generate_and_consume() below and manage.py create_rentshield_demo_data's
    contract-seeding helper, previously duplicated between the two.

    `filename` is sanitized here, not by the caller -- reason labels like
    "Personal Use / Recovery" contain characters (e.g. "/") that are
    unsafe as a path segment; an earlier version of this code sanitized
    only the temp file's own name and passed the raw string through to
    DocumentMetadataOverrides.filename, which paperless-ngx's consumer
    uses to build its own working-copy path -- causing a
    FileNotFoundError the moment a reason label contained a "/".

    synchronous=True calls consume_file() in-process and returns the
    resulting Document directly (raises RuntimeError if it somehow
    didn't produce one) -- what demo-data seeding and tests need.
    synchronous=False (the default, matching the real API path)
    dispatches via Celery and returns the task id instead; poll it via
    paperless-ngx's own GET /api/tasks/?task_id=...
    """
    safe_filename = pathvalidate.sanitize_filename(filename)
    settings.SCRATCH_DIR.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(tempfile.mkdtemp(dir=settings.SCRATCH_DIR))
    temp_file_path = temp_dir / safe_filename
    if isinstance(content, bytes):
        temp_file_path.write_bytes(content)
    else:
        temp_file_path.write_text(content, encoding="utf-8")

    t = int(mktime(datetime.now().timetuple()))
    os.utime(temp_file_path, times=(t, t))

    input_doc = ConsumableDocument(
        source=DocumentSource.ApiUpload,
        original_file=temp_file_path,
    )
    overrides = DocumentMetadataOverrides(
        filename=safe_filename,
        title=title or safe_filename.removesuffix(".pdf"),
        owner_id=owner_id,
        tag_ids=tag_ids or [],
        custom_fields=custom_fields or {},
    )

    if synchronous:
        result = consume_file(input_doc, overrides)
        document_id = result.get("document_id") if isinstance(result, dict) else None
        if document_id is None:
            msg = f"consume_file did not produce a document for {title or safe_filename!r}: {result!r}"
            raise RuntimeError(msg)
        return Document.objects.get(id=document_id)

    async_task = consume_file.apply_async(
        kwargs={"input_doc": input_doc, "overrides": overrides},
    )
    return async_task.id


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
        {
            "certified_esignature": bool(fields.get("add_notarization")),
            "ai_review": bool(fields.get("add_ai_review")),
            "legal_review": bool(fields.get("add_legal_review")),
            "real_notarization": bool(fields.get("add_real_notarization")),
        },
    )

    document_data = build_notice(notice_to_builder_input(fields))
    pdf_bytes = render_notice_pdf(document_data)

    reason_meta = ALL_REASONS.get(reason)
    reason_label = reason_meta["label"] if reason_meta else reason
    doc_name = f"Notice of {reason_label} - {fields.get('tenant_name')}.pdf"

    custom_fields_for_document = {
        **fields,
        "notice_period_days": period_days,
        "total_price_aed": total_price_aed,
    }

    tag, _ = Tag.objects.get_or_create(name=RENTSHIELD_TAG_NAME, defaults={"color": "#10b981"})
    tag_ids = [tag.id]

    if fields.get("add_legal_review"):
        from documents.rentshield.custom_fields import LEGAL_REVIEW_REQUESTED_TAG_NAME

        legal_review_tag, _ = Tag.objects.get_or_create(
            name=LEGAL_REVIEW_REQUESTED_TAG_NAME,
            defaults={"color": "#8b5cf6"},
        )
        tag_ids.append(legal_review_tag.id)
        _notify_legal_review_requested(fields)

    if fields.get("add_real_notarization"):
        from documents.rentshield.custom_fields import AWAITING_NOTARY_PUBLIC_TAG_NAME

        awaiting_notary_tag, _ = Tag.objects.get_or_create(
            name=AWAITING_NOTARY_PUBLIC_TAG_NAME,
            defaults={"color": "#f59e0b"},
        )
        tag_ids.append(awaiting_notary_tag.id)
        custom_fields_for_document["notary_status"] = "pending"
        _notify_notary_fulfillment_requested(fields)

    return write_and_consume(
        pdf_bytes,
        doc_name,
        owner_id=owner_id,
        tag_ids=tag_ids,
        custom_fields=_custom_fields_payload(custom_fields_for_document),
        synchronous=synchronous,
    )


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


SIGNER_TOKEN_SALT = "rentshield-signer-verify"
SIGNER_TOKEN_MAX_AGE_SECONDS = int(timedelta(days=14).total_seconds())


def _fire_signing_request(document: Document, fields: dict) -> dict:
    """The actual DocuSeal/OpenSign dispatch -- split out of
    request_notarization() below so it can be called either immediately
    (a notice whose signer already verified once before) or later, once
    signer_views.py's capture flow confirms the signer's identity."""
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


def _send_signer_verification_email(document: Document, verification) -> None:
    """Emails the notice's signer a link to RentShield's own capture
    page (Angular route /sign-verify/:token, no login -- the signer has
    no RentShield account) instead of a DocuSeal/OpenSign link directly.
    Same signed-token shape as rentshield_views.py's invite-accept link
    (django.core.signing.dumps, no separate token column to keep in
    sync) -- built from settings.PAPERLESS_URL/BASE_URL rather than a
    request.build_absolute_uri, the same way workflows/actions.py builds
    doc_url, since this fires from Celery tasks with no request in hand."""
    from urllib.parse import quote

    from django.core.signing import dumps

    token = dumps({"verification_id": verification.id}, salt=SIGNER_TOKEN_SALT)
    # A query param, not a path segment (unlike signer_views.py's own
    # API urls) -- this is an Angular route (sign-verify.component.ts),
    # and a trailing-slash path segment is one more thing for the
    # frontend router's UrlSerializer to normalize correctly; a query
    # param sidesteps that entirely, same as rentshield_views.py's own
    # invite-accept link.
    verify_url = f"{settings.PAPERLESS_URL}{settings.BASE_URL}sign-verify/?token={quote(token, safe='')}"
    send_mail(
        subject="Verify your identity to sign this notice",
        message=(
            f"You've been asked to sign a tenancy notice on RentShield.\n\n"
            "Before you can sign, confirm your identity with a quick photo ID + selfie check "
            f"(takes under a minute): {verify_url}\n\n"
            "Once you're verified, you'll receive a separate email with the actual document to sign."
        ),
        from_email=None,
        recipient_list=[verification.signer_email],
        fail_silently=False,
    )


def request_notarization(document: Document) -> dict:
    """Routes the notice on `document` through a real e-signature
    workflow (DocuSeal primary, OpenSign fallback) via
    documents.rentshield.esign.orchestrator, then writes the result back
    onto that Document's own CustomFieldInstance rows -- no separate
    Notice row to update. Requires the notarization add-on to have been
    selected and a landlord email to route the signing request to.

    Identity-verification gate (2026-09-23): DocuSeal/OpenSign's own
    email-link signing has no identity check at all -- anyone holding
    the link can sign. Rather than firing that request straight away,
    this get_or_creates a NoticeSignerVerification for the document and,
    unless it's already VERIFIED (e.g. a retried dispatch after the
    signer completed capture once), emails the signer RentShield's own
    capture link instead and returns early with an
    "awaiting_signer_verification" status -- a real, freeform STRING
    custom field (see custom_fields.py), so this is a safe value to
    write. signer_views.py's signer_upload_selfie_view is what actually
    calls _fire_signing_request() once that verification succeeds.
    """
    fields = read_notice_fields(document)
    if not fields.get("add_notarization"):
        raise ValueError("Notarization add-on was not selected for this notice")
    if not fields.get("landlord_email"):
        raise ValueError("A landlord email is required to route the notarization request")

    from documents.rentshield_identity.models import NoticeSignerVerification

    verification, _created = NoticeSignerVerification.objects.get_or_create(
        document=document,
        defaults={
            "signer_name": fields.get("landlord_name") or "",
            "signer_email": fields["landlord_email"],
        },
    )
    if verification.status != NoticeSignerVerification.Status.VERIFIED:
        _send_signer_verification_email(document, verification)
        result = {"provider": "", "external_id": "", "signing_url": "", "status": "awaiting_signer_verification"}
        _set_custom_field_value(document, "esign_status", result["status"])
        return result

    return _fire_signing_request(document, fields)


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
    sync_notarization_stage_tag(document, status["status"])
    return {
        "provider": provider,
        "status": status["status"],
        "signed_document_url": status.get("signed_document_url"),
    }


# Provider status strings (documents/rentshield/esign/docuseal_client.py,
# opensign_client.py) that mean the request is fully resolved, one way or
# the other -- everything else ("pending") is still in flight and leaves
# the "Being Notarized" tag alone. "failed" is not a real provider status;
# it's the sentinel the Celery task below passes when the DISPATCH itself
# threw (e.g. neither DocuSeal nor OpenSign was reachable at all), which
# never produced a provider status string to check here.
_NOTARIZATION_SUCCESS_STATUSES = {"completed"}
_NOTARIZATION_FAILURE_STATUSES = {"archived", "declined", "failed"}


def sync_notarization_stage_tag(document: Document, status: str) -> None:
    """Swaps the "Being Notarized" pipeline-stage tag for "Notarized" or
    "Notarization Failed" once `status` reflects a final outcome; a no-op
    for an in-flight ("pending") status. Called both right after a fresh
    dispatch (documents.tasks.run_notarization_task) and every time
    check_notarization_status() polls again later, so a request that was
    still pending at dispatch time still gets its tag corrected once
    someone (or a future scheduled check) discovers it resolved."""
    from documents.rentshield.custom_fields import BEING_NOTARIZED_TAG_NAME
    from documents.rentshield.custom_fields import NOTARIZATION_FAILED_TAG_NAME
    from documents.rentshield.custom_fields import NOTARIZED_TAG_NAME

    if status not in _NOTARIZATION_SUCCESS_STATUSES and status not in _NOTARIZATION_FAILURE_STATUSES:
        return

    being_notarized_tag = Tag.objects.filter(name=BEING_NOTARIZED_TAG_NAME).first()
    if being_notarized_tag:
        document.tags.remove(being_notarized_tag)

    final_tag_name = NOTARIZED_TAG_NAME if status in _NOTARIZATION_SUCCESS_STATUSES else NOTARIZATION_FAILED_TAG_NAME
    final_tag, _ = Tag.objects.get_or_create(
        name=final_tag_name,
        defaults={"color": "#059669" if status in _NOTARIZATION_SUCCESS_STATUSES else "#dc2626"},
    )
    document.tags.add(final_tag)
