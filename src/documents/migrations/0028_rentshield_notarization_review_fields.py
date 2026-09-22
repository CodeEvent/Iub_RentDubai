# Extends the RentShield CustomField bootstrap (0026/0027) with what the
# notarization review-gate pipeline needs: a place for a Property Owner/
# Lawyer to confirm a notice's details before it's dispatched to a
# notary, and tags marking that notice's stage through the pipeline
# (Pending Review -> Being Notarized -> Notarized/Notarization Failed).
# See documents/rentshield/service.py and
# manage.py create_rentshield_workflows.
#
# Idempotent (get_or_create by name), same pattern as 0026/0027.
from django.db import migrations


def create_notarization_review_fields(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")
    Tag = apps.get_model("documents", "Tag")

    CustomField.objects.get_or_create(
        name="RentShield: Details Confirmed",
        defaults={"data_type": "boolean", "extra_data": None},
    )

    Tag.objects.get_or_create(
        name="Pending Review",
        defaults={"color": "#f59e0b"},
    )
    Tag.objects.get_or_create(
        name="Being Notarized",
        defaults={"color": "#6366f1"},
    )
    Tag.objects.get_or_create(
        name="Notarized",
        defaults={"color": "#059669"},
    )
    Tag.objects.get_or_create(
        name="Notarization Failed",
        defaults={"color": "#dc2626"},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0027_rentshield_ai_review_fields"),
    ]

    operations = [
        migrations.RunPython(create_notarization_review_fields, noop_reverse),
    ]
