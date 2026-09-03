/* A small, native citation graph over an uploaded tenancy document —
   inspired by github.com/Open-Source-Legal/OpenContracts' core idea
   (treat a document's clauses and the legal provisions they cite as a
   traversable graph of nodes/edges, not just isolated regex matches),
   scaled down to run as plain JS in this Node/Vue stack instead of
   OpenContracts' own Django + GraphQL + Celery + Docling service, which
   this project doesn't run.

   It is still fundamentally regex/keyword heuristics, same honesty
   caveat as complianceCheck.js: a real signal when it fires, not proof
   of a clean document when it doesn't. Every legal citation used here
   (Article 25(1)/(2)/(3)) is one already established and cross-checked
   elsewhere in this codebase (reasons.js, the notice-service-method-uae
   skill) — nothing new is asserted about UAE law here that isn't
   already backed there. */
import { SERVICE_METHODS } from './serviceMethods.js';

const NOTICE_DAYS_RE = /(\d{1,3})\s*[- ]?\s*day(?:s)?\s*(?:'|’)?\s*(?:written\s+)?notice/gi;
const EJARI_RE = /ejari[^0-9]{0,20}(\d{6,})/i;
const STATUTORY_MINIMUM_DAYS = 365;

export function buildCitationGraph(rawText) {
  const text = rawText || '';
  const nodes = [{ id: 'doc', type: 'document', label: 'Uploaded tenancy document' }];
  const edges = [];
  const nodeIds = new Set(['doc']);
  let seq = 0;

  function ensureStatuteNode(id, label) {
    if (nodeIds.has(id)) return;
    nodeIds.add(id);
    nodes.push({ id, type: 'statute', label });
  }

  // --- Notice-period clauses -> Article 25(2) (or a violation of it) ---
  const seenClauses = new Set();
  const noticeRe = new RegExp(NOTICE_DAYS_RE.source, NOTICE_DAYS_RE.flags);
  let match;
  while ((match = noticeRe.exec(text)) !== null) {
    const days = parseInt(match[1], 10);
    const clauseText = match[0].trim();
    const key = clauseText.toLowerCase();
    if (Number.isNaN(days) || seenClauses.has(key)) continue;
    seenClauses.add(key);

    const clauseId = `clause-notice-${seq++}`;
    nodes.push({ id: clauseId, type: 'clause', label: clauseText, category: 'notice-period' });
    edges.push({ from: 'doc', to: clauseId, relation: 'contains' });

    ensureStatuteNode('statute-art25-2', 'Law No. (33) of 2008, Article 25(2) — 365-day statutory notice');
    const compliant = days >= STATUTORY_MINIMUM_DAYS;
    edges.push({
      from: clauseId,
      to: 'statute-art25-2',
      relation: compliant ? 'satisfies' : 'violates',
      note: compliant
        ? `${days}-day period meets or exceeds the ${STATUTORY_MINIMUM_DAYS}-day statutory minimum.`
        : `${days}-day period falls short of the ${STATUTORY_MINIMUM_DAYS}-day statutory minimum. Only Article 25(1)'s specific breach grounds (non-payment, unauthorized subleasing) permit a 30-day period — a private clause cannot invoke that on its own, and would be void and unenforceable at the RDSC.`
    });
  }

  // --- Service-method mentions -> Article 25(3) ---
  for (const [key, method] of Object.entries(SERVICE_METHODS)) {
    const found = method.pattern.exec(text);
    if (!found) continue;

    const clauseId = `clause-service-${key}`;
    nodes.push({ id: clauseId, type: 'clause', label: found[0], category: 'service-method' });
    edges.push({ from: 'doc', to: clauseId, relation: 'contains' });

    ensureStatuteNode('statute-art25-3', 'Law No. (33) of 2008, Article 25(3) — valid notice service methods');
    edges.push({
      from: clauseId,
      to: 'statute-art25-3',
      relation: method.valid ? 'satisfies' : 'violates',
      note: method.valid
        ? `${method.label} is one of the three methods Article 25(3) recognizes.`
        : `${method.label} is not one of the three methods Article 25(3) recognizes (Notary Public, registered mail, or court bailiff) — a notice served this way is likely to be challenged as invalid.`
    });
  }

  // --- Ejari identifier ---
  const ejariMatch = text.match(EJARI_RE);
  if (ejariMatch) {
    nodes.push({ id: 'ejari', type: 'identifier', label: `Ejari No. ${ejariMatch[1]}` });
    edges.push({ from: 'doc', to: 'ejari', relation: 'has' });
  }

  const violations = edges.filter((e) => e.relation === 'violates');

  return {
    nodes,
    edges,
    ejariNumber: ejariMatch ? ejariMatch[1] : null,
    hasViolation: violations.length > 0,
    violationCount: violations.length
  };
}
