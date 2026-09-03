// Orchestrates the two e-signature engines behind one interface, so the
// "Notarization Service" add-on actually routes the generated notice
// through a real signing workflow instead of just charging for it.
//
// Combines DocuSeal and OpenSign as primary + fallback rather than
// picking one: if the primary self-hosted instance is unreachable or
// misconfigured, the request is retried against the other before it's
// reported as failed. Either can also be pinned outright via
// ESIGN_PRIMARY / ESIGN_FALLBACK.
import { renderNoticeHtml } from './renderNoticeHtml.js';
import { renderHtmlToPdf } from './renderPdf.js';
import * as docuseal from './docusealClient.js';
import * as opensign from './opensignClient.js';

const ESIGN_PRIMARY = process.env.ESIGN_PRIMARY || 'docuseal';
const ESIGN_FALLBACK = process.env.ESIGN_FALLBACK || 'opensign';

async function runProvider(provider, document, notice) {
  if (provider === 'docuseal') {
    const html = renderNoticeHtml(document, { includeSignatureField: true });
    return docuseal.createHtmlSubmission({
      name: `Notice of ${notice.reasonLabel} — ${notice.tenantName}`,
      html,
      submitterName: notice.landlordName,
      submitterEmail: notice.landlordEmail
    });
  }
  if (provider === 'opensign') {
    const html = renderNoticeHtml(document, { includeSignatureField: false });
    const pdfBuffer = await renderHtmlToPdf(html);
    return opensign.createDocumentSubmission({
      name: `Notice of ${notice.reasonLabel} — ${notice.tenantName}`,
      pdfBuffer,
      submitterName: notice.landlordName,
      submitterEmail: notice.landlordEmail
    });
  }
  throw new Error(`Unknown e-signature provider "${provider}"`);
}

// notice must include landlordEmail — the field the wizard doesn't
// currently collect; see the /notarize route for the 400 it returns
// when that's missing.
export async function requestSigning(document, notice) {
  try {
    return await runProvider(ESIGN_PRIMARY, document, notice);
  } catch (primaryErr) {
    if (!ESIGN_FALLBACK || ESIGN_FALLBACK === ESIGN_PRIMARY) {
      throw new Error(`${ESIGN_PRIMARY} failed and no distinct fallback is configured: ${primaryErr.message}`);
    }
    try {
      return await runProvider(ESIGN_FALLBACK, document, notice);
    } catch (fallbackErr) {
      throw new Error(
        `Both e-signature providers failed. ${ESIGN_PRIMARY}: ${primaryErr.message}. ${ESIGN_FALLBACK}: ${fallbackErr.message}`
      );
    }
  }
}

export async function checkSigningStatus(provider, externalId) {
  if (provider === 'docuseal') return docuseal.getSubmissionStatus(externalId);
  if (provider === 'opensign') return opensign.getDocumentStatus(externalId);
  throw new Error(`Unknown e-signature provider "${provider}"`);
}
