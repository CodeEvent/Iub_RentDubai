// Client for a self-hosted DocuSeal instance (https://github.com/docusealco/docuseal).
// Endpoint shapes below are taken directly from DocuSeal's own committed
// API docs (docs/api/nodejs.md, docs/openapi.json in that repo) — not
// guessed. Self-hosted DocuSeal mounts its public API under the same
// `/api` namespace api.docuseal.com uses, so DOCUSEAL_URL should point at
// the app root (e.g. http://docuseal:3000), not a subdomain.
const DOCUSEAL_URL = process.env.DOCUSEAL_URL || 'http://localhost:3000';
const DOCUSEAL_API_TOKEN = process.env.DOCUSEAL_API_TOKEN || '';

async function docusealFetch(path, options = {}) {
  const res = await fetch(`${DOCUSEAL_URL}/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Auth-Token': DOCUSEAL_API_TOKEN,
      ...options.headers
    }
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.error || `DocuSeal API returned ${res.status}`);
  }
  return body;
}

// Creates a one-off signing request straight from HTML — no template
// pre-creation step needed, which fits a platform that already renders
// the notice as HTML for the browser preview.
export async function createHtmlSubmission({ name, html, submitterName, submitterEmail }) {
  const submitters = await docusealFetch('/submissions/html', {
    method: 'POST',
    body: JSON.stringify({
      name,
      send_email: true,
      documents: [{ name, html }],
      submitters: [{ role: 'Landlord', name: submitterName, email: submitterEmail }]
    })
  });

  const submitter = Array.isArray(submitters) ? submitters[0] : submitters?.submitters?.[0];
  if (!submitter) throw new Error('DocuSeal did not return a submitter for the created submission');

  return {
    provider: 'docuseal',
    externalId: String(submitter.submission_id ?? submitter.id),
    signingUrl: submitter.embed_src || submitter.url || null,
    status: 'pending'
  };
}

export async function getSubmissionStatus(externalId) {
  const submission = await docusealFetch(`/submissions/${externalId}`);
  const completed = !!submission.completed_at;
  const documentsRes = completed
    ? await docusealFetch(`/submissions/${externalId}/documents`)
    : null;

  return {
    status: submission.archived_at ? 'archived' : completed ? 'completed' : 'pending',
    signedDocumentUrl: documentsRes?.documents?.[0]?.url || null
  };
}
