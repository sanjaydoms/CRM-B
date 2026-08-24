/**
 * How money and time are written down, in the browser.
 *
 * The mirror of core/formatting.py, and it has to stay a mirror: a customer
 * comparing an invoice against their tracking page is comparing this file's
 * output against that one's. They disagreed -- the invoice said Rs49,875 while
 * the tracking page said Rs49875.00 for the same order -- which is the defect
 * these two modules exist to close.
 *
 * Rules, identical on both sides:
 *   money  INR, Indian (lakh) grouping, paise only when there are paise
 *   time   the boutique's timezone, rendered from a UTC-stored instant
 */

// 'en-IN' gives lakh grouping natively: 1,00,000 rather than 100,000. The
// Python side spells the same grouping out by hand, because Python's own
// separator is Western.
const INR = 'en-IN';

/** Rs49,875 -- and Rs49,875.50 only when there are actually paise. */
export function formatMoney(value, { symbol = '₹' } = {}) {
  const amount = Number(value ?? 0);
  if (!Number.isFinite(amount)) return `${symbol}0`;
  // Rounded first, so 0.999 does not print as "1" with a stray paise test.
  const rounded = Math.round(amount * 100) / 100;
  const hasPaise = Math.abs(rounded * 100) % 100 !== 0;
  const text = Math.abs(rounded).toLocaleString(INR, {
    minimumFractionDigits: hasPaise ? 2 : 0,
    maximumFractionDigits: hasPaise ? 2 : 0,
  });
  return `${rounded < 0 ? '-' : ''}${symbol}${text}`;
}

/** The boutique's timezone, supplied by the API; falls back to the browser's. */
let boutiqueTimeZone = null;
export function setBoutiqueTimeZone(name) {
  boutiqueTimeZone = name || null;
}
function zone() {
  return boutiqueTimeZone ? { timeZone: boutiqueTimeZone } : {};
}

function asDate(value) {
  if (!value) return null;
  const parsed = value instanceof Date ? value : new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/** 24 Aug 2026 */
export function formatDate(value) {
  const d = asDate(value);
  if (!d) return '';
  return d.toLocaleDateString('en-GB', {
    day: 'numeric', month: 'short', year: 'numeric', ...zone(),
  });
}

/** 3:00 PM */
export function formatTime(value) {
  const d = asDate(value);
  if (!d) return '';
  // en-IN renders the meridiem lowercase ("3:00 pm") in most engines, while
  // the Python side produces "3:00 PM". A customer reading a staff screen and
  // their own tracking page should not see two spellings of the same minute.
  return d
    .toLocaleTimeString(INR, {
      hour: 'numeric', minute: '2-digit', hour12: true, ...zone(),
    })
    .replace(/\b([ap])\.?m\.?\b/i, (m) => m.replace(/\./g, '').toUpperCase());
}

/** 24 Aug 2026, 3:00 PM */
export function formatDateTime(value) {
  const d = asDate(value);
  if (!d) return '';
  return `${formatDate(d)}, ${formatTime(d)}`;
}
