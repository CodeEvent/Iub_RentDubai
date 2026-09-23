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

import json

from documents.models import CustomField
from documents.rentshield.service_methods import SERVICE_METHODS

RENTSHIELD_TAG_NAME = "RentShield Notice"
TENANCY_CONTRACT_TAG_NAME = "Tenancy Contract"
AI_REVIEWED_TAG_NAME = "AI-Reviewed"
NEEDS_AI_REVIEW_TAG_NAME = "Needs AI Review"
DEMO_DATA_TAG_NAME = "Demo Data"

# Notarization review-gate pipeline stage tags (see
# manage.py create_rentshield_workflows and
# documents/rentshield/service.py's sync_notarization_stage_tag()): a
# notice moves Pending Review -> Being Notarized -> Notarized/
# Notarization Failed, never holding more than one of these at once.
PENDING_REVIEW_TAG_NAME = "Pending Review"
BEING_NOTARIZED_TAG_NAME = "Being Notarized"
NOTARIZED_TAG_NAME = "Notarized"
NOTARIZATION_FAILED_TAG_NAME = "Notarization Failed"

# Legal Review is a paid add-on (documents/rentshield/pricing.py),
# fulfilled operationally -- this tag plus an email an admin acts on
# manually -- not a login role or object-permission grant. See README's
# dated "Roles simplified" section: this replaced the old Lawyer role's
# one real use (reviewing sensitive-reason notices).
LEGAL_REVIEW_REQUESTED_TAG_NAME = "Legal Review Requested"

# Real Notary Public add-on (2026-09-09, documents/rentshield/pricing.py's
# real_notarization entry) -- fulfilled the same way Legal Review is:
# a tag plus an email a human acts on manually, not an API integration
# (no UAE notary exposes one -- see documents/rentshield/notary_research/)
# and not a login role (see README's "Roles simplified" section for why
# a dedicated role/object-permission-grant machinery was cut). The human
# here is a real notary-services contact who processes these exactly as
# she did before this existed -- reads the notice, does the actual
# physical notarization herself, then comes back and records the result
# using paperless-ngx's OWN document editor: uploads the scanned/stamped
# copy as a normal Document, links it via the "Notarized Copy" field
# below, fills in the reference number, and swaps this tag for
# NOTARY_PUBLIC_COMPLETED_TAG_NAME/NOTARY_PUBLIC_REJECTED_TAG_NAME
# herself -- no bespoke completion UI or endpoint, same reasoning
# roles.py gives for keeping this off the object-permission-grant path
# that already caused this project's worst bugs once.
#
# Business logic (2026-09-11): a notary-public visit is itself one of
# the three legally recognized ways to serve a Dubai tenancy notice on
# a tenant under Article 25(3) (documents/rentshield/service_methods.py)
# -- so her marking "Notary Public Status" completed isn't just "the
# document got stamped," it's the actual legal service event. documents/
# rentshield/signals.py watches for that exact transition (still through
# the same plain document editor, no new UI) and: stamps "RentShield:
# Served Date" automatically, and emails the landlord that their notice
# has been served (or, on rejection, that it wasn't, with her notes) --
# closing the loop that used to end in silence. See service.py's
# _notify_notice_served().
AWAITING_NOTARY_PUBLIC_TAG_NAME = "Awaiting Notary Public"
NOTARY_PUBLIC_COMPLETED_TAG_NAME = "Notary Public Completed"
NOTARY_PUBLIC_REJECTED_TAG_NAME = "Notary Public Rejected"

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
    "RentShield: Legal Review Add-on": (CustomField.FieldDataType.BOOL, None),
    "RentShield: Total Price (AED)": (CustomField.FieldDataType.INT, None),
    "RentShield: E-Sign Provider": (CustomField.FieldDataType.STRING, None),
    "RentShield: E-Sign External ID": (CustomField.FieldDataType.STRING, None),
    "RentShield: E-Sign Signing URL": (CustomField.FieldDataType.URL, None),
    "RentShield: E-Sign Status": (CustomField.FieldDataType.STRING, None),
    "RentShield: E-Sign Signed Document URL": (CustomField.FieldDataType.URL, None),
    "RentShield: AI Review Summary": (CustomField.FieldDataType.LONG_TEXT, None),
    "RentShield: AI Review Findings Count": (CustomField.FieldDataType.INT, None),
    "RentShield: Details Confirmed": (CustomField.FieldDataType.BOOL, None),
    "RentShield: Real Notarization Add-on": (CustomField.FieldDataType.BOOL, None),
    "RentShield: Notary Public Status": (CustomField.FieldDataType.STRING, None),
    "RentShield: Notary Reference No.": (CustomField.FieldDataType.STRING, None),
    "RentShield: Notary Notes": (CustomField.FieldDataType.LONG_TEXT, None),
    "RentShield: Notarized Copy": (CustomField.FieldDataType.DOCUMENTLINK, None),
    "RentShield: Served Date": (CustomField.FieldDataType.DATE, None),
    "RentShield: Reason Requirements Acknowledged": (CustomField.FieldDataType.BOOL, None),
    # RDSC filing-packet support (2026-09-23) -- served_date above already
    # covers *when*; these cover *how* and *with what evidence*, which
    # today only the Real Notary Public path captures (via its own
    # notary_status signal). Registered mail and court bailiff -- the
    # other two Article 25(3)-valid methods -- had no capture at all.
    "RentShield: Service Method": (
        CustomField.FieldDataType.SELECT,
        {
            "select_options": [
                {"id": key, "label": meta["label"]}
                for key, meta in SERVICE_METHODS.items()
                if meta["valid"]
            ],
        },
    ),
    "RentShield: Ejari Certificate": (CustomField.FieldDataType.DOCUMENTLINK, None),
    "RentShield: Tenancy Contract": (CustomField.FieldDataType.DOCUMENTLINK, None),
    "RentShield: Service Evidence": (CustomField.FieldDataType.DOCUMENTLINK, None),
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
    "add_legal_review": "RentShield: Legal Review Add-on",
    "total_price_aed": "RentShield: Total Price (AED)",
    "esign_provider": "RentShield: E-Sign Provider",
    "esign_external_id": "RentShield: E-Sign External ID",
    "esign_signing_url": "RentShield: E-Sign Signing URL",
    "esign_status": "RentShield: E-Sign Status",
    "esign_signed_document_url": "RentShield: E-Sign Signed Document URL",
    "ai_review_summary": "RentShield: AI Review Summary",
    "ai_review_findings_count": "RentShield: AI Review Findings Count",
    "details_confirmed": "RentShield: Details Confirmed",
    "add_real_notarization": "RentShield: Real Notarization Add-on",
    "notary_status": "RentShield: Notary Public Status",
    "notary_reference_no": "RentShield: Notary Reference No.",
    "notary_notes": "RentShield: Notary Notes",
    "notarized_copy_document": "RentShield: Notarized Copy",
    "served_date": "RentShield: Served Date",
    "reason_requirements_acknowledged": "RentShield: Reason Requirements Acknowledged",
    "service_method": "RentShield: Service Method",
    "ejari_certificate_document": "RentShield: Ejari Certificate",
    "tenancy_contract_document": "RentShield: Tenancy Contract",
    "service_evidence_document": "RentShield: Service Evidence",
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


def notarization_pending_query(notarization_field_id: int, esign_status_field_id: int) -> str:
    """paperless-ngx CustomField filter query string for "the Certified
    E-Signature add-on was selected but dispatch hasn't produced a
    status yet" -- shared by manage.py create_rentshield_workflows (a
    Workflow trigger) and create_rentshield_dashboards (a Saved View
    filter), which both need the exact same query; previously defined
    twice, verbatim, in each command.

    `exists: False`, not `isnull: True`: the correct op for "this
    CustomField was never set on this document" is `exists: False` --
    `isnull` only matches a CustomFieldInstance row whose value column
    is SQL NULL, which request_notarization()/_set_custom_field_value()
    never produces (they only ever write a real string). A doc that
    never had notarization requested has no esign_status instance row
    at all, so `isnull` silently matched nothing -- confirmed via a
    real un-notarized demo notice returning 0 instead of 1 from this
    exact query. old_buggy_notarization_pending_query() below is kept
    only so both commands' one-time repair helpers can detect and fix
    any already-shipped Workflow/SavedView still carrying that old,
    always-empty value.
    """
    return json.dumps(
        [
            "AND",
            [
                [notarization_field_id, "exact", True],
                ["OR", [[esign_status_field_id, "exists", False], [esign_status_field_id, "exact", ""]]],
            ],
        ],
    )


def old_buggy_notarization_pending_query(notarization_field_id: int, esign_status_field_id: int) -> str:
    return json.dumps(
        [
            "AND",
            [
                [notarization_field_id, "exact", True],
                ["OR", [[esign_status_field_id, "isnull", True], [esign_status_field_id, "exact", ""]]],
            ],
        ],
    )
