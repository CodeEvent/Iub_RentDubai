/* RERA statutory date math: 12-month (365-day) notices under Article 25(2),
   30-day breach notices under Article 25(1). Ported verbatim from the
   original prototype's date logic. */

const EN_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
const AR_MONTHS = ['يناير', 'فبراير', 'مارس', 'أبريل', 'مايو', 'يونيو', 'يوليو', 'أغسطس', 'سبتمبر', 'أكتوبر', 'نوفمبر', 'ديسمبر'];

export function formatDateEn(d) {
  if (!d) return '[Notice Date]';
  const dt = new Date(d + 'T00:00:00');
  return `${String(dt.getDate()).padStart(2, '0')} ${EN_MONTHS[dt.getMonth()]} ${dt.getFullYear()}`;
}

export function formatDateAr(d) {
  if (!d) return '[تاريخ الإنذار]';
  const dt = new Date(d + 'T00:00:00');
  return `${String(dt.getDate()).padStart(2, '0')} ${AR_MONTHS[dt.getMonth()]} ${dt.getFullYear()}`;
}

export function getExpiryDate(d, days = 365) {
  if (!d) return null;
  const dt = new Date(d + 'T00:00:00');
  dt.setDate(dt.getDate() + days);
  return dt;
}

export function formatExpiryEn(d, days = 365) {
  const dt = getExpiryDate(d, days);
  if (!dt) return '[Expiry Date]';
  return `${String(dt.getDate()).padStart(2, '0')} ${EN_MONTHS[dt.getMonth()]} ${dt.getFullYear()}`;
}

export function formatExpiryAr(d, days = 365) {
  const dt = getExpiryDate(d, days);
  if (!dt) return '[تاريخ الانتهاء]';
  return `${String(dt.getDate()).padStart(2, '0')} ${AR_MONTHS[dt.getMonth()]} ${dt.getFullYear()}`;
}

export function fallback(val, placeholder) {
  return val && String(val).trim() ? String(val).trim() : placeholder;
}
