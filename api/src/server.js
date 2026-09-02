import express from 'express';
import cors from 'cors';
import { ALL_REASONS } from '@rentshield/shared';
import { notices } from './routes/notices.js';

const app = express();
const PORT = process.env.PORT || 4000;

app.use(cors());
app.use(express.json());

app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: '@rentshield/api' });
});

// Expose the statutory grounds so any client (Vue, MCP, a future mobile
// app) can render the picker without bundling shared/ directly.
app.get('/api/reasons', (req, res) => {
  res.json({ reasons: ALL_REASONS });
});

app.use('/api/notices', notices);

app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'Internal server error' });
});

app.listen(PORT, () => {
  console.log(`RentShield API listening on http://localhost:${PORT}`);
});
