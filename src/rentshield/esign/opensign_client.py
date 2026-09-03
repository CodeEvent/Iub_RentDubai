# Client for a self-hosted OpenSign instance (https://github.com/opensignlabs/OpenSign).
# OpenSign's backend is a Parse Server app (Node/MongoDB) mounted at
# `/app` by default (apps/OpenSignServer/index.js: `PARSE_MOUNT || '/app'`),
# exposing the standard Parse REST API plus OpenSign's own Cloud
# Functions. Shapes below (contracts_Document fields, the
# `createdocumentfromapp` Cloud Function, and the `contracts_Contactbook`
# pointer class) were read directly out of that repo's
# `cloud/parsefunction/*.js`, not guessed from marketing docs.
# Ported 1:1 from legacy-v1/api/src/services/esign/opensignClient.js.
from __future__ import annotations

import json
import os
from urllib.parse import quote

import requests

OPENSIGN_URL = os.environ.get("OPENSIGN_URL", "http://localhost:8080")
OPENSIGN_APP_ID = os.environ.get("OPENSIGN_APP_ID", "")
OPENSIGN_MASTER_KEY = os.environ.get("OPENSIGN_MASTER_KEY", "")
# Parse _User objectId of the service/admin account that owns documents
# created by this integration — a one-time setup value, documented in
# the root README, not something end users of RentShield ever see.
OPENSIGN_SERVICE_USER_ID = os.environ.get("OPENSIGN_SERVICE_USER_ID", "")


def _parse_headers(extra: dict | None = None) -> dict:
    return {
        "X-Parse-Application-Id": OPENSIGN_APP_ID,
        "X-Parse-Master-Key": OPENSIGN_MASTER_KEY,
        "Content-Type": "application/json",
        **(extra or {}),
    }


def _parse_fetch(path: str, method: str = "GET", json_body: dict | None = None) -> dict:
    res = requests.request(
        method,
        f"{OPENSIGN_URL}/app{path}",
        json=json_body,
        headers=_parse_headers(),
        timeout=30,
    )
    body = res.json() if res.content else {}
    if not res.ok:
        raise RuntimeError(body.get("error") or f"OpenSign API returned {res.status_code}")
    return body


def _find_or_create_contact(email: str, name: str) -> str:
    query = json.dumps({
        "Email": email,
        "CreatedBy": {"__type": "Pointer", "className": "_User", "objectId": OPENSIGN_SERVICE_USER_ID},
    })
    existing = _parse_fetch(f"/classes/contracts_Contactbook?where={quote(query)}&limit=1")
    if existing.get("results"):
        return existing["results"][0]["objectId"]

    created = _parse_fetch(
        "/classes/contracts_Contactbook",
        method="POST",
        json_body={
            "Name": name,
            "Email": email,
            "CreatedBy": {"__type": "Pointer", "className": "_User", "objectId": OPENSIGN_SERVICE_USER_ID},
        },
    )
    return created["objectId"]


def upload_file(content: bytes, filename: str, content_type: str) -> str:
    res = requests.post(
        f"{OPENSIGN_URL}/app/files/{quote(filename)}",
        data=content,
        headers={"X-Parse-Application-Id": OPENSIGN_APP_ID, "Content-Type": content_type},
        timeout=60,
    )
    body = res.json() if res.content else {}
    if not res.ok:
        raise RuntimeError(body.get("error") or f"OpenSign file upload returned {res.status_code}")
    return body["url"]


# pdf_bytes must already be a rendered PDF of the notice — OpenSign
# signs an uploaded file, it doesn't render HTML like DocuSeal does.
def create_document_submission(name: str, pdf_bytes: bytes, submitter_name: str, submitter_email: str) -> dict:
    if not OPENSIGN_SERVICE_USER_ID:
        raise RuntimeError(
            "OPENSIGN_SERVICE_USER_ID is not configured — see README for the one-time OpenSign setup step"
        )

    file_url = upload_file(pdf_bytes, f'{name.replace(" ", "-")}.pdf', "application/pdf")
    contact_id = _find_or_create_contact(submitter_email, submitter_name)
    contact_ptr = {"__type": "Pointer", "className": "contracts_Contactbook", "objectId": contact_id}

    doc = _parse_fetch(
        "/functions/createdocumentfromapp",
        method="POST",
        json_body={
            "document": {
                "Name": name,
                "URL": file_url,
                "ExtUserPtr": contact_ptr,
                "CreatedBy": {"__type": "Pointer", "className": "_User", "objectId": OPENSIGN_SERVICE_USER_ID},
                "Signers": [contact_ptr],
                "SendinOrder": False,
                "Placeholders": [
                    {
                        "Id": 1,
                        "Type": "signature",
                        "pageNumber": 1,
                        "signerPtr": contact_ptr,
                        "signerObjId": contact_id,
                        "email": submitter_email,
                        "options": {"x": 60, "y": 700, "width": 150, "height": 40},
                    }
                ],
            }
        },
    )

    result = doc.get("result", doc)
    return {
        "provider": "opensign",
        "external_id": result.get("objectId"),
        "signing_url": file_url,
        "status": "pending",
    }


def get_document_status(external_id: str) -> dict:
    doc = _parse_fetch(f"/classes/contracts_Document/{external_id}")
    if doc.get("IsCompleted"):
        status = "completed"
    elif doc.get("IsDeclined"):
        status = "declined"
    else:
        status = "pending"
    return {"status": status, "signed_document_url": doc.get("SignedUrl")}
