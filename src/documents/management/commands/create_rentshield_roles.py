# Idempotently sets up RentShield's 4 role Groups (Tenant, Property
# Owner, Notary, Lawyer) with real, model-level Django Document
# permissions -- the same mechanism a human admin sets up by hand via
# Django's own Group permission checkboxes. This is the ceiling on what
# each role can ever do; which specific documents a member actually
# sees/edits is narrowed further per-document by ownership or by a
# Workflow's object-level grant (see create_rentshield_workflows.py's
# Notary/Lawyer grants). The 5th role, full-access Admin, is Django's own
# is_staff/is_superuser -- not a group, see documents/rentshield/roles.py.
from __future__ import annotations

from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from documents.models import Document
from documents.rentshield.roles import BASELINE_PERMISSIONS
from documents.rentshield.roles import LAWYER_GROUP_NAME
from documents.rentshield.roles import ROLE_DOCUMENT_PERMISSIONS


class Command(BaseCommand):
    help = (
        "Idempotently creates RentShield's Tenant, Property Owner, and "
        "Notary Groups (and fixes up model-level permissions on the "
        "Lawyer group created by create_rentshield_workflows) with real "
        "Django model-level permissions: Document permissions per role, "
        "plus baseline permissions on every role that paperless-ngx's own "
        "Angular app needs unconditionally just to load and to use "
        "RentShield's own pages -- see documents/rentshield/roles.py's "
        "BASELINE_PERMISSIONS for exactly which and why. Safe to re-run: "
        "always sets each group's permission set to exactly what's "
        "defined in documents/rentshield/roles.py, so it also heals a "
        "group whose permissions were edited into an inconsistent state."
    )

    def handle(self, *args, **options):
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
                "Before relying on these:\n"
                "  - No user is a member of any of these groups yet -- add "
                "real users to Tenant/Property Owner/Notary/Lawyer under "
                "Settings > Users & Groups (or Django admin), based on their "
                "actual role.\n"
                "  - Model-level Document permissions are a ceiling, not a "
                "guarantee of visibility: a Property Owner only sees "
                "notices they personally generated (paperless-ngx's own "
                "owner field, set automatically at creation); a Notary only "
                "sees notices with notarization requested (Workflow "
                f"'RentShield: grant Notary access on notarization request'); "
                "a Lawyer only sees sensitive-reason notices (Workflow "
                "'RentShield: restrict sensitive notices'). Run "
                "`manage.py create_rentshield_workflows` if you haven't -- "
                "those two Workflows are what actually grant per-document "
                "access.\n"
                f"  - {LAWYER_GROUP_NAME}/Notary object grants normally only "
                "apply going forward (Workflow triggers fire on "
                "DOCUMENT_ADDED, not retroactively) -- `manage.py "
                "create_rentshield_workflows` also backfills the grant for "
                "any already-existing matching document each time it runs, "
                "so re-run it after creating roles/demo data out of order.\n"
                "  - There is no Tenant-facing scoping yet: tenant_name on "
                "a notice is free text, not a link to a real user account, "
                "so a Tenant-group member sees nothing until an admin "
                "manually grants them view access to their own notice(s). "
                "Linking a real user account to a notice's tenant is bigger "
                "schema work, named here rather than silently skipped.",
            ),
        )
