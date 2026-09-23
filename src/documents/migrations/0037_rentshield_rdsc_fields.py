# RDSC filing-packet support -- served_date already exists and records
# *when* a notice was served; these fields record *how* and *with what
# evidence*, which today only the Real Notary Public path captures.
# Registered mail and court bailiff -- the other two Article 25(3)-valid
# service methods -- had no capture at all.
#
# Mirrors documents.rentshield.custom_fields.CUSTOM_FIELD_DEFS -- kept as
# a plain literal here (not imported), same reasoning as every migration
# since 0026: migrations must not depend on application code that can
# change independently of this migration's own history.
#
# Idempotent (get_or_create by name), same pattern as 0026-0032.
from django.db import migrations


def create_fields(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")

    CustomField.objects.get_or_create(
        name="RentShield: Service Method",
        defaults={
            "data_type": "select",
            "extra_data": {
                "select_options": [
                    {"id": "notary_public", "label": "Notary Public"},
                    {"id": "registered_mail", "label": "Registered mail with acknowledgment of receipt"},
                    {"id": "court_bailiff", "label": "Court bailiff (محضر)"},
                ],
            },
        },
    )
    CustomField.objects.get_or_create(
        name="RentShield: Ejari Certificate",
        defaults={"data_type": "documentlink", "extra_data": None},
    )
    CustomField.objects.get_or_create(
        name="RentShield: Tenancy Contract",
        defaults={"data_type": "documentlink", "extra_data": None},
    )
    CustomField.objects.get_or_create(
        name="RentShield: Service Evidence",
        defaults={"data_type": "documentlink", "extra_data": None},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0036_alter_rentshieldpermissionauditlog_actor"),
    ]

    operations = [
        migrations.RunPython(create_fields, noop_reverse),
    ]
