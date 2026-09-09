/**
 * Tell the server this browser crashed.
 *
 * Deliberately not routed through services/api.js. That module retries, unpacks
 * DRF error shapes, and signs the user out on a confirmed 401 -- all correct for
 * a request the user is waiting on, and all wrong here. A crash reporter that
 * can log someone out because reporting failed is worse than no crash reporter.
 *
 * So: bare fetch, no retry, no auth handling, and every failure swallowed. The
 * caller is an error boundary that has already failed once.
 */

const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

/** Matches core.exceptions and crm_api.client_errors, which cap again server-side. */
const LIMITS = { name: 200, message: 2000, stack: 4000, route: 300 };

const clip = (value, key) => String(value ?? '').slice(0, LIMITS[key]);

/**
 * One report per distinct crash per page load.
 *
 * A React error boundary can be re-entered on every attempted re-render, so a
 * component that throws in a loop would otherwise spend the endpoint's whole
 * rate limit on one bug and drown out the next one.
 */
const alreadySent = new Set();

export function reportCrash(error, info) {
  try {
    const name = clip(error?.name || 'Error', 'name');
    const message = clip(error?.message || String(error), 'message');
    // The component stack names the component that threw, which a JS stack
    // minified by Vite does not. Prefer it, and fall back when React did not
    // give us one (a crash outside rendering, e.g. an event handler).
    const stack = clip(info?.componentStack || error?.stack || '', 'stack');

    const key = `${name}|${message}|${stack.slice(0, 200)}`;
    if (alreadySent.has(key)) return;
    alreadySent.add(key);

    const headers = { 'Content-Type': 'application/json' };
    const tenantId = localStorage.getItem('tenant_id');
    if (tenantId) headers['X-Tenant-ID'] = tenantId;

    fetch(`${BASE_URL}/client-errors/`, {
      method: 'POST',
      headers,
      // No credentials and no Authorization header: the endpoint takes
      // anonymous reports on purpose, and a crash on the login screen is the
      // one it most needs to hear about.
      body: JSON.stringify({
        name,
        message,
        stack,
        route: clip(window.location.pathname + window.location.hash, 'route'),
      }),
    }).catch(() => {});
  } catch {
    // Reporting a crash must never be the thing that crashes.
  }
}
