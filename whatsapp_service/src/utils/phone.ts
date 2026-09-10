/**
 * Normalizes phone numbers to WhatsApp JID format (e.g., "919876543210@s.whatsapp.net").
 */
export function formatToWhatsAppJid(phone: string): string | null {
  if (!phone || typeof phone !== 'string') return null;

  // If already formatted as a full JID
  if (phone.endsWith('@s.whatsapp.net')) {
    return phone;
  }

  // Remove all non-digit characters
  let digits = phone.replace(/\D/g, '');

  // Check minimum length requirement for a valid phone number
  if (!digits || digits.length < 7) {
    return null;
  }

  // Standard Indian 10-digit mobile number prefixing
  if (digits.length === 10 && /^[6-9]\d{9}$/.test(digits)) {
    digits = `91${digits}`;
  }

  return `${digits}@s.whatsapp.net`;
}
