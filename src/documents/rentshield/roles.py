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
# Angular app requires unconditionally just to finish loading -- most
# critically view/change_uisettings: GET /api/ui_settings/ is the very
# first call the app makes on every load (it's what tells the frontend
# what the user *can* do in the first place, so it can't itself be gated
# behind a permission check), and it 403s outright without this. Found by
# actually logging in as a role-restricted user in a real browser, not by
# API-only testing -- the automated verification in Roles & Permissions
# above never exercised this endpoint.
BASELINE_PERMISSIONS: list[str] = ["view_uisettings", "change_uisettings"]


def user_in_group(user: User | None, group_name: str) -> bool:
    return bool(user and user.is_authenticated and user.groups.filter(name=group_name).exists())


def can_manage_notices(user: User | None) -> bool:
    """Property Owner or Admin: the two RentShield actions that create or
    dispatch a real legal document (generating a notice, requesting
    notarization) are limited to whoever owns the tenancy relationship or
    has full platform access -- not Tenant, Notary, or Lawyer, who each
    only need to view/act on specific documents once one exists."""
    if not user or not user.is_authenticated:
        return False
    return bool(user.is_staff or user.is_superuser or user_in_group(user, PROPERTY_OWNER_GROUP_NAME))


class CanManageNotices(BasePermission):
    """DRF permission for create_notice_view/analyze_document_view/
    notarize_view: Property Owner or Admin role only."""

    def has_permission(self, request, view) -> bool:
        return can_manage_notices(request.user)
