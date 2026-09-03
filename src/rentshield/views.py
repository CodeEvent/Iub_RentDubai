from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from rentshield.constants import ALL_REASONS
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
