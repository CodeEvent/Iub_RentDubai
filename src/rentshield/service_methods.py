# Recognized methods of serving a Dubai tenancy notice under Article
# 25(3) of Law No. (33) of 2008 — the single source of truth shared by
# citation_graph.py and the legal-skills check_service_method endpoint,
# so both agree on the same list instead of drifting. Ported 1:1 from
# legacy-v1/shared/serviceMethods.js.
import re

SERVICE_METHODS = {
    "notary_public": {
        "valid": True,
        "label": "Notary Public",
        "pattern": re.compile(r"notary\s+public|k[aā]tib\s+al-?adl|كاتب\s+العدل", re.IGNORECASE),
    },
    "registered_mail": {
        "valid": True,
        "label": "Registered mail with acknowledgment of receipt",
        "pattern": re.compile(r"registered\s+mail|recorded\s+delivery", re.IGNORECASE),
    },
    "court_bailiff": {
        "valid": True,
        "label": "Court bailiff (محضر)",
        "pattern": re.compile(r"court\s+bailiff|محضر", re.IGNORECASE),
    },
    "whatsapp": {
        "valid": False,
        "label": "WhatsApp / SMS",
        "pattern": re.compile(r"whatsapp|\bsms\b|text\s+message", re.IGNORECASE),
    },
    "email": {
        "valid": False,
        "label": "Plain (non-registered) email",
        "pattern": re.compile(r"\be-?mail\b", re.IGNORECASE),
    },
    "verbal": {
        "valid": False,
        "label": "Verbal notice",
        "pattern": re.compile(r"verbal(ly)?\s+notic|orally\s+inform", re.IGNORECASE),
    },
    "hand_delivery_unwitnessed": {
        "valid": False,
        "label": "Hand delivery without notarization or a witnessed receipt",
        "pattern": re.compile(r"hand[\s-]?deliver(ed|y)", re.IGNORECASE),
    },
}
