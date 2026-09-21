# Target list for the notary-provider research scan (see
# documents/rentshield/notary_research/scanner.py). Every URL here was
# confirmed to exist via a real, live web search on 2026-09-09 (not
# guessed from memory) while researching Phase 0 of the notarization-
# automation plan in this project's README -- the question being
# "does any UAE notary service expose a third-party/developer API?".
#
# What that research already found, worth keeping in mind when reading
# scan results:
# - Dubai Courts' own "Smart Electronic Notary" (dc.gov.ae) and the UAE
#   Ministry of Justice's E-Notary system (moj.gov.ae) both require the
#   party themselves to log in with UAE Pass/Emirates ID and complete a
#   video-call verification -- there is no public sign either exposes a
#   third-party API a SaaS could call on a landlord's behalf. These two
#   are included so the scan can catch it if that ever changes, not
#   because an API is expected to appear here.
# - The private notary services below are consumer-facing "notarize
#   your own document online" businesses, not confirmed API providers --
#   same reasoning, included to catch a future partner-program
#   announcement, not because one is known to exist today.
# - A general web search for "UAE notary API for developers" surfaced
#   only non-UAE remote-online-notarization platforms (e.g. OneNotary,
#   US-based), which aren't valid under UAE Federal Decree-Law No.
#   20/2022 -- not included here since they're confirmed not to be a
#   real option, not omitted by oversight.
# - (2026-09-09) Emirates Post's Registered Email/Registered Digital
#   Communication service is a real, TRA-accredited service producing
#   legally admissible delivery certificates -- Article 25(3)'s
#   "registered mail with acknowledgment of receipt" channel,
#   independent of the Notary Public channel the rest of this list
#   targets. Emirates Post has a real, live developer API program
#   ("EMX API", developers.emx.ae, api@emx.ae) -- confirmed via a
#   public Postman collection (CreateBooking/Tracking/Cancel/Create
#   Shipment endpoints, sandbox host tracking-stg.epservices.ae) AND
#   the developers.emx.ae/local.html and /faqs.html pages themselves.
#   CONFIRMED NOW (previously "unconfirmed"): that API surface is
#   courier/parcel shipment ONLY -- CreateBooking, Tracking, Cancel,
#   label printing. Neither the Postman collection nor the docs expose
#   any registered-email/registered-mail/legal-notice-delivery
#   endpoint. This is still the most promising lead found so far for
#   an Article-25(3)-valid delivery channel (more promising than any
#   notary integration, since e-signature isn't a 25(3)-recognized
#   method at all) -- but it is now confirmed NOT self-serve via API,
#   so the only real next step is direct manual outreach to api@emx.ae
#   asking specifically whether the registered-email product can be
#   added to their API program, not waiting on this scan or their
#   public docs to change.
from __future__ import annotations

TARGETS: list[dict[str, str]] = [
    {
        "name": "Dubai Courts - Smart Electronic Notary",
        "url": "https://www.dc.gov.ae/PublicServices/CMSPage.aspx?PageName=SmartElectronicNotary&lang=en",
        "note": "Official Dubai Courts e-notary service. Consumer/UAE-Pass portal as of last check.",
    },
    {
        "name": "UAE Ministry of Justice - E-Notary System",
        "url": "https://www.moj.gov.ae/en/services/esystems/e-notary.aspx",
        "note": "Federal e-notary system covering emirates outside Dubai's own court system.",
    },
    {
        "name": "Private Notary Dubai",
        "url": "https://privatenotarydubai.ae/notary-public-dubai-online/",
        "note": "Private licensed notary intermediary, online notarization marketed as 24/7.",
    },
    {
        "name": "Private Notary Dubai - E-Notary",
        "url": "https://privatenotarydubai.ae/e-notary-dubai/",
        "note": "Same provider as above, separate service page.",
    },
    {
        "name": "POA.ae - Online Notarization",
        "url": "https://www.poa.ae/poa-online-notarization/",
        "note": "Power-of-attorney-focused private notary/legal service.",
    },
    {
        "name": "Notary Services Dubai",
        "url": "https://notaryservicesdubai.com/",
        "note": "Advertises licensed Dubai Courts services + private online notarization.",
    },
    {
        "name": "Helpline Group UAE - Online Notary",
        "url": "https://helplinegroupuae.com/online-notary-service/",
        "note": "Private legal/PRO services company offering online notarization.",
    },
    {
        "name": "Superior Dubai - Online Notary",
        "url": "https://superiordubai.com/online-notary-service-in-dubai/",
        "note": "Private online notary service listing.",
    },
    {
        "name": "E-Notary Dubai",
        "url": "https://www.enotarydubai.ae/",
        "note": (
            "Checked directly on 2026-09-09 (user-supplied URL, fetched live, not "
            "guessed): a private notary-SUPPORT service, not a licensed notary "
            "itself -- its own site says it drafts the document and books the "
            "appointment, with actual notarization still happening via Dubai "
            "Courts/Ministry of Justice licensed notaries over video call. No "
            "API/developer/partner-program mention found. Notably, unlike the "
            "other private sites here, it explicitly advertises 'licensed "
            "notification service delivery' for eviction and legal notices -- "
            "closer to RentShield's actual use case than a generic notary "
            "listing, and worth prioritizing for direct outreach (manual "
            "partnership, not a self-serve API) even without an API today."
        ),
    },
    {
        "name": "Emirates Post - Registered Email",
        "url": "https://www.emiratespost.ae/all-services/registered-email",
        "note": (
            "Checked 2026-09-09: the Article 25(3) 'registered mail with "
            "acknowledgment of receipt' channel, not a notary. Real, TRA-"
            "accredited, produces legally admissible delivery certificates -- "
            "the most promising lead so far, since it's a genuinely 25(3)-"
            "recognized method (unlike certified e-signature). Emirates Post "
            "has a real, live developer API program (EMX API, "
            "developers.emx.ae, api@emx.ae, sandbox at "
            "tracking-stg.epservices.ae / local-stg.epservices.ae) -- "
            "CONFIRMED (2026-09-09, via a public Postman collection plus "
            "developers.emx.ae/local.html and /faqs.html) to cover ONLY "
            "courier/parcel shipment (CreateBooking, Tracking, Cancel, "
            "label printing). No registered-email/legal-notice endpoint "
            "exists in that API today. Direct manual outreach to api@emx.ae "
            "asking them to extend API access to the registered-email "
            "product is the real next step, not waiting on this scan."
        ),
    },
]

# Case-insensitive substrings that suggest a page is now talking about
# programmatic/partner access rather than just a consumer-facing web
# form -- deliberately broad (better a false positive worth a human
# glance than a missed real signal).
API_SIGNAL_KEYWORDS: list[str] = [
    "api",
    "developer",
    "integration",
    "sdk",
    "webhook",
    "partner program",
    "partner api",
    "rest api",
    "third-party integration",
]
