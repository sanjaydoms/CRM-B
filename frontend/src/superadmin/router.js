/**
 * A hash router in fifteen lines, because the alternative is a dependency.
 *
 * The console has ~15 screens and needs exactly three things from a router: read
 * the current route, change it, and re-render when it changes. react-router is
 * not a dependency of this project (frontend/package.json lists react, react-dom
 * and lucide-react, and nothing else), and adding one to this bundle for those
 * three things is not a trade worth making.
 *
 * The hash rather than the path deliberately. frontend/vercel.json rewrites
 * /superadmin/:path* to superadmin.html, so a path router would work in
 * production -- but `vite preview` and any static file server do not rewrite,
 * so /superadmin/errors would 404 in every local check. The hash never leaves
 * the browser, so it behaves identically everywhere.
 *
 * useSyncExternalStore rather than a useState+useEffect pair: it is the built-in
 * React 19 hook for exactly this (subscribe to something outside React, read a
 * snapshot), it gets the tearing semantics right during concurrent renders, and
 * it is less code.
 */

import { useSyncExternalStore } from 'react';

const listeners = new Set();

const emit = () => listeners.forEach((fn) => fn());

function subscribe(fn) {
  listeners.add(fn);
  window.addEventListener('hashchange', emit);
  return () => {
    listeners.delete(fn);
    if (listeners.size === 0) window.removeEventListener('hashchange', emit);
  };
}

const snapshot = () => window.location.hash.replace(/^#\/?/, '') || 'dashboard';

/** Change route. Pushes history, so the browser Back button works. */
export function go(route) {
  if (snapshot() === route) return;
  window.location.hash = `/${route}`;
}

/** Replace the route without a history entry -- for redirects. */
export function replace(route) {
  window.history.replaceState(null, '', `#/${route}`);
  emit();
}

/**
 * The current route as [head, ...rest].
 *
 * 'boutiques/abc_123/data' -> ['boutiques', 'abc_123', 'data'], so a screen can
 * read its own parameters without a matcher. Fifteen screens do not need one.
 */
export function useRoute() {
  const hash = useSyncExternalStore(subscribe, snapshot, () => 'dashboard');
  const parts = hash.split('/').filter(Boolean);
  // `go` is passed through rather than wrapped in useCallback: it is a
  // module-level function, so it is already the same reference on every render
  // and wrapping it would only obscure that.
  return { hash, head: parts[0] || 'dashboard', parts, go };
}
