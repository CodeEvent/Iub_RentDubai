# Extends the RentShield CustomField bootstrap (0026) with the fields
# and tags the AI compliance-review pipeline needs: a place to store the
# citation-graph findings on a document, and tags marking a document as
# a landlord-uploaded tenancy contract vs. one that's already been
# reviewed. See documents/rentshield/service.py's run_ai_review().
#
# Idempotent (get_or_create by name), same pattern as 0026.
from django.db import migrations


def create_ai_review_fields(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")
    Tag = apps.get_model("documents", "Tag")

    CustomField.objects.get_or_create(
        name="RentShield: AI Review Summary",
        defaults={"data_type": "longtext", "extra_data": None},
    )
    CustomField.objects.get_or_create(
        name="RentShield: AI Review Findings Count",
        defaults={"data_type": "integer", "extra_data": None},
    )

    Tag.objects.get_or_create(
        name="Tenancy Contract",
        defaults={"color": "#6366f1"},
    )
    Tag.objects.get_or_create(
        name="AI-Reviewed",
        defaults={"color": "#059669"},
    )
    Tag.objects.get_or_create(
        name="Needs AI Review",
        defaults={"color": "#f59e0b"},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0026_rentshield_custom_fields"),
    ]

    operations = [
        migrations.RunPython(create_ai_review_fields, noop_reverse),
    ]
