# Ported 1:1 from legacy-v1/shared/pricing.js. Base self-serve generator
# fee plus optional add-ons — see that file's header comment for the
# jurist.ae-inspired-but-not-matched pricing rationale, preserved as-is.
#
# Low-friction-entry pricing (2026-09-04): AED 29 to generate removes
# the "is this worth trying" hesitation; the real margin sits on the
# add-ons. Correction (2026-09-12): Certified E-Signature at AED 299 is
# NOT the step that matters legally for service under Article 25(3) --
# see documents/rentshield/service_methods.py's valid methods
# (notary_public/registered_mail/court_bailiff) and its description
# below. Real Notary Public at AED 599 is the one add-on that actually
# is.

BASE_PRICE_AED = 29

# Resolved (2026-09-09) -- the labeling question this TODO used to raise
# has a decision now, made by a human, not silently by this code: what
# used to be sold as a single "Notarization Service" is split into two
# honest tiers. documents/rentshield/service.py's request_notarization()
# -> documents/rentshield/esign/orchestrator.py (DocuSeal/OpenSign) is
# NOT a licensed UAE Notary Public integration -- it's a certified
# e-signature and delivery workflow, and is now labeled as exactly that.
#
# Real Notary Public (2026-09-09) -- now purchasable, but honestly:
# there is still no UAE notary API to integrate with (confirmed via live
# research; see documents/rentshield/notary_research/), so this is
# fulfilled by a real person, not code. Selecting it queues the notice
# for a real notary-services contact who processes it the same way she
# always has -- reads the notice, does the actual physical notarization
# herself, then records the result back onto the notice. See
# documents/rentshield/custom_fields.py's comment above
# AWAITING_NOTARY_PUBLIC_TAG_NAME for the full flow. This is genuinely
# real notarization, just human-fulfilled rather than instant/API-driven
# -- the description below says exactly that, not "coming soon".
# The underlying Django CustomField/tag names (add_notarization,
# "Being Notarized", etc.) deliberately keep their existing internal
# names -- nobody-facing, no relabeling needed there; only what a
# customer actually reads and pays against changed here.
ADD_ONS = {
    "certified_esignature": {
        "label": "Certified E-Signature Service",
        "description": "Route your notice through a certified e-signature workflow (DocuSeal/OpenSign) to certify the landlord's signature. This does NOT constitute legal service on the tenant under Article 25(3) of Law No. (33) of 2008 -- only a Notary Public, registered mail, or a court bailiff does. Add Real Notary Public below, or arrange registered mail/court bailiff service yourself, for the notice to actually be served.",
        "price_aed": 299,
    },
    "ai_review": {
        "label": "AI Compliance Review",
        "description": "Upload your tenancy contract addendum for automated clause analysis against Dubai Law No. (33) of 2008.",
        "price_aed": 99,
    },
    "legal_review": {
        "label": "Legal Review",
        "description": "Flag this notice for a lawyer to review before you serve it, especially for sensitive-reason notices (personal use, demolition, renovation).",
        "price_aed": 349,
    },
    "real_notarization": {
        "label": "Real Notary Public",
        "description": "Route your notice to a real UAE notary-services contact for actual physical notarization -- not just a certified e-signature workflow. This is fulfilled by a person, not an instant API (none exists yet), so it takes longer than the other add-ons: you'll be notified once it's been completed and the notarized copy is attached to your notice.",
        "price_aed": 599,
        "available": True,
    },
}


def calculate_total(selected_add_ons: dict | None = None) -> int:
    selected_add_ons = selected_add_ons or {}
    total = BASE_PRICE_AED
    for key, addon in ADD_ONS.items():
        if selected_add_ons.get(key):
            total += addon["price_aed"]
    return total
