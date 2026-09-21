# Authelia's file-backed authentication_backend has no self-service
# registration of its own (confirmed against its own docs, not
# guessed) -- users_database.yml is meant to be hand-edited or written
# by an external tool. This is that tool: called once, right after
# rentshield_views.py's signup_verify_view creates the matching Django
# User, so every account this project has has a real Authelia login
# from the moment it exists (2026-09-15, requested explicitly: Authelia
# is now the only signup/signin path).
#
# ponytail: shells out to the running Authelia container for the actual
# argon2 hashing (the same `docker exec ... authelia crypto hash
# generate argon2` this session already ran by hand repeatedly) rather
# than adding a new Python argon2 dependency purely to duplicate a
# capability the container already has. Reads/rewrites the whole YAML
# file unlocked, single-process -- fine at this project's real scale (a
# handful of accounts, provisioned rarely, never concurrently); the
# real upgrade path if that ever stops being true is Authelia's own
# `ldap` authentication_backend instead of `file` (configuration.yml's
# own header comment already flags this).
from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path

import requests
import yaml
from django.conf import settings

AUTHELIA_CONTAINER_NAME = "iub_rentdubai-authelia-1"
AUTHELIA_BASE_URL = "https://auth.rentshield.local:9091"
# Same page src-ui's Security tab already redirects to for "Add a
# passkey" (src-ui/src/environments/environment.ts's autheliaBridgeUrl)
# -- registers a WebAuthn credential via a direct API call instead of
# Authelia's own "Add Device" dialog, which has a confirmed live bug
# under experimental_enable_passkey_uv_two_factors (every attempt fails
# with "You cancelled the attestation request", no server-side trace at
# all -- the bug is in Authelia's own React dialog specifically, not the
# underlying ceremony; this bridge calls the same API directly and does
# not hit it, confirmed via an automated Playwright + virtual-
# authenticator run).
AUTHELIA_BRIDGE_URL = f"{AUTHELIA_BASE_URL}/rentshield-bridge/index.html"
USERS_DATABASE_PATH = Path(settings.BASE_DIR).parent / "authelia" / "users_database.yml"

logger = logging.getLogger(__name__)


class AutheliaProvisioningError(Exception):
    pass


# yaml.safe_dump has no concept of preserving comments on a round-trip
# (confirmed against PyYAML's own docs -- it isn't a limitation worth
# working around with a heavier YAML library just to keep a comment) --
# re-prepended by hand on every write instead of letting the file's own
# explanation get silently dropped the first time this runs.
_USERS_DATABASE_HEADER = """\
# GITIGNORED (contains password hashes -- see .gitignore). File-backed
# user store for Authelia (authentication_backend.file in
# configuration.yml), maintained by
# documents/rentshield/authelia_provisioning.py -- every RentShield
# account gets an entry here the moment it's created (see
# rentshield_views.py's signup_verify_view), so hand-edits will be
# overwritten the next time someone signs up. Group names here must
# match Django's exact Group names ("Property Owner" / "Notary Public",
# see documents/rentshield/roles.py) so
# PAPERLESS_SOCIAL_ACCOUNT_SYNC_GROUPS can map them 1:1 with no claim-
# name translation.
"""


def _generate_random_password() -> tuple[str, str]:
    """Returns (plaintext, argon2_hash) -- the same `authelia crypto
    hash generate argon2 --random` command already run by hand this
    session to create every test user's credentials so far."""
    result = subprocess.run(
        [
            "docker", "exec", AUTHELIA_CONTAINER_NAME,
            "authelia", "crypto", "hash", "generate", "argon2", "--random", "--no-confirm",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise AutheliaProvisioningError(f"authelia crypto hash generate failed: {result.stderr.strip()}")

    password = digest = None
    for line in result.stdout.splitlines():
        if line.startswith("Random Password:"):
            password = line.split(":", 1)[1].strip()
        elif line.startswith("Digest:"):
            digest = line.split(":", 1)[1].strip()
    if not password or not digest:
        raise AutheliaProvisioningError(f"Could not parse a password/digest from: {result.stdout!r}")
    return password, digest


def provision_authelia_user(username: str, email: str, groups: list[str], displayname: str = "") -> str:
    """Creates (or replaces) `username`'s entry in Authelia's
    users_database.yml with a fresh random password, returning that
    plaintext password -- report it to whoever needs to actually log in
    with it, the same way every other generated credential this session
    has surfaced. `watch: true` in configuration.yml means Authelia
    picks this up live, no restart needed."""
    password, digest = _generate_random_password()

    data = yaml.safe_load(USERS_DATABASE_PATH.read_text()) or {"users": {}}
    data.setdefault("users", {})[username] = {
        "disabled": False,
        "displayname": displayname or username,
        "password": digest,
        "email": email,
        "groups": groups,
    }
    USERS_DATABASE_PATH.write_text(
        _USERS_DATABASE_HEADER + yaml.safe_dump(data, sort_keys=False, default_flow_style=False),
    )
    return password


def bootstrap_authelia_session(username: str, password: str) -> str:
    """Performs the one-time first-factor login for a just-provisioned
    account using the random password only this server ever knows, and
    returns Authelia's resulting session cookie *value* -- the caller
    relays it onto the user's own browser response (matching
    configuration.yml's session cookie attributes: domain
    'rentshield.local', secure, httponly, samesite Lax) so the user shows
    up at Authelia already first-factor-authenticated, with zero 2FA
    methods registered yet, having never seen or typed a password
    (2026-09-15, requested explicitly: "only biometrics, no passwords" --
    Authelia's file backend still requires *a* password hash to exist,
    this is what keeps that requirement from ever reaching the user).
    Relies on REQUESTS_CA_BUNDLE (already configured for allauth's own
    OIDC calls) to trust Authelia's dev cert; `requests` picks that env
    var up automatically, no explicit `verify=` needed here.

    Also sets the account's default 2FA method to 'webauthn' right here
    -- confirmed live (via an automated Playwright + virtual-authenticator
    run, not guessed) that Authelia's own default preference is 'totp',
    so a brand-new account that goes on to register a passkey would
    still land on the "One-Time Password" tab on its next login,
    *looking* like no device is registered until the user manually
    switches tabs. Setting this now, before any 2FA method even exists,
    means the very first passkey the user registers is already what
    login defaults to -- confirmed this call needs no elevation.

    Elevation itself (the last step) is best-effort: if it fails (a
    confirmed-live case -- Authelia's own identity-verification rate
    limiter, keyed by IP with no config knob, can return 429 under
    bursty traffic), the account and first-factor session are already
    good and must not be thrown away over it -- signup_done's "Register
    your passkey" link still works, it just falls back to the Security
    tab's own elevation-code modal (a real, already-built retry path,
    not a dead end) instead of skipping straight to the WebAuthn
    prompt."""
    session = requests.Session()
    response = session.post(
        f"{AUTHELIA_BASE_URL}/api/firstfactor",
        json={"username": username, "password": password, "keepMeLoggedIn": False},
        timeout=10,
    )
    if response.status_code != 200:
        raise AutheliaProvisioningError(
            f"Authelia firstfactor bootstrap failed: {response.status_code} {response.text}",
        )
    if not session.cookies.get("authelia_session"):
        raise AutheliaProvisioningError("Authelia did not return a session cookie")

    method_response = session.post(
        f"{AUTHELIA_BASE_URL}/api/user/info/2fa_method",
        json={"method": "webauthn"},
        timeout=10,
    )
    if method_response.status_code != 200:
        raise AutheliaProvisioningError(
            f"Authelia 2fa_method bootstrap failed: {method_response.status_code} {method_response.text}",
        )

    try:
        _elevate_session(session)
    except AutheliaProvisioningError as exc:
        logger.warning("Skipping passkey pre-elevation for %s: %s", username, exc)

    # Read the cookie last, not right after firstfactor -- confirmed
    # live that Authelia rotates the session's cookie value after
    # elevation (session-fixation protection on a privilege change, the
    # same reason most auth systems reissue a session ID after login).
    # Relaying the pre-elevation value left the browser holding an
    # already-superseded session ID -- it looked first-factor-
    # authenticated to this function (session.cookies always has the
    # *current* value for this function's own later calls) but read as
    # fully anonymous to Authelia on the browser's own next request.
    cookie_value = session.cookies.get("authelia_session")
    if not cookie_value:
        raise AutheliaProvisioningError("Authelia session cookie disappeared after setup")
    return cookie_value


def _latest_notification_code() -> str:
    """Reads the newest one-time code Authelia's filesystem notifier
    wrote (authelia/configuration.yml's notifier.filesystem) -- the same
    `docker exec ... cat /config/notification.txt` grab this session
    already did by hand for every identity-verification code so far.
    Written synchronously as part of handling the POST that triggers it
    (confirmed live), so reading it immediately after that POST is
    reliable at this project's scale (see this module's own header
    comment on why "provisioned rarely, never concurrently" is fine
    here)."""
    result = subprocess.run(
        ["docker", "exec", AUTHELIA_CONTAINER_NAME, "cat", "/config/notification.txt"],
        capture_output=True, text=True, timeout=10,
    )
    codes = re.findall(r"\n([A-Z0-9]{8})\n", result.stdout)
    if not codes:
        raise AutheliaProvisioningError("No one-time code found in Authelia's notification file")
    return codes[-1]


def _elevate_session(session: requests.Session) -> None:
    """Completes Authelia's identity-verification (session elevation)
    challenge server-side, using the same filesystem notifier this whole
    session has been reading by hand -- so the relayed session is
    already elevated, not just first-factor-authenticated, letting the
    caller immediately register a passkey (which requires elevation)
    with zero extra step for the user (2026-09-15, requested explicitly:
    "everything must be passwordless" -- an elevation-code screen with
    no code visible to the user would be exactly as much of a dead end
    as the password screen this replaces).

    Can fail with 429 -- confirmed live that Authelia's own identity-
    verification rate limiter (separate from the login `regulation`
    block, no config knob for it in this version, and its cooldown runs
    minutes not seconds) applies here. Not retried -- the caller
    (bootstrap_authelia_session) treats this as best-effort and falls
    back to the Security tab's own elevation-code modal instead."""
    start_response = session.post(f"{AUTHELIA_BASE_URL}/api/user/session/elevation", timeout=10)
    if start_response.status_code != 200:
        raise AutheliaProvisioningError(
            f"Authelia elevation start failed: {start_response.status_code} {start_response.text}",
        )
    time.sleep(0.5)  # give the filesystem notifier a moment to write
    code = _latest_notification_code()
    verify_response = session.put(
        f"{AUTHELIA_BASE_URL}/api/user/session/elevation",
        json={"otc": code},
        timeout=10,
    )
    if verify_response.status_code != 200:
        raise AutheliaProvisioningError(
            f"Authelia elevation verify failed: {verify_response.status_code} {verify_response.text}",
        )
