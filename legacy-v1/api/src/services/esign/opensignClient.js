// Client for a self-hosted OpenSign instance (https://github.com/opensignlabs/OpenSign).
// OpenSign's backend is a Parse Server app (Node/MongoDB) mounted at
// `/app` by default (apps/OpenSignServer/index.js: `PARSE_MOUNT || '/app'`),
// exposing the standard Parse REST API plus OpenSign's own Cloud
// Functions. Shapes below (contracts_Document fields, the
// `createdocumentfromapp` Cloud Function, and the `contracts_Contactbook`
// pointer class) were read directly out of that repo's
// `cloud/parsefunction/*.js`, not guessed from marketing docs.
const OPENSIGN_URL = process.env.OPENSIGN_URL || 'http://localhost:8080';
const OPENSIGN_APP_ID = process.env.OPENSIGN_APP_ID || '';
const OPENSIGN_MASTER_KEY = process.env.OPENSIGN_MASTER_KEY || '';
// Parse _User objectId of the service/admin account that owns documents
// created by this integration — a one-time setup value, documented in
// the README, not something end users of RentShield ever see.
const OPENSIGN_SERVICE_USER_ID = process.env.OPENSIGN_SERVICE_USER_ID || '';

function parseHeaders(extra = {}) {
  return {
    'X-Parse-Application-Id': OPENSIGN_APP_ID,
    'X-Parse-Master-Key': OPENSIGN_MASTER_KEY,
    'Content-Type': 'application/json',
    ...extra
  };
}

async function parseFetch(path, options = {}) {
  const res = await fetch(`${OPENSIGN_URL}/app${path}`, {
    ...options,
    headers: parseHeaders(options.headers)
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.error || `OpenSign API returned ${res.status}`);
  }
  return body;
}

async function findOrCreateContact(email, name) {
  const query = encodeURIComponent(JSON.stringify({
    Email: email,
    CreatedBy: { __type: 'Pointer', className: '_User', objectId: OPENSIGN_SERVICE_USER_ID }
  }));
  const existing = await parseFetch(`/classes/contracts_Contactbook?where=${query}&limit=1`, { method: 'GET' });
  if (existing.results?.length) return existing.results[0].objectId;

  const created = await parseFetch('/classes/contracts_Contactbook', {
    method: 'POST',
    body: JSON.stringify({
      Name: name,
      Email: email,
      CreatedBy: { __type: 'Pointer', className: '_User', objectId: OPENSIGN_SERVICE_USER_ID }
    })
  });
  return created.objectId;
}

export async function uploadFile(buffer, filename, contentType) {
  const res = await fetch(`${OPENSIGN_URL}/app/files/${encodeURIComponent(filename)}`, {
    method: 'POST',
    headers: { 'X-Parse-Application-Id': OPENSIGN_APP_ID, 'Content-Type': contentType },
    body: buffer
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error || `OpenSign file upload returned ${res.status}`);
  return body.url;
}

// pdfBuffer must already be a rendered PDF of the notice — OpenSign
// signs an uploaded file, it doesn't render HTML like DocuSeal does.
export async function createDocumentSubmission({ name, pdfBuffer, submitterName, submitterEmail }) {
  if (!OPENSIGN_SERVICE_USER_ID) {
    throw new Error('OPENSIGN_SERVICE_USER_ID is not configured — see README for the one-time OpenSign setup step');
  }

  const fileUrl = await uploadFile(pdfBuffer, `${name.replace(/\s+/g, '-')}.pdf`, 'application/pdf');
  const contactId = await findOrCreateContact(submitterEmail, submitterName);
  const contactPtr = { __type: 'Pointer', className: 'contracts_Contactbook', objectId: contactId };

  const doc = await parseFetch('/functions/createdocumentfromapp', {
    method: 'POST',
    body: JSON.stringify({
      document: {
        Name: name,
        URL: fileUrl,
        ExtUserPtr: contactPtr,
        CreatedBy: { __type: 'Pointer', className: '_User', objectId: OPENSIGN_SERVICE_USER_ID },
        Signers: [contactPtr],
        SendinOrder: false,
        Placeholders: [
          {
            Id: 1,
            Type: 'signature',
            pageNumber: 1,
            signerPtr: contactPtr,
            signerObjId: contactId,
            email: submitterEmail,
            options: { x: 60, y: 700, width: 150, height: 40 }
          }
        ]
      }
    })
  });

  return {
    provider: 'opensign',
    externalId: doc.result?.objectId || doc.objectId,
    signingUrl: fileUrl,
    status: 'pending'
  };
}

export async function getDocumentStatus(externalId) {
  const doc = await parseFetch(`/classes/contracts_Document/${externalId}`, { method: 'GET' });
  return {
    status: doc.IsCompleted ? 'completed' : doc.IsDeclined ? 'declined' : 'pending',
    signedDocumentUrl: doc.SignedUrl || null
  };
}
