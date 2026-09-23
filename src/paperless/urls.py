from allauth.account import views as allauth_account_views
from allauth.mfa.base import views as allauth_mfa_views
from allauth.socialaccount import views as allauth_social_account_views
from allauth.urls import build_provider_urlpatterns
from django.conf import settings
from django.conf.urls import include
from django.contrib import admin
from django.contrib.auth.decorators import login_required
from django.urls import path
from django.urls import re_path
from django.utils.translation import gettext_lazy as _
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.generic import RedirectView
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView
from drf_spectacular.views import SpectacularSwaggerView
from rest_framework.routers import DefaultRouter

from documents.admin_views import dashboard_view
from documents.rentshield_billing.views import checkout_status_view
from documents.rentshield_billing.views import create_checkout_view
from documents.rentshield_billing.views import stripe_webhook_view
from documents.rentshield_identity.admin_views import admin_export_verifications_view
from documents.rentshield_identity.admin_views import admin_list_verifications_view
from documents.rentshield_identity.admin_views import notary_status_view
from documents.rentshield_identity.pairing_views import apk_redirect_view
from documents.rentshield_identity.pairing_views import pair_claim_view
from documents.rentshield_identity.pairing_views import pair_start_view
from documents.rentshield_identity.pairing_views import pair_status_view
from documents.rentshield_identity.views import admin_delete_verification_view
from documents.rentshield_identity.views import admin_reset_verification_view
from documents.rentshield_identity.views import claim_verification_view
from documents.rentshield_identity.views import complete_video_call_view
from documents.rentshield_identity.views import confirm_video_call_view
from documents.rentshield_identity.views import idswyft_webhook_view
from documents.rentshield_identity.views import notary_confirm_view
from documents.rentshield_identity.views import notary_reject_view
from documents.rentshield_identity.views import notary_request_more_info_view
from documents.rentshield_identity.views import release_verification_view
from documents.rentshield_identity.signer_views import notice_signer_verify_page_view
from documents.rentshield_identity.signer_views import signer_start_view
from documents.rentshield_identity.signer_views import signer_status_view
from documents.rentshield_identity.signer_views import signer_upload_front_view
from documents.rentshield_identity.signer_views import signer_upload_selfie_view
from documents.rentshield_identity.views import request_video_call_reschedule_view
from documents.rentshield_identity.views import schedule_video_call_view
from documents.rentshield_identity.views import start_verification_view
from documents.rentshield_identity.views import submit_chip_data_view
from documents.rentshield_identity.views import upload_additional_id_view
from documents.rentshield_identity.views import upload_front_document_view
from documents.rentshield_identity.views import upload_live_capture_view
from documents.rentshield_identity.views import upload_video_view
from documents.rentshield_identity.views import verification_status_view
from documents.rentshield_views import analyze_document_view
from documents.rentshield_views import analyze_uploaded_view
from documents.rentshield_views import check_service_method_view
from documents.rentshield_views import create_notice_view
from documents.rentshield_views import landing_view
from documents.rentshield_views import legal_skill_detail_view
from documents.rentshield_views import legal_skills_view
from documents.rentshield_views import notarize_status_view
from documents.rentshield_views import notarize_uploaded_view
from documents.rentshield_views import notarize_view
from documents.rentshield_views import rdsc_packet_view
from documents.rentshield_views import organization_dashboard_view
from documents.rentshield_views import organization_members_view
from documents.rentshield_views import organization_status_view
from documents.rentshield_views import rentshield_invite_accept_view
from documents.rentshield_views import rentshield_invite_resend_view
from documents.rentshield_views import rentshield_invite_revoke_view
from documents.rentshield_views import rentshield_invite_view
from documents.rentshield_views import rentshield_teammate_deactivate_view
from documents.rentshield_views import rentshield_teammate_reactivate_view
from documents.rentshield_views import signup_done_view
from documents.rentshield_views import signup_email_view
from documents.rentshield_views import signup_start_view
from documents.rentshield_views import signup_verify_view
from documents.rentshield_views import rentshield_logout_view
from documents.rentshield_views import rentshield_passkey_add_view
from documents.rentshield_views import rentshield_passkey_delete_view
from documents.rentshield_views import rentshield_passkeys_view
from documents.rentshield_views import zitadel_passkey_start_view
from documents.rentshield_views import zitadel_passkey_verify_view
from documents.rentshield_views import pricing_view
from documents.rentshield_views import reasons_view
from documents.views import BulkDownloadView
from documents.views import BulkEditObjectsView
from documents.views import BulkEditView
from documents.views import ChatStreamingView
from documents.views import CorrespondentViewSet
from documents.views import CustomFieldViewSet
from documents.views import DeleteDocumentsView
from documents.views import DocumentTypeViewSet
from documents.views import EditPdfDocumentsView
from documents.views import GlobalSearchView
from documents.views import IndexView
from documents.views import LogViewSet
from documents.views import MergeDocumentsAsVersionsView
from documents.views import MergeDocumentsView
from documents.views import PostDocumentView
from documents.views import RemoteVersionView
from documents.views import RemovePasswordDocumentsView
from documents.views import ReprocessDocumentsView
from documents.views import RotateDocumentsView
from documents.views import SavedViewViewSet
from documents.views import SearchAutoCompleteView
from documents.views import SelectionDataView
from documents.views import SharedLinkView
from documents.views import ShareLinkBundleViewSet
from documents.views import ShareLinkViewSet
from documents.views import StatisticsView
from documents.views import StoragePathViewSet
from documents.views import SystemStatusView
from documents.views import TagViewSet
from documents.views import TasksViewSet
from documents.views import TrashView
from documents.views import UiSettingsView
from documents.views import UnifiedSearchViewSet
from documents.views import WorkflowActionViewSet
from documents.views import WorkflowTriggerViewSet
from documents.views import WorkflowViewSet
from documents.views import serve_logo
from paperless.consumers import StatusConsumer
from paperless.views import ApplicationConfigurationViewSet
from paperless.views import DisconnectSocialAccountView
from paperless.views import FaviconView
from paperless.views import GenerateAuthTokenView
from paperless.views import GroupViewSet
from paperless.views import PaperlessObtainAuthTokenView
from paperless.views import ProfileView
from paperless.views import SocialAccountProvidersView
from paperless.views import TOTPView
from paperless.views import UserViewSet
from paperless_mail.views import MailAccountViewSet
from paperless_mail.views import MailRuleViewSet
from paperless_mail.views import OauthCallbackView
from paperless_mail.views import ProcessedMailViewSet

api_router = DefaultRouter()
api_router.register(r"correspondents", CorrespondentViewSet)
api_router.register(r"document_types", DocumentTypeViewSet)
api_router.register(r"documents", UnifiedSearchViewSet)
api_router.register(r"logs", LogViewSet, basename="logs")
api_router.register(r"tags", TagViewSet)
api_router.register(r"saved_views", SavedViewViewSet)
api_router.register(r"storage_paths", StoragePathViewSet)
api_router.register(r"tasks", TasksViewSet, basename="tasks")
api_router.register(r"users", UserViewSet, basename="users")
api_router.register(r"groups", GroupViewSet, basename="groups")
api_router.register(r"mail_accounts", MailAccountViewSet)
api_router.register(r"mail_rules", MailRuleViewSet)
api_router.register(r"share_link_bundles", ShareLinkBundleViewSet)
api_router.register(r"share_links", ShareLinkViewSet)
api_router.register(r"workflow_triggers", WorkflowTriggerViewSet)
api_router.register(r"workflow_actions", WorkflowActionViewSet)
api_router.register(r"workflows", WorkflowViewSet)
api_router.register(r"custom_fields", CustomFieldViewSet)
api_router.register(r"config", ApplicationConfigurationViewSet)
api_router.register(r"processed_mail", ProcessedMailViewSet)


urlpatterns = [
    re_path(
        r"^api/",
        include(
            [
                re_path(
                    "^auth/",
                    include(
                        (
                            [
                                path(
                                    "login/",
                                    allauth_account_views.login,
                                    name="login",
                                ),
                                path(
                                    "logout/",
                                    allauth_account_views.logout,
                                    name="logout",
                                ),
                            ],
                            "rest_framework",
                        ),
                        namespace="rest_framework",
                    ),
                ),
                re_path(
                    "^search/",
                    include(
                        [
                            re_path(
                                "^$",
                                GlobalSearchView.as_view(),
                                name="global_search",
                            ),
                            re_path(
                                "^autocomplete/",
                                SearchAutoCompleteView.as_view(),
                                name="autocomplete",
                            ),
                        ],
                    ),
                ),
                re_path(
                    "^statistics/",
                    StatisticsView.as_view(),
                    name="statistics",
                ),
                re_path(
                    "^documents/",
                    include(
                        [
                            re_path(
                                "^post_document/",
                                PostDocumentView.as_view(),
                                name="post_document",
                            ),
                            # RentShield notice generation -- plumbing
                            # paperless-ngx doesn't have natively (bilingual
                            # PDF rendering, pricing/notice-period math,
                            # e-signature orchestration). Every notice is a
                            # real Document with CustomField values (see
                            # documents/rentshield/); listing and consume-
                            # status polling use paperless-ngx's own stock
                            # GET /api/documents/ and GET /api/tasks/.
                            re_path(
                                "^notice/reasons/",
                                reasons_view,
                                name="rentshield-reasons",
                            ),
                            re_path(
                                "^notice/pricing/",
                                pricing_view,
                                name="rentshield-pricing",
                            ),
                            re_path(
                                "^notice/create/",
                                create_notice_view,
                                name="rentshield-create-notice",
                            ),
                            re_path(
                                r"^notice/checkout/$",
                                create_checkout_view,
                                name="rentshield-checkout",
                            ),
                            re_path(
                                r"^notice/checkout/(?P<order_id>\d+)/status/$",
                                checkout_status_view,
                                name="rentshield-checkout-status",
                            ),
                            re_path(
                                "^notice/stripe-webhook/",
                                stripe_webhook_view,
                                name="rentshield-stripe-webhook",
                            ),
                            re_path(
                                "^notice/analyze/",
                                analyze_document_view,
                                name="rentshield-analyze-document",
                            ),
                            re_path(
                                "^notice/analyze-uploaded/",
                                analyze_uploaded_view,
                                name="rentshield-analyze-uploaded",
                            ),
                            re_path(
                                r"^notice/legal-skills/(?P<skill_id>[\w-]+)/$",
                                legal_skill_detail_view,
                                name="rentshield-legal-skill-detail",
                            ),
                            re_path(
                                "^notice/legal-skills/$",
                                legal_skills_view,
                                name="rentshield-legal-skills",
                            ),
                            re_path(
                                "^notice/check-service-method/",
                                check_service_method_view,
                                name="rentshield-check-service-method",
                            ),
                            re_path(
                                r"^notice/(?P<document_id>\d+)/notarize/$",
                                notarize_view,
                                name="rentshield-notarize",
                            ),
                            re_path(
                                "^notice/notarize-uploaded/",
                                notarize_uploaded_view,
                                name="rentshield-notarize-uploaded",
                            ),
                            re_path(
                                r"^notice/(?P<document_id>\d+)/notarize-status/$",
                                notarize_status_view,
                                name="rentshield-notarize-status",
                            ),
                            re_path(
                                r"^notice/(?P<document_id>\d+)/rdsc-packet/$",
                                rdsc_packet_view,
                                name="rentshield-rdsc-packet",
                            ),
                            re_path(
                                "^security/passkeys/$",
                                rentshield_passkeys_view,
                                name="rentshield-passkeys",
                            ),
                            re_path(
                                "^security/passkeys/add/$",
                                rentshield_passkey_add_view,
                                name="rentshield-passkey-add",
                            ),
                            re_path(
                                r"^security/passkeys/(?P<passkey_id>[\w-]+)/$",
                                rentshield_passkey_delete_view,
                                name="rentshield-passkey-delete",
                            ),
                            re_path(
                                "^organization/status/$",
                                organization_status_view,
                                name="rentshield-organization-status",
                            ),
                            re_path(
                                "^organization/dashboard/$",
                                organization_dashboard_view,
                                name="rentshield-organization-dashboard",
                            ),
                            re_path(
                                "^organization/invite/$",
                                rentshield_invite_view,
                                name="rentshield-organization-invite",
                            ),
                            re_path(
                                "^organization/members/$",
                                organization_members_view,
                                name="rentshield-organization-members",
                            ),
                            re_path(
                                r"^organization/members/(?P<user_id>\d+)/resend/$",
                                rentshield_invite_resend_view,
                                name="rentshield-organization-member-resend",
                            ),
                            re_path(
                                r"^organization/members/(?P<user_id>\d+)/deactivate/$",
                                rentshield_teammate_deactivate_view,
                                name="rentshield-organization-member-deactivate",
                            ),
                            re_path(
                                r"^organization/members/(?P<user_id>\d+)/reactivate/$",
                                rentshield_teammate_reactivate_view,
                                name="rentshield-organization-member-reactivate",
                            ),
                            re_path(
                                r"^organization/members/(?P<user_id>\d+)/$",
                                rentshield_invite_revoke_view,
                                name="rentshield-organization-member-revoke",
                            ),
                            # Property-owner identity verification --
                            # documents/rentshield_identity/, a separate
                            # small app since a verification row has to
                            # exist independently of any Document (see
                            # its apps.py comment).
                            re_path(
                                r"^identity/verify/start/$",
                                start_verification_view,
                                name="rentshield-identity-verify-start",
                            ),
                            re_path(
                                r"^identity/verify/status/$",
                                verification_status_view,
                                name="rentshield-identity-verify-status",
                            ),
                            re_path(
                                r"^identity/verify/front-document/$",
                                upload_front_document_view,
                                name="rentshield-identity-verify-front-document",
                            ),
                            re_path(
                                r"^identity/verify/live-capture/$",
                                upload_live_capture_view,
                                name="rentshield-identity-verify-live-capture",
                            ),
                            re_path(
                                r"^identity/verify/webhook/$",
                                idswyft_webhook_view,
                                name="rentshield-identity-verify-webhook",
                            ),
                            # Notice-signer identity verification --
                            # documents/rentshield_identity/signer_views.py.
                            # Token-gated (AllowAny), not session-gated: the
                            # signer has no RentShield account at all.
                            re_path(
                                r"^notice-signer/(?P<token>[^/]+)/start/$",
                                signer_start_view,
                                name="rentshield-signer-verify-start",
                            ),
                            re_path(
                                r"^notice-signer/(?P<token>[^/]+)/status/$",
                                signer_status_view,
                                name="rentshield-signer-verify-status",
                            ),
                            re_path(
                                r"^notice-signer/(?P<token>[^/]+)/front-document/$",
                                signer_upload_front_view,
                                name="rentshield-signer-verify-front-document",
                            ),
                            re_path(
                                r"^notice-signer/(?P<token>[^/]+)/live-capture/$",
                                signer_upload_selfie_view,
                                name="rentshield-signer-verify-live-capture",
                            ),
                            re_path(
                                r"^identity/verify/admin/list/$",
                                admin_list_verifications_view,
                                name="rentshield-identity-verify-admin-list",
                            ),
                            re_path(
                                r"^identity/verify/admin/export/$",
                                admin_export_verifications_view,
                                name="rentshield-identity-verify-admin-export",
                            ),
                            re_path(
                                r"^identity/verify/notary-status/$",
                                notary_status_view,
                                name="rentshield-identity-verify-notary-status",
                            ),
                            re_path(
                                r"^identity/verify/chip-data/$",
                                submit_chip_data_view,
                                name="rentshield-identity-verify-chip-data",
                            ),
                            re_path(
                                r"^identity/verify/video/$",
                                upload_video_view,
                                name="rentshield-identity-verify-video",
                            ),
                            re_path(
                                r"^identity/verify/additional-id/$",
                                upload_additional_id_view,
                                name="rentshield-identity-verify-additional-id",
                            ),
                            re_path(
                                r"^identity/verify/notary/(?P<verification_id>\d+)/confirm/$",
                                notary_confirm_view,
                                name="rentshield-identity-verify-notary-confirm",
                            ),
                            re_path(
                                r"^identity/verify/notary/(?P<verification_id>\d+)/reject/$",
                                notary_reject_view,
                                name="rentshield-identity-verify-notary-reject",
                            ),
                            re_path(
                                r"^identity/verify/notary/(?P<verification_id>\d+)/request-more-info/$",
                                notary_request_more_info_view,
                                name="rentshield-identity-verify-notary-request-more-info",
                            ),
                            re_path(
                                r"^identity/verify/admin/(?P<verification_id>\d+)/reset/$",
                                admin_reset_verification_view,
                                name="rentshield-identity-verify-admin-reset",
                            ),
                            re_path(
                                r"^identity/verify/admin/(?P<verification_id>\d+)/delete/$",
                                admin_delete_verification_view,
                                name="rentshield-identity-verify-admin-delete",
                            ),
                            # Notary/property-owner video call scheduling
                            # (documents/rentshield_identity/models.py's
                            # IdentityVerificationCall)
                            re_path(
                                r"^identity/verify/notary/(?P<verification_id>\d+)/claim/$",
                                claim_verification_view,
                                name="rentshield-identity-verify-claim",
                            ),
                            re_path(
                                r"^identity/verify/notary/(?P<verification_id>\d+)/release/$",
                                release_verification_view,
                                name="rentshield-identity-verify-release",
                            ),
                            re_path(
                                r"^identity/verify/notary/(?P<verification_id>\d+)/schedule-call/$",
                                schedule_video_call_view,
                                name="rentshield-identity-verify-schedule-call",
                            ),
                            re_path(
                                r"^identity/verify/call/(?P<call_id>\d+)/confirm/$",
                                confirm_video_call_view,
                                name="rentshield-identity-verify-call-confirm",
                            ),
                            re_path(
                                r"^identity/verify/call/(?P<call_id>\d+)/request-reschedule/$",
                                request_video_call_reschedule_view,
                                name="rentshield-identity-verify-call-request-reschedule",
                            ),
                            re_path(
                                r"^identity/verify/notary/(?P<verification_id>\d+)/calls/(?P<call_id>\d+)/complete/$",
                                complete_video_call_view,
                                name="rentshield-identity-verify-call-complete",
                            ),
                            # "Scan to sign in" device pairing --
                            # documents/rentshield_identity/pairing_views.py
                            re_path(
                                r"^identity/pair/start/$",
                                pair_start_view,
                                name="rentshield-identity-pair-start",
                            ),
                            re_path(
                                r"^identity/pair/status/$",
                                pair_status_view,
                                name="rentshield-identity-pair-status",
                            ),
                            re_path(
                                r"^identity/pair/claim/$",
                                pair_claim_view,
                                name="rentshield-identity-pair-claim",
                            ),
                            re_path(
                                "^bulk_edit/",
                                BulkEditView.as_view(),
                                name="bulk_edit",
                            ),
                            re_path(
                                "^delete/",
                                DeleteDocumentsView.as_view(),
                                name="delete_documents",
                            ),
                            re_path(
                                "^reprocess/",
                                ReprocessDocumentsView.as_view(),
                                name="reprocess_documents",
                            ),
                            re_path(
                                "^rotate/",
                                RotateDocumentsView.as_view(),
                                name="rotate_documents",
                            ),
                            re_path(
                                "^merge/",
                                MergeDocumentsView.as_view(),
                                name="merge_documents",
                            ),
                            re_path(
                                "^merge_as_versions/",
                                MergeDocumentsAsVersionsView.as_view(),
                                name="merge_documents_as_versions",
                            ),
                            re_path(
                                "^edit_pdf/",
                                EditPdfDocumentsView.as_view(),
                                name="edit_pdf_documents",
                            ),
                            re_path(
                                "^remove_password/",
                                RemovePasswordDocumentsView.as_view(),
                                name="remove_password_documents",
                            ),
                            re_path(
                                "^bulk_download/",
                                BulkDownloadView.as_view(),
                                name="bulk_download",
                            ),
                            re_path(
                                "^selection_data/",
                                SelectionDataView.as_view(),
                                name="selection_data",
                            ),
                            re_path(
                                "^chat/",
                                ChatStreamingView.as_view(),
                                name="chat_streaming_view",
                            ),
                        ],
                    ),
                ),
                re_path(
                    "^bulk_edit_objects/",
                    BulkEditObjectsView.as_view(),
                    name="bulk_edit_objects",
                ),
                re_path(
                    "^remote_version/",
                    RemoteVersionView.as_view(),
                    name="remoteversion",
                ),
                re_path(
                    "^ui_settings/",
                    UiSettingsView.as_view(),
                    name="ui_settings",
                ),
                path(
                    "token/",
                    PaperlessObtainAuthTokenView.as_view(),
                ),
                re_path(
                    "^profile/",
                    include(
                        [
                            re_path(
                                "^$",
                                ProfileView.as_view(),
                                name="profile_view",
                            ),
                            path(
                                "generate_auth_token/",
                                GenerateAuthTokenView.as_view(),
                            ),
                            path(
                                "disconnect_social_account/",
                                DisconnectSocialAccountView.as_view(),
                            ),
                            path(
                                "social_account_providers/",
                                SocialAccountProvidersView.as_view(),
                            ),
                            path(
                                "totp/",
                                TOTPView.as_view(),
                                name="totp_view",
                            ),
                        ],
                    ),
                ),
                re_path(
                    "^status/",
                    SystemStatusView.as_view(),
                    name="system_status",
                ),
                re_path(
                    "^trash/",
                    TrashView.as_view(),
                    name="trash",
                ),
                re_path(
                    r"^oauth/callback/",
                    OauthCallbackView.as_view(),
                    name="oauth_callback",
                ),
                re_path(
                    "^schema/",
                    include(
                        [
                            re_path(
                                "^$",
                                SpectacularAPIView.as_view(),
                                name="schema",
                            ),
                            re_path(
                                "^view/",
                                SpectacularSwaggerView.as_view(),
                                name="swagger-ui",
                            ),
                        ],
                    ),
                ),
                re_path("^auth/headless/", include("allauth.headless.urls")),
                re_path(
                    "^$",  # Redirect to the API swagger view
                    RedirectView.as_view(url="schema/view/"),
                ),
                *api_router.urls,
            ],
        ),
    ),
    re_path(r"^share/(?P<slug>\w+)/?$", SharedLinkView.as_view()),
    re_path(r"^favicon.ico$", FaviconView.as_view(), name="favicon"),
    path(
        "admin/dashboard/",
        dashboard_view,
        name="rentshield-admin-dashboard",
    ),
    re_path(r"admin/", admin.site.urls),
    re_path(
        r"^fetch/",
        include(
            [
                re_path(
                    r"^doc/(?P<pk>\d+)$",
                    RedirectView.as_view(
                        url=settings.BASE_URL + "api/documents/%(pk)s/download/",
                    ),
                ),
                re_path(
                    r"^thumb/(?P<pk>\d+)$",
                    RedirectView.as_view(
                        url=settings.BASE_URL + "api/documents/%(pk)s/thumb/",
                    ),
                ),
                re_path(
                    r"^preview/(?P<pk>\d+)$",
                    RedirectView.as_view(
                        url=settings.BASE_URL + "api/documents/%(pk)s/preview/",
                    ),
                ),
            ],
        ),
    ),
    # Frontend assets TODO: this is pretty bad, but it works.
    path(
        "assets/<path:path>",
        RedirectView.as_view(
            url=settings.STATIC_URL + "frontend/en-US/assets/%(path)s",
        ),
        # TODO: with localization, this is even worse! :/
    ),
    # App logo
    re_path(r"^logo(?:/(?P<filename>.+))?/?$", serve_logo, name="app_logo"),
    # allauth
    path(
        "accounts/",
        include(
            [
                # see allauth/account/urls.py
                # login, logout, signup, account_inactive
                path("login/", allauth_account_views.login, name="account_login"),
                # RentShield fork (2026-09-22, requested explicitly:
                # "force full re-auth on every logout") -- replaces
                # allauth's own logout view, which only ever cleared the
                # local Django session; see rentshield_logout_view's own
                # comment for why that silently left the browser signed
                # in to ZITADEL.
                path("logout/", rentshield_logout_view, name="account_logout"),
                # RentShield fork (2026-09-18, requested explicitly:
                # signup is only ever managed through /signup/ --
                # allauth's own signup.html renders real
                # username/password fields entirely unconditionally
                # (confirmed live, unlike login.html's own username/
                # password block, this one was never gated behind
                # DISABLE_REGULAR_LOGIN at all) -- a second, parallel
                # account-creation path that bypasses Authelia/passkeys
                # completely. Redirecting the URL itself, not just
                # hiding template fields, so there's no path left to
                # reach that form at all. Kept the name="account_signup"
                # -- other allauth code paths reference this URL by
                # name, e.g. login.html's own "Sign up" link.
                path(
                    "signup/",
                    RedirectView.as_view(pattern_name="rentshield-signup-start", permanent=False),
                    name="account_signup",
                ),
                path(
                    "account_inactive/",
                    allauth_account_views.account_inactive,
                    name="account_inactive",
                ),
                # password reset
                path(
                    "password/",
                    include(
                        [
                            path(
                                "reset/",
                                allauth_account_views.password_reset,
                                name="account_reset_password",
                            ),
                            path(
                                "reset/done/",
                                allauth_account_views.password_reset_done,
                                name="account_reset_password_done",
                            ),
                            path(
                                "reset/key/done/",
                                allauth_account_views.password_reset_from_key_done,
                                name="account_reset_password_from_key_done",
                            ),
                        ],
                    ),
                ),
                re_path(
                    r"^confirm-email/(?P<key>[-:\w]+)/$",
                    allauth_account_views.ConfirmEmailView.as_view(),
                    name="account_confirm_email",
                ),
                re_path(
                    r"^password/reset/key/(?P<uidb36>[0-9A-Za-z]+)-(?P<key>.+)/$",
                    allauth_account_views.password_reset_from_key,
                    name="account_reset_password_from_key",
                ),
                # social account base urls, see allauth/socialaccount/urls.py
                path(
                    "3rdparty/",
                    include(
                        [
                            path(
                                "login/cancelled/",
                                allauth_social_account_views.login_cancelled,
                                name="socialaccount_login_cancelled",
                            ),
                            path(
                                "login/error/",
                                allauth_social_account_views.login_error,
                                name="socialaccount_login_error",
                            ),
                            path(
                                "signup/",
                                allauth_social_account_views.signup,
                                name="socialaccount_signup",
                            ),
                        ],
                    ),
                ),
                *build_provider_urlpatterns(),
                # mfa, see allauth/mfa/base/urls.py
                path(
                    "2fa/authenticate/",
                    allauth_mfa_views.authenticate,
                    name="mfa_authenticate",
                ),
            ],
        ),
    ),
    # Public landing page -- the one URL in this project deliberately
    # NOT behind login_required (see documents/rentshield_views.py's
    # landing_view docstring for why: it has to render for a visitor who
    # hasn't signed in yet, so it can't be an Angular route -- Angular's
    # entire index.html is gated below). Must be registered before the
    # catch-all "Root of the Frontend" pattern so it isn't shadowed.
    re_path(
        r"^welcome/?$",
        landing_view,
        name="rentshield-landing",
    ),
    # Signup (2026-09-15) -- see rentshield_views.py's own header comment
    # on the signup_* views: email + a real one-time code creates the
    # account (Django + a matching Authelia entry) directly now --
    # Authelia is the only signup/signin path, NFC/chip verification
    # happens afterward, once logged in, on the pre-existing identity-
    # verification page. Anonymous by nature (same as /welcome/ above),
    # so registered here, before the login-gated catch-all.
    #
    # Path is /login/, not /signup/ (2026-09-18, requested explicitly)
    # -- this one page is the single entry point for BOTH an existing
    # user signing in and a new user signing up (its own heading says
    # "Sign in to RentShield"), so /signup/ read as inconsistent with
    # what the page actually does. View function/URL names are
    # unchanged (`signup_*_view` / `rentshield-signup-*`) -- every other
    # reference to these already goes through reverse()/{% url %} by
    # name, confirmed by searching the whole repo for hardcoded
    # "/signup/" strings before this rename (only this file and this
    # fork's FirstFactorForm.tsx had any).
    re_path(r"^login/?$", signup_start_view, name="rentshield-signup-start"),
    re_path(r"^login/email/?$", signup_email_view, name="rentshield-signup-email"),
    re_path(r"^login/verify/?$", signup_verify_view, name="rentshield-signup-verify"),
    re_path(r"^login/done/?$", signup_done_view, name="rentshield-signup-done"),
    # B2B teammate invites (2026-09-22) -- public, no login required,
    # same as the /login/* signup steps above: an invited user has no
    # session yet either. See rentshield_invite_accept_view's own
    # comment.
    re_path(r"^invite/accept/?$", rentshield_invite_accept_view, name="rentshield-invite-accept"),
    # Notice-signer identity verification page (2026-09-23) -- public, no
    # login required, same reasoning as /login/* and /invite/accept/
    # above: a notice signer has no RentShield account either. See
    # signer_views.py's notice_signer_verify_page_view docstring.
    re_path(r"^sign-verify/?$", notice_signer_verify_page_view, name="rentshield-signer-verify-page"),
    # ZITADEL migration Phase D -- called cross-origin from the
    # zitadel.rentshield.local bridge page, not from anything on this
    # domain. Not yet reachable through the real signup flow (Phase F).
    re_path(r"^zitadel/passkey/start/?$", zitadel_passkey_start_view, name="rentshield-zitadel-passkey-start"),
    re_path(r"^zitadel/passkey/verify/?$", zitadel_passkey_verify_view, name="rentshield-zitadel-passkey-verify"),
    # Short, stable link to download the Android app (2026-09-14,
    # explicitly requested -- the long cache-busted static URL changes
    # on every rebuild, which is exactly wrong for something meant to
    # be typed/QR-scanned and reused). See
    # documents/rentshield_identity/pairing_views.py's apk_redirect_view.
    # Must be registered before the catch-all "Root of the Frontend"
    # pattern so it isn't shadowed, same as the landing page above.
    re_path(
        r"^app/?$",
        apk_redirect_view,
        name="rentshield-apk-redirect",
    ),
    # Uploaded identity-verification evidence
    # (documents/rentshield_identity/) -- dev-only convenience serving,
    # same reasoning as Django's own django.conf.urls.static.static()
    # helper; a real deployment serves MEDIA_ROOT via its own front-end
    # web server, not this process. Must be registered before the
    # catch-all "Root of the Frontend" pattern so it isn't shadowed, same
    # as the landing page above.
    *(
        [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
        if settings.DEBUG
        else []
    ),
    # Root of the Frontend
    re_path(
        r".*",
        login_required(ensure_csrf_cookie(IndexView.as_view())),
        name="base",
    ),
]


websocket_urlpatterns = [
    path("ws/status/", StatusConsumer.as_asgi()),
]

# Text in each page's <h1> (and above login form).
admin.site.site_header = "Paperless-ngx"
# Text at the end of each page's <title>.
admin.site.site_title = "Paperless-ngx"
# Text at the top of the admin index page.
admin.site.index_title = _("Paperless-ngx administration")
