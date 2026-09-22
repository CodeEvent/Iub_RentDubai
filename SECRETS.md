# Secret rotation runbook

Every long-lived credential in the ZITADEL identity stack, where it lives, and how to rotate
it. Written 2026-09-22 after the ZITADEL migration left five real secrets with no rotation
process at all -- this is the "at minimum, before automating" version: a runbook to follow by
hand, not a script. None of the procedures below are guessed; each API call is confirmed against
ZITADEL's own `management.proto` or its documented `--masterkey-old` rotation flow.

## What exists today

| Secret | Lives in | Rotatable? |
|---|---|---|
| `ZITADEL_MASTERKEY` | `.env` | Yes, with a real re-encryption step -- see below |
| `ZITADEL_DB_PASSWORD` | `.env` | Yes, ordinary Postgres credential rotation |
| ZITADEL OIDC client secret | `.env` (`ZITADEL_OIDC_CLIENT_SECRET`), `zitadel/secrets/oidc_app_credentials.txt` | Yes, via ZITADEL's Management API |
| Provisioner PAT | `zitadel/secrets/provisioner.pat` | Yes, via ZITADEL's Management API. Currently expires `2030-01-01` -- effectively unrotated |
| `PAPERLESS_SECRET_KEY` | Dev launch command (hardcoded `devsecretkey`) | Django's own signing key -- **placeholder value, must never reach production** |

None of these have ever been rotated since first being generated this session. No calendar
reminder or automation exists yet -- this table plus the procedures below are step one.

## `ZITADEL_MASTERKEY`

Confirmed live (Phase A of the ZITADEL migration): ZITADEL's own deploy docs originally read as
"cannot be changed without losing access to encrypted data" -- true only if you swap it blind.
ZITADEL actually supports a real rotation path: start the instance with **both**
`--masterkey` (the new key) **and** `--masterkey-old` (the current one). ZITADEL decrypts every
secret with the old key and re-encrypts with the new one; once that finishes, the old key is
no longer needed or usable.

```bash
# 1. Generate a new 32-byte key
NEW_MASTERKEY=$(openssl rand -hex 16)   # exactly 32 chars, like the current one

# 2. Stop zitadel-api, then start it once with both keys so it can re-encrypt
docker compose run --rm zitadel-api \
  start-from-init --masterkey "$NEW_MASTERKEY" --masterkey-old "$OLD_MASTERKEY"

# 3. Once that run completes cleanly, update .env's ZITADEL_MASTERKEY to $NEW_MASTERKEY
#    and restart zitadel-api normally (no --masterkey-old on subsequent starts).
```

Do this rarely and deliberately -- it's a real data re-encryption pass across the whole
instance, not a cheap operation.

## `ZITADEL_DB_PASSWORD`

Ordinary Postgres credential. Rotate via a normal `ALTER USER` + config update, no ZITADEL-side
step needed:

```bash
docker compose exec zitadel-db psql -U zitadel -c "ALTER USER zitadel WITH PASSWORD '<new password>';"
# Update ZITADEL_DB_PASSWORD in .env, then:
docker compose up -d zitadel-api zitadel-db
```

## ZITADEL OIDC client secret

Regenerate via the Management API (confirmed path, `management.proto` line 3934), using the
provisioner PAT the same way `zitadel_provisioning.py` already does:

```bash
curl -sk --resolve zitadel.rentshield.local:9092:127.0.0.1 \
  -H "Authorization: Bearer $(cat zitadel/secrets/provisioner.pat)" \
  -H "x-zitadel-orgid: 391824042086105094" \
  -X POST "https://zitadel.rentshield.local:9092/management/v1/projects/391824049719738374/apps/391824136139177990/oidc_config/_generate_client_secret"
```

Returns a new `clientSecret`. Update `ZITADEL_OIDC_CLIENT_SECRET` in `.env` (and the bare-host
dev launch command's inline JSON, if still running that way) and restart the webserver -- the
old secret stops working the moment the new one is issued, so this is a real cutover, not
additive.

## Provisioner PAT

Create a new one before revoking the old one, so `zitadel_provisioning.py` never has zero valid
credentials mid-rotation:

```bash
# 1. Create a new PAT for the provisioner machine user (need its user_id --
#    look it up in the ZITADEL console under the org's machine users, or
#    GetUserByLoginName for "rentshield-provisioner").
curl -sk --resolve zitadel.rentshield.local:9092:127.0.0.1 \
  -H "Authorization: Bearer $(cat zitadel/secrets/provisioner.pat)" \
  -H "x-zitadel-orgid: 391824042086105094" -H "Content-Type: application/json" \
  -X POST "https://zitadel.rentshield.local:9092/management/v1/users/<provisioner_user_id>/pats" \
  -d '{"expiration_date": "2027-01-01T00:00:00Z"}'

# 2. Replace zitadel/secrets/provisioner.pat with the returned token.

# 3. Only after confirming the new PAT works (e.g. a test provision_zitadel_user call),
#    revoke the old one:
curl -sk ... -X DELETE ".../management/v1/users/<provisioner_user_id>/pats/<old_token_id>"
```

## `PAPERLESS_SECRET_KEY`

Not ZITADEL-related, but the same category of gap: the dev launch command hardcodes
`devsecretkey`. This is fine for local dev, but **rotating this in a real deployment
invalidates every active session and password-reset link** -- standard Django behavior, not
specific to this project. Generate a real one for any non-dev environment:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Not done yet

- No calendar reminder or expiry alerting on any of the above.
- No automation -- every step above is manual.
- The provisioner PAT's `2030-01-01` expiration is a long way off by design (this session set
  it that way deliberately, matching the login-client PAT's own pattern) -- worth shortening
  once a real rotation cadence exists, rather than relying on a five-year-out expiry as the only
  backstop.
