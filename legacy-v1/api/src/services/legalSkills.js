// Reads the mcp/ workspace's skills library directly (mcp/skills/*.md) so
// the same reviewable content backs both the MCP tools (list_legal_skills
// / get_legal_skill) and the in-app chat drawer, rather than maintaining
// two copies. See mcp/src/loadSkills.js for the format this parses.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILLS_DIR = path.join(__dirname, '..', '..', '..', 'mcp', 'skills');

export function listLegalSkills() {
  const files = fs.readdirSync(SKILLS_DIR).filter((f) => f.endsWith('.md'));
  return files.map((file) => {
    const raw = fs.readFileSync(path.join(SKILLS_DIR, file), 'utf-8');
    const { data, content } = matter(raw);
    return { ...data, body: content.trim() };
  });
}

export function getLegalSkill(id) {
  return listLegalSkills().find((s) => s.id === id) || null;
}
