import { Router } from 'express';
import { listLegalSkills, getLegalSkill } from '../services/legalSkills.js';

export const legalSkills = Router();

// GET /api/legal-skills — summaries only, for a picker/suggestion list
legalSkills.get('/', (req, res) => {
  const skills = listLegalSkills().map(({ id, title, jurisdiction, practice_area }) => ({
    id, title, jurisdiction, practice_area
  }));
  res.json({ skills });
});

// GET /api/legal-skills/:id — full guidance text + disclaimer
legalSkills.get('/:id', (req, res) => {
  const skill = getLegalSkill(req.params.id);
  if (!skill) return res.status(404).json({ error: 'Skill not found' });
  res.json({ skill });
});
