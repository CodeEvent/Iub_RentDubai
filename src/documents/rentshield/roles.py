# RentShield's 5 roles are plain Django Groups + paperless-ngx's own
# permission machinery (Django model-level Permissions on Document, plus
# guardian object-level grants via documents.permissions -- see
# create_rentshield_roles.py) -- there is no separate roles/permissions
# table or framework of our own.
#
# - Tenant, Property Owner, Notary: created + given model-level Document
#   permissions by create_rentshield_roles.py.
# - Lawyer: created by create_rentshield_workflows.py (it needs the group
#   to exist to assign it on Workflow #10), given model-level permissions
#   by create_rentshield_roles.py.
# - Full-access Admin: Django's own is_staff/is_superuser, not a group at
#   all -- paperless-ngx (and Django itself) already treats a superuser as
#   unrestricted everywhere, so a 5th "Admin" group would be redundant
#   and, worse, a second, weaker notion of "admin" alongside the real one.
from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework.permissions import BasePermission

TENANT_GROUP_NAME = "Tenant"
PROPERTY_OWNER_GROUP_NAME = "Property Owner"
NOTARY_GROUP_NAME = "Notary"
LAWYER_GROUP_NAME = "Lawyer"

# Model-level Django permissions (paperless-ngx's own auto-generated
# add/view/change/delete_document) granted to each role's Group. This is
# the *ceiling* on what the role can ever do; which specific documents a
# given member actually sees/edits is narrowed further per-document by
# ownership (the Property Owner who generated a notice) or by guardian
# object-level grants a Workflow assigns at consumption time (Notary on
# notarization-requested notices, Lawyer on sensitive-reason notices --
# see create_rentshield_workflows.py).
ROLE_DOCUMENT_PERMISSIONS: dict[str, list[str]] = {
    PROPERTY_OWNER_GROUP_NAME: ["add_document", "view_document", "change_document"],
    TENANT_GROUP_NAME: ["view_document"],
    NOTARY_GROUP_NAME: ["view_document", "change_document"],
    LAWYER_GROUP_NAME: ["view_document", "change_document"],
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
