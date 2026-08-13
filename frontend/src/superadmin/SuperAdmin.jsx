/**
 * The platform console shell: sign-in, navigation, global search, routing.
 *
 * Screens live in ./screens/ and are plain components. This file owns only the
 * things every screen shares -- who is signed in, which route is showing, the
 * toast host and the error boundary -- so that adding a screen is adding a file
 * and one line in nav.js rather than editing a growing conditional.
 *
 * Deliberately separate from src/App.jsx. That is a boutique's workspace, signed
 * in as a boutique and scoped to one tenant; this is signed in as the platform
 * and scoped to all of them. One bundle for both would mean a boutique-role bug
 * becomes a cross-tenant one.
 */

import { Component, useCallback, useEffect, useState } from 'react';
import { LogOut, RefreshCw, ShieldCheck } from 'lucide-react';

import { clearToken, consoleApi, getToken } from './api';
import { NAV, ROUTES } from './nav';
import { useRoute } from './router';
import { Empty, Failed, SearchBox, ToastHost, count } from './ui';
import './superadmin.css';

import Dashboard from './screens/Dashboard.jsx';
import Boutiques from './screens/Boutiques.jsx';
import BoutiqueDetail from './screens/BoutiqueDetail.jsx';
import UsersScreen from './screens/Users.jsx';
import Onboarding from './screens/Onboarding.jsx';
import Leads from './screens/Leads.jsx';
import Modules from './screens/Modules.jsx';
import Flags from './screens/Flags.jsx';
import Config from './screens/Config.jsx';
import OrdersMonitor from './screens/OrdersMonitor.jsx';
import Integrations from './screens/Integrations.jsx';
import Messaging from './screens/Messaging.jsx';
import Errors from './screens/Errors.jsx';
import Health from './screens/Health.jsx';
import Audit from './screens/Audit.jsx';
import Sessions from './screens/Sessions.jsx';
import Support from './screens/Support.jsx';
import NotMeasured from './screens/NotMeasured.jsx';

const SCREENS = {
  dashboard: Dashboard,
  health: Health,
  boutiques: Boutiques,
  users: UsersScreen,
  onboarding: Onboarding,
  leads: Leads,
  modules: Modules,
  flags: Flags,
  config: Config,
  orders: OrdersMonitor,
  integrations: Integrations,
  messaging: Messaging,
  errors: Errors,
  jobs: NotMeasured,
  api: NotMeasured,
  audit: Audit,
  sessions: Sessions,
  support: Support,
};

/* ---------------------------------------------------------------- guard */

/**
 * One thrown render must not blank the whole console.
 *
 * Without this, a single bad field in one API response takes down the screen an
 * administrator opened *because* something is broken -- the worst possible time
 * for the tool to disappear. Class component because React has no hook form of
 * componentDidCatch.
 */
class Boundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Nothing collects frontend errors yet -- the backend Error Center captures
    // server exceptions only. The console at least says so out loud.
    console.error('Console screen crashed:', error, info);
  }

  componentDidUpdate(prev) {
    if (prev.routeKey !== this.props.routeKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <Failed
          error={{ message: `This screen failed to render: ${this.state.error.message}` }}
          onRetry={() => this.setState({ error: null })}
        />
      );
    }
    return this.props.children;
  }
}

/* -------------------------------------------------------------- sign in */

function SignIn({ onSignedIn }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onSignedIn(await consoleApi.login(username, password));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="sa-signin">
      <form className="sa-signin-card" onSubmit={submit}>
        <h1>Platform console</h1>
        <p className="sa-sub">Scaleezy administrators only.</p>

        {error && <div className="sa-note error">{error}</div>}

        <div className="sa-field">
          <label htmlFor="sa-username">Administrator username</label>
          <input id="sa-username" className="sa-input" value={username} autoComplete="username"
            onChange={(e) => setUsername(e.target.value)} required />
        </div>
        <div className="sa-field">
          <label htmlFor="sa-password">Password</label>
          <input id="sa-password" className="sa-input" type="password" value={password}
            autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} required />
        </div>

        <button className="sa-btn primary" type="submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}

/* --------------------------------------------------------- global search */

function GlobalSearch({ onOpen }) {
  const [term, setTerm] = useState('');
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (term.trim().length < 2) { setResults(null); return; }
    let live = true;
    setBusy(true);
    consoleApi.search(term)
      .then((data) => { if (live) setResults(data.results || []); })
      .catch(() => { if (live) setResults([]); })
      .finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [term]);

  return (
    <div style={{ position: 'relative', flex: '0 1 380px' }}>
      <SearchBox value={term} onChange={setTerm}
        placeholder="Search boutiques, users, customers, orders, errors…" />
      {results && (
        <div className="sa-results">
          {busy && <div className="sa-empty">Searching…</div>}
          {!busy && results.length === 0 && <div className="sa-empty">Nothing matches.</div>}
          {results.map((r, i) => (
            <button key={`${r.type}-${r.id}-${i}`} className="sa-result"
              onClick={() => { setTerm(''); setResults(null); onOpen(r); }}>
              <span className="sa-result-type">{r.type}</span>
              <span>
                {r.label}
                {r.sublabel && <span className="sa-muted"> — {r.sublabel}</span>}
              </span>
              {r.boutique_name && <span className="sa-result-sub">{r.boutique_name}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ app */

export default function SuperAdmin() {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  const [errorCount, setErrorCount] = useState(0);
  const route = useRoute();

  // A token in storage is not proof of a live session -- it may have been
  // revoked, or belong to an account that is no longer a superuser -- so the
  // console asks the server before it draws anything.
  useEffect(() => {
    if (!getToken()) { setChecking(false); return; }
    consoleApi.me()
      .then(setUser)
      .catch(() => clearToken())
      .finally(() => setChecking(false));
  }, []);

  // The unresolved-error count rides in the nav so a new incident is visible
  // from whichever screen someone happens to be on.
  const refreshBadges = useCallback(() => {
    if (!user) return;
    consoleApi.errorSummary()
      .then((d) => setErrorCount(d.unresolved || 0))
      .catch(() => setErrorCount(0));
  }, [user]);

  useEffect(() => { refreshBadges(); }, [refreshBadges, route.head]);

  const signOut = async () => {
    await consoleApi.logout();
    setUser(null);
  };

  const openResult = (result) => {
    if (result.type === 'boutique') route.go(`boutiques/${result.boutique}`);
    else if (result.type === 'error') route.go('errors');
    else if (result.type === 'user') route.go('users');
    else if (result.boutique) route.go(`boutiques/${result.boutique}/data`);
  };

  if (checking) {
    return <div className="sa-empty" style={{ paddingTop: 80 }}>Checking your session…</div>;
  }
  if (!user) return <SignIn onSignedIn={setUser} />;

  // A boutique route carries its schema in the URL, so a detail page survives a
  // reload and can be linked to.
  const isDetail = route.head === 'boutiques' && route.parts.length > 1;
  const Screen = isDetail ? BoutiqueDetail : SCREENS[route.head];

  return (
    <ToastHost>
      <div className="sa-shell">
        <nav className="sa-nav">
          <div className="sa-nav-brand">
            <ShieldCheck size={19} />
            Scaleezy
            <span className="sa-tag">Platform</span>
          </div>

          {NAV.map((group) => (
            <div key={group.group} className="sa-nav-group">
              <div className="sa-nav-group-title">{group.group}</div>
              {group.items.map((item) => {
                const Icon = item.icon;
                const active = route.head === item.key;
                return (
                  <button key={item.key} className="sa-nav-item"
                    aria-current={active ? 'page' : undefined}
                    onClick={() => route.go(item.key)}>
                    <Icon size={14} />
                    {item.label}
                    {item.badge === 'errors' && errorCount > 0 && (
                      <span className="sa-nav-badge">{count(errorCount)}</span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        <div className="sa-content">
          <header className="sa-topbar">
            <GlobalSearch onOpen={openResult} />
            <div className="sa-topbar-right">
              <button className="sa-btn" onClick={() => window.location.reload()}>
                <RefreshCw size={13} /> Refresh
              </button>
              <span className="sa-who">{user.username}</span>
              <button className="sa-btn" onClick={signOut}>
                <LogOut size={13} /> Sign out
              </button>
            </div>
          </header>

          <main className="sa-page">
            <Boundary routeKey={route.hash}>
              {Screen
                ? <Screen route={route} onBadges={refreshBadges} />
                : <Empty title="No such screen."
                    detail={`"${route.head}" is not part of the console.`}
                    action={<button className="sa-btn" onClick={() => route.go('dashboard')}>
                      Go to the dashboard
                    </button>} />}
            </Boundary>
          </main>
        </div>
      </div>
    </ToastHost>
  );
}

export { ROUTES };
