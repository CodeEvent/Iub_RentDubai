# Client for a self-hosted DocuSeal instance (https://github.com/docusealco/docuseal).
# Endpoint shapes below are taken directly from DocuSeal's own committed
# API docs (docs/api/nodejs.md, docs/openapi.json in that repo) — not
# guessed. Self-hosted DocuSeal mounts its public API under the same
# `/api` namespace api.docuseal.com uses, so DOCUSEAL_URL should point at
# the app root (e.g. http://docuseal:3000), not a subdomain.
# Ported 1:1 from legacy-v1/api/src/services/esign/docusealClient.js.
from __future__ import annotations

import os

import requests

DOCUSEAL_URL = os.environ.get("DOCUSEAL_URL", "http://localhost:3000")
DOCUSEAL_API_TOKEN = os.environ.get("DOCUSEAL_API_TOKEN", "")


def _docuseal_fetch(path: str, method: str = "GET", json: dict | None = None) -> dict:
    res = requests.request(
        method,
        f"{DOCUSEAL_URL}/api{path}",
        json=json,
        headers={"Content-Type": "application/json", "X-Auth-Token": DOCUSEAL_API_TOKEN},
        timeout=30,
    )
    body = res.json() if res.content else {}
    if not res.ok:
        raise RuntimeError(body.get("error") or f"DocuSeal API returned {res.status_code}")
    return body


# Creates a one-off signing request straight from HTML — no template
# pre-creation step needed, which fits a platform that already renders
# the notice as HTML for the browser preview.
def create_html_submission(name: str, html: str, submitter_name: str, submitter_email: str) -> dict:
    submitters = _docuseal_fetch(
        "/submissions/html",
        method="POST",
        json={
            "name": name,
            "send_email": True,
            "documents": [{"name": name, "html": html}],
            "submitters": [{"role": "Landlord", "name": submitter_name, "email": submitter_email}],
        },
    )

    submitter = submitters[0] if isinstance(submitters, list) else (submitters or {}).get("submitters", [None])[0]
    if not submitter:
        raise RuntimeError("DocuSeal did not return a submitter for the created submission")

    return {
        "provider": "docuseal",
        "external_id": str(submitter.get("submission_id") or submitter.get("id")),
        "signing_url": submitter.get("embed_src") or submitter.get("url"),
        "status": "pending",
    }


def get_submission_status(external_id: str) -> dict:
    submission = _docuseal_fetch(f"/submissions/{external_id}")
    completed = bool(submission.get("completed_at"))
    documents_res = _docuseal_fetch(f"/submissions/{external_id}/documents") if completed else None

    if submission.get("archived_at"):
        status = "archived"
    elif completed:
        status = "completed"
    else:
        status = "pending"

    signed_document_url = None
    if documents_res and documents_res.get("documents"):
        signed_document_url = documents_res["documents"][0].get("url")

    return {"status": status, "signed_document_url": signed_document_url}
