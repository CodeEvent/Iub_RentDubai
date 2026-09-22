# Extends the RentShield CustomField bootstrap (0026/0027/0028/0029)
# with the "Real Notary Public" paid add-on (documents/rentshield/
# pricing.py) -- fulfilled by a real human notary-services contact
# working a manual queue (see documents/rentshield/custom_fields.py's
# comment above AWAITING_NOTARY_PUBLIC_TAG_NAME for the full flow), not
# an API integration -- no UAE notary exposes one (documents/rentshield/
# notary_research/).
#
# Idempotent (get_or_create by name), same pattern as 0026/0027/0028/0029.
from django.db import migrations


def create_real_notarization_fields(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")
    Tag = apps.get_model("documents", "Tag")

    field_defs = {
        "RentShield: Real Notarization Add-on": ("boolean", None),
        "RentShield: Notary Public Status": ("string", None),
        "RentShield: Notary Reference No.": ("string", None),
        "RentShield: Notary Notes": ("longtext", None),
        "RentShield: Notarized Copy": ("documentlink", None),
    }
    for name, (data_type, extra_data) in field_defs.items():
        CustomField.objects.get_or_create(
            name=name,
            defaults={"data_type": data_type, "extra_data": extra_data},
        )

    Tag.objects.get_or_create(
        name="Awaiting Notary Public",
        defaults={"color": "#f59e0b"},
    )
    Tag.objects.get_or_create(
        name="Notary Public Completed",
        defaults={"color": "#059669"},
    )
    Tag.objects.get_or_create(
        name="Notary Public Rejected",
        defaults={"color": "#dc2626"},
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0029_rentshield_legal_review_addon"),
    ]

    operations = [
        migrations.RunPython(create_real_notarization_fields, noop_reverse),
    ]
