/* Scans free text — typically OCR output from an uploaded tenancy
   contract addendum — for clauses that purport to shorten the statutory
   notice period below what Dubai Law No. (33) of 2008 actually allows,
   and for an Ejari certificate number.

   This is deliberately simple regex-based text analysis, not a language
   model: it looks for the literal pattern "<number> day(s) notice" and
   flags any that fall short of the statutory minimum. A clause worded
   differently (e.g. spelled-out numbers, a different phrase entirely)
   won't be caught — flagged findings are a real signal, but a clean
   scan is not proof the document has no problematic clauses. */

const NOTICE_DAYS_RE = /(\d{1,3})\s*[- ]?\s*day(?:s)?\s*(?:'|’)?\s*(?:written\s+)?notice/gi;
const EJARI_RE = /ejari[^0-9]{0,20}(\d{6,})/i;

// The 12-month statutory ground is the default assumption for a private
// contract clause trying to set its own notice period — Article 25(1)'s
// 30-day breach grounds (non-payment, unauthorized subleasing) are
// specific statutory carve-outs, not something a landlord can invoke by
// just writing "30 days" into an addendum.
const STATUTORY_MINIMUM_DAYS = 365;

export function analyzeTenancyText(rawText) {
  const text = rawText || '';
  const findings = [];
  const seen = new Set();
  let match;

  NOTICE_DAYS_RE.lastIndex = 0;
  while ((match = NOTICE_DAYS_RE.exec(text)) !== null) {
    const days = parseInt(match[1], 10);
    const clause = match[0].trim();
    if (Number.isNaN(days) || days >= STATUTORY_MINIMUM_DAYS || seen.has(clause.toLowerCase())) continue;
    seen.add(clause.toLowerCase());
    findings.push({
      clause,
      statedDays: days,
      statutoryMinimumDays: STATUTORY_MINIMUM_DAYS,
      message: `Found a clause stating "${clause}." Under Dubai Law No. (33) of 2008, a landlord cannot contractually shorten the mandatory notice period for eviction — the statutory minimum is ${STATUTORY_MINIMUM_DAYS} days (the 30-day period only applies to specific Article 25(1) breach grounds such as non-payment or unauthorized subleasing, not a general private agreement). This clause would be legally void and unenforceable at the RDSC.`
    });
  }

  const ejariMatch = text.match(EJARI_RE);

  return {
    ejariNumber: ejariMatch ? ejariMatch[1] : null,
    findings,
    hasViolation: findings.length > 0
  };
}
