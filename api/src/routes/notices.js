import { Router } from 'express';
import crypto from 'node:crypto';
import { db } from '../db.js';
import { buildNotice, ALL_REASONS, noticePeriodDays, calculateTotal } from '@rentshield/shared';
import { requestSigning, checkSigningStatus } from '../services/esign/index.js';

export const notices = Router();

const REQUIRED_FIELDS = ['landlordName', 'tenantName', 'noticeDate', 'reason'];

function rowToInput(row) {
  return {
    landlordName: row.landlord_name,
    tenantName: row.tenant_name,
    propertyType: row.property_type,
    unitNo: row.unit_no,
    buildingName: row.building_name,
    plotNumber: row.plot_number,
    ejariNumber: row.ejari_number,
    noticeDate: row.notice_date,
    reason: row.reason
  };
}

function rowSummary(row) {
  const r = ALL_REASONS[row.reason];
  const addOns = { notarization: !!row.add_notarization, aiReview: !!row.add_ai_review };
  return {
    id: row.id,
    landlordName: row.landlord_name,
    tenantName: row.tenant_name,
    propertyType: row.property_type,
    unitNo: row.unit_no,
    buildingName: row.building_name,
    plotNumber: row.plot_number,
    ejariNumber: row.ejari_number,
    noticeDate: row.notice_date,
    reason: row.reason,
    reasonLabel: r ? r.label : row.reason,
    noticePeriodDays: noticePeriodDays(row.reason),
    addOns,
    totalPriceAed: calculateTotal(addOns),
    landlordEmail: row.landlord_email,
    esign: {
      provider: row.esign_provider,
      status: row.esign_status,
      signingUrl: row.esign_signing_url,
      signedDocumentUrl: row.esign_signed_document_url
    },
    createdAt: row.created_at
  };
}

// GET /api/notices — list, newest first
notices.get('/', (req, res) => {
  const rows = db.prepare('SELECT * FROM notices ORDER BY created_at DESC').all();
  res.json({ notices: rows.map(rowSummary) });
});

// POST /api/notices — create a notice record
notices.post('/', (req, res) => {
  const body = req.body || {};
  const missing = REQUIRED_FIELDS.filter((f) => !body[f]);
  if (missing.length) {
    return res.status(400).json({ error: `Missing required field(s): ${missing.join(', ')}` });
  }
  if (!ALL_REASONS[body.reason]) {
    return res.status(400).json({ error: `Unrecognized reason "${body.reason}"` });
  }

  const id = crypto.randomUUID();
  const addOns = body.addOns || {};

  db.prepare(`
    INSERT INTO notices (id, landlord_name, landlord_email, tenant_name, property_type, unit_no, building_name, plot_number, ejari_number, notice_date, reason, add_notarization, add_ai_review)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    id,
    body.landlordName,
    body.landlordEmail || null,
    body.tenantName,
    body.propertyType || 'Apartment',
    body.unitNo || null,
    body.buildingName || null,
    body.plotNumber || null,
    body.ejariNumber || null,
    body.noticeDate,
    body.reason,
    addOns.notarization ? 1 : 0,
    addOns.aiReview ? 1 : 0
  );

  const row = db.prepare('SELECT * FROM notices WHERE id = ?').get(id);
  res.status(201).json({ notice: rowSummary(row), document: buildNotice(rowToInput(row)) });
});

// GET /api/notices/:id — full record + freshly-rendered bilingual document
notices.get('/:id', (req, res) => {
  const row = db.prepare('SELECT * FROM notices WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'Notice not found' });
  res.json({ notice: rowSummary(row), document: buildNotice(rowToInput(row)) });
});

// POST /api/notices/:id/notarize — routes the saved notice through a real
// e-signature workflow (DocuSeal primary, OpenSign fallback). Requires
// the notarization add-on to have been selected and a landlord email to
// route the signing request to.
notices.post('/:id/notarize', async (req, res) => {
  const row = db.prepare('SELECT * FROM notices WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'Notice not found' });
  if (!row.add_notarization) {
    return res.status(400).json({ error: 'Notarization add-on was not selected for this notice' });
  }
  if (!row.landlord_email) {
    return res.status(400).json({ error: 'A landlord email is required to route the notarization request' });
  }

  const document = buildNotice(rowToInput(row));
  const reason = ALL_REASONS[row.reason];

  let result;
  try {
    result = await requestSigning(document, {
      landlordName: row.landlord_name,
      landlordEmail: row.landlord_email,
      tenantName: row.tenant_name,
      reasonLabel: reason ? reason.label : row.reason
    });
  } catch (err) {
    return res.status(502).json({ error: err.message });
  }

  db.prepare(`
    UPDATE notices
    SET esign_provider = ?, esign_external_id = ?, esign_signing_url = ?, esign_status = ?, esign_requested_at = datetime('now')
    WHERE id = ?
  `).run(result.provider, result.externalId, result.signingUrl, result.status, row.id);

  res.json({ provider: result.provider, status: result.status, signingUrl: result.signingUrl });
});

// GET /api/notices/:id/notarize/status — refreshes the signing status
// from whichever provider originally handled the request.
notices.get('/:id/notarize/status', async (req, res) => {
  const row = db.prepare('SELECT * FROM notices WHERE id = ?').get(req.params.id);
  if (!row) return res.status(404).json({ error: 'Notice not found' });
  if (!row.esign_provider || !row.esign_external_id) {
    return res.status(400).json({ error: 'No notarization request has been made for this notice yet' });
  }

  let status;
  try {
    status = await checkSigningStatus(row.esign_provider, row.esign_external_id);
  } catch (err) {
    return res.status(502).json({ error: err.message });
  }

  db.prepare(`
    UPDATE notices SET esign_status = ?, esign_signed_document_url = ? WHERE id = ?
  `).run(status.status, status.signedDocumentUrl, row.id);

  res.json({ provider: row.esign_provider, status: status.status, signedDocumentUrl: status.signedDocumentUrl });
});

// DELETE /api/notices/:id
notices.delete('/:id', (req, res) => {
  const result = db.prepare('DELETE FROM notices WHERE id = ?').run(req.params.id);
  if (result.changes === 0) return res.status(404).json({ error: 'Notice not found' });
  res.status(204).end();
});
