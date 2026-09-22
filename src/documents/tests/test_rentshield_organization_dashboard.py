"""Integration tests for the Agency Dashboard endpoints
(documents/rentshield_views.py's organization_status_view /
organization_dashboard_view) and the atomicity of the
RentShieldPermissionAuditLog write inside grant_organization_access
(documents/rentshield/signals.py). Codifies the manual test.Client /
shell verification done by hand while building both features."""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from guardian.shortcuts import get_groups_with_perms
from rest_framework.test import APITestCase

from documents.models import CustomFieldInstance
from documents.models import Document
from documents.models import Organization
from documents.models import RentShieldPermissionAuditLog
from documents.rentshield.custom_fields import AWAITING_NOTARY_PUBLIC_TAG_NAME
from documents.rentshield.custom_fields import LEGAL_REVIEW_REQUESTED_TAG_NAME
from documents.rentshield.custom_fields import RENTSHIELD_TAG_NAME
from documents.rentshield.custom_fields import key_to_id_map
from documents.rentshield.signals import grant_organization_access


def _make_org(name: str, zitadel_org_id: str) -> Organization:
    group = Group.objects.create(name=f"{name} group")
    return Organization.objects.create(name=name, zitadel_org_id=zitadel_org_id, group=group)


class TestOrganizationDashboard(APITestCase):
    """GET /api/documents/organization/status/ and
    /api/documents/organization/dashboard/. Note the real contract:
    there is no per-org-id URL parameter -- the endpoint always
    resolves "my own organization" from request.user, so there is no
    "User B requests Org A's dashboard" request to make. The isolation
    guarantees this actually needs are: (1) an org member's own
    dashboard never contains another org's data, and (2) an account
    with no Organization at all (individual self-serve, or a member of
    a different org asking about a specific org) gets a 404, never a
    200 with empty/zeroed data -- see organization_dashboard_view's own
    docstring on why."""

    def setUp(self):
        super().setUp()
        self.org_a = _make_org("Org A", "org-a-zitadel-id")
        self.org_b = _make_org("Org B", "org-b-zitadel-id")

        self.user_a = User.objects.create_user(username="user_a")
        self.user_a.groups.add(self.org_a.group)
        self.user_b = User.objects.create_user(username="user_b")
        self.user_b.groups.add(self.org_b.group)
        self.user_c = User.objects.create_user(username="user_c")  # no Organization

        field_ids = key_to_id_map()
        today = datetime.date.today()

        self.doc_a1 = Document.objects.create(
            owner=self.user_a,
            title="Org A notice 1",
            checksum="org-a-doc-1",
            mime_type="application/pdf",
        )
        self.doc_a1.tags.set(self._tags(RENTSHIELD_TAG_NAME, AWAITING_NOTARY_PUBLIC_TAG_NAME))
        CustomFieldInstance.objects.create(
            document=self.doc_a1,
            field_id=field_ids["notice_date"],
            value_date=today,
        )
        CustomFieldInstance.objects.create(
            document=self.doc_a1,
            field_id=field_ids["notice_period_days"],
            value_int=30,
        )

        self.doc_a2 = Document.objects.create(
            owner=self.user_a,
            title="Org A notice 2",
            checksum="org-a-doc-2",
            mime_type="application/pdf",
        )
        self.doc_a2.tags.set(self._tags(RENTSHIELD_TAG_NAME, LEGAL_REVIEW_REQUESTED_TAG_NAME))

        self.doc_b1 = Document.objects.create(
            owner=self.user_b,
            title="Org B notice 1",
            checksum="org-b-doc-1",
            mime_type="application/pdf",
        )
        self.doc_b1.tags.set(self._tags(RENTSHIELD_TAG_NAME))

    @staticmethod
    def _tags(*names):
        from documents.models import Tag

        return [Tag.objects.get_or_create(name=name)[0] for name in names]

    def test_status_view_reports_organization_membership(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/documents/organization/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"in_organization": True, "organization_name": "Org A"},
        )

    def test_status_view_false_for_individual_account(self):
        self.client.force_authenticate(user=self.user_c)
        response = self.client.get("/api/documents/organization/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data,
            {"in_organization": False, "organization_name": None},
        )

    def test_dashboard_returns_correct_aggregate_metrics_for_org_member(self):
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get("/api/documents/organization/dashboard/")
        self.assertEqual(response.status_code, 200)
        body = response.data

        self.assertEqual(body["organization"], {"id": self.org_a.id, "name": "Org A"})
        self.assertEqual(body["active_notices_count"], 2)

        status_map = {row["tags__name"]: row["count"] for row in body["status_breakdown"]}
        self.assertEqual(status_map.get(AWAITING_NOTARY_PUBLIC_TAG_NAME), 1)
        self.assertEqual(status_map.get(LEGAL_REVIEW_REQUESTED_TAG_NAME), 1)

        deadlines = {row["document_id"]: row for row in body["upcoming_deadlines"]}
        self.assertIn(self.doc_a1.id, deadlines)
        self.assertEqual(deadlines[self.doc_a1.id]["days_remaining"], 30)
        self.assertNotIn(self.doc_a2.id, deadlines)  # no notice_date/period set

        activity_ids = {row["id"] for row in body["recent_activity"]}
        self.assertEqual(activity_ids, {self.doc_a1.id, self.doc_a2.id})

    def test_dashboard_never_leaks_another_organizations_documents(self):
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get("/api/documents/organization/dashboard/")
        self.assertEqual(response.status_code, 200)
        body = response.data

        self.assertEqual(body["organization"], {"id": self.org_b.id, "name": "Org B"})
        self.assertEqual(body["active_notices_count"], 1)
        activity_ids = {row["id"] for row in body["recent_activity"]}
        self.assertEqual(activity_ids, {self.doc_b1.id})
        self.assertNotIn(self.doc_a1.id, activity_ids)
        self.assertNotIn(self.doc_a2.id, activity_ids)
        deadline_doc_ids = {row["document_id"] for row in body["upcoming_deadlines"]}
        self.assertNotIn(self.doc_a1.id, deadline_doc_ids)

    def test_dashboard_404s_for_individual_account_with_no_organization(self):
        self.client.force_authenticate(user=self.user_c)
        response = self.client.get("/api/documents/organization/dashboard/")
        self.assertEqual(response.status_code, 404)

    def test_dashboard_requires_authentication(self):
        response = self.client.get("/api/documents/organization/dashboard/")
        self.assertEqual(response.status_code, 401)


@pytest.mark.django_db
class TestGrantOrganizationAccessAtomicity:
    """documents/rentshield/signals.py's grant_organization_access wraps
    the guardian permission grant and the RentShieldPermissionAuditLog
    write in one transaction.atomic() block. The meaningful failure
    mode to prove rollback against is a failure AFTER
    set_permissions_for_object has already written real permission
    rows -- if set_permissions_for_object itself were the one to fail,
    nothing would have been written yet and "rollback" would be a
    vacuous assertion. Failing the audit-log write instead exercises
    the real guarantee: a real prior DB write in the same block gets
    undone too."""

    def test_failure_writing_audit_log_rolls_back_the_permission_grant(self):
        group = Group.objects.create(name="Atomicity Org group")
        Organization.objects.create(
            name="Atomicity Org",
            zitadel_org_id="atomicity-org-zitadel-id",
            group=group,
        )
        owner = User.objects.create_user(username="atomicity_owner")
        owner.groups.add(group)
        document = Document.objects.create(
            owner=owner,
            title="Atomicity test doc",
            checksum="atomicity-doc",
            mime_type="application/pdf",
        )

        with (
            patch(
                "documents.models.RentShieldPermissionAuditLog.objects.create",
                side_effect=RuntimeError("simulated audit log write failure"),
            ),
            pytest.raises(RuntimeError, match="simulated audit log write failure"),
        ):
            grant_organization_access(sender=None, document=document)

        assert RentShieldPermissionAuditLog.objects.filter(document=document).count() == 0

        groups_with_perms = get_groups_with_perms(document, attach_perms=True)
        assert group not in groups_with_perms, (
            "guardian permission grant was not rolled back alongside the "
            "failed audit log write"
        )

    def test_successful_grant_writes_both_permission_and_audit_row(self):
        group = Group.objects.create(name="Success Org group")
        org = Organization.objects.create(
            name="Success Org",
            zitadel_org_id="success-org-zitadel-id",
            group=group,
        )
        owner = User.objects.create_user(username="success_owner")
        owner.groups.add(group)
        document = Document.objects.create(
            owner=owner,
            title="Success test doc",
            checksum="success-doc",
            mime_type="application/pdf",
        )

        grant_organization_access(sender=None, document=document)

        groups_with_perms = get_groups_with_perms(document, attach_perms=True)
        assert "view_document" in groups_with_perms.get(group, [])
        assert "change_document" in groups_with_perms.get(group, [])

        log_row = RentShieldPermissionAuditLog.objects.get(document=document)
        assert log_row.organization_id == org.id
        assert log_row.action == RentShieldPermissionAuditLog.ACTION_ORGANIZATION_GRANT

    def test_document_with_no_organization_owner_is_a_no_op(self):
        owner = User.objects.create_user(username="no_org_owner")
        document = Document.objects.create(
            owner=owner,
            title="No org doc",
            checksum="no-org-doc",
            mime_type="application/pdf",
        )

        grant_organization_access(sender=None, document=document)

        assert RentShieldPermissionAuditLog.objects.filter(document=document).count() == 0
        assert not get_groups_with_perms(document).exists()
