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

import json
import logging
import re
import secrets
from datetime import datetime
from datetime import timedelta
from urllib.parse import quote
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth import logout as django_logout
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core.validators import validate_email
from django.http import Http404
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
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
from documents.rentshield.zitadel_provisioning import ZITADEL_BRIDGE_URL
from documents.rentshield.zitadel_provisioning import ZitadelProvisioningError
from documents.rentshield.zitadel_provisioning import build_end_session_url
from documents.rentshield.zitadel_provisioning import issue_passkey_nonce
from documents.rentshield.zitadel_provisioning import list_passkeys
from documents.rentshield.zitadel_provisioning import provision_zitadel_user
from documents.rentshield.zitadel_provisioning import redeem_passkey_nonce
from documents.rentshield.zitadel_provisioning import remove_passkey
from documents.rentshield.zitadel_provisioning import start_passkey_registration
from documents.rentshield.zitadel_provisioning import verify_passkey_registration
from documents.rentshield.roles import CanActOnDocument
from documents.rentshield.roles import CanManageNotices
from documents.rentshield.roles import grant_property_owner
from documents.rentshield.service import check_notarization_status
from documents.rentshield.service import generate_and_consume
from documents.rentshield.service import request_notarization
from documents.rentshield.service_methods import SERVICE_METHODS
from documents.rentshield.skills_lib import get_skill
from documents.rentshield.skills_lib import load_skills

logger = logging.getLogger("paperless.auth")

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


def validate_notice_fields(data) -> tuple[dict | None, Response | None]:
    """Shared by create_notice_view (direct, unpaid -- kept for
    scripts/tests) and rentshield_billing's checkout view (the real,
    payment-gated path the Angular frontend now calls). Returns
    (fields, None) on success or (None, error_response) on validation
    failure, so both callers handle errors the same way."""
    if not data.get("landlord_name") or not data.get("tenant_name"):
        return None, Response({"error": "Landlord name and tenant name are required"}, status=400)
    if not data.get("reason") or data["reason"] not in ALL_REASONS:
        return None, Response({"error": "A recognized reason is required"}, status=400)
    if not data.get("notice_date"):
        return None, Response({"error": "A notice date is required"}, status=400)
    if not data.get("ejari_number"):
        return None, Response(
            {"error": "An Ejari certificate number is required -- this notice cites it as the registered tenancy contract."},
            status=400,
        )
    if bool(data.get("add_notarization")) and not data.get("landlord_email"):
        return None, Response({"error": "A landlord email is required when Certified E-Signature is selected."}, status=400)
    if bool(data.get("add_real_notarization")) and not data.get("landlord_email"):
        return None, Response({"error": "A landlord email is required when Real Notary Public is selected."}, status=400)
    if not data.get("reason_requirements_acknowledged"):
        reason_meta = ALL_REASONS.get(data.get("reason"))
        warning = reason_meta["warning"] if reason_meta else "the legal requirements for this reason"
        return None, Response(
            {"error": f"You must acknowledge the following before generating this notice: {warning}"},
            status=400,
        )

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
        "add_legal_review": bool(data.get("add_legal_review")),
        "add_real_notarization": bool(data.get("add_real_notarization")),
        "reason_requirements_acknowledged": True,
    }
    return fields, None


@api_view(["POST"])
@permission_classes([IsAuthenticated, CanManageNotices])
def create_notice_view(request):
    """POST /api/documents/notice/create/ -- renders the bilingual
    notice to a real PDF and hands it to paperless-ngx's own
    consumption pipeline with every field attached as a CustomField
    value and the "RentShield Notice" tag applied. Returns the Celery
    task id; poll GET /api/tasks/?task_id=<id> (paperless-ngx's own
    stock endpoint) to learn the resulting Document id.

    Deliberately still here and NOT payment-gated -- kept for direct/
    scripted use (demo data, tests). The Angular notice-form now calls
    documents.rentshield_billing's checkout endpoint instead, which is
    the real, paid path (see README's dated Stripe/billing section).
    """
    fields, error = validate_notice_fields(request.data)
    if error:
        return error
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


# MARK: -- Staged signup wizard (2026-09-15, requested explicitly --
# GOV.UK One Login's own registration flow, pasted in full, was the
# reference): one focused step per page instead of a modal, email
# genuinely *verified* via a one-time code (not just format/uniqueness-
# checked) before an account can be created, and document details typed
# here on a real keyboard rather than the app's small screen -- same
# reasoning pairing_views.py's own declared-fields step already
# documents. Draft state lives in the session between steps; nothing
# hits the database until signup_review_view's POST, so an abandoned
# wizard leaves no half-finished row behind. The final step hands off to
# the RentShield app for biometric + NFC only -- see pairing_views.py's
# signup_complete_view for what happens once the phone finishes.

SIGNUP_SESSION_KEY = "signup_draft"
SIGNUP_OTP_TTL = timedelta(minutes=15)


def _signup_draft(request) -> dict:
    return request.session.get(SIGNUP_SESSION_KEY, {})


def signup_start_view(request):
    """GET /signup/ -- the intro step. Clears any stale draft so
    reloading this page always starts clean, same as GOV.UK's own entry
    point."""
    request.session.pop(SIGNUP_SESSION_KEY, None)
    return render(request, "rentshield/signup_start.html")


def signup_email_view(request):
    """GET/POST /signup/email/ -- step 1: email + terms agreement. A
    real one-time code is emailed on POST, checked in
    signup_verify_view -- not just a format/uniqueness check.

    One single URL channel for signin AND signup (2026-09-15, requested
    explicitly): an email that already has an account transparently
    redirects into sign-in (passkey-only, no password prompt) instead of
    dead-ending with an error -- this one email field is the entire
    entry point either way.

    ZITADEL migration Phase F cleanup (2026-09-22): Authelia itself has
    been permanently deleted (containers, vendor/authelia/, its own
    config/secrets -- requested explicitly, "clean up server space"),
    so an existing email now needs to check WHICH provider that account
    actually has a SocialAccount for before redirecting, rather than
    blindly sending everyone to Authelia's now-dead URL. Any account
    created before this cleanup has its passkey on the now-deleted
    Authelia instance and no way back in -- WebAuthn credentials aren't
    portable between relying parties, confirmed earlier in this same
    migration, and there is no migration story for that; this just
    stops making it worse by redirecting them into a dead link."""
    error = None
    if request.method == "POST":
        email = (request.POST.get("email") or "").strip().lower()
        if request.POST.get("agree") != "on":
            error = "You must agree to the terms and conditions to continue."
        else:
            try:
                validate_email(email)
            except DjangoValidationError:
                error = "Enter a valid email address."
        if not error:
            existing_user = get_user_model().objects.filter(email__iexact=email).first()
            if existing_user is not None:
                if existing_user.socialaccount_set.filter(provider="zitadel").exists():
                    return redirect("/accounts/oidc/zitadel/login/")
                error = (
                    "This account was created before a platform migration and can no "
                    "longer sign in this way -- contact support to regain access."
                )
        if not error:
            otp = f"{secrets.randbelow(1_000_000):06d}"
            request.session[SIGNUP_SESSION_KEY] = {
                "email": email,
                "otp": otp,
                "otp_expires_at": (timezone.now() + SIGNUP_OTP_TTL).isoformat(),
                "email_verified": False,
            }
            send_mail(
                subject="Your RentShield security code",
                message=f"Your RentShield security code is {otp}. It expires in 15 minutes.",
                from_email=None,
                recipient_list=[email],
                fail_silently=False,
            )
            return redirect("rentshield-signup-verify")
    return render(request, "rentshield/signup_email.html", {"error": error})


def signup_verify_view(request):
    """GET/POST /signup/verify/ -- step 2: the 6-digit code just
    emailed. Redirects back to the email step with no pending code in
    the session at all (enforces the linear order, same as GOV.UK's own
    flow refusing to skip ahead).

    Verifying the code is also the LAST step now (2026-09-15, requested
    explicitly: Authelia is the only signup/signin path from here on) --
    a successful code creates the Django User (unusable local password,
    Property Owner group, same as ever) *and* a matching ZITADEL account
    right away, then sends them to sign in. Document declaration +
    NFC/selfie/video verification happen afterward, on the existing
    (pre-session) identity-verification page, once they're actually
    logged in -- pair_start_view/pair_claim_view need no changes at all
    for that to work, they only ever check request.user.is_authenticated,
    never how that login happened.

    ZITADEL migration Phase F (2026-09-22) -- new signups provision into
    ZITADEL now, not Authelia (see documents/rentshield/
    zitadel_provisioning.py). Deliberately additive, not a hard replace:
    Authelia's OIDC app stays registered in PAPERLESS_SOCIALACCOUNT_PROVIDERS
    and signup_email_view's "already have an account" branch still sends
    existing emails there unchanged -- every account created before this
    line shipped has its passkey on Authelia, not ZITADEL, and there's no
    way to migrate a WebAuthn credential between relying parties, so
    breaking their sign-in for a same-session naming purity would be a
    real regression for zero benefit. No cookie to set here any more,
    unlike the Authelia path -- see provision_zitadel_user's own comment
    on why: ZITADEL needs no pre-elevated session for the passkey
    ceremony, only the nonce signup_done_view mints below."""
    draft = _signup_draft(request)
    if "otp" not in draft:
        return redirect("rentshield-signup-email")

    error = None
    if request.method == "POST":
        if request.POST.get("resend") == "1":
            return redirect("rentshield-signup-email")
        code = (request.POST.get("code") or "").strip()
        if timezone.now() > datetime.fromisoformat(draft["otp_expires_at"]):
            error = "That code has expired -- request a new one."
        elif code != draft["otp"]:
            error = "That code doesn't match -- check your email and try again."
        else:
            email = draft["email"]
            username = _unique_username_from_email(email)
            user = get_user_model().objects.create(username=username, email=email)
            user.set_unusable_password()
            user.save(update_fields=["password"])
            grant_property_owner(user)
            zitadel_user_id = provision_zitadel_user(username, email, groups=["Property Owner"])
            request.session.pop(SIGNUP_SESSION_KEY, None)
            request.session["signup_zitadel_user_id"] = zitadel_user_id
            request.session["signup_zitadel_username"] = username
            return redirect("rentshield-signup-done")
    return render(request, "rentshield/signup_verify.html", {"error": error, "email": draft.get("email")})


def signup_done_view(request):
    """GET /signup/done/ -- GOV.UK-style confirmation. Links to
    RentShield's own ZITADEL bridge page (documents/rentshield/
    zitadel_provisioning.py's own comment on why this exists rather than
    calling ZITADEL directly: the admin-level provisioner PAT must never
    reach the browser) to register the very first passkey. Needs no
    pre-authenticated session at all any more (2026-09-22 -- Authelia's
    version needed one, ZITADEL's RegisterPasskey doesn't) -- no
    password is ever shown or set (2026-09-15, requested explicitly:
    passwordless only).

    `return` points back at THIS view, not `/profile` (confirmed live
    bug this caused: /profile requires being logged in, which is
    impossible before a first working 2FA device exists -- so a failed
    registration here, for any reason, used to bounce the user through
    /accounts/login into Authelia's own OIDC 2FA screen, whose only
    option is its native "Add Device" dialog -- the exact buggy flow
    this whole bridge page exists to avoid. Looping back here instead
    means "try again" always re-offers the working bridge link, no
    matter why the previous attempt failed -- this view needs no login
    of its own, only the same pre-signup session state the very first
    visit did.

    A successful registration (?passkeyAdded=1) redirects straight into
    the real sign-in trigger instead of rendering this page again
    (2026-09-18, requested explicitly: registering shouldn't dead-end on
    a static page that makes the user go find their own way to sign in
    afterward) -- completes the actual OIDC login (one tap if the
    passkey carried full verification, a second confirming tap
    otherwise, see LoginPortal.tsx's own comment in this fork), landing
    on the dashboard with no separate manual step.

    ZITADEL migration Phase F (2026-09-22) -- bridge_url now points at
    the zitadel-proxy bridge page (Phase D) with a freshly-minted
    single-use nonce (zitadel_provisioning.issue_passkey_nonce) instead
    of Authelia's `description` param; a fresh one is minted on every
    GET (cheap, and correctly handles both a plain reload and the
    passkey_error retry case below without needing to distinguish
    them). signup_zitadel_user_id has to already be in the session --
    it's set by signup_verify_view right before redirecting here, never
    accepted from the client.

    Real bug hit live (2026-09-22): passkey registration is entirely
    server-to-server (Django's provisioner PAT calls ZITADEL directly --
    see zitadel_provisioning.py's own comment on why), so it never
    establishes a browser-side ZITADEL session for the account that was
    just created. A bare `/accounts/oidc/zitadel/login/` redirect from
    here silently reused whatever OTHER ZITADEL session was already
    active in that browser (a stale SSO session from a previous signup
    in the same tab), landing the user in the WRONG, unrelated account
    with zero interaction -- confirmed live via the Django access log's
    own `Syncing groups for user ...` line naming the wrong username.
    `login_hint` + `prompt=login` via allauth's dynamic
    `?auth_params=` (django-allauth's oauth2 provider.py, not a custom
    subclass) forces ZITADEL to authenticate as THIS specific account
    every time, never silently reusing an unrelated session -- deliberately
    only applied here, not on signup_email_view's returning-user
    redirect, where reusing an existing same-account session is exactly
    the point."""
    if request.GET.get("passkeyAdded") == "1":
        username = request.session.pop("signup_zitadel_username", None)
        auth_params = urlencode({"login_hint": username, "prompt": "login"}) if username else ""
        login_url = "/accounts/oidc/zitadel/login/"
        if auth_params:
            login_url += f"?auth_params={quote(auth_params, safe='')}"
        return redirect(login_url)

    zitadel_user_id = request.session.get("signup_zitadel_user_id")
    if not zitadel_user_id:
        return redirect("rentshield-signup-start")

    done_url = request.build_absolute_uri(reverse("rentshield-signup-done"))
    nonce = issue_passkey_nonce(zitadel_user_id)
    bridge_url = (
        f"{ZITADEL_BRIDGE_URL}?description=My+passkey"
        f"&return={quote(done_url, safe='')}"
        f"&nonce={quote(nonce, safe='')}"
    )
    return render(
        request,
        "rentshield/signup_done.html",
        {"bridge_url": bridge_url, "passkey_error": request.GET.get("passkeyError")},
    )


# MARK: -- ZITADEL migration Phase D (2026-09-22, see /home/giova/.claude/
# plans/synchronous-finding-storm.md). Not called from anywhere real yet
# -- signup_verify_view/signup_done_view above still run the Authelia
# path exclusively; Phase F is what points them at
# zitadel_provisioning.provision_zitadel_user and a ZITADEL-flavored
# bridge_url instead. These two views exist now so the adapted bridge
# page (authelia/nginx/nginx.conf's zitadel-proxy counterpart) has
# something real to call during Phase D's own live verification.
#
# Cross-origin from zitadel.rentshield.local, same reason
# authelia/nginx/nginx.conf's /api/ location needs its own CORS block --
# see nginx/app-proxy/nginx.conf's matching location for the allowed
# origin. Authorized by a single-use nonce (zitadel_provisioning.
# issue_passkey_nonce), not a shared session cookie -- see that
# function's own comment for why. @csrf_exempt is safe here for the
# same reason DRF's api_view endpoints elsewhere in this file don't
# carry Django's session-cookie-based CSRF risk: nothing here is
# authenticated by a cookie Django would need to protect, the nonce
# itself is the credential and it's single-use on the verify path.


@csrf_exempt
def zitadel_passkey_start_view(request):
    """POST /zitadel/passkey/start {"nonce": "..."} -- returns the
    WebAuthn creation options for navigator.credentials.create(), same
    shape the bridge page already consumes from Authelia today."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
    try:
        nonce = json.loads(request.body)["nonce"]
    except (ValueError, KeyError):
        return JsonResponse({"error": "Malformed request."}, status=400)
    user_id = redeem_passkey_nonce(nonce, consume=False)
    if not user_id:
        return JsonResponse({"error": "This link has expired -- go back and try again."}, status=400)
    try:
        result = start_passkey_registration(user_id)
    except ZitadelProvisioningError as exc:
        logger.warning("ZITADEL passkey start failed: %s", exc)
        return JsonResponse({"error": "Could not start passkey registration."}, status=502)
    return JsonResponse(result)


@csrf_exempt
def zitadel_passkey_verify_view(request):
    """POST /zitadel/passkey/verify {"nonce", "passkeyId", "publicKeyCredential"}
    -- completes the ceremony. The nonce is consumed here (not on
    start), so a device prompt the user cancelled and retried doesn't
    burn the link, but a completed registration can't be replayed."""
    if request.method != "POST":
        return JsonResponse({"error": "POST required."}, status=405)
    try:
        body = json.loads(request.body)
        nonce = body["nonce"]
        passkey_id = body["passkeyId"]
        credential = body["publicKeyCredential"]
    except (ValueError, KeyError):
        return JsonResponse({"error": "Malformed request."}, status=400)
    passkey_name = (body.get("passkeyName") or "My passkey")[:200]
    user_id = redeem_passkey_nonce(nonce, consume=True)
    if not user_id:
        return JsonResponse({"error": "This link has expired -- go back and try again."}, status=400)
    try:
        verify_passkey_registration(user_id, passkey_id, credential, passkey_name)
    except ZitadelProvisioningError as exc:
        logger.warning("ZITADEL passkey verify failed: %s", exc)
        return JsonResponse({"error": "Registration failed -- you can try again below."}, status=502)
    return JsonResponse({"status": "ok"})


def _unique_username_from_email(email: str) -> str:
    """No username is typed anywhere in this flow -- derived from the
    email's local part (the bit before @), de-duplicated with a numeric
    suffix on collision, the same first guess most signup forms make
    when offering to auto-fill a username from an email address."""
    User = get_user_model()
    local_part = email.split("@", 1)[0]
    base = re.sub(r"[^\w.@+-]", "_", local_part)[:140] or "user"
    candidate = base
    suffix = 1
    while User.objects.filter(username=candidate).exists():
        suffix += 1
        candidate = f"{base}{suffix}"[:150]
    return candidate


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
@permission_classes([IsAuthenticated, CanActOnDocument])
def notarize_view(request, document_id: int):
    """POST /api/documents/notice/<document_id>/notarize/ -- routes the
    notice on this Document through a real e-signature workflow
    (DocuSeal primary, OpenSign fallback). Gated on "Change Document"
    (not "Add Document" like creating a notice) -- this modifies an
    existing one, matching Django's own permission semantics."""
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


@api_view(["POST"])
@permission_classes([AllowAny])
def notarize_uploaded_view(request):
    """POST /api/documents/notice/notarize-uploaded/ {"doc_id": <id>} --
    dispatches the real notarization request (DocuSeal primary, OpenSign
    fallback) for an EXISTING notice and returns immediately with a
    Celery task id. This is what the "RentShield: send confirmed notice
    to notary" Workflow's webhook action calls, once a Property Owner/
    Lawyer has reviewed a notarization-requested notice and ticked its
    "Details Confirmed" custom field (see manage.py
    create_rentshield_workflows) -- paperless-ngx's own Workflow webhooks
    time out after 5 seconds, so this must not call
    documents.rentshield.service.request_notarization() inline -- see
    documents.tasks.run_notarization_task.

    Deliberately AllowAny, same reasoning as analyze_uploaded_view above:
    the caller is paperless-ngx's own Celery worker calling back into
    this same Django process via settings.RENTSHIELD_INTERNAL_URL, not a
    human, so there's no user session to authenticate. It's scoped to a
    single, narrow action (queue notarization dispatch for a doc id that
    must already exist) rather than exposing anything readable/writable
    beyond that.
    """
    from documents.tasks import run_notarization_task

    doc_id = request.data.get("doc_id") or request.data.get("document_id")
    if not doc_id:
        return Response({"error": "doc_id is required"}, status=400)
    get_object_or_404(Document, id=doc_id)  # 404 early rather than queuing a task for nothing

    async_task = run_notarization_task.apply_async(kwargs={"document_id": int(doc_id)})
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


# MARK: -- My Profile "Security" tab, ZITADEL-backed (2026-09-22).
# Replaces authelia-security.service.ts, which called
# environment.autheliaApiUrl directly and has been fully broken (not
# just unmigrated) since Authelia was deleted earlier this session.
# Two features from the old Authelia version are dropped, not ported:
# - Rename: ZITADEL's passkey API has no update/rename RPC at all
#   (confirmed against user_service.proto -- Register/Verify/List/Remove
#   only), so there's nothing to call.
# - Change password / the whole "elevation" (email one-time-code) gate
#   on every mutating action: RentShield has no passwords to change any
#   more, and ZITADEL's RegisterPasskey/RemovePasskey need no elevated
#   session the way Authelia's did (confirmed live in Phase C) -- the
#   provisioner PAT calls them the same way it does during signup. Add
#   and Remove below rely on the same trust boundary every other
#   authenticated action in this app already does (a valid Django
#   session), not a bespoke step-up flow that only existed because of
#   Authelia's own architecture.
def _zitadel_user_id_for(user) -> str | None:
    social_account = user.socialaccount_set.filter(provider="zitadel").first()
    return social_account.uid if social_account else None


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def rentshield_passkeys_view(request):
    """GET /api/documents/security/passkeys/ -- list the logged-in
    user's own passkeys."""
    zitadel_user_id = _zitadel_user_id_for(request.user)
    if not zitadel_user_id:
        return Response({"error": "This account has no ZITADEL identity linked."}, status=400)
    try:
        passkeys = list_passkeys(zitadel_user_id)
    except ZitadelProvisioningError as exc:
        logger.warning("ZITADEL passkey list failed: %s", exc)
        return Response({"error": "Could not load your passkeys."}, status=502)
    return Response(passkeys)


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def rentshield_passkey_add_view(request):
    """POST /api/documents/security/passkeys/add/ -- mints a single-use
    nonce for the logged-in user's OWN zitadel_user_id and returns the
    full bridge-page redirect URL, same nonce mechanism signup already
    uses (zitadel_provisioning.issue_passkey_nonce) -- the ceremony
    itself still has to happen on zitadel.rentshield.local (the RP-id
    origin constraint), so the browser still needs a real redirect, not
    just an API call."""
    zitadel_user_id = _zitadel_user_id_for(request.user)
    if not zitadel_user_id:
        return Response({"error": "This account has no ZITADEL identity linked."}, status=400)
    description = (request.data.get("description") or "New passkey").strip()[:200]
    return_to = request.build_absolute_uri(request.data.get("return_to") or "/")
    nonce = issue_passkey_nonce(zitadel_user_id)
    redirect_url = (
        f"{ZITADEL_BRIDGE_URL}?description={quote(description)}"
        f"&return={quote(return_to, safe='')}"
        f"&nonce={quote(nonce, safe='')}"
    )
    return Response({"redirect_url": redirect_url})


@api_view(["DELETE"])
@permission_classes([IsAuthenticated])
def rentshield_passkey_delete_view(request, passkey_id: str):
    """DELETE /api/documents/security/passkeys/<passkey_id>/"""
    zitadel_user_id = _zitadel_user_id_for(request.user)
    if not zitadel_user_id:
        return Response({"error": "This account has no ZITADEL identity linked."}, status=400)
    try:
        remove_passkey(zitadel_user_id, passkey_id)
    except ZitadelProvisioningError as exc:
        logger.warning("ZITADEL passkey removal failed: %s", exc)
        return Response({"error": "Could not remove that passkey."}, status=502)
    return Response(status=204)


def rentshield_logout_view(request):
    """GET/POST /accounts/logout/ -- replaces allauth's own logout view
    at this URL (2026-09-22, requested explicitly: "force full re-auth
    on every logout"). allauth's version only ever cleared the LOCAL
    Django session; the browser kept a separate, still-valid ZITADEL
    session the whole time, so signing back in silently reused it with
    no fresh passkey tap -- confirmed live, not assumed (Django's own
    session for a test account survived a server restart and a
    subsequent "log out" here, then still landed back on /dashboard
    with zero interaction on the next sign-in click). Local logout
    still happens here first, same as before -- this only adds the
    redirect through ZITADEL's own end_session_endpoint afterward, per
    zitadel_provisioning.build_end_session_url's own comment on why
    that needs no stored id_token."""
    django_logout(request)
    post_logout_redirect_uri = request.build_absolute_uri(
        f"{reverse('account_login')}?loggedout=1",
    )
    return redirect(build_end_session_url(post_logout_redirect_uri))
    return Response(result)
