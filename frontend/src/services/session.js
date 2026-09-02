/**
 * Where the signed-in session lives.
 *
 * Three keys used to be read and written straight out of localStorage in a
 * dozen places across api.js and App.jsx. That was fine while the browser was
 * the only client. It is not fine now, for two reasons that arrived together:
 *
 *   * The access token expires, so something has to know WHEN, and hold the
 *     refresh token that renews it.
 *   * On Android the credential should not sit in the WebView's own storage
 *     when the platform offers an encrypted store. Capacitor's secure storage
 *     is asynchronous, and `getHeaders()` is called synchronously by every one
 *     of a hundred request sites.
 *
 * So the session is held IN MEMORY for the life of the page -- synchronous to
 * read, which is what the request path needs -- and a backend persists it
 * underneath. The web backend is localStorage and is seeded synchronously at
 * import, so nothing about the browser's behaviour changes. Android installs
 * an encrypted backend at boot (see setSessionBackend) and calls
 * hydrateSession() before rendering.
 */

const KEYS = {
  token: 'token',
  refresh: 'refresh_token',
  tenantId: 'tenant_id',
  expiresAt: 'token_expires_at',
};

const empty = { token: null, refresh: null, tenantId: null, expiresAt: 0 };

let memory = { ...empty };

const webBackend = {
  read: () => {
    try {
      return {
        token: localStorage.getItem(KEYS.token),
        refresh: localStorage.getItem(KEYS.refresh),
        tenantId: localStorage.getItem(KEYS.tenantId),
        expiresAt: Number(localStorage.getItem(KEYS.expiresAt) || 0),
      };
    } catch {
      // Private mode, or a WebView with storage disabled. An unreadable store
      // is an empty session, not a crash on the first line of the app.
      return { ...empty };
    }
  },
  write: (session) => {
    try {
      Object.entries(KEYS).forEach(([field, key]) => {
        const value = session[field];
        if (value === null || value === undefined || value === '' || value === 0) {
          localStorage.removeItem(key);
        } else {
          localStorage.setItem(key, String(value));
        }
      });
    } catch { /* nothing to do about a storage that refuses writes */ }
  },
};

let backend = webBackend;

// Seeded at import so the very first getHeaders() on the web has the token
// without waiting for anything.
memory = { ...empty, ...webBackend.read() };

/**
 * Install a different persistence backend -- Android's encrypted store.
 *
 * Named `set` rather than `use`: a `use` prefix makes React's linter treat this
 * as a hook and refuse the call outside a component, which is exactly where it
 * belongs (boot, before anything renders).
 *
 * `read` may be async there, which is why hydrateSession exists separately:
 * installing the backend does not itself load anything.
 */
export const setSessionBackend = (impl) => { backend = impl; };

/** Load the persisted session into memory. Call once, before rendering. */
export const hydrateSession = async () => {
  const stored = await backend.read();
  memory = { ...empty, ...(stored || {}) };
  return memory;
};

export const getToken = () => memory.token;
export const getRefreshToken = () => memory.refresh;
export const getTenantId = () => memory.tenantId;

/** Whether the access token is within `skewSeconds` of expiry (or already past). */
export const accessExpiringWithin = (skewSeconds) => {
  if (!memory.token) return false;
  // 0 means an older session that predates expiry tracking, or a server that
  // did not say. Treat it as "not known to be expiring" and let a 401 drive
  // the refresh instead of guessing.
  if (!memory.expiresAt) return false;
  return memory.expiresAt - Date.now() <= skewSeconds * 1000;
};

/**
 * Record what a login or refresh returned. Missing fields are left alone, so a
 * response that omits `tenant_id` does not wipe the tenant.
 */
export const saveSession = ({ token, refresh, expires_in, tenant_id } = {}) => {
  if (token) memory.token = token;
  if (refresh) memory.refresh = refresh;
  if (tenant_id) memory.tenantId = tenant_id;
  if (expires_in) memory.expiresAt = Date.now() + Number(expires_in) * 1000;
  backend.write(memory);
  return memory;
};

export const clearSession = () => {
  memory = { ...empty };
  backend.write(memory);
};
