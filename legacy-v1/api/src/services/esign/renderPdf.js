// Server-side HTML → PDF rendering via headless Chromium, using the
// same rendered notice HTML DocuSeal receives. Needed because OpenSign
// signs an uploaded file rather than accepting raw HTML the way DocuSeal
// does. Replaces the previous "there is no server-side PDF, the browser
// prints it" gap with a real, byte-for-byte reproducible PDF.
import { chromium } from 'playwright';
import fs from 'node:fs';

// Prefer the browser bundled with the installed playwright-core version;
// fall back to this environment's pre-installed Chromium (a pinned older
// revision) when the versions have drifted apart, rather than trying to
// download a new one over the network at request time.
const PINNED_CHROMIUM = '/opt/pw-browsers/chromium-1194/chrome-linux/chrome';
const launchOptions = fs.existsSync(PINNED_CHROMIUM) ? { executablePath: PINNED_CHROMIUM } : {};

export async function renderHtmlToPdf(html) {
  const browser = await chromium.launch(launchOptions);
  try {
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'load' });
    return await page.pdf({ format: 'A4', printBackground: true, margin: { top: '20px', bottom: '20px' } });
  } finally {
    await browser.close();
  }
}
