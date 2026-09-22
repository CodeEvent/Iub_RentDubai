# /admin/dashboard/ -- superuser-only System & Business Overview
# (documents/admin.py registers a proxy model so it also shows up as a
# normal entry in the admin sidebar/index, no template overrides
# needed). Docker status is a local-dev convenience only (DEBUG-gated,
# see _docker_status's own comment) -- everything else reads data
# Django already owns.
from __future__ import annotations

import json
import shutil
import subprocess

from django.conf import settings
from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import Group
from django.db.models import Count
from django.shortcuts import render
from django.utils import timezone

from documents.models import Document
from documents.models import RentShieldLoginLog
from documents.rentshield.custom_fields import AWAITING_NOTARY_PUBLIC_TAG_NAME

REPO_ROOT = settings.BASE_DIR.parent


def _docker_status() -> list[dict] | None:
    """Only meaningful in this exact local-dev setup, where Django runs
    as a bare host process alongside `docker compose`-managed containers
    -- not something a real (containerized) deployment can rely on, and
    not worth the Docker socket exposure a container-to-container check
    would need. DEBUG-gated per that. Fixed argv list, no shell=True --
    no command injection surface even though this runs from a web
    request."""
    if not settings.DEBUG:
        return None
    try:
        result = subprocess.run(
            ["docker", "compose", "ps", "--format", "json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    # docker compose ps --format json prints one JSON object per line.
    containers = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            containers.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return containers


@staff_member_required
def dashboard_view(request):
    disk_total, disk_used, disk_free = shutil.disk_usage(settings.MEDIA_ROOT)

    role_counts = (
        Group.objects.filter(name__in=["Property Owner", "Notary Public"])
        .annotate(member_count=Count("user"))
        .values("name", "member_count")
    )

    pending_notarization_count = Document.objects.filter(
        tags__name=AWAITING_NOTARY_PUBLIC_TAG_NAME,
    ).count()

    since = timezone.now() - timezone.timedelta(days=7)
    recent_uploads_by_user = (
        Document.objects.filter(added__gte=since)
        .values("owner__username")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    context = {
        **admin.site.each_context(request),
        "title": "System & Business Overview",
        "docker_containers": _docker_status(),
        "media_root": settings.MEDIA_ROOT,
        "disk_total": disk_total,
        "disk_used": disk_used,
        "disk_free": disk_free,
        "role_counts": role_counts,
        "pending_notarization_count": pending_notarization_count,
        "recent_uploads_by_user": recent_uploads_by_user,
        "recent_logins": RentShieldLoginLog.objects.select_related("user")[:10],
    }
    return render(request, "admin/rentshield_dashboard.html", context)
