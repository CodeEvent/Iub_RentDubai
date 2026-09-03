import { Router } from 'express';
import multer from 'multer';
import { analyzeTenancyText } from '@rentshield/shared';

export const documents = Router();

const upload = multer({
  storage: multer.memoryStorage(),
  limits: { fileSize: 15 * 1024 * 1024 }
});

const OCR_SERVICE_URL = process.env.OCR_SERVICE_URL || 'http://localhost:8001';

// POST /api/documents/analyze — the real OCR + compliance-check pipeline
// behind the chat drawer's document upload. Forwards the file to
// ocr/ (PaddleOCR), then runs shared's regex-based clause detector
// against whatever text actually came back — no canned response.
documents.post('/analyze', upload.single('file'), async (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'No file uploaded' });
  }

  const form = new FormData();
  form.append('file', new Blob([req.file.buffer], { type: req.file.mimetype }), req.file.originalname);

  let ocrResult;
  try {
    const ocrRes = await fetch(`${OCR_SERVICE_URL}/extract`, { method: 'POST', body: form });
    const body = await ocrRes.json().catch(() => ({}));
    if (!ocrRes.ok) {
      return res.status(502).json({ error: body.detail || `OCR service returned ${ocrRes.status}` });
    }
    ocrResult = body;
  } catch (err) {
    return res.status(502).json({ error: `OCR service unavailable: ${err.message}` });
  }

  const analysis = analyzeTenancyText(ocrResult.text);
  res.json({ ocr: ocrResult, analysis });
});
