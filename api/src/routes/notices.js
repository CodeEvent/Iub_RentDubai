import { Router } from 'express';
import crypto from 'node:crypto';
import { db } from '../db.js';
import { buildNotice, ALL_REASONS, noticePeriodDays, calculateTotal } from '@rentshield/shared';

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
    INSERT INTO notices (id, landlord_name, tenant_name, property_type, unit_no, building_name, plot_number, ejari_number, notice_date, reason, add_notarization, add_ai_review)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).run(
    id,
    body.landlordName,
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

// DELETE /api/notices/:id
notices.delete('/:id', (req, res) => {
  const result = db.prepare('DELETE FROM notices WHERE id = ?').run(req.params.id);
  if (result.changes === 0) return res.status(404).json({ error: 'Notice not found' });
  res.status(204).end();
});
