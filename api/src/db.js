// Node's built-in SQLite (stable since Node 22.5, still flagged
// experimental by the runtime) — deliberately chosen over MySQL/Postgres
// so the whole platform stays zero-infrastructure to run locally, in
// keeping with the project's "zero budget" constraint. Swap this file
// alone if a real deployment later needs Postgres/MySQL.
import { DatabaseSync } from 'node:sqlite';
import path from 'node:path';
import fs from 'node:fs';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.join(__dirname, '..', 'data');
fs.mkdirSync(dataDir, { recursive: true });

const dbPath = process.env.RENTSHIELD_DB_PATH || path.join(dataDir, 'rentshield.sqlite');
export const db = new DatabaseSync(dbPath);

db.exec(`
  CREATE TABLE IF NOT EXISTS notices (
    id TEXT PRIMARY KEY,
    landlord_name TEXT NOT NULL,
    tenant_name TEXT NOT NULL,
    property_type TEXT NOT NULL DEFAULT 'Apartment',
    unit_no TEXT,
    building_name TEXT,
    plot_number TEXT,
    ejari_number TEXT,
    notice_date TEXT NOT NULL,
    reason TEXT NOT NULL,
    add_notarization INTEGER NOT NULL DEFAULT 0,
    add_ai_review INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
  )
`);
