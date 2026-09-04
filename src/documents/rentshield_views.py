# RentShield notice-generation endpoints -- plain views living directly
# inside the documents app (not a separate installed app) and mounted
# under the documents/ URL namespace in paperless/urls.py. There is no
# rentshield database table: notice data lives as paperless-ngx
# CustomField values on a real Document (see documents/rentshield/), and
# these views are the thin, necessary plumbing paperless-ngx doesn't
# have natively -- rendering the bilingual PDF, computing pricing/
# notice-period math, and talking to DocuSeal/OpenSign. Listing notices
# and polling consumption status use paperless-ngx's own stock
# GET /api/documents/ and GET /api/tasks/ endpoints instead of anything
# bespoke -- see src-ui's rentshield-api.service.ts.
from __future__ import annotations

from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import render
from rest_framework.decorators import api_view
from rest_framework.decorators import parser_classes
from rest_framework.decorators import permission_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.models import Document
from documents.permissions import has_perms_owner_aware
from documents.rentshield.citation_graph import build_citation_graph
from documents.rentshield.constants import ALL_REASONS
from documents.rentshield.constants import BREACH_REASONS
from documents.rentshield.constants import STATUTORY_REASONS
from documents.rentshield.document_analysis import DocumentAnalysisError
from documents.rentshield.document_analysis import analyze_document
from documents.rentshield.pricing import ADD_ONS
from documents.rentshield.pricing import BASE_PRICE_AED
from documents.rentshield.roles import CanManageNotices
from documents.rentshield.service import check_notarization_status
from documents.rentshield.service import generate_and_consume
from documents.rentshield.service import request_notarization
from documents.rentshield.service_methods import SERVICE_METHODS
from documents.rentshield.skills_lib import get_skill
from documents.rentshield.skills_lib import load_skills

# Real permission gating (task 5): CanManageNotices (documents/rentshield/
# roles.py) restricts notice creation and notarization dispatch to the
# Property Owner / Admin roles; a plain IsAuthenticated gate covers the
# read-only reference endpoints any role can use. analyze_uploaded_view
# stays AllowAny -- it's an internal server-to-server webhook callback,
# not a human-facing endpoint, see its own docstring.


def _get_visible_document_or_404(request, document_id: int) -> Document:
    """Loads a Document the requesting user is actually allowed to see
    (owns it, or has an explicit/group guardian grant, or is staff/
    superuser) -- 404 rather than 403 for a document that exists but
    isn't visible, so its existence isn't leaked to someone with no
    access to it at all."""
    document = get_object_or_404(Document, id=document_id)
    user = request.user
    if not (
        getattr(user, "is_staff", False)
        or getattr(user, "is_superuser", False)
        or has_perms_owner_aware(user, "view_document", document)
    ):
        raise Http404
    return document


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanManageNotices])
def create_notice_view(request):
    """POST /api/documents/notice/create/ -- renders the bilingual
    notice to a real PDF and hands it to paperless-ngx's own
    consumption pipeline with every field attached as a CustomField
    value and the "RentShield Notice" tag applied. Returns the Celery
    task id; poll GET /api/tasks/?task_id=<id> (paperless-ngx's own
    stock endpoint) to learn the resulting Document id.
    """
    data = request.data
    if not data.get("landlord_name") or not data.get("tenant_name"):
        return Response({"error": "Landlord name and tenant name are required"}, status=400)
    if not data.get("reason") or data["reason"] not in ALL_REASONS:
        return Response({"error": "A recognized reason is required"}, status=400)
    if not data.get("notice_date"):
        return Response({"error": "A notice date is required"}, status=400)
    if bool(data.get("add_notarization")) and not data.get("landlord_email"):
        return Response({"error": "A landlord email is required when Notarization is selected."}, status=400)

    fields = {
        "landlord_name": data.get("landlord_name"),
        "landlord_email": data.get("landlord_email"),
        "tenant_name": data.get("tenant_name"),
        "property_type": data.get("property_type") or "Apartment",
        "unit_no": data.get("unit_no"),
        "building_name": data.get("building_name"),
        "plot_number": data.get("plot_number"),
        "ejari_number": data.get("ejari_number"),
        "notice_date": data.get("notice_date"),
        "reason": data.get("reason"),
        "add_notarization": bool(data.get("add_notarization")),
        "add_ai_review": bool(data.get("add_ai_review")),
    }
    task_id = generate_and_consume(fields, owner_id=request.user.id)
    return Response({"task_id": task_id})


def reasons_view(request):
    return JsonResponse({"reasons": ALL_REASONS})


def pricing_view(request):
    return JsonResponse({"base_price_aed": BASE_PRICE_AED, "add_ons": ADD_ONS})


def landing_view(request):
    """GET /welcome/ -- the one page in this project deliberately NOT
    behind paperless-ngx's login_required gate (see paperless/urls.py):
    a public marketing page for prospective users, styled with
    paperless-ngx's own static/base.css color tokens rather than
    Angular's SCSS pipeline, since it has to render before Angular
    (and its login-gated index.html) ever loads. All reasons/pricing
    shown are the real values from documents/rentshield/constants.py
    and pricing.py -- nothing here is invented copy independent of what
    the product actually does.
    """
    return render(
        request,
        "rentshield/landing.html",
        {
            "statutory_reasons": list(STATUTORY_REASONS.values()),
            "breach_reasons": list(BREACH_REASONS.values()),
            "base_price_aed": BASE_PRICE_AED,
            "add_ons": ADD_ONS,
        },
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanManageNotices])
@parser_classes([MultiPartParser])
def analyze_document_view(request):
    """POST /api/documents/notice/analyze/ -- structured extraction for
    an uploaded tenancy contract, via docling-service (default) or
    deepseek-ocr-service (pass use_deepseek_ocr=true for a hard scan),
    plus the citation-graph analysis run directly against the extracted
    text -- clauses linked to the specific Article 25 provision they
    satisfy or violate.
    """
    upload = request.FILES.get("file")
    if not upload:
        return Response({"error": "No file uploaded"}, status=400)

    use_deepseek_ocr = str(request.data.get("use_deepseek_ocr", "")).lower() == "true"

    try:
        result = analyze_document(
            upload.name,
            upload.read(),
            upload.content_type or "application/octet-stream",
            use_deepseek_ocr=use_deepseek_ocr,
        )
    except DocumentAnalysisError as exc:
        return Response({"error": str(exc)}, status=502)

    result["citation_graph"] = build_citation_graph(result.get("text"))
    return Response(result)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def legal_skills_view(request):
    """GET /api/documents/notice/legal-skills/ -- summaries only (id,
    title, jurisdiction, practice_area), for a picker/suggestion list.
    """
    summaries = [
        {"id": s.get("id"), "title": s.get("title"), "jurisdiction": s.get("jurisdiction"), "practice_area": s.get("practice_area")}
        for s in load_skills()
    ]
    return Response({"skills": summaries})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def legal_skill_detail_view(request, skill_id: str):
    """GET /api/documents/notice/legal-skills/<id>/ -- full guidance
    text + disclaimer."""
    skill = get_skill(skill_id)
    if not skill:
        return Response({"error": "Skill not found"}, status=404)
    return Response({"skill": skill})


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def check_service_method_view(request):
    """POST /api/documents/notice/check-service-method/
    {"method": "..."} -- whether a notice-service method satisfies
    Article 25(3)."""
    method_key = request.data.get("method")
    method = SERVICE_METHODS.get(method_key)
    if not method:
        return Response(
            {"error": f'Unknown method "{method_key}". Valid values: {", ".join(SERVICE_METHODS)}'},
            status=400,
        )

    return Response(
        {
            "method": method["label"],
            "is_valid_under_article_25_3": method["valid"],
            "note": (
                "Recognized under Article 25(3) -- keep the notarized certificate / registered-mail "
                "receipt / bailiff report as proof of service for any later RDSC filing."
                if method["valid"]
                else (
                    "Not one of the three methods Article 25(3) recognizes. A notice served this way is "
                    "likely to be challenged as invalid -- re-serve using a Notary Public, registered mail, "
                    "or a court bailiff."
                )
            ),
        },
    )


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanManageNotices])
def notarize_view(request, document_id: int):
    """POST /api/documents/notice/<document_id>/notarize/ -- routes the
    notice on this Document through a real e-signature workflow
    (DocuSeal primary, OpenSign fallback)."""
    document = _get_visible_document_or_404(request, document_id)
    try:
        result = request_notarization(document)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001 - both providers failed; surface why
        return Response({"error": str(exc)}, status=502)
    return Response(
        {
            "provider": result["provider"],
            "status": result["status"],
            "signing_url": result["signing_url"],
        },
    )


@api_view(["POST"])
@permission_classes([AllowAny])
def analyze_uploaded_view(request):
    """POST /api/documents/notice/analyze-uploaded/ {"doc_id": <id>} --
    dispatches the AI compliance-review pipeline for an EXISTING
    paperless-ngx Document (already uploaded through paperless-ngx's own
    native uploader -- no file in this request) and returns immediately
    with a Celery task id. This is what the "AI suggestions on uploaded
    contracts" Workflow's webhook action calls (see
    manage.py create_rentshield_workflows); paperless-ngx's own Workflow
    webhooks time out after 5 seconds, so this must not do the actual
    docling-service call inline -- see documents.tasks.run_ai_review_task.

    Deliberately still AllowAny (task 5 wired real role gating into every
    other endpoint in this file, but not this one): the caller is
    paperless-ngx's own Celery worker calling back into this same Django
    process via settings.RENTSHIELD_INTERNAL_URL, not a human, so there's
    no user session to authenticate. It's scoped to a single, narrow
    action (queue AI review for a doc id that must already exist) rather
    than exposing anything readable/writable beyond that.
    """
    from documents.tasks import run_ai_review_task

    doc_id = request.data.get("doc_id") or request.data.get("document_id")
    if not doc_id:
        return Response({"error": "doc_id is required"}, status=400)
    get_object_or_404(Document, id=doc_id)  # 404 early rather than queuing a task for nothing

    use_deepseek_ocr = str(request.data.get("use_deepseek_ocr", "")).lower() == "true"
    async_task = run_ai_review_task.apply_async(
        kwargs={"document_id": int(doc_id), "use_deepseek_ocr": use_deepseek_ocr},
    )
    return Response({"task_id": async_task.id})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notarize_status_view(request, document_id: int):
    """GET /api/documents/notice/<document_id>/notarize-status/ --
    refreshes the signing status from whichever provider originally
    handled the request. Read-only, so any role that can already see the
    document (Property Owner who owns it, Notary/Lawyer via their
    Workflow-granted object permissions, Admin) can check it -- not
    limited to CanManageNotices like creating/dispatching."""
    document = _get_visible_document_or_404(request, document_id)
    try:
        result = check_notarization_status(document)
    except ValueError as exc:
        return Response({"error": str(exc)}, status=400)
    except Exception as exc:  # noqa: BLE001
        return Response({"error": str(exc)}, status=502)
    return Response(result)
