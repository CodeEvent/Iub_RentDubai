"""Tests for the identity-verified e-signature gate (2026-09-23):
documents.rentshield.service.request_notarization() no longer emails a
DocuSeal/OpenSign signing link directly -- it first routes the notice's
signer through documents/rentshield_identity/signer_views.py's
token-gated capture flow (NoticeSignerVerification), closing the real
gap found by reading orchestrator.py: DocuSeal/OpenSign email-link
signing has no identity check of its own."""

from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.signing import dumps
from rest_framework.test import APITestCase

from documents.models import Document
from documents.rentshield.custom_fields import key_to_id_map
from documents.rentshield.service import SIGNER_TOKEN_SALT
from documents.rentshield.service import request_notarization
from documents.rentshield.service import _set_custom_field_value
from documents.rentshield_identity.models import NoticeSignerVerification
from documents.rentshield_identity.signer_views import _names_roughly_match


def _make_notice(landlord_name="John Smith", landlord_email="landlord@example.com", add_notarization=True) -> Document:
    owner = User.objects.create_user(username=f"owner-{landlord_email}")
    document = Document.objects.create(owner=owner, title="Test Notice", checksum=landlord_email, mime_type="application/pdf")
    for key, value in {
        "landlord_name": landlord_name,
        "landlord_email": landlord_email,
        "tenant_name": "Jane Tenant",
        "reason": "nonpayment",
        "add_notarization": add_notarization,
    }.items():
        _set_custom_field_value(document, key, value)
    return document


class TestNamesRoughlyMatch(APITestCase):
    def test_identical_names_match(self):
        self.assertTrue(_names_roughly_match("John Smith", "John Smith"))

    def test_subset_of_words_matches(self):
        self.assertTrue(_names_roughly_match("Mohammed Al Futtaim", "Mohammed A. Al Futtaim"))

    def test_different_names_do_not_match(self):
        self.assertFalse(_names_roughly_match("John Smith", "Ahmed Khan"))

    def test_blank_name_is_not_treated_as_a_mismatch(self):
        self.assertTrue(_names_roughly_match("", "John Smith"))


class TestRequestNotarizationGating(APITestCase):
    def test_first_call_creates_a_pending_signer_verification_and_emails_the_signer(self):
        document = _make_notice()
        result = request_notarization(document)

        self.assertEqual(result["status"], "awaiting_signer_verification")
        verification = NoticeSignerVerification.objects.get(document=document)
        self.assertEqual(verification.status, NoticeSignerVerification.Status.PENDING)
        self.assertEqual(verification.signer_email, "landlord@example.com")
        self.assertEqual(verification.signer_name, "John Smith")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["landlord@example.com"])
        self.assertIn("sign-verify/", mail.outbox[0].body)

    def test_does_not_fire_docuseal_until_verified(self):
        document = _make_notice()
        with patch("documents.rentshield.service._fire_signing_request") as fire:
            request_notarization(document)
        fire.assert_not_called()

    def test_already_verified_signer_goes_straight_to_docuseal(self):
        document = _make_notice()
        NoticeSignerVerification.objects.create(
            document=document,
            signer_name="John Smith",
            signer_email="landlord@example.com",
            status=NoticeSignerVerification.Status.VERIFIED,
        )
        with patch("documents.rentshield.service._fire_signing_request", return_value={"status": "sent"}) as fire:
            result = request_notarization(document)

        fire.assert_called_once()
        self.assertEqual(result["status"], "sent")
        self.assertEqual(len(mail.outbox), 0)

    def test_missing_landlord_email_still_raises_before_creating_a_verification_row(self):
        document = _make_notice(landlord_email="")
        with self.assertRaises(ValueError):
            request_notarization(document)
        self.assertFalse(NoticeSignerVerification.objects.filter(document=document).exists())


class TestSignerViews(APITestCase):
    def setUp(self):
        super().setUp()
        self.document = _make_notice()
        self.verification = NoticeSignerVerification.objects.create(
            document=self.document,
            signer_name="John Smith",
            signer_email="landlord@example.com",
        )
        self.token = dumps({"verification_id": self.verification.id}, salt=SIGNER_TOKEN_SALT)

    def test_status_view_rejects_a_bad_token(self):
        response = self.client.get("/api/documents/notice-signer/not-a-real-token/status/")
        self.assertEqual(response.status_code, 400)

    def test_status_view_returns_the_current_status(self):
        response = self.client.get(f"/api/documents/notice-signer/{self.token}/status/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "pending")

    @patch("documents.rentshield_identity.idswyft_client.create_verification_session_for_signer")
    @patch("documents.rentshield_identity.idswyft_client.is_configured", return_value=True)
    def test_start_view_creates_an_idswyft_session(self, _is_configured, create_session):
        create_session.return_value = {"verification_id": "idswyft-123", "hosted_url": ""}
        response = self.client.post(f"/api/documents/notice-signer/{self.token}/start/")
        self.assertEqual(response.status_code, 200)
        create_session.assert_called_once_with(self.verification.id)
        self.verification.refresh_from_db()
        self.assertEqual(self.verification.verification_id, "idswyft-123")

    @patch("documents.rentshield_identity.idswyft_client.is_configured", return_value=False)
    def test_start_view_503s_when_idswyft_is_not_configured(self, _is_configured):
        response = self.client.post(f"/api/documents/notice-signer/{self.token}/start/")
        self.assertEqual(response.status_code, 503)

    def test_upload_views_require_a_session_already_started(self):
        response = self.client.post(
            f"/api/documents/notice-signer/{self.token}/front-document/",
            {"document": SimpleUploadedFile("id.jpg", b"fake", content_type="image/jpeg")},
            format="multipart",
        )
        self.assertEqual(response.status_code, 400)

    @patch("documents.tasks.fire_signing_after_verification_task.delay")
    @patch("documents.rentshield_identity.idswyft_client.upload_live_capture")
    @patch("documents.rentshield_identity.idswyft_client.normalize_image_for_idswyft")
    def test_selfie_upload_that_verifies_and_matches_the_name_fires_the_signing_task(
        self, normalize, upload_live_capture, fire_task,
    ):
        self.verification.verification_id = "idswyft-123"
        self.verification.name_mismatch = False
        self.verification.save()
        normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        upload_live_capture.return_value = {"status": "COMPLETE", "final_result": "verified"}

        response = self.client.post(
            f"/api/documents/notice-signer/{self.token}/live-capture/",
            {"selfie": SimpleUploadedFile("selfie.jpg", b"fake", content_type="image/jpeg")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "verified")
        self.verification.refresh_from_db()
        self.assertEqual(self.verification.status, NoticeSignerVerification.Status.VERIFIED)
        fire_task.assert_called_once_with(self.document.id)

    @patch("documents.tasks.fire_signing_after_verification_task.delay")
    @patch("documents.rentshield_identity.idswyft_client.upload_live_capture")
    @patch("documents.rentshield_identity.idswyft_client.normalize_image_for_idswyft")
    def test_selfie_upload_with_a_name_mismatch_downgrades_to_manual_review_and_does_not_fire_signing(
        self, normalize, upload_live_capture, fire_task,
    ):
        self.verification.verification_id = "idswyft-123"
        self.verification.name_mismatch = True
        self.verification.save()
        normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        upload_live_capture.return_value = {"status": "COMPLETE", "final_result": "verified"}

        response = self.client.post(
            f"/api/documents/notice-signer/{self.token}/live-capture/",
            {"selfie": SimpleUploadedFile("selfie.jpg", b"fake", content_type="image/jpeg")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "manual_review")
        fire_task.assert_not_called()

    @patch("documents.rentshield_identity.idswyft_client.upload_front_document")
    @patch("documents.rentshield_identity.idswyft_client.normalize_image_for_idswyft")
    def test_front_document_upload_flags_a_name_mismatch_from_ocr(self, normalize, upload_front_document):
        self.verification.verification_id = "idswyft-123"
        self.verification.save()
        normalize.return_value = (b"jpeg-bytes", "image/jpeg")
        upload_front_document.return_value = {"status": "AWAITING_LIVE", "ocr_data": {"name": "Someone Else Entirely"}}

        response = self.client.post(
            f"/api/documents/notice-signer/{self.token}/front-document/",
            {"document": SimpleUploadedFile("id.jpg", b"fake", content_type="image/jpeg")},
            format="multipart",
        )

        self.assertEqual(response.status_code, 200)
        self.verification.refresh_from_db()
        self.assertTrue(self.verification.name_mismatch)
        self.assertEqual(self.verification.ocr_full_name, "Someone Else Entirely")
