from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.decorators import api_view
from rest_framework.decorators import parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from rentshield.citation_graph import build_citation_graph
from rentshield.constants import ALL_REASONS
from rentshield.document_analysis import DocumentAnalysisError
from rentshield.document_analysis import analyze_document
from rentshield.models import Notice
from rentshield.pricing import ADD_ONS
from rentshield.pricing import BASE_PRICE_AED
from rentshield.serializers import NoticeDetailSerializer
from rentshield.serializers import NoticeSerializer
from rentshield.service_methods import SERVICE_METHODS
from rentshield.services import check_consume_status
from rentshield.services import generate_and_consume
from rentshield.skills import get_skill
from rentshield.skills import load_skills


class NoticeViewSet(viewsets.ModelViewSet):
    """CRUD for generated notices, mirroring legacy-v1's
    api/src/routes/notices.js — same fields, same pricing math, but
    every notice now becomes a real paperless-ngx Document (OCR,
    full-text search, tags) via services.generate_and_consume() instead
    of being written to a bespoke SQLite table with a detached file.

    Deliberately AllowAny for now (Phase 1 scope): paperless-ngx's own
    auth (django-allauth / DRF token auth) governs the rest of the app;
    wiring rentshield into it is Phase 2, not silently skipped.
    """

    queryset = Notice.objects.all()
    permission_classes = [AllowAny]

    def get_serializer_class(self):
        if self.action in ("retrieve",):
            return NoticeDetailSerializer
        return NoticeSerializer

    def perform_create(self, serializer):
        notice = serializer.save()
        owner = self.request.user if self.request.user.is_authenticated else None
        generate_and_consume(notice, owner_id=owner.id if owner else None)

    @action(detail=True, methods=["get"], url_path="consume-status")
    def consume_status(self, request, pk=None):
        notice = self.get_object()
        return Response(check_consume_status(notice))


def reasons_view(request):
    from django.http import JsonResponse

    return JsonResponse({"reasons": ALL_REASONS})


def pricing_view(request):
    from django.http import JsonResponse

    return JsonResponse({"base_price_aed": BASE_PRICE_AED, "add_ons": ADD_ONS})


@api_view(["POST"])
@parser_classes([MultiPartParser])
def analyze_document_view(request):
    """POST /api/rentshield/documents/analyze/ — structured extraction
    for an uploaded tenancy contract, via docling-service (default) or
    deepseek-ocr-service (pass use_deepseek_ocr=true for a hard scan),
    plus the citation-graph analysis (citation_graph.py) run directly
    against the extracted text — clauses linked to the specific Article
    25 provision they satisfy or violate, same as legacy-v1's
    /api/documents/analyze response shape.
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
def legal_skills_view(request):
    """GET /api/rentshield/legal-skills/ — summaries only (id, title,
    jurisdiction, practice_area), for a picker/suggestion list. Mirrors
    the MCP list_legal_skills tool and legacy-v1's GET /api/legal-skills.
    """
    summaries = [
        {"id": s.get("id"), "title": s.get("title"), "jurisdiction": s.get("jurisdiction"), "practice_area": s.get("practice_area")}
        for s in load_skills()
    ]
    return Response({"skills": summaries})


@api_view(["GET"])
def legal_skill_detail_view(request, skill_id: str):
    """GET /api/rentshield/legal-skills/<id>/ — full guidance text +
    disclaimer. Mirrors the MCP get_legal_skill tool and legacy-v1's
    GET /api/legal-skills/:id.
    """
    skill = get_skill(skill_id)
    if not skill:
        return Response({"error": "Skill not found"}, status=404)
    return Response({"skill": skill})


@api_view(["POST"])
def check_service_method_view(request):
    """POST /api/rentshield/check-service-method/ {"method": "..."} —
    whether a notice-service method satisfies Article 25(3). Mirrors the
    MCP check_notice_service_method_validity tool, built on the same
    SERVICE_METHODS table citation_graph.py uses.
    """
    method_key = request.data.get("method")
    method = SERVICE_METHODS.get(method_key)
    if not method:
        return Response(
            {"error": f'Unknown method "{method_key}". Valid values: {", ".join(SERVICE_METHODS)}'},
            status=400,
        )

    return Response({
        "method": method["label"],
        "is_valid_under_article_25_3": method["valid"],
        "note": (
            "Recognized under Article 25(3) — keep the notarized certificate / registered-mail "
            "receipt / bailiff report as proof of service for any later RDSC filing."
            if method["valid"]
            else (
                "Not one of the three methods Article 25(3) recognizes. A notice served this way is "
                "likely to be challenged as invalid — re-serve using a Notary Public, registered mail, "
                "or a court bailiff."
            )
        ),
    })
