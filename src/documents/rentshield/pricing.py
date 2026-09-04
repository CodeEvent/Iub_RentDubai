# Ported 1:1 from legacy-v1/shared/pricing.js. Base self-serve generator
# fee plus optional add-ons — see that file's header comment for the
# jurist.ae-inspired-but-not-matched pricing rationale, preserved as-is.

BASE_PRICE_AED = 95

ADD_ONS = {
    "notarization": {
        "label": "Notarization Service",
        "description": "Route your notice through a licensed UAE notary for physical notarization before service.",
        "price_aed": 249,
    },
    "ai_review": {
        "label": "AI Compliance Review",
        "description": "Upload your tenancy contract addendum for automated clause analysis against Dubai Law No. (33) of 2008.",
        "price_aed": 99,
    },
}


def calculate_total(selected_add_ons: dict | None = None) -> int:
    selected_add_ons = selected_add_ons or {}
    total = BASE_PRICE_AED
    for key, addon in ADD_ONS.items():
        if selected_add_ons.get(key):
            total += addon["price_aed"]
    return total
