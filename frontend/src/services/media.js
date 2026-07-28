/**
 * Resolve an image reference into a URL the browser can actually fetch.
 *
 * Seeded catalogue rows store a bare filename ("fabric_02.jpg") rather than a
 * URL, while owner-entered rows store a full external URL. Rendering the bare
 * filename directly makes the browser resolve it against the *frontend* origin,
 * so on Vercel every seeded image 404s at https://<site>/fabric_02.jpg. Deriving
 * the media host from the configured API URL fixes that, and replaces the
 * hardcoded http://localhost:8000/media/ that could only ever work locally.
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const MEDIA_BASE = API_BASE.replace(/\/api\/?$/, '');

export const resolveMediaUrl = (url, fallback = '') => {
  if (!url) return fallback;
  if (/^https?:\/\//i.test(url) || url.startsWith('data:') || url.startsWith('blob:')) {
    return url;
  }
  if (url.startsWith('/')) return `${MEDIA_BASE}${url}`;
  return `${MEDIA_BASE}/media/${url}`;
};
