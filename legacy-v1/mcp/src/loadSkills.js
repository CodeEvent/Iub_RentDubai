// Loads the mcp/skills/*.md library — Markdown files with YAML
// frontmatter (id, title, jurisdiction, practice_area, disclaimer),
// following the SKILL.md convention popularized by two open-source
// legal-skills libraries this platform was evaluated against:
// github.com/ThomasMoreAI/legal-skills-open and
// github.com/zgbrenner/agentcounsel. The skill content itself is
// authored for RentShield specifically (not copied from either repo —
// this session didn't have file-level access to pull their exact
// content), but the "small, disclaimed, human-reviewed reference skill"
// shape and the safety framing in each skill's disclaimer field
// deliberately mirror both projects' approach.
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import matter from 'gray-matter';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SKILLS_DIR = path.join(__dirname, '..', 'skills');

export function loadSkills() {
  const files = fs.readdirSync(SKILLS_DIR).filter((f) => f.endsWith('.md'));
  return files.map((file) => {
    const raw = fs.readFileSync(path.join(SKILLS_DIR, file), 'utf-8');
    const { data, content } = matter(raw);
    return { ...data, body: content.trim() };
  });
}
