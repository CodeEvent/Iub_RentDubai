# Bootstraps the paperless-ngx CustomField definitions and the Tag that
# RentShield notices are stored against. There is no separate rentshield
# app/database table (see documents/rentshield/) -- every notice is a
# real Document carrying these CustomField values, so paperless-ngx
# itself is the sole system of record.
#
# Idempotent (get_or_create by name) so it's safe to re-run against a
# database that already has these rows -- e.g. after a partial migrate,
# or if a field was manually deleted and needs restoring.
from django.db import migrations


def create_rentshield_fields(apps, schema_editor):
    CustomField = apps.get_model("documents", "CustomField")
    Tag = apps.get_model("documents", "Tag")

    # Mirrors documents.rentshield.custom_fields.CUSTOM_FIELD_DEFS -- kept
    # as a plain literal here (not imported) since migrations must not
    # depend on application code that can change independently of this
    # migration's own history.
    field_defs = {
        "RentShield: Landlord Name": ("string", None),
        "RentShield: Landlord Email": ("string", None),
        "RentShield: Tenant Name": ("string", None),
        "RentShield: Property Type": (
            "select",
            {
                "select_options": [
                    {"id": "Apartment", "label": "Apartment"},
                    {"id": "Villa", "label": "Villa"},
                    {"id": "Townhouse", "label": "Townhouse"},
                    {"id": "Office", "label": "Office"},
                    {"id": "Retail", "label": "Retail"},
                ],
            },
        ),
        "RentShield: Unit No.": ("string", None),
        "RentShield: Building / Community": ("string", None),
        "RentShield: Plot No.": ("string", None),
        "RentShield: Ejari No.": ("string", None),
        "RentShield: Notice Date": ("date", None),
        "RentShield: Reason": (
            "select",
            {
                "select_options": [
                    {"id": "sale", "label": "Sale of Property"},
                    {"id": "personal", "label": "Personal Use / Recovery"},
                    {"id": "demolition", "label": "Demolition"},
                    {"id": "renovation", "label": "Extensive Renovation"},
                    {"id": "nonpayment", "label": "Non-payment of Rent"},
                    {"id": "sublease", "label": "Unauthorized Subleasing"},
                ],
            },
        ),
        "RentShield: Notice Period (Days)": ("integer", None),
        "RentShield: Notarization Add-on": ("boolean", None),
        "RentShield: AI Review Add-on": ("boolean", None),
        "RentShield: Total Price (AED)": ("integer", None),
        "RentShield: E-Sign Provider": ("string", None),
        "RentShield: E-Sign External ID": ("string", None),
        "RentShield: E-Sign Signing URL": ("url", None),
        "RentShield: E-Sign Status": ("string", None),
        "RentShield: E-Sign Signed Document URL": ("url", None),
    }

    for name, (data_type, extra_data) in field_defs.items():
        CustomField.objects.get_or_create(
            name=name,
            defaults={"data_type": data_type, "extra_data": extra_data},
        )

    Tag.objects.get_or_create(
        name="RentShield Notice",
        defaults={"color": "#10b981"},
    )


def noop_reverse(apps, schema_editor):
    # Deliberately not deleting the fields/tag on reverse: any documents
    # created while this migration was applied would silently lose their
    # custom field values, and CustomField deletion is a real, visible
    # action better left to a human via the paperless-ngx UI/API.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0025_workflowaction_apply_ai_suggestions"),
    ]

    operations = [
        migrations.RunPython(create_rentshield_fields, noop_reverse),
    ]
