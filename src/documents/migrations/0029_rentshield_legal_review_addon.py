# Extends the RentShield CustomField bootstrap (0026/0027/0028) with the
# "Legal Review" paid add-on: a boolean field on the notice plus the tag
# an admin filters by to find notices that requested it. See README's
# dated "Roles simplified" section -- this replaces the old Lawyer
# role's one real use (reviewing sensitive-reason notices) with a plain
# add-on fulfilled by a tag + an email, not in-app RBAC.
#
# Idempotent (get_or_create by name), same pattern as 0026/0027/0028.
from django.db import migrations


def create_legal_review_addon_field(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")
    Tag = apps.get_model("documents", "Tag")

    CustomField.objects.get_or_create(
        name="RentShield: Legal Review Add-on",
        defaults={"data_type": "boolean", "extra_data": None},
    )

    Tag.objects.get_or_create(
        name="Legal Review Requested",
        defaults={"color": "#8b5cf6"},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0028_rentshield_notarization_review_fields"),
    ]

    operations = [
        migrations.RunPython(create_legal_review_addon_field, noop_reverse),
    ]
