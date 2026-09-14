# Idempotently sets up RentShield's one self-service role Group --
# Property Owner -- with real, model-level Django Document permissions:
# the same mechanism a human admin sets up by hand via Django's own
# Group permission checkboxes. This is the ceiling on what the role can
# ever do; which specific documents a member actually sees/edits is
# narrowed further per-document by ownership alone (paperless-ngx's own
# Document.owner). The other account type, full-access Admin, is
# Django's own is_staff/is_superuser -- not a group, see
# documents/rentshield/roles.py.
#
# This used to also create/maintain Tenant, Notary, and Lawyer Groups
# (see README's dated "Roles simplified" section for why they were cut).
# Real bug found auditing this later (2026-09-13): those three stale
# Group rows were still sitting in the database with real, in one case
# genuinely dangerous, Django model permissions -- "Lawyer" carried
# delete_document/delete_workflow/delete_mailaccount, and the `lawyer`
# dev account was still a member of it. The header comment here used to
# claim this was harmless because "nothing gates on group membership by
# name" -- true, but irrelevant: Django's own user.has_perm() grants a
# permission through ANY group a user belongs to regardless of whether
# any of this app's own code checks that group by name. Deleted all
# three stale groups directly (Group.objects.filter(name=...).delete())
# rather than reversing this with a migration, and made that deletion
# part of what this command does on every run (STALE_GROUP_NAMES below)
# so the same drift can't quietly reappear in another environment
# (production, a freshly seeded CI database, ...) without anyone
# noticing -- it's re-asserted every time this command runs, the same
# "safe to re-run, heals drift" idiom the rest of this command already
# uses for Property Owner/Notary Public's own permission sets.
#
# The `lawyer`/`tenant` dev login accounts themselves (2026-09-14,
# explicitly requested) got the same treatment as the groups above, for
# the same reason -- deleted directly (STALE_USER_NAMES below) and
# re-asserted on every run rather than a one-off manual delete, so a
# fresh/older environment that still has them doesn't quietly keep
# them around. Already dropped from documents/rentshield/dev_accounts.py's
# Quick-dev-login panel list.
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from documents.models import Document
from documents.rentshield.roles import BASELINE_PERMISSIONS
from documents.rentshield.roles import ROLE_DOCUMENT_PERMISSIONS

STALE_GROUP_NAMES = ("Lawyer", "Notary", "Tenant")
STALE_USER_NAMES = ("lawyer", "tenant")


class Command(BaseCommand):
    help = (
        "Idempotently creates RentShield's Property Owner Group with "
        "real Django model-level permissions: Document add/view/change, "
        "plus baseline permissions (view/change_uisettings, view_tag, ...) "
        "that paperless-ngx's own Angular app needs unconditionally just "
        "to load and to use RentShield's own pages -- see "
        "documents/rentshield/roles.py's BASELINE_PERMISSIONS for exactly "
        "which and why. Safe to re-run: always sets the group's "
        "permission set to exactly what's defined in "
        "documents/rentshield/roles.py, so it also heals a group whose "
        "permissions were edited into an inconsistent state."
    )

    def handle(self, *args, **options):
        deleted_count, _ = Group.objects.filter(name__in=STALE_GROUP_NAMES).delete()
        if deleted_count:
            self.stdout.write(
                self.style.WARNING(
                    f"Deleted {deleted_count} stale role Group row(s) "
                    f"({', '.join(STALE_GROUP_NAMES)}) left over from before "
                    "the roles simplification -- any account that was a "
                    "member keeps no permissions from them any more.",
                ),
            )

        deleted_user_count, _ = get_user_model().objects.filter(username__in=STALE_USER_NAMES).delete()
        if deleted_user_count:
            self.stdout.write(
                self.style.WARNING(
                    f"Deleted {deleted_user_count} stale dev login account row(s) "
                    f"({', '.join(STALE_USER_NAMES)}) left over from before the "
                    "roles simplification.",
                ),
            )

        document_content_type = ContentType.objects.get_for_model(Document)
        # Baseline permissions span more than one model (UiSettings, Tag,
        # ...) -- looked up by codename alone rather than pinned to a
        # single content type, since Django's auto-generated codenames
        # (<action>_<model name>) are unique across this app already.
        baseline_permissions = Permission.objects.filter(codename__in=BASELINE_PERMISSIONS)

        for group_name, document_codenames in ROLE_DOCUMENT_PERMISSIONS.items():
            group, created = Group.objects.get_or_create(name=group_name)

            document_permissions = Permission.objects.filter(
                content_type=document_content_type,
                codename__in=document_codenames,
            )
            all_codenames = set(document_codenames) | set(BASELINE_PERMISSIONS)
            found_codenames = set(
                document_permissions.values_list("codename", flat=True),
            ) | set(baseline_permissions.values_list("codename", flat=True))
            missing = all_codenames - found_codenames
            if missing:
                self.stderr.write(
                    self.style.ERROR(
                        f"Could not find Permission(s) {sorted(missing)} -- "
                        f"Django's migrations should have created these "
                        f"automatically. Skipping {group_name!r}.",
                    ),
                )
                continue

            before = set(group.permissions.values_list("codename", flat=True))
            group.permissions.set(list(document_permissions) + list(baseline_permissions))
            after = set(group.permissions.values_list("codename", flat=True))

            if created:
                self.stdout.write(self.style.SUCCESS(f"Created group: {group_name} ({', '.join(sorted(all_codenames))})"))
            elif before != after:
                self.stdout.write(
                    self.style.SUCCESS(f"Repaired permissions on existing group: {group_name} ({', '.join(sorted(all_codenames))})"),
                )
            else:
                self.stdout.write(f"Already up to date: {group_name}")

        self.stdout.write(self.style.SUCCESS("\nRentShield roles created/verified."))
        self.stdout.write(
            self.style.WARNING(
                "Before relying on this:\n"
                "  - No user is a member of Property Owner yet -- add real "
                "users to it under Settings > Users & Groups (or Django "
                "admin). Self-service signup already does this "
                "automatically (documents/rentshield/forms.py).\n"
                "  - Model-level Document permissions are a ceiling, not a "
                "guarantee of visibility: a Property Owner only sees "
                "notices they personally generated (paperless-ngx's own "
                "owner field, set automatically at creation).\n"
                "  - Tenant/Notary/Lawyer Groups, and the lawyer/tenant dev "
                "login accounts, from before the roles simplification (see "
                "README) are actively deleted every time this command runs "
                "(see the top of this run's output if any existed) -- the "
                "Groups carried real Document permissions nothing in this "
                "app's code still means to grant.",
            ),
        )
