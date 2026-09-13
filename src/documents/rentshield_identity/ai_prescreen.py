# AI pre-screening for the Notary Public review queue -- Claude reads
# everything the automated pipeline already gathered (OCR vs. chip
# cross-check, both independent face-match scores, Idswyft's own
# result) and writes a short, plain-language summary of anything worth
# double-checking. Advisory only: this never sets `status`, never
# blocks a review, and is always labeled as AI-generated wherever it's
# shown -- the Notary Public remains the only one who can mark a
# verification VERIFIED (see models.py's docstring). This is a genuine
# first for this codebase: the existing "AI Compliance Review" add-on
# (documents.rentshield.service.run_ai_review) is a deterministic
# citation-graph/rules engine, not an LLM call -- there was no
# pre-existing Claude/Anthropic integration anywhere to build on.
from __future__ import annotations

import logging
import os

import anthropic

from documents.rentshield_identity.models import IdentityVerification

logger = logging.getLogger("paperless.rentshield")

# Per this project's own Claude API guidance: default to Opus for
# quality unless there's a specific reason to trade down -- cost is the
# user's call to make, not a default I pick for them. A Notary review
# happens at most a few times a day per property owner, so per-call
# cost here is negligible either way.
MODEL = os.environ.get("RENTSHIELD_AI_PRESCREEN_MODEL", "claude-opus-5")

_SYSTEM_PROMPT = """You are assisting a human Notary Public who reviews identity \
verifications for a Dubai tenancy-notice platform. You will be given structured \
data already gathered by an automated pipeline: what the property owner declared \
on the web (typed on a keyboard, before ever touching a document -- their own \
claimed passport/ID details), OCR text read from a photographed ID document, text \
read directly off the document's own NFC chip, two independent face-match \
similarity scores, and the automated document-verification result. A short \
confirmation video also exists for the Notary to watch separately -- you have not \
seen it and must never imply otherwise.

Compare the three data sources (declared, card photo OCR, NFC chip) yourself and \
describe anything inconsistent, borderline, or worth a closer look, in plain \
language (3-5 sentences) -- and say plainly if everything looks consistent. An \
automated cross-check between these same sources is also given to you; use it as \
a starting point, not a substitute for your own reading of the raw fields -- a \
plain string mismatch can still be an actual match (e.g. word order, a missing \
middle name, transliteration).

Then, on its own final line, give your own assessed likely outcome starting \
exactly with "Likely outcome:", using exactly one of these three labels: \
"Consistent -- no concerns found", "Minor inconsistency -- worth a second look", \
or "Significant inconsistency -- recommend close review". This is YOUR assessment \
for the Notary to weigh, not a decision -- never use the words "verified", \
"approved", or "rejected", and never imply the outcome is already decided; the \
Notary alone decides. If a field is missing or a match score is null, say so \
rather than guessing why."""


class AiPrescreenError(Exception):
    pass


def _build_user_message(record: IdentityVerification) -> str:
    def line(label: str, value) -> str:
        return f"{label}: {value if value not in (None, '') else '(not available)'}"

    return "\n".join(
        [
            line("Declared document type (typed on the web, before any capture)", record.declared_document_type),
            line("Declared document number", record.declared_document_number),
            line("Declared date of birth", record.declared_date_of_birth),
            line("Card photo OCR -- name", record.card_ocr_full_name),
            line("Card photo OCR -- date of birth", record.card_ocr_date_of_birth),
            line("Card photo OCR -- document number", record.card_ocr_document_number),
            line("NFC chip -- name", record.chip_full_name),
            line("NFC chip -- date of birth", record.chip_date_of_birth),
            line("NFC chip -- document number", record.chip_document_number),
            line(
                "Automated cross-check notes (declared vs. card photo OCR vs. chip)",
                record.identity_mismatch_notes or "no mismatch flagged",
            ),
            line("Idswyft's own card-photo-vs-selfie result", record.automated_result),
            line(
                "Independent chip-photo-vs-selfie similarity (0-1, ~0.36+ suggests same person)",
                record.chip_selfie_match_score,
            ),
            line(
                "Confirmation video",
                "recorded and available for the Notary to watch (not analyzed here)" if record.video else None,
            ),
        ],
    )


def summarize_for_notary(record: IdentityVerification) -> str:
    """Returns a short advisory summary, or raises AiPrescreenError -- the
    caller (the Celery task) is expected to log and swallow that, same
    "never block the pipeline on an optional extra" pattern as
    face_match.py's own error handling."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise AiPrescreenError("ANTHROPIC_API_KEY is not configured")

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(record)}],
        )
    except anthropic.APIError as exc:
        raise AiPrescreenError(str(exc)) from exc

    text = "".join(block.text for block in response.content if block.type == "text").strip()
    if not text:
        raise AiPrescreenError("Claude returned no text content")
    return text
