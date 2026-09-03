// Renders a buildNotice() document object into a standalone, print-ready
// bilingual HTML page — used both as the DocuSeal "submission from HTML"
// payload and as the source document for the Playwright-rendered PDF
// handed to OpenSign. Kept deliberately separate from Vue's
// DocumentPreview.vue, which renders the same data as live Vue markup
// for on-screen editing, not as a string to hand to a third-party service.
function escapeHtml(str) {
  return String(str ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));
}

function renderSide(side, { includeSignatureField }) {
  const paragraphs = side.paragraphs.map((p) => `<p>${escapeHtml(p)}</p>`).join('\n');
  const signatureBlock = includeSignatureField
    ? `<p style="margin-top:2em;">${escapeHtml(side.landlordName)}<br>
        <text-field name="Landlord Signature" role="Landlord" required="true"
          style="width:220px;height:60px;display:inline-block;border-bottom:1px solid #333;margin-top:8px;"></text-field>
       </p>`
    : `<p style="margin-top:2em;">${escapeHtml(side.landlordName)} — ${escapeHtml(side.signDate)}</p>`;

  return `
    <header>
      <p class="kicker">${escapeHtml(side.kicker)}</p>
      <h1>${escapeHtml(side.title)}</h1>
      <p class="subtitle">${escapeHtml(side.subtitle)}</p>
    </header>
    <table class="meta">
      <tr><td>${escapeHtml(side.dateLabel)}</td><td>${escapeHtml(side.dateValue)}</td></tr>
      <tr><td>${escapeHtml(side.deadlineLabel)}</td><td>${escapeHtml(side.deadlineValue)}</td></tr>
    </table>
    <p><strong>${escapeHtml(side.to)}</strong></p>
    <p>${escapeHtml(side.ejariLine)}<br>${escapeHtml(side.propertyLine)}</p>
    ${paragraphs}
    <p><strong>${escapeHtml(side.reasonLabel)}</strong><br>${escapeHtml(side.reasonText)}</p>
    <p>${escapeHtml(side.closing)}</p>
    <p class="footer">${escapeHtml(side.footer)}</p>
    ${signatureBlock}
  `;
}

// includeSignatureField=true embeds DocuSeal's <text-field> tag syntax
// (see docs/api HTML submission docs) so the landlord's signature block
// becomes an actual fillable/signable field, not just static text.
export function renderNoticeHtml(document, { includeSignatureField = false } = {}) {
  return `<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { font-family: 'Times New Roman', serif; color: #1a1a1a; line-height: 1.6; padding: 40px; }
  .kicker { text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; color: #666; }
  h1 { font-size: 22px; margin: 4px 0; }
  .subtitle { font-size: 12px; color: #444; }
  .meta { margin: 16px 0; font-size: 13px; }
  .meta td { padding: 2px 12px 2px 0; }
  .footer { font-size: 11px; color: #666; margin-top: 24px; }
  .divider { border: none; border-top: 2px solid #333; margin: 32px 0; }
  [dir="rtl"] { text-align: right; font-family: 'Traditional Arabic', 'Arial', sans-serif; }
</style>
</head>
<body>
  <section dir="ltr">${renderSide(document.en, { includeSignatureField })}</section>
  <hr class="divider">
  <section dir="rtl">${renderSide(document.ar, { includeSignatureField: false })}</section>
</body>
</html>`;
}
