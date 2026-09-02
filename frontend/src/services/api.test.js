/**
 * The renewal path, which has no other way to be checked.
 *
 * Everything else in api.js is a fetch and a shape. This is the one part with
 * real control flow -- and the one part that, done wrong, signs the whole shop
 * out: refreshing twice in parallel spends the same refresh token twice, which
 * the server correctly reads as a stolen credential and answers by ending every
 * session the user has. That failure is invisible until eight requests land at
 * once, which is exactly what opening the dashboard does.
 *
 * Run: npm test
 */

import assert from 'node:assert/strict';
import { beforeEach, describe, it } from 'node:test';

import { api } from './api.js';
import { clearSession, getToken, saveSession, setSessionBackend } from './session.js';

// No localStorage and no window in node. The session store already survives an
// unusable storage (it catches), but it must not PERSIST between tests either,
// so an in-memory backend is installed.
let stored = {};
setSessionBackend({ read: () => stored, write: (s) => { stored = { ...s }; } });
globalThis.window = { location: { reload() {} }, dispatchEvent() {} };
globalThis.CustomEvent = class { constructor(type, init) { Object.assign(this, init); this.type = type; } };

const json = (status, body) => ({
  status,
  ok: status >= 200 && status < 300,
  clone() { return this; },
  json: async () => body,
});

/** A fetch that answers 401 until the caller presents `goodToken`. */
const server = ({
  goodToken = 'new-access',
  refreshAnswer = json(200, { token: 'new-access', refresh: 'new-refresh', expires_in: 3600 }),
} = {}) => {
  const calls = [];
  const fn = async (url, options = {}) => {
    calls.push({ url: String(url), auth: options.headers?.Authorization });
    if (String(url).endsWith('/auth/refresh/')) return refreshAnswer;
    if (options.headers?.Authorization === `Token ${goodToken}`) {
      return json(200, { ok: true });
    }
    return json(401, { detail: 'Your session has expired.', code: 'token_expired' });
  };
  fn.calls = calls;
  fn.refreshes = () => calls.filter((c) => c.url.endsWith('/auth/refresh/')).length;
  return fn;
};

describe('renewing an expired access token', () => {
  beforeEach(() => {
    stored = {};
    clearSession();
    saveSession({ token: 'old-access', refresh: 'old-refresh', expires_in: 3600, tenant_id: 'atelier' });
  });

  it('refreshes once on a 401 and retries with the NEW token', async () => {
    const fetchStub = server();
    globalThis.fetch = fetchStub;

    const data = await api.getDashboard();

    assert.equal(data.ok, true);
    assert.equal(fetchStub.refreshes(), 1);
    // The retry must not carry the header the call site built before the
    // refresh ran. This is the assertion that would catch a regression to
    // passing the caller's headers straight through.
    assert.equal(fetchStub.calls.at(-1).auth, 'Token new-access');
    assert.equal(getToken(), 'new-access');
  });

  it('refreshes ONCE for eight requests that expire together', async () => {
    const fetchStub = server();
    globalThis.fetch = fetchStub;

    const results = await Promise.all(Array.from({ length: 8 }, () => api.getDashboard()));

    assert.equal(results.length, 8);
    assert.equal(fetchStub.refreshes(), 1, 'a second refresh would spend an already-spent token');
  });

  it('gives up rather than looping when the refresh token is refused', async () => {
    const fetchStub = server({ refreshAnswer: json(401, { code: 'refresh_invalid' }) });
    globalThis.fetch = fetchStub;

    await assert.rejects(() => api.getDashboard());
    assert.equal(fetchStub.refreshes(), 1);
  });

  it('does not attempt a refresh when nothing was ever stored', async () => {
    clearSession();
    const fetchStub = server({ goodToken: 'unreachable' });
    globalThis.fetch = fetchStub;

    await assert.rejects(() => api.getDashboard());
    assert.equal(fetchStub.refreshes(), 0);
  });

  it('renews before sending when the token is nearly out of time', async () => {
    saveSession({ token: 'old-access', refresh: 'old-refresh', expires_in: 5 });
    const fetchStub = server();
    globalThis.fetch = fetchStub;

    await api.getDashboard();

    // The very first call is the refresh: the token was known to be expiring,
    // so the request never had to fail to find that out.
    assert.ok(fetchStub.calls[0].url.endsWith('/auth/refresh/'));
    assert.equal(fetchStub.refreshes(), 1);
  });

  it('turns a dead network into a sentence rather than "Failed to fetch"', async () => {
    // What a phone actually does when it has no signal: fetch rejects, with no
    // response to translate. The raw TypeError was reaching the screen.
    globalThis.fetch = async () => { throw new TypeError('Failed to fetch'); };

    await assert.rejects(() => api.getDashboard(), (error) => {
      assert.match(error.message, /no connection/i);
      assert.doesNotMatch(error.message, /Failed to fetch/);
      return true;
    });
  });
});
