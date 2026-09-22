# RentShield has 2 account types: Property Owner (plain Django Group +
# paperless-ngx's own model-level Document permissions) and full-access
# Admin (Django's own is_staff/is_superuser, not a group at all --
# paperless-ngx, and Django itself, already treats a superuser as
# unrestricted everywhere, so a separate "Admin" group would be
# redundant and, worse, a second, weaker notion of "admin" alongside the
# real one). There is no separate roles/permissions table or framework
# of our own.
#
# Previously (see README's dated "Roles simplified" section) there were
# 4 self/admin-assignable roles -- Tenant, Notary, and Lawyer alongside
# Property Owner. Cut because: Tenant had no working per-notice
# visibility (tenant_name is free text, not linked to a real account) so
# a self-registered Tenant saw a permanently empty Notices list; Notary
# duplicated what the DocuSeal/OpenSign e-signature integration already
# automates; and Lawyer's object-permission-grant machinery was this
# project's single biggest source of real bugs (see the "bug found and
# fixed" entries this same file used to carry). Lawyer's one real use --
# flagging sensitive-reason notices for legal review -- is now a plain
# paid add-on (a tag + an email an admin acts on manually), not a login
# role; see documents/rentshield/pricing.py's "Legal Review" entry and
# create_notice_view's add_legal_review handling.
#
# Notary Public (2026-09-13) is a deliberate, requested exception to
# "no roles/permissions table" above -- reviewing an identity
# verification's video before it can become VERIFIED. Explicitly NOT a
# repeat of the old Lawyer mistake: it's a flat Group membership check
# (NOTARY_PUBLIC_GROUP_NAME below) with no per-object grant of any kind,
# because IdentityVerification has no Document-style ownership/visibility
# model to begin with -- a Notary either can or can't see the review
# queue, there's no "which specific rows" layer to get wrong.
from __future__ import annotations

from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from rest_framework.permissions import BasePermission

PROPERTY_OWNER_GROUP_NAME = "Property Owner"
NOTARY_PUBLIC_GROUP_NAME = "Notary Public"

# Model-level Django permissions (paperless-ngx's own auto-generated
# add/view/change/delete_document) granted to the Property Owner Group.
# This is the *ceiling* on what the role can ever do; which specific
# documents a member actually sees/edits is narrowed further by
# ownership (paperless-ngx's own Document.owner, set automatically at
# creation) -- there is no other role/object-grant layer any more.
ROLE_DOCUMENT_PERMISSIONS: dict[str, list[str]] = {
    PROPERTY_OWNER_GROUP_NAME: ["add_document", "view_document", "change_document"],
    # No Document permissions at all -- a Notary reviews
    # IdentityVerification rows (admin_views.py), a separate model with
    # no Document/tag involvement, so only the baseline permissions
    # every logged-in RentShield account needs (below) apply.
    NOTARY_PUBLIC_GROUP_NAME: [],
}

# Every one of these role groups also needs paperless-ngx's own baseline
# permissions that have nothing to do with documents but that its own
# Angular app requires unconditionally just to finish loading or to use
# RentShield's own pages -- found the same way each time (a real user
# testing in a real browser, not the API-only automated checks, which
# never exercise these specific calls):
#   - view/change_uisettings: GET /api/ui_settings/ is the very first
#     call the app makes on every load (it tells the frontend what the
#     user *can* do in the first place, so it can't itself be gated
#     behind a permission check) -- 403s outright without this.
#   - view_tag: rentshield-api.service.ts resolves the "RentShield
#     Notice" tag's id via GET /api/tags/?name__iexact=... to build the
#     Notices list's filter query -- 403s the Notices page without this
#     (tag *creation* on notice generation happens server-side via the
#     ORM directly in documents/rentshield/service.py, not through this
#     API, so add_tag isn't needed here).
BASELINE_PERMISSIONS: list[str] = ["view_uisettings", "change_uisettings", "view_tag"]


def user_in_group(user: User | None, group_name: str) -> bool:
    return bool(user and user.is_authenticated and user.groups.filter(name=group_name).exists())


def get_user_organization(user: User | None):
    """B2B cross-tenant isolation (2026-09-22, see /home/giova/.claude/
    plans/synchronous-finding-storm.md) -- returns the Organization
    `user` belongs to, or None for an individual self-serve account
    (the common case; unaffected by any of this). A user's org is
    whichever Organization.group they're a member of -- ordinary Django
    group membership, not a separate table. Deliberately the only
    lookup function for this: documents/rentshield/signals.py's
    document_consumption_finished handler is the one caller."""
    from documents.models import Organization

    if not user or not user.is_authenticated:
        return None
    return Organization.objects.filter(group__in=user.groups.all()).first()


def grant_property_owner(user: User) -> None:
    """Every self-serve signup path grants exactly this one role (see
    this file's header comment on why Tenant/Notary/Lawyer aren't
    self-serve) -- shared by RentShieldSignupExtra.signup() (the normal
    web signup form) and pairing_views.py's signup_complete_view (the
    QR+biometric+NFC signup) so the two paths can't drift apart."""
    group, _ = Group.objects.get_or_create(name=PROPERTY_OWNER_GROUP_NAME)
    user.groups.add(group)


def can_manage_notices(user: User | None) -> bool:
    """Whether `user` can generate a RentShield notice.

    Deliberately just Django's own "documents.add_document" permission --
    the exact same Document > Add checkbox an admin already sees and
    edits under Settings > Users & Groups (or on a single user's own
    permission list there) -- not a separate, hidden rule checking group
    membership by name. Property Owner is granted this by default (see
    ROLE_DOCUMENT_PERMISSIONS below); ticking "Add" for Document on any
    other group or on an individual user extends the ability to them too,
    with no code change needed here. `has_perm` already treats an active
    superuser as having every permission, so no separate staff/superuser
    check is needed.

    (Previously this checked PROPERTY_OWNER_GROUP_NAME membership
    directly, which meant granting "Add" on Document to another group
    through the real permissions UI silently did nothing -- confirmed by
    a real admin doing exactly that and the action still being refused.)
    """
    if not user or not user.is_authenticated:
        return False
    return user.has_perm("documents.add_document")


def can_act_on_document(user: User | None) -> bool:
    """Whether `user` can dispatch an action against an existing
    document (e.g. requesting notarization) -- Django's own
    "documents.change_document" permission, same reasoning as
    can_manage_notices() above. Which *specific* document a request can
    act on is still checked separately (ownership or an explicit
    object-level grant), this only gates the action in general."""
    if not user or not user.is_authenticated:
        return False
    return user.has_perm("documents.change_document")


class CanManageNotices(BasePermission):
    """DRF permission for create_notice_view/analyze_document_view:
    requires Django's own "Add Document" permission."""

    def has_permission(self, request, view) -> bool:
        return can_manage_notices(request.user)


class CanActOnDocument(BasePermission):
    """DRF permission for notarize_view: requires Django's own "Change
    Document" permission. Object-level visibility for the specific
    document is checked separately by the view itself."""

    def has_permission(self, request, view) -> bool:
        return can_act_on_document(request.user)


class IsRentshieldAdmin(BasePermission):
    """DRF permission for admin-only RentShield views (the identity-
    verification review page) -- is_staff alone, same check
    src-ui/src/app/services/permissions.service.ts's isAdmin() already
    uses on the frontend, not is_superuser: this project's "Admin"
    account type is is_staff/is_superuser together (see this file's own
    header comment), and every other admin-gated page in the app already
    treats is_staff as sufficient to see the page."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_staff)


def is_notary_public(user: User | None) -> bool:
    """Flat Group membership only -- see this file's header comment on
    why that's a real, different thing from the old Lawyer role's
    per-object grants. Staff/superusers can always act too (an admin
    should never be locked out of a queue a lower-privileged Notary
    account can reach)."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user_in_group(user, NOTARY_PUBLIC_GROUP_NAME)


class IsNotaryPublic(BasePermission):
    """DRF permission for the identity-verification video review queue
    (admin_views.py's notary_confirm_view/notary_reject_view, and the
    admin list view also accepts this so a Notary can see what they're
    reviewing)."""

    def has_permission(self, request, view) -> bool:
        return is_notary_public(request.user)
