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

from allauth.socialaccount.models import SocialAccount
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.core import mail
from django.core.signing import dumps
from rest_framework.test import APITestCase

from documents.models import Organization
from documents.models import RentShieldPermissionAuditLog
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
        with (
            patch(
                "documents.rentshield_views.provision_zitadel_user",
                return_value="fake-zitadel-id",
            ) as mock_provision,
            patch(
                "documents.rentshield_views.find_zitadel_user_id_by_username",
                return_value="fake-zitadel-id",
            ),
        ):
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

        log_entry = RentShieldPermissionAuditLog.objects.get(
            action=RentShieldPermissionAuditLog.ACTION_TEAMMATE_INVITED,
        )
        self.assertEqual(log_entry.organization_id, self.org.id)
        self.assertEqual(log_entry.actor_id, self.inviter.id)
        self.assertIn("newteammate@example.com", log_entry.details)

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
        self.assertFalse(
            RentShieldPermissionAuditLog.objects.filter(
                action=RentShieldPermissionAuditLog.ACTION_TEAMMATE_INVITED,
            ).exists(),
        )


class TestOrganizationMembers(APITestCase):
    """organization_members_view / rentshield_invite_resend_view /
    rentshield_invite_revoke_view -- "pending" is derived purely from
    the presence/absence of an allauth SocialAccount(provider="zitadel")
    row, not a stored field, so these tests create that row directly
    to simulate "already completed setup" rather than driving a real
    OIDC login."""

    def setUp(self):
        super().setUp()
        self.org_a = _make_org("Members Org A", "members-org-a-zitadel-id")
        self.org_b = _make_org("Members Org B", "members-org-b-zitadel-id")

        self.requester = User.objects.create_user(username="requester", email="requester@example.com")
        self.requester.groups.add(self.org_a.group)

        self.pending_teammate = User.objects.create_user(
            username="pending_teammate",
            email="pending@example.com",
        )
        self.pending_teammate.groups.add(self.org_a.group)

        self.active_teammate = User.objects.create_user(
            username="active_teammate",
            email="active@example.com",
        )
        self.active_teammate.groups.add(self.org_a.group)
        SocialAccount.objects.create(
            user=self.active_teammate,
            provider="zitadel",
            uid="zitadel-uid-active-teammate",
        )

        self.other_org_member = User.objects.create_user(username="other_org_member")
        self.other_org_member.groups.add(self.org_b.group)

    def test_members_list_reports_pending_and_active_correctly(self):
        self.client.force_authenticate(user=self.requester)
        response = self.client.get("/api/documents/organization/members/")
        self.assertEqual(response.status_code, 200)
        by_username = {row["username"]: row for row in response.data}

        self.assertIn("requester", by_username)
        self.assertIn("pending_teammate", by_username)
        self.assertIn("active_teammate", by_username)
        self.assertNotIn("other_org_member", by_username)

        self.assertTrue(by_username["pending_teammate"]["pending"])
        self.assertFalse(by_username["active_teammate"]["pending"])

    def test_members_list_requires_organization_membership(self):
        lone = User.objects.create_user(username="lone_for_members_test")
        self.client.force_authenticate(user=lone)
        response = self.client.get("/api/documents/organization/members/")
        self.assertEqual(response.status_code, 403)

    def test_resend_works_for_a_pending_teammate(self):
        self.client.force_authenticate(user=self.requester)
        with patch(
            "documents.rentshield_views.find_zitadel_user_id_by_username",
            return_value="fake-zitadel-id",
        ):
            response = self.client.post(
                f"/api/documents/organization/members/{self.pending_teammate.id}/resend/",
            )
        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("pending@example.com", mail.outbox[0].to)

        log_entry = RentShieldPermissionAuditLog.objects.get(
            action=RentShieldPermissionAuditLog.ACTION_TEAMMATE_INVITE_RESENT,
        )
        self.assertEqual(log_entry.organization_id, self.org_a.id)
        self.assertEqual(log_entry.actor_id, self.requester.id)
        self.assertIn("pending@example.com", log_entry.details)

    def test_resend_rejects_an_already_active_teammate(self):
        self.client.force_authenticate(user=self.requester)
        response = self.client.post(
            f"/api/documents/organization/members/{self.active_teammate.id}/resend/",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(mail.outbox), 0)

    def test_resend_404s_for_a_member_of_a_different_organization(self):
        self.client.force_authenticate(user=self.requester)
        response = self.client.post(
            f"/api/documents/organization/members/{self.other_org_member.id}/resend/",
        )
        self.assertEqual(response.status_code, 404)

    def test_revoke_deletes_both_the_zitadel_and_django_user_for_a_pending_teammate(self):
        self.client.force_authenticate(user=self.requester)
        with (
            patch(
                "documents.rentshield_views.find_zitadel_user_id_by_username",
                return_value="fake-zitadel-id",
            ),
            patch("documents.rentshield_views.delete_zitadel_user") as mock_delete,
        ):
            response = self.client.delete(
                f"/api/documents/organization/members/{self.pending_teammate.id}/",
            )
        self.assertEqual(response.status_code, 204)
        mock_delete.assert_called_once_with("fake-zitadel-id", self.org_a)
        self.assertFalse(User.objects.filter(pk=self.pending_teammate.id).exists())

        log_entry = RentShieldPermissionAuditLog.objects.get(
            action=RentShieldPermissionAuditLog.ACTION_TEAMMATE_INVITE_REVOKED,
        )
        self.assertEqual(log_entry.organization_id, self.org_a.id)
        self.assertEqual(log_entry.actor_id, self.requester.id)
        self.assertIn("pending@example.com", log_entry.details)

    def test_revoke_frees_the_email_for_an_immediate_re_invite(self):
        self.client.force_authenticate(user=self.requester)
        with (
            patch("documents.rentshield_views.find_zitadel_user_id_by_username", return_value="id"),
            patch("documents.rentshield_views.delete_zitadel_user"),
        ):
            self.client.delete(f"/api/documents/organization/members/{self.pending_teammate.id}/")

        with (
            patch("documents.rentshield_views.provision_zitadel_user", return_value="new-id"),
            patch("documents.rentshield_views.find_zitadel_user_id_by_username", return_value="new-id"),
        ):
            response = self.client.post(
                "/api/documents/organization/invite/",
                {"email": "pending@example.com"},
            )
        self.assertEqual(response.status_code, 201)

    def test_revoke_rejects_an_already_active_teammate(self):
        self.client.force_authenticate(user=self.requester)
        response = self.client.delete(
            f"/api/documents/organization/members/{self.active_teammate.id}/",
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.active_teammate.id).exists())

    def test_revoke_404s_for_a_member_of_a_different_organization(self):
        self.client.force_authenticate(user=self.requester)
        response = self.client.delete(
            f"/api/documents/organization/members/{self.other_org_member.id}/",
        )
        self.assertEqual(response.status_code, 404)
        self.assertTrue(User.objects.filter(pk=self.other_org_member.id).exists())


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
