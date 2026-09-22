# Every STATUTORY_REASONS/BREACH_REASONS entry (documents/rentshield/
# constants.py) already carries a "warning" -- e.g. demolition/renovation
# require a permit/technical report at the RDSC, personal-use carries a
# 2-year non-relet restriction -- but until now the form only displayed
# it; nothing stopped a landlord generating and paying for the notice
# without it being true. This field records an affirmative attestation
# (checked in the notice form, enforced in rentshield_views.py's
# validate_notice_fields()) instead of a silently ignorable note --
# RentShield can't verify a government permit exists, but it can require
# the landlord to represent that it does, which is the honest, achievable
# version of "enforcing" this.
#
# Idempotent (get_or_create by name), same pattern as 0026-0031.
from django.db import migrations


def create_field(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")

    CustomField.objects.get_or_create(
        name="RentShield: Reason Requirements Acknowledged",
        defaults={"data_type": "boolean", "extra_data": None},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0031_rentshield_service_fields"),
    ]

    operations = [
        migrations.RunPython(create_field, noop_reverse),
    ]
