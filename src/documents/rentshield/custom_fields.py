# Every RentShield notice is a real paperless-ngx Document — there is no
# separate rentshield database table. Structured notice fields (landlord,
# tenant, reason, e-sign status, ...) live as paperless-ngx CustomField
# values on that Document, and every generated notice carries the
# RENTSHIELD_TAG_NAME tag so the Angular frontend can list them with
# paperless's own stock GET /api/documents/?tags__id__in=<tag_id> — no
# rentshield-specific list endpoint needed either.
#
# The CustomField definitions themselves are bootstrapped by the data
# migration documents/migrations/0026_rentshield_custom_fields.py, which
# imports CUSTOM_FIELD_DEFS from this module (single source of truth for
# the field list); this module is also imported at request time by
# documents/rentshield_views.py to map field name -> id.
from __future__ import annotations

from documents.models import CustomField

RENTSHIELD_TAG_NAME = "RentShield Notice"

PROPERTY_TYPE_OPTIONS = [
    {"id": "Apartment", "label": "Apartment"},
    {"id": "Villa", "label": "Villa"},
    {"id": "Townhouse", "label": "Townhouse"},
    {"id": "Office", "label": "Office"},
    {"id": "Retail", "label": "Retail"},
]

REASON_OPTIONS = [
    {"id": "sale", "label": "Sale of Property"},
    {"id": "personal", "label": "Personal Use / Recovery"},
    {"id": "demolition", "label": "Demolition"},
    {"id": "renovation", "label": "Extensive Renovation"},
    {"id": "nonpayment", "label": "Non-payment of Rent"},
    {"id": "sublease", "label": "Unauthorized Subleasing"},
]

# name -> (data_type, extra_data). Field names double as their display
# label in paperless-ngx's own document-detail UI, so they're prefixed
# for grouping there.
CUSTOM_FIELD_DEFS: dict[str, tuple[str, dict | None]] = {
    "RentShield: Landlord Name": (CustomField.FieldDataType.STRING, None),
    "RentShield: Landlord Email": (CustomField.FieldDataType.STRING, None),
    "RentShield: Tenant Name": (CustomField.FieldDataType.STRING, None),
    "RentShield: Property Type": (
        CustomField.FieldDataType.SELECT,
        {"select_options": PROPERTY_TYPE_OPTIONS},
    ),
    "RentShield: Unit No.": (CustomField.FieldDataType.STRING, None),
    "RentShield: Building / Community": (CustomField.FieldDataType.STRING, None),
    "RentShield: Plot No.": (CustomField.FieldDataType.STRING, None),
    "RentShield: Ejari No.": (CustomField.FieldDataType.STRING, None),
    "RentShield: Notice Date": (CustomField.FieldDataType.DATE, None),
    "RentShield: Reason": (
        CustomField.FieldDataType.SELECT,
        {"select_options": REASON_OPTIONS},
    ),
    "RentShield: Notice Period (Days)": (CustomField.FieldDataType.INT, None),
    "RentShield: Notarization Add-on": (CustomField.FieldDataType.BOOL, None),
    "RentShield: AI Review Add-on": (CustomField.FieldDataType.BOOL, None),
    "RentShield: Total Price (AED)": (CustomField.FieldDataType.INT, None),
    "RentShield: E-Sign Provider": (CustomField.FieldDataType.STRING, None),
    "RentShield: E-Sign External ID": (CustomField.FieldDataType.STRING, None),
    "RentShield: E-Sign Signing URL": (CustomField.FieldDataType.URL, None),
    "RentShield: E-Sign Status": (CustomField.FieldDataType.STRING, None),
    "RentShield: E-Sign Signed Document URL": (CustomField.FieldDataType.URL, None),
}

# Short keys used everywhere in Python/TypeScript code that isn't the
# CustomField admin UI -- maps 1:1 onto CUSTOM_FIELD_DEFS in the same
# order (kept as two dicts, not one, so the *stored* CustomField.name
# can be a friendly display label without every call site spelling it out).
FIELD_KEYS: dict[str, str] = {
    "landlord_name": "RentShield: Landlord Name",
    "landlord_email": "RentShield: Landlord Email",
    "tenant_name": "RentShield: Tenant Name",
    "property_type": "RentShield: Property Type",
    "unit_no": "RentShield: Unit No.",
    "building_name": "RentShield: Building / Community",
    "plot_number": "RentShield: Plot No.",
    "ejari_number": "RentShield: Ejari No.",
    "notice_date": "RentShield: Notice Date",
    "reason": "RentShield: Reason",
    "notice_period_days": "RentShield: Notice Period (Days)",
    "add_notarization": "RentShield: Notarization Add-on",
    "add_ai_review": "RentShield: AI Review Add-on",
    "total_price_aed": "RentShield: Total Price (AED)",
    "esign_provider": "RentShield: E-Sign Provider",
    "esign_external_id": "RentShield: E-Sign External ID",
    "esign_signing_url": "RentShield: E-Sign Signing URL",
    "esign_status": "RentShield: E-Sign Status",
    "esign_signed_document_url": "RentShield: E-Sign Signed Document URL",
}


def key_to_id_map() -> dict[str, int]:
    """short key (e.g. "landlord_name") -> live CustomField.id, read
    fresh from the DB on every call — these are looked up per-request in
    a handful of low-traffic notice endpoints, not a hot path, so there's
    no need for process-lifetime caching (and caching would go stale if
    a field were ever renamed/recreated without a full app restart)."""
    names = list(FIELD_KEYS.values())
    id_by_name = dict(CustomField.objects.filter(name__in=names).values_list("name", "id"))
    return {key: id_by_name[name] for key, name in FIELD_KEYS.items() if name in id_by_name}


def id_to_key_map() -> dict[int, str]:
    return {v: k for k, v in key_to_id_map().items()}
