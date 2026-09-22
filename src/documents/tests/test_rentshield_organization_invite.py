"""Integration tests for the B2B teammate invite flow
(documents/rentshield_views.py's rentshield_invite_view /
rentshield_invite_accept_view). Codifies the manual test.Client / shell
verification done by hand while building the feature -- including a
regression test for a real bug caught during live browser testing: a
failed ZITADEL provisioning call used to leave an orphaned local User
row behind (no ZITADEL identity, so no passkey is ever possible, and
its mere existence permanently blocked re-inviting the same email)."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.core import mail
from django.core.signing import dumps
from rest_framework.test import APITestCase

from documents.models import Organization
from documents.rentshield.zitadel_provisioning import ZitadelProvisioningError
from documents.rentshield_views import INVITE_TOKEN_SALT


def _make_org(name: str, zitadel_org_id: str) -> Organization:
    group = Group.objects.create(name=f"{name} group")
    return Organization.objects.create(name=name, zitadel_org_id=zitadel_org_id, group=group)


class TestOrganizationInvite(APITestCase):
    def setUp(self):
        super().setUp()
        self.org = _make_org("Invite Test Org", "invite-test-org-zitadel-id")
        self.inviter = User.objects.create_user(username="inviter", email="inviter@example.com")
        self.inviter.groups.add(self.org.group)
        self.lone_user = User.objects.create_user(username="lone_user")  # no Organization

    def test_invite_requires_authentication(self):
        response = self.client.post("/api/documents/organization/invite/", {"email": "x@example.com"})
        self.assertEqual(response.status_code, 401)

    def test_invite_requires_the_inviter_to_belong_to_an_organization(self):
        self.client.force_authenticate(user=self.lone_user)
        response = self.client.post("/api/documents/organization/invite/", {"email": "x@example.com"})
        self.assertEqual(response.status_code, 403)

    def test_invite_rejects_an_invalid_email(self):
        self.client.force_authenticate(user=self.inviter)
        response = self.client.post("/api/documents/organization/invite/", {"email": "not-an-email"})
        self.assertEqual(response.status_code, 400)

    def test_invite_rejects_an_email_that_already_has_an_account(self):
        User.objects.create_user(username="existing", email="existing@example.com")
        self.client.force_authenticate(user=self.inviter)
        response = self.client.post(
            "/api/documents/organization/invite/",
            {"email": "existing@example.com"},
        )
        self.assertEqual(response.status_code, 400)

    def test_successful_invite_creates_a_passwordless_org_member_and_emails_a_link(self):
        self.client.force_authenticate(user=self.inviter)
        with patch(
            "documents.rentshield_views.provision_zitadel_user",
            return_value="fake-zitadel-id",
        ) as mock_provision:
            response = self.client.post(
                "/api/documents/organization/invite/",
                {"email": "newteammate@example.com"},
            )
        self.assertEqual(response.status_code, 201)

        invited = User.objects.get(email="newteammate@example.com")
        self.assertFalse(invited.has_usable_password())
        self.assertIn(self.org.group, invited.groups.all())
        mock_provision.assert_called_once()
        self.assertEqual(mock_provision.call_args.kwargs["organization"], self.org)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("newteammate@example.com", mail.outbox[0].to)
        self.assertIn("/invite/accept", mail.outbox[0].body)

    def test_failed_zitadel_provisioning_does_not_leave_an_orphaned_user(self):
        """Regression test for a real bug caught during live browser
        testing (2026-09-22): provision_zitadel_user used to be called
        AFTER the transaction.atomic() block that created the local
        User row, so a real ZITADEL failure (confirmed live: a 403
        "Organisation doesn't exist") left that row committed anyway --
        permanently orphaned, since a User with no ZITADEL identity can
        never register a passkey in this passwordless-only app, and its
        mere existence would reject any future re-invite of the same
        email. Fixed by moving the provisioning call inside the same
        atomic block."""
        self.client.force_authenticate(user=self.inviter)
        self.client.raise_request_exception = False
        with patch(
            "documents.rentshield_views.provision_zitadel_user",
            side_effect=ZitadelProvisioningError("simulated ZITADEL failure"),
        ):
            response = self.client.post(
                "/api/documents/organization/invite/",
                {"email": "orphan-check@example.com"},
            )
        self.assertEqual(response.status_code, 500)
        self.assertFalse(User.objects.filter(email="orphan-check@example.com").exists())


class TestOrganizationInviteAccept(APITestCase):
    def setUp(self):
        super().setUp()
        self.invited_user = User.objects.create_user(
            username="invited_teammate",
            email="invited@example.com",
        )

    def _token(self, **overrides):
        payload = {"zitadel_user_id": "fake-zitadel-id-123", "username": self.invited_user.username}
        payload.update(overrides)
        return dumps(payload, salt=INVITE_TOKEN_SALT)

    def test_valid_token_redirects_into_the_existing_signup_done_flow(self):
        response = self.client.get("/invite/accept/", {"token": self._token()})
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/done", response.url)
        session = self.client.session
        self.assertEqual(session["signup_zitadel_user_id"], "fake-zitadel-id-123")
        self.assertEqual(session["signup_zitadel_username"], self.invited_user.username)

    def test_garbage_token_404s_rather_than_500s(self):
        response = self.client.get("/invite/accept/", {"token": "not-a-real-token"})
        self.assertEqual(response.status_code, 404)

    def test_expired_token_shows_a_friendly_page_not_a_500(self):
        with patch("documents.rentshield_views.INVITE_TOKEN_MAX_AGE_SECONDS", -1):
            response = self.client.get("/invite/accept/", {"token": self._token()})
        self.assertEqual(response.status_code, 400)

    def test_accept_link_is_reusable(self):
        """No one-time state is consumed by visiting this link -- see
        rentshield_invite_accept_view's own comment on why that's
        deliberate (the account is already created at invite-send time,
        so a lost/re-clicked email link just re-shows the passkey
        bridge, harmlessly)."""
        token = self._token()
        first = self.client.get("/invite/accept/", {"token": token})
        second = self.client.get("/invite/accept/", {"token": token})
        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 302)
