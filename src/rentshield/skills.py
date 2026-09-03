# Loads the rentshield/skills/*.md library — Markdown files with YAML
# frontmatter (id, title, jurisdiction, practice_area, disclaimer),
# following the SKILL.md convention popularized by two open-source
# legal-skills libraries this platform was evaluated against:
# github.com/ThomasMoreAI/legal-skills-open and
# github.com/zgbrenner/agentcounsel. The skill content itself is
# authored for RentShield specifically (not copied from either repo),
# but the "small, disclaimed, human-reviewed reference skill" shape and
# the safety framing in each skill's disclaimer field deliberately
# mirror both projects' approach. Ported 1:1 from
# legacy-v1/mcp/src/loadSkills.js — same three skill files (copied
# verbatim, they're plain Markdown with no JS-specific content), same
# frontmatter format, re-parsed here with PyYAML instead of gray-matter
# since this stack no longer has a Node runtime.
from __future__ import annotations

import pathlib

import yaml

SKILLS_DIR = pathlib.Path(__file__).parent / "skills"

_FRONTMATTER_RE_DELIM = "---"


def _parse_frontmatter(raw: str) -> tuple[dict, str]:
    """Splits a `---\\nYAML\\n---\\nbody` file into (frontmatter dict, body)."""
    if not raw.startswith(_FRONTMATTER_RE_DELIM):
        return {}, raw.strip()
    parts = raw.split(_FRONTMATTER_RE_DELIM, 2)
    if len(parts) < 3:
        return {}, raw.strip()
    _, frontmatter_raw, body = parts
    data = yaml.safe_load(frontmatter_raw) or {}
    return data, body.strip()


def load_skills() -> list[dict]:
    skills = []
    for path in sorted(SKILLS_DIR.glob("*.md")):
        raw = path.read_text(encoding="utf-8")
        data, body = _parse_frontmatter(raw)
        skills.append({**data, "body": body})
    return skills


def get_skill(skill_id: str) -> dict | None:
    for skill in load_skills():
        if skill.get("id") == skill_id:
            return skill
    return None
