#!/usr/bin/env node
// Seeds the local SQLite database with a couple of realistic example
// notices, so a fresh checkout of the platform opens with working data
// instead of an empty screen. Safe to re-run — it no-ops if data exists.
import crypto from 'node:crypto';
import { db } from '../api/src/db.js';

const { c: existingCount } = db.prepare('SELECT COUNT(*) as c FROM notices').get();
if (existingCount > 0) {
  console.log(`Database already has ${existingCount} notice(s) — skipping seed.`);
  process.exit(0);
}

const samples = [
  {
    landlord_name: 'Ahmed Khalifa Al Suwaidi',
    tenant_name: 'John Michael Smith',
    property_type: 'Apartment',
    unit_no: '1204',
    building_name: 'Marina Heights, Dubai Marina',
    plot_number: '341-2891',
    ejari_number: '1234567890',
    notice_date: '2026-01-15',
    reason: 'personal',
    tier: 'standard'
  },
  {
    landlord_name: 'Fatima Al Marri',
    tenant_name: 'Priya Patel',
    property_type: 'Villa',
    unit_no: '12',
    building_name: 'Al Barsha South, Community 3',
    plot_number: '552-1190',
    ejari_number: '9876543210',
    notice_date: '2026-02-01',
    reason: 'nonpayment',
    tier: 'premium'
  }
];

const insert = db.prepare(`
  INSERT INTO notices (id, landlord_name, tenant_name, property_type, unit_no, building_name, plot_number, ejari_number, notice_date, reason, tier)
  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
`);

for (const s of samples) {
  insert.run(
    crypto.randomUUID(),
    s.landlord_name, s.tenant_name, s.property_type, s.unit_no,
    s.building_name, s.plot_number, s.ejari_number, s.notice_date,
    s.reason, s.tier
  );
}

console.log(`Seeded ${samples.length} example notice(s).`);
