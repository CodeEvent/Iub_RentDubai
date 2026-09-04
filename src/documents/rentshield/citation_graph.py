# A small, native citation graph over an uploaded tenancy document —
# inspired by github.com/Open-Source-Legal/OpenContracts' core idea
# (treat a document's clauses and the legal provisions they cite as a
# traversable graph of nodes/edges, not just isolated regex matches),
# scaled down to run as plain Python instead of OpenContracts' own
# Django + GraphQL + Celery + Docling service. Ported 1:1 from
# legacy-v1/shared/citationGraph.js.
#
# Still fundamentally regex/keyword heuristics: a real signal when it
# fires, not proof of a clean document when it doesn't. Every legal
# citation used here (Article 25(1)/(2)/(3)) is one already established
# and cross-checked elsewhere in this codebase (constants.py, the
# notice-service-method-uae skill) — nothing new is asserted about UAE
# law here that isn't already backed there.
from __future__ import annotations

import re

from documents.rentshield.service_methods import SERVICE_METHODS

NOTICE_DAYS_RE = re.compile(r"(\d{1,3})\s*[- ]?\s*day(?:s)?\s*(?:'|’)?\s*(?:written\s+)?notice", re.IGNORECASE)
EJARI_RE = re.compile(r"ejari[^0-9]{0,20}(\d{6,})", re.IGNORECASE)
STATUTORY_MINIMUM_DAYS = 365


def build_citation_graph(raw_text: str | None) -> dict:
    text = raw_text or ""
    nodes = [{"id": "doc", "type": "document", "label": "Uploaded tenancy document"}]
    edges = []
    node_ids = {"doc"}
    seq = 0

    def ensure_statute_node(node_id: str, label: str) -> None:
        if node_id in node_ids:
            return
        node_ids.add(node_id)
        nodes.append({"id": node_id, "type": "statute", "label": label})

    # --- Notice-period clauses -> Article 25(2) (or a violation of it) ---
    seen_clauses = set()
    for match in NOTICE_DAYS_RE.finditer(text):
        try:
            days = int(match.group(1))
        except ValueError:
            continue
        clause_text = match.group(0).strip()
        key = clause_text.lower()
        if key in seen_clauses:
            continue
        seen_clauses.add(key)

        clause_id = f"clause-notice-{seq}"
        seq += 1
        nodes.append({"id": clause_id, "type": "clause", "label": clause_text, "category": "notice-period"})
        edges.append({"from": "doc", "to": clause_id, "relation": "contains"})

        ensure_statute_node("statute-art25-2", "Law No. (33) of 2008, Article 25(2) — 365-day statutory notice")
        compliant = days >= STATUTORY_MINIMUM_DAYS
        edges.append({
            "from": clause_id,
            "to": "statute-art25-2",
            "relation": "satisfies" if compliant else "violates",
            "note": (
                f"{days}-day period meets or exceeds the {STATUTORY_MINIMUM_DAYS}-day statutory minimum."
                if compliant
                else (
                    f"{days}-day period falls short of the {STATUTORY_MINIMUM_DAYS}-day statutory minimum. "
                    "Only Article 25(1)'s specific breach grounds (non-payment, unauthorized subleasing) "
                    "permit a 30-day period — a private clause cannot invoke that on its own, and would be "
                    "void and unenforceable at the RDSC."
                )
            ),
        })

    # --- Service-method mentions -> Article 25(3) ---
    for key, method in SERVICE_METHODS.items():
        found = method["pattern"].search(text)
        if not found:
            continue

        clause_id = f"clause-service-{key}"
        nodes.append({"id": clause_id, "type": "clause", "label": found.group(0), "category": "service-method"})
        edges.append({"from": "doc", "to": clause_id, "relation": "contains"})

        ensure_statute_node("statute-art25-3", "Law No. (33) of 2008, Article 25(3) — valid notice service methods")
        edges.append({
            "from": clause_id,
            "to": "statute-art25-3",
            "relation": "satisfies" if method["valid"] else "violates",
            "note": (
                f'{method["label"]} is one of the three methods Article 25(3) recognizes.'
                if method["valid"]
                else (
                    f'{method["label"]} is not one of the three methods Article 25(3) recognizes '
                    "(Notary Public, registered mail, or court bailiff) — a notice served this way is "
                    "likely to be challenged as invalid."
                )
            ),
        })

    # --- Ejari identifier ---
    ejari_match = EJARI_RE.search(text)
    if ejari_match:
        nodes.append({"id": "ejari", "type": "identifier", "label": f"Ejari No. {ejari_match.group(1)}"})
        edges.append({"from": "doc", "to": "ejari", "relation": "has"})

    violations = [e for e in edges if e["relation"] == "violates"]

    return {
        "nodes": nodes,
        "edges": edges,
        "ejari_number": ejari_match.group(1) if ejari_match else None,
        "has_violation": len(violations) > 0,
        "violation_count": len(violations),
    }
