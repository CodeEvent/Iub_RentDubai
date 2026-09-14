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
from pathlib import Path
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
from documents.rentshield_identity.models import IdentityVerification

PAIRING_CODE_TTL = timedelta(minutes=5)

# Wherever the current CI-built debug APK actually is, dropped there by
# hand after each Android build (see README) -- served as a completely
# ordinary static file (documents/static/ is already served this same
# way for the compiled frontend bundle, no new URL wiring needed).
# Overwriting this file is what makes the download link always point
# at "whatever's newest" without editing any URL/setting -- exactly the
# problem with repeatedly sending the APK as a chat attachment, where a
# phone's own stale duplicate downloads kept shadowing the real update.
_APK_STATIC_PATH = Path(settings.BASE_DIR) / "documents" / "static" / "downloads" / "rentshield-app-debug.apk"


def _apk_download_url(request) -> str | None:
    """None when the file genuinely isn't there -- settings.
    RENTSHIELD_ANDROID_APK_URL (a real Play Store/hosted link, once one
    exists) takes priority when set; otherwise falls back to this
    server's own copy so the download link works today, on the same
    LAN the phone already has to reach to scan the QR at all.

    Real bug hit live (2026-09-14): this file's own name never changes
    between rebuilds, and a phone's browser/download manager can cache
    a URL's response independent of HTTP cache-control headers -- the
    server can be serving a genuinely fresh, verified-correct APK and a
    phone still installs a stale cached one from days earlier with the
    exact same URL. `?v=<mtime>` forces a new cache key every time the
    file is actually rebuilt, without needing to keep this in sync with
    the Android project's own versionCode by hand."""
    if settings.RENTSHIELD_ANDROID_APK_URL:
        return settings.RENTSHIELD_ANDROID_APK_URL
    if not _APK_STATIC_PATH.exists():
        return None
    url = request.build_absolute_uri(settings.STATIC_URL + "downloads/rentshield-app-debug.apk")
    return f"{url}?v={int(_APK_STATIC_PATH.stat().st_mtime)}"


def _is_live(pairing: DevicePairingCode) -> bool:
    return pairing.created_at >= timezone.now() - PAIRING_CODE_TTL


def _validate_declared_document(data) -> tuple[dict, str | None]:
    """The user types these on the web -- a real keyboard, with real
    field-level validation -- specifically instead of on the app's own
    small screen, where a mistyped CAN or the card's printed serial
    number typed into the CAN field (see MainActivity.kt's onScanClicked
    comment) was this whole project's single most repeated support
    issue. Returns (fields, error) -- fields is empty when error is set,
    matching this module's existing (dict, error-or-None) convention."""
    document_type = (data.get("declared_document_type") or "").strip()
    if document_type not in ("passport", "cie"):
        return {}, 'declared_document_type must be "passport" or "cie".'

    document_number = (data.get("declared_document_number") or "").strip()
    if not document_number:
        return {}, "A document/ID number is required."

    fields = {
        "declared_document_type": document_type,
        "declared_document_number": document_number[:64],
    }

    if document_type == "passport":
        dob = (data.get("declared_date_of_birth") or "").strip()
        expiry = (data.get("declared_expiry_date") or "").strip()
        if not dob or not expiry:
            return {}, "Date of birth and expiry date are required for a passport."
        fields["declared_date_of_birth"] = dob[:32]
        fields["declared_expiry_date"] = expiry[:32]
    else:
        can = (data.get("declared_can") or "").strip()
        # The chip's own firmware only ever accepts a 6-digit CAN as a
        # PACE key -- rejecting anything else here, on the web, with an
        # immediate message is strictly better than the app silently
        # trying and failing a PACE handshake with the card's serial
        # number instead (the exact confusion this session hit three
        # separate times).
        if not (can.isdigit() and len(can) == 6):
            return {}, "CAN must be exactly 6 digits (not the card's longer ID/serial number)."
        fields["declared_can"] = can

    return fields, None


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def pair_start_view(request):
    """POST /api/documents/identity/pair/start/ -- the web page calls
    this once the property owner has declared their document (passport
    number/DOB/expiry, or CIE CAN/document number) and is ready for a
    QR. Requires an IdentityVerification row to already exist (the web
    page always calls startIdentityVerification() first) -- the
    declared fields get stored on that same row, not on the pairing
    code itself, since they're identity evidence that outlives one
    pairing attempt. Any of this user's still-pending codes are
    invalidated first: only one QR should ever be live at a time,
    otherwise an old, already-displayed QR would keep working after the
    page generated a fresh one (e.g. on a page reload)."""
    try:
        record = request.user.rentshield_identity_verification
    except IdentityVerification.DoesNotExist:
        return Response({"error": "Start identity verification first."}, status=400)

    declared_fields, error = _validate_declared_document(request.data)
    if error:
        return Response({"error": error}, status=400)
    for field, value in declared_fields.items():
        setattr(record, field, value)
    record.save(update_fields=[*declared_fields.keys(), "updated_at"])

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
            "apk_url": _apk_download_url(request),
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

    # What the user typed on the web (pair_start_view above), handed
    # back so the app can pre-fill its own document-entry screen
    # instead of asking from scratch -- still shown as editable fields
    # there, never blindly trusted, but no longer blank.
    record = IdentityVerification.objects.filter(user=pairing.user).first()
    declared = {
        "declared_document_type": record.declared_document_type if record else "",
        "declared_document_number": record.declared_document_number if record else "",
        "declared_date_of_birth": record.declared_date_of_birth if record else "",
        "declared_expiry_date": record.declared_expiry_date if record else "",
        "declared_can": record.declared_can if record else "",
    }
    return Response({"token": token.key, "username": pairing.user.username, **declared})
