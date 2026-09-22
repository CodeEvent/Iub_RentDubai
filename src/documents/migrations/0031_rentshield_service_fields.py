# Extends the RentShield CustomField bootstrap (0026-0030) with a
# "RentShield: Served Date" field -- once the Real Notary Public human
# fulfiller marks a notice's "Notary Public Status" completed, that
# completion IS the legal service of the notice on the tenant under
# Article 25(3) of Law No. (33) of 2008 (a notary-public visit is one of
# the three recognized service methods -- see documents/rentshield/
# service_methods.py). documents/rentshield/signals.py stamps this field
# automatically the moment that transition is detected, so the served
# date is recorded without adding a manual step to her existing flow.
#
# Idempotent (get_or_create by name), same pattern as 0026-0030.
from django.db import migrations


def create_service_fields(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")

    CustomField.objects.get_or_create(
        name="RentShield: Served Date",
        defaults={"data_type": "date", "extra_data": None},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0030_rentshield_real_notarization_fields"),
    ]

    operations = [
        migrations.RunPython(create_service_fields, noop_reverse),
    ]
