# ZITADEL migration Phase C (2026-09-22, see /home/giova/.claude/plans/
# synchronous-finding-storm.md) -- not wired into signup_verify_view yet
# (that's Phase F). Sibling to authelia_provisioning.py, but structurally
# simpler than it, for a reason confirmed live against the running
# instance rather than assumed: ZITADEL's v2 User API lets a human user
# be created with NO password at all (Password is one arm of a oneof,
# never required), and RegisterPasskey/VerifyPasskeyRegistration are
# authorized for any caller holding a valid bearer token for the target
# user_id -- not gated on that specific user's own session the way
# Authelia's file backend required. Confirmed live: the provisioner PAT
# (IAM_OWNER, see docker-compose.yml's zitadel-api.environment) can call
# RegisterPasskey directly for a user it just created, no password,
# firstfactor login, or elevation dance needed at all -- the entire
# reason authelia_provisioning.py exists (provision_authelia_user +
# bootstrap_authelia_session, ~180 lines) collapses to one user-creation
# call plus a role grant here.
#
# The PAT itself never reaches the browser -- it's read from the
# zitadel-bootstrap volume (docker-compose.yml's webserver.volumes) and
# used only for server-to-server calls. The passkey ceremony's two
# browser-facing steps (get creation options, submit the credential) are
# Phase D's job: the bridge page will call back into Django (this
# module) rather than ZITADEL directly, so the admin-level PAT is never
# exposed client-side -- mirrors the CORS pattern
# authelia/nginx/nginx.conf's own /api/ location already established for
# the same reason (My Profile's Security tab calling Authelia directly).
#
# Org/project IDs below are hardcoded to Phase B's already-created
# resources (RentShield Operations org, RentShield project) -- move to
# settings/env once Phase F's cutover makes this the live path; no
# point wiring configurability for a module nothing calls yet.
from __future__ import annotations

import logging
import secrets
from pathlib import Path
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger("paperless.auth")

# Authorizes the bridge page's two cross-origin calls into Django
# (zitadel.rentshield.local -> app.rentshield.local) without a shared
# session cookie -- deliberately not cookie-based: Django's session
# cookie is host-only (app.rentshield.local specifically, no
# SESSION_COOKIE_DOMAIN override), and widening it to the whole
# rentshield.local site just to cover this one flow is a bigger,
# site-wide change than this warrants. A single-use, time-limited,
# unguessable nonce in the bridge URL's query string does the same job
# as the existing `description`/`return` params already there, reusing
# Django's own cache framework (PAPERLESS_REDIS-backed, already
# configured) instead of adding a new store.
_NONCE_TTL_SECONDS = 15 * 60  # matches SIGNUP_OTP_TTL in rentshield_views.py
_NONCE_CACHE_PREFIX = "zitadel-signup-nonce:"


def issue_passkey_nonce(zitadel_user_id: str) -> str:
    nonce = secrets.token_urlsafe(32)
    cache.set(f"{_NONCE_CACHE_PREFIX}{nonce}", zitadel_user_id, timeout=_NONCE_TTL_SECONDS)
    return nonce


def redeem_passkey_nonce(nonce: str, *, consume: bool) -> str | None:
    """Looks up the ZITADEL user_id for a nonce. consume=True (the
    verify step, once the ceremony actually succeeds) deletes it after
    reading so it can't be replayed; consume=False (the start step, can
    legitimately be retried if the user's device prompt fails) leaves
    it alone."""
    key = f"{_NONCE_CACHE_PREFIX}{nonce}"
    user_id = cache.get(key)
    if consume and user_id is not None:
        cache.delete(key)
    return user_id

ZITADEL_BASE_URL = "https://zitadel.rentshield.local:9092"
ZITADEL_ORG_ID = "391824042086105094"
ZITADEL_PROJECT_ID = "391824049719738374"
# Phase F (2026-09-22): deliberately NOT auth.rentshield.local -- that
# would mean changing ZITADEL's own ExternalDomain on an
# already-bootstrapped instance (org/project/roles/app/action, plus this
# session's own live-tested passkey, are all already keyed to
# zitadel.rentshield.local), and ZITADEL's own deploy docs warn that a
# mismatched domain/port/secure setting after first boot produces
# "Instance not found" errors -- real, avoidable risk for a naming
# nicety with zero functional benefit. zitadel.rentshield.local:9092
# stays the permanent address, not a temporary side door.
ZITADEL_BRIDGE_URL = f"{ZITADEL_BASE_URL}/rentshield-bridge/index.html"
# Phase B's OIDC app -- same value as ZITADEL_OIDC_CLIENT_ID in .env /
# docker-compose.yml's webserver environment, hardcoded here for the
# same "nothing else needs this configurable yet" reason as org/project
# above. Only used for RP-Initiated Logout below; the actual sign-in
# flow gets its client_id from Django's own allauth SocialApp config,
# not from here.
ZITADEL_CLIENT_ID = "391824136155955206"
ZITADEL_END_SESSION_URL = f"{ZITADEL_BASE_URL}/oidc/v1/end_session"
# A one-time copy of the file ZITADEL wrote at first boot (see
# zitadel-api.environment's ZITADEL_FIRSTINSTANCE_PATPATH in
# docker-compose.yml), not a live-mounted volume -- confirmed live that
# a mounted-volume path breaks for this project's own dev setup (Django
# runs as a bare host process here, not the compose `webserver`
# container, so it has no access to Docker volumes at all). Same
# gitignored-static-secret-file convention as
# zitadel/secrets/oidc_app_credentials.txt and
# authelia/secrets/oidc_client_secret_plaintext.txt -- works identically
# whether Django runs bare or containerized, and the PAT never rotates
# on its own, so there's nothing this module would gain from reading it
# live.
PROVISIONER_PAT_PATH = Path(settings.BASE_DIR).parent / "zitadel" / "secrets" / "provisioner.pat"


class ZitadelProvisioningError(Exception):
    pass


def _headers() -> dict:
    pat = PROVISIONER_PAT_PATH.read_text().strip()
    return {
        "Authorization": f"Bearer {pat}",
        "Content-Type": "application/json",
        "x-zitadel-orgid": ZITADEL_ORG_ID,
    }


def provision_zitadel_user(username: str, email: str, groups: list[str], displayname: str = "") -> str:
    """Creates a passwordless ZITADEL human user (email pre-verified --
    RentShield's own OTP step already proved it, so ZITADEL is never
    asked to send its own verification mail) and grants the matching
    project roles, returning the new user's ZITADEL user_id.

    given_name/family_name are required by ZITADEL's API even though
    RentShield's signup wizard collects neither today -- filled with a
    placeholder (username / "RentShield User") rather than blocked on
    adding a name field to the wizard, which is a real product decision
    this module has no business making unilaterally."""
    response = requests.post(
        f"{ZITADEL_BASE_URL}/v2/users/new",
        headers=_headers(),
        json={
            "organizationId": ZITADEL_ORG_ID,
            "username": username,
            "human": {
                "profile": {
                    "givenName": displayname or username,
                    "familyName": "RentShield User",
                },
                "email": {"email": email, "isVerified": True},
            },
        },
        timeout=10,
    )
    if response.status_code != 200:
        raise ZitadelProvisioningError(
            f"ZITADEL user creation failed: {response.status_code} {response.text}",
        )
    user_id = response.json()["id"]

    if groups:
        grant_response = requests.post(
            f"{ZITADEL_BASE_URL}/management/v1/users/{user_id}/grants",
            headers=_headers(),
            json={"project_id": ZITADEL_PROJECT_ID, "role_keys": groups},
            timeout=10,
        )
        if grant_response.status_code != 200:
            raise ZitadelProvisioningError(
                f"ZITADEL role grant failed: {grant_response.status_code} {grant_response.text}",
            )

    return user_id


def start_passkey_registration(user_id: str) -> dict:
    """Calls RegisterPasskey server-side using the provisioner PAT and
    returns {"passkeyId", "publicKey"} -- the bridge page (Phase D)
    forwards `publicKey` straight into
    PublicKeyCredential.parseCreationOptionsFromJSON(), same shape the
    Authelia bridge already consumes today, and relays `passkeyId` back
    to verify_passkey_registration below once the ceremony completes."""
    response = requests.post(
        f"{ZITADEL_BASE_URL}/v2/users/{user_id}/passkeys",
        headers=_headers(),
        json={},
        timeout=10,
    )
    if response.status_code != 200:
        raise ZitadelProvisioningError(
            f"ZITADEL passkey registration start failed: {response.status_code} {response.text}",
        )
    data = response.json()
    return {
        "passkeyId": data["passkeyId"],
        "publicKey": data["publicKeyCredentialCreationOptions"]["publicKey"],
    }


def verify_passkey_registration(
    user_id: str,
    passkey_id: str,
    public_key_credential: dict,
    passkey_name: str = "My passkey",
) -> None:
    """Completes the ceremony: public_key_credential is exactly what the
    browser's `credential.toJSON()` produces (ZITADEL accepts it as an
    arbitrary protobuf Struct, no reshaping needed) -- same object the
    Authelia bridge already POSTs today, just handed to Django instead
    of straight to the IdP, since VerifyPasskeyRegistration also needs
    the PAT this module holds server-side. passkey_name is REQUIRED by
    ZITADEL's own API (unlike Authelia, which took the equivalent
    `description` up front on RegisterPasskey instead) -- confirmed
    against user_service.proto, not guessed."""
    response = requests.post(
        f"{ZITADEL_BASE_URL}/v2/users/{user_id}/passkeys/{passkey_id}",
        headers=_headers(),
        json={"publicKeyCredential": public_key_credential, "passkeyName": passkey_name},
        timeout=10,
    )
    if response.status_code != 200:
        raise ZitadelProvisioningError(
            f"ZITADEL passkey verification failed: {response.status_code} {response.text}",
        )


def list_passkeys(user_id: str) -> list[dict]:
    """For the My Profile > Security tab (2026-09-22) -- replaces the
    now-fully-broken authelia-security.service.ts (it called
    environment.autheliaApiUrl directly, which pointed at the Authelia
    backend deleted earlier this session)."""
    response = requests.post(
        f"{ZITADEL_BASE_URL}/v2/users/{user_id}/passkeys/_search",
        headers=_headers(),
        json={},
        timeout=10,
    )
    if response.status_code != 200:
        raise ZitadelProvisioningError(
            f"ZITADEL passkey list failed: {response.status_code} {response.text}",
        )
    return response.json().get("result", [])


def remove_passkey(user_id: str, passkey_id: str) -> None:
    response = requests.delete(
        f"{ZITADEL_BASE_URL}/v2/users/{user_id}/passkeys/{passkey_id}",
        headers=_headers(),
        timeout=10,
    )
    if response.status_code != 200:
        raise ZitadelProvisioningError(
            f"ZITADEL passkey removal failed: {response.status_code} {response.text}",
        )


def build_end_session_url(post_logout_redirect_uri: str) -> str:
    """RP-Initiated Logout (2026-09-22, requested explicitly: "force
    full re-auth on every logout") -- Django's own /accounts/logout/
    only ever ended the LOCAL session; the browser kept a separate,
    still-valid ZITADEL session the whole time, so signing back in
    silently reused it with no fresh passkey tap. Confirmed against
    ZITADEL's own docs: id_token_hint is NOT required -- client_id
    alone is enough to identify the app and validate
    post_logout_redirect_uri against its registered
    post_logout_redirect_uris (set via Phase B's OIDC app, updated
    2026-09-22 to include this). Avoids the alternative (capturing and
    storing the raw id_token JWT at login just to hand it back here) --
    allauth's own openid_connect adapter decodes and discards it,
    never persists the compact string, so getting one back would need
    its own plumbing for no benefit ZITADEL actually requires."""
    return (
        f"{ZITADEL_END_SESSION_URL}"
        f"?client_id={ZITADEL_CLIENT_ID}"
        f"&post_logout_redirect_uri={quote(post_logout_redirect_uri, safe='')}"
    )
