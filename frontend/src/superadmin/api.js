/**
 * The platform console's API client.
 *
 * Deliberately not src/services/api.js, and the difference is not stylistic.
 * That client attaches an `X-Tenant-ID` header from localStorage and reads the
 * `token` key; this console must send neither. A stale tenant header is ignored
 * by the server (the middleware pins /api/superadmin/ to the public schema), but
 * sharing the *token* key would be a real fault: opening the console in a
 * browser already signed in to a boutique would overwrite that boutique's token
 * with an administrator one, and signing out of either would sign the person out
 * of both. Separate key, separate client, no interference in either direction.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';
const CONSOLE_URL = `${BASE_URL}/superadmin`;

export const TOKEN_KEY = 'superadmin_token';
const REFRESH_KEY = 'superadmin_refresh';

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const clearToken = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
};

const storeSession = (data) => {
  if (data.token) localStorage.setItem(TOKEN_KEY, data.token);
  if (data.refresh) localStorage.setItem(REFRESH_KEY, data.refresh);
};

/**
 * Renew the console's access token, at most once at a time.
 *
 * The console's tokens expire now, like every other token in the product. An
 * administrator reading an audit log for two hours should not be thrown out
 * mid-page, and every rotation invalidates the token it replaced -- so two
 * concurrent refreshes would spend the same refresh token twice and the server
 * would correctly treat the second as a replay. Hence the single flight.
 */
let refreshInFlight = null;

const refreshSession = () => {
  if (refreshInFlight) return refreshInFlight;
  const refresh = localStorage.getItem(REFRESH_KEY);
  if (!refresh) return Promise.resolve(false);

  refreshInFlight = fetch(`${CONSOLE_URL}/auth/refresh/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ refresh }),
  })
    .then(async (res) => {
      if (!res.ok) return false;
      const data = await res.json().catch(() => null);
      if (!data || !data.token) return false;
      storeSession(data);
      return true;
    })
    .catch(() => false)
    .finally(() => { refreshInFlight = null; });

  return refreshInFlight;
};

/**
 * Filters as a query string, with empty values dropped.
 *
 * A cleared filter must send nothing rather than `status=`, which the server
 * would read as a real value and match against no rows -- an empty table that
 * looks like an answer.
 */
const qs = (filters) =>
  new URLSearchParams(
    Object.entries(filters).filter(
      ([, v]) => v !== undefined && v !== null && v !== '')
  ).toString();

const headers = () => {
  const h = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) h.Authorization = `Token ${token}`;
  return h;
};

/** Turn a failed response into a sentence worth showing someone. */
const describe = (res, data) => {
  if (data && typeof data === 'object') {
    // `message` for the user actions: UserActionView answers a refusal with
    // HTTP 400 and {ok: false, message}, so without it the one sentence that
    // explains why -- "that account is the boutique owner" -- is thrown away
    // here and the console shows "that request failed (error 400)" instead.
    const text = data.error || data.detail || data.message;
    if (text) return String(text);
  }
  if (res.status === 401 || res.status === 403) return 'Your session has ended. Please sign in again.';
  if (res.status >= 500) return `The server could not complete that (error ${res.status}).`;
  return `That request failed (error ${res.status}).`;
};

async function request(path, { method = 'GET', body } = {}) {
  const send = () => fetch(`${CONSOLE_URL}${path}`, {
    method,
    // Rebuilt per attempt, not captured: after a refresh the headers built for
    // the first attempt name a token that has been replaced.
    headers: headers(),
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  let res = await send();
  // An expired access token is an ordinary event on a console left open. Try
  // the refresh token before concluding the session is over.
  if (res.status === 401 && await refreshSession()) {
    res = await send();
  }

  if (res.status === 204) return null;

  // A 401/403 on anything other than the login call means the stored token is
  // no longer good. Dropping it here rather than in each caller is what stops
  // the console sitting on a dead token and showing the same error forever.
  // A 500 can come back as an HTML traceback page, and a proxy's 502 as
  // nothing at all, so the body is parsed defensively rather than assumed.
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    if (res.status === 401 || res.status === 403) clearToken();
    const error = new Error(describe(res, data));
    error.status = res.status;
    throw error;
  }
  return data;
}

export const consoleApi = {
  async login(username, password) {
    // Uses fetch directly: request() would attach a stale Authorization header
    // and clear the token on a wrong password, which is the one place a 400 is
    // an ordinary answer rather than a broken session.
    const res = await fetch(`${CONSOLE_URL}/auth/login/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json().catch(() => null);
    if (!res.ok) throw new Error(describe(res, data));
    storeSession(data);
    return data.user;
  },

  me: () => request('/auth/me/'),

  async logout() {
    try {
      await request('/auth/logout/', { method: 'POST' });
    } finally {
      // The token is dropped locally whatever the server said. A failed logout
      // that leaves the console signed in is the worse outcome of the two.
      clearToken();
    }
  },

  overview: () => request('/overview/'),
  // The reason is not decoration: the server records it on the audit entry, and
  // it is the only place the answer to "why was this boutique switched off"
  // ever gets written down. Dropping it here would leave the trail with a who
  // and a when and no why.
  suspend: (schema, reason = '') =>
    request(`/boutiques/${schema}/suspend/`, { method: 'POST', body: { reason } }),
  reactivate: (schema, reason = '') =>
    request(`/boutiques/${schema}/reactivate/`, { method: 'POST', body: { reason } }),

  leads: () => request('/leads/'),
  updateLead: (id, fields) => request(`/leads/${id}/`, { method: 'PATCH', body: fields }),

  // Everything inside one boutique. `datasets` is the sidebar (every table with
  // its row count); `dataset` is a page of one of them.
  datasets: (schema) => request(`/boutiques/${schema}/data/`),
  dataset: (schema, key, { page = 1, pageSize = 50, search = '' } = {}) => {
    const params = new URLSearchParams({ page, page_size: pageSize });
    if (search) params.set('q', search);
    return request(`/boutiques/${schema}/data/${key}/?${params}`);
  },

  // --- Control Center -------------------------------------------------
  //
  // Every filter and page is a query parameter rather than a client-side
  // slice: these tables can run to thousands of rows and the server pages
  // them. `qs()` drops empty values so a cleared filter does not send
  // `?status=` and match nothing.

  users: (filters = {}) => request(`/users/?${qs(filters)}`),
  userAction: (schema, username, action, reason = '') =>
    request(`/users/${schema}/${encodeURIComponent(username)}/${action}/`,
            { method: 'POST', body: { reason } }),
  // Returns {link, expires_minutes, emailed, email_address, ...}. The link is
  // credential-equivalent until it is used: it is shown once, never stored by
  // this client, and never written to the audit trail server-side.
  accessLink: (schema, username, reason = '') =>
    request(`/users/${schema}/${encodeURIComponent(username)}/access-link/`,
            { method: 'POST', body: { reason } }),

  onboarding: () => request('/onboarding/'),
  onboardingFor: (schema) => request(`/onboarding/${schema}/`),

  modules: () => request('/modules/'),
  setModules: (schema, modules, reason = '') =>
    request(`/boutiques/${schema}/modules/`, { method: 'PATCH', body: { modules, reason } }),

  flags: () => request('/flags/'),
  createFlag: (body) => request('/flags/', { method: 'POST', body }),
  updateFlag: (key, body) => request(`/flags/${key}/`, { method: 'PATCH', body }),
  deleteFlag: (key, reason = '') =>
    request(`/flags/${key}/`, { method: 'DELETE', body: { reason } }),

  config: () => request('/config/'),
  setConfig: (key, value, reason = '') =>
    request('/config/', { method: 'PUT', body: { key, value, reason } }),

  health: () => request('/health/'),

  errors: (filters = {}) => request(`/errors/?${qs(filters)}`),
  errorSummary: () => request('/errors/summary/'),
  updateError: (id, body) => request(`/errors/${id}/`, { method: 'PATCH', body }),

  audit: (filters = {}) => request(`/audit/?${qs(filters)}`),

  ordersMonitor: () => request('/orders/'),
  ordersFor: (schema) => request(`/orders/${schema}/`),

  search: (term, limit) => request(`/search/?${qs({ q: term, limit })}`),
  support: (schema) => request(`/support/${schema}/`),
};
