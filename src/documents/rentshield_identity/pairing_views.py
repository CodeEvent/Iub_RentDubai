# "Scan to sign in" -- lets the native Android/iOS app authenticate by
# scanning a QR code shown on identity-verification.component.ts,
# instead of typing a username/password on the phone. See
# DevicePairingCode's own docstring (models.py) for the full security
# reasoning; the short version is: the code has 192 bits of entropy, is
# single-use, and expires in PAIRING_CODE_TTL, so pair_claim_view can
# safely be AllowAny (the phone has no account yet at that point) --
# claiming one only ever grants the same DRF auth Token a normal
# password login already would.
from __future__ import annotations

import base64
import secrets
from datetime import timedelta
from io import BytesIO
from urllib.parse import urlencode

import qrcode
from django.conf import settings
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from documents.rentshield_identity.models import DevicePairingCode

PAIRING_CODE_TTL = timedelta(minutes=5)


def _is_live(pairing: DevicePairingCode) -> bool:
    return pairing.created_at >= timezone.now() - PAIRING_CODE_TTL


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pair_start_view(request):
    """POST /api/documents/identity/pair/start/ -- the web page calls
    this when the property owner reaches the "download the app" step.
    Any of this user's still-pending codes are invalidated first: only
    one QR should ever be live at a time, otherwise an old, already-
    displayed QR would keep working after the page generated a fresh
    one (e.g. on a page reload)."""
    DevicePairingCode.objects.filter(
        user=request.user, status=DevicePairingCode.Status.PENDING,
    ).delete()

    code = secrets.token_urlsafe(24)
    pairing = DevicePairingCode.objects.create(user=request.user, code=code)

    # The app needs both the server to talk to and the code -- it has
    # no other way to know which RentShield instance this is, unlike a
    # user typing a server URL in by hand on first login. A real URI
    # (not a hand-split "a:b:c" string) so the query string survives a
    # server URL that itself contains a colon (e.g. "https://host:8000")
    # -- and it's a real custom scheme, so it can later double as an
    # actual Android App Link / iOS Universal Link for "tap to open the
    # app" when the property owner is already on their phone, not just
    # a QR to scan cross-device.
    server = request.build_absolute_uri("/").rstrip("/")
    qr_payload = "rentshieldpair://pair?" + urlencode({"server": server, "code": code})
    qr_image = qrcode.make(qr_payload)
    buffer = BytesIO()
    qr_image.save(buffer, format="PNG")
    qr_data_uri = "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")

    return Response(
        {
            "code": code,
            "qr_data_uri": qr_data_uri,
            "expires_at": pairing.created_at + PAIRING_CODE_TTL,
            # None when unset (see settings.RENTSHIELD_ANDROID_APK_URL's
            # own comment on why there's no real default here) -- the
            # frontend hides the download button rather than link
            # somewhere fake.
            "apk_url": settings.RENTSHIELD_ANDROID_APK_URL or None,
        },
    )


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def pair_status_view(request):
    """GET /api/documents/identity/pair/status/ -- the web page polls
    this (same pattern as verification_status_view) while showing the
    QR, so it can automatically switch to "continue on your phone" the
    moment the app scans it, with no action needed on the desktop side.
    Scoped to request.user, not the code itself, so nobody who merely
    sees the QR/code on someone else's screen can query its status."""
    pairing = DevicePairingCode.objects.filter(user=request.user).order_by("-created_at").first()
    if not pairing:
        return Response({"status": None})
    if pairing.status == DevicePairingCode.Status.PENDING and not _is_live(pairing):
        return Response({"status": "expired"})
    return Response({"status": pairing.status})


@api_view(["POST"])
@permission_classes([AllowAny])
def pair_claim_view(request):
    """POST /api/documents/identity/pair/claim/ -- called by the app
    right after it scans the QR. AllowAny is correct here, not a
    mistake: the whole point is the phone has no credentials yet, this
    is how it gets its first one. See DevicePairingCode's docstring for
    why an opaque, single-use, short-lived code makes that safe."""
    code = (request.data.get("code") or "").strip()
    if not code:
        return Response({"error": "A pairing code is required."}, status=400)

    pairing = DevicePairingCode.objects.filter(
        code=code, status=DevicePairingCode.Status.PENDING,
    ).select_related("user").first()
    if not pairing or not _is_live(pairing):
        return Response({"error": "This code is invalid or has expired -- go back and get a new QR."}, status=400)

    pairing.status = DevicePairingCode.Status.CLAIMED
    pairing.claimed_at = timezone.now()
    pairing.save(update_fields=["status", "claimed_at"])

    # Same token a password login already returns (see
    # paperless.views.PaperlessObtainAuthTokenView) -- claiming a
    # pairing code is a different way to obtain it, not a different
    # kind of access.
    token, _ = Token.objects.get_or_create(user=pairing.user)
    return Response({"token": token.key, "username": pairing.user.username})
