/**
 * The boutique workspace's error boundary. There was not one.
 *
 * App.jsx is the largest file in this product and the one every boutique uses
 * all day. A thrown render there unmounted the whole tree: the user got a white
 * page with no explanation and no way forward, and the server -- which had
 * answered every request correctly -- never heard about it. The Super Admin
 * console has had a boundary since it was written; the app the customers
 * actually use did not.
 *
 * Two jobs, in this order:
 *
 * 1. Show the person something other than a blank page, with a way out that is
 *    not "reload and hope".
 * 2. Tell the server, so the crash appears in the Super Admin Error Center as
 *    kind='frontend' instead of existing only in one browser's console.
 *
 * Class component because React still has no hook form of componentDidCatch.
 */

import { Component } from 'react';

import { reportCrash } from './services/reportCrash';

export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    reportCrash(error, info);
    // Kept alongside the report: whoever has devtools open should still see it
    // immediately rather than waiting for it to appear in the console.
    console.error('The workspace crashed:', error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div role="alert" style={{
        maxWidth: 560, margin: '15vh auto', padding: '0 24px',
        fontFamily: 'system-ui, -apple-system, Segoe UI, sans-serif',
        color: '#1f2328', lineHeight: 1.6,
      }}>
        <h1 style={{ fontSize: 21, margin: '0 0 12px' }}>This screen stopped working.</h1>
        <p style={{ margin: '0 0 8px' }}>
          Nothing you were looking at has been lost or changed — the page failed to
          draw, not to save. We have been told about it automatically.
        </p>
        <p style={{ margin: '0 0 20px', color: '#57606a', fontSize: 14 }}>
          {this.state.error.message}
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          {/* Clearing the error re-renders the same tree, which is the right
              first try: most render crashes come from one bad response, and a
              retry after the next fetch succeeds. Reloading is the fallback,
              not the only offer. */}
          <button onClick={() => this.setState({ error: null })} style={BUTTON}>
            Try again
          </button>
          <button onClick={() => window.location.reload()} style={QUIET}>
            Reload the page
          </button>
        </div>
      </div>
    );
  }
}

const BUTTON = {
  padding: '9px 16px', borderRadius: 8, border: '1px solid #1f6feb',
  background: '#1f6feb', color: '#fff', fontSize: 14, cursor: 'pointer',
};

const QUIET = { ...BUTTON, background: '#fff', color: '#1f2328', borderColor: '#d0d7de' };
