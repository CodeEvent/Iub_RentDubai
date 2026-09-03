from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.decorators import api_view
from rest_framework.decorators import parser_classes
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from rentshield.constants import ALL_REASONS
from rentshield.document_analysis import DocumentAnalysisError
from rentshield.document_analysis import analyze_document
from rentshield.models import Notice
from rentshield.pricing import ADD_ONS
from rentshield.pricing import BASE_PRICE_AED
from rentshield.serializers import NoticeDetailSerializer
from rentshield.serializers import NoticeSerializer
from rentshield.services import check_consume_status
from rentshield.services import generate_and_consume


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
    deepseek-ocr-service (pass use_deepseek_ocr=true for a hard scan).
    Returns raw extracted text/markdown/tables; running that back through
    shared/complianceCheck.js- or citationGraph.js-style clause detection
    is a follow-on (see the root README) — this endpoint's job is real
    text extraction only.
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

    return Response(result)
