"""Tests for the RDSC filing-packet generator (2026-09-23):
documents.rentshield.rdsc_packet + rdsc_packet_view in
documents/rentshield_views.py. Once a notice has been served (its Served
Date custom field is set), this assembles a reference checklist for
Dubai's Rental Dispute Settlement Centre's own online portal
(rdc.gov.ae) -- not an RDC API integration (none exists) and not the RDC
claim form itself."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from documents.models import Document
from documents.rentshield.rdsc_packet import render_rdsc_packet_html
from documents.rentshield.service import _set_custom_field_value


def _make_notice(owner: User, **field_overrides) -> Document:
    document = Document.objects.create(
        owner=owner,
        title="Test Notice",
        checksum=f"rdsc-test-{owner.username}",
        mime_type="application/pdf",
    )
    fields = {
        "landlord_name": "John Smith",
        "tenant_name": "Jane Tenant",
        "reason": "nonpayment",
        "notice_date": "2026-08-01",
        "notice_period_days": 30,
        **field_overrides,
    }
    for key, value in fields.items():
        _set_custom_field_value(document, key, value)
    return document


class TestRenderRdscPacketHtml(APITestCase):
    def test_missing_attachments_are_flagged(self):
        html = render_rdsc_packet_html({"reason": "nonpayment", "tenant_name": "Jane"})
        self.assertIn('class="rs-missing"', html)
        self.assertIn("Ejari certificate", html)
        self.assertIn("Tenancy contract", html)

    def test_present_attachments_are_marked_present(self):
        html = render_rdsc_packet_html(
            {
                "reason": "nonpayment",
                "tenant_name": "Jane",
                "ejari_certificate_document": [5],
                "tenancy_contract_document": [6],
                "service_evidence_document": [7],
                "service_method": "registered_mail",
            },
        )
        # 4 checklist rows total; all 4 present here (notice itself is always present)
        self.assertEqual(html.count('class="rs-present"'), 4)
        self.assertEqual(html.count('class="rs-missing"'), 0)
        self.assertIn("Registered mail with acknowledgment of receipt", html)

    def test_notary_public_service_counts_as_proof_of_service_without_a_separate_upload(self):
        html = render_rdsc_packet_html({"reason": "nonpayment", "tenant_name": "Jane", "service_method": "notary_public"})
        # 3 rows missing (ejari cert, contract, evidence-doc-link) but NOT "proof of service"
        rows = html.split("<li")
        proof_row = next(r for r in rows if "Proof of service" in r)
        self.assertIn("rs-present", proof_row)

    def test_reason_and_service_method_labels_are_resolved(self):
        html = render_rdsc_packet_html({"reason": "demolition", "tenant_name": "Jane", "service_method": "court_bailiff"})
        self.assertIn("Demolition", html)
        self.assertIn("Court bailiff", html)


class TestRdscPacketView(APITestCase):
    def setUp(self):
        super().setUp()
        self.owner = User.objects.create_user(username="rdsc-owner")
        self.owner.user_permissions.add(Permission.objects.get(codename="change_document"))

    def test_requires_authentication(self):
        document = _make_notice(self.owner)
        response = self.client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")
        self.assertEqual(response.status_code, 401)

    def test_rejects_a_notice_that_has_not_been_served(self):
        document = _make_notice(self.owner)
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")
        self.assertEqual(response.status_code, 400)
        self.assertIn("Served Date", response.data["error"])

    @patch("documents.rentshield_views.write_and_consume", return_value="fake-task-id")
    @patch("documents.rentshield.rdsc_packet.build_rdsc_packet", return_value=b"%PDF-fake")
    def test_generates_a_packet_once_served(self, build_packet, write_and_consume):
        document = _make_notice(self.owner, served_date="2026-09-01")
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["task_id"], "fake-task-id")
        build_packet.assert_called_once()
        write_and_consume.assert_called_once()
        _, kwargs = write_and_consume.call_args
        self.assertEqual(kwargs["owner_id"], self.owner.id)

    def test_404s_for_someone_else_s_notice(self):
        other_owner = User.objects.create_user(username="rdsc-other-owner")
        document = _make_notice(other_owner, served_date="2026-09-01")
        self.client.force_authenticate(user=self.owner)
        response = self.client.post(f"/api/documents/notice/{document.id}/rdsc-packet/")
        self.assertEqual(response.status_code, 404)
