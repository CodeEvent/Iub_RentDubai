# Orchestrates the two e-signature engines behind one interface, so the
# "Notarization Service" add-on actually routes the generated notice
# through a real signing workflow instead of just charging for it.
#
# Combines DocuSeal and OpenSign as primary + fallback rather than
# picking one: if the primary self-hosted instance is unreachable or
# misconfigured, the request is retried against the other before it's
# reported as failed. Either can also be pinned outright via
# ESIGN_PRIMARY / ESIGN_FALLBACK.
# Ported 1:1 from legacy-v1/api/src/services/esign/index.js.
from __future__ import annotations

import os

from rentshield.esign import docuseal_client
from rentshield.esign import opensign_client
from rentshield.pdf import render_notice_html
from rentshield.pdf import render_notice_pdf

ESIGN_PRIMARY = os.environ.get("ESIGN_PRIMARY", "docuseal")
ESIGN_FALLBACK = os.environ.get("ESIGN_FALLBACK", "opensign")


def _run_provider(provider: str, document: dict, notice_context: dict) -> dict:
    name = f'Notice of {notice_context["reason_label"]} — {notice_context["tenant_name"]}'

    if provider == "docuseal":
        html = render_notice_html(document, include_signature_field=True)
        return docuseal_client.create_html_submission(
            name, html, notice_context["landlord_name"], notice_context["landlord_email"]
        )
    if provider == "opensign":
        pdf_bytes = render_notice_pdf(document)
        return opensign_client.create_document_submission(
            name, pdf_bytes, notice_context["landlord_name"], notice_context["landlord_email"]
        )
    raise RuntimeError(f'Unknown e-signature provider "{provider}"')


# notice_context must include landlord_email — the field the Notice
# model doesn't require (nullable), but notarization needs to route the
# signing request somewhere; see views.py's 400 when it's missing.
def request_signing(document: dict, notice_context: dict) -> dict:
    try:
        return _run_provider(ESIGN_PRIMARY, document, notice_context)
    except Exception as primary_err:  # noqa: BLE001 - re-raised with combined context below
        if not ESIGN_FALLBACK or ESIGN_FALLBACK == ESIGN_PRIMARY:
            raise RuntimeError(
                f"{ESIGN_PRIMARY} failed and no distinct fallback is configured: {primary_err}"
            ) from primary_err
        try:
            return _run_provider(ESIGN_FALLBACK, document, notice_context)
        except Exception as fallback_err:  # noqa: BLE001
            raise RuntimeError(
                f"Both e-signature providers failed. {ESIGN_PRIMARY}: {primary_err}. "
                f"{ESIGN_FALLBACK}: {fallback_err}"
            ) from fallback_err


def check_signing_status(provider: str, external_id: str) -> dict:
    if provider == "docuseal":
        return docuseal_client.get_submission_status(external_id)
    if provider == "opensign":
        return opensign_client.get_document_status(external_id)
    raise RuntimeError(f'Unknown e-signature provider "{provider}"')
