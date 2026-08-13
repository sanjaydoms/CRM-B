/**
 * The landing screen: the whole platform in one view.
 *
 * Three calls rather than one, each with its own state. The overview is the
 * page; health and the error count are strips on it, and a failing /health/ must
 * not blank the boutique figures next to it -- a dashboard that disappears
 * because one of its three sources is down is the opposite of what it is for.
 *
 * Every tile routes somewhere. A number an administrator cannot act on belongs
 * on a report, not on the screen they open when something is wrong.
 *
 * What is deliberately absent is at the foot of the page: trials, failed
 * payments, request rates, integration counts, sign-ins this month. This product
 * has no billing, no gateway, no request instrumentation and never calls
 * login(), so User.last_login is never written. A zero in a tile is a
 * measurement that came back empty; there is no measurement here to come back.
 */

import { useCallback, useMemo } from 'react';
import { AlertTriangle, Check, HeartPulse, Info } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Empty, Pill, SectionHead, Stat, Table,
  count, day, money, since, useApi,
} from '../ui';

/** Worst reason first, so an unreadable schema never sits under a quiet one. */
const REASON_RANK = { unreadable: 0, suspended: 1, quiet: 2 };

const DAY = 86400000;

export default function Dashboard({ route }) {
  const state = useApi(useCallback(() => consoleApi.overview(), []));
  const health = useApi(useCallback(() => consoleApi.health(), []));
  const errors = useApi(useCallback(() => consoleApi.errorSummary(), []));

  const attention = useMemo(() => {
    if (!state.data) return [];
    return state.data.boutiques
      .map((b) => {
        const last = since(b.last_order);
        const reasons = [];
        if (!b.healthy) reasons.push({ kind: 'unreadable', tone: 'off', text: 'Schema could not be read' });
        if (!b.is_active) reasons.push({ kind: 'suspended', tone: 'off', text: 'Suspended' });
        // since() already calls anything 30 days old or never 'warn' -- the same
        // threshold this list wants -- so it is read from there rather than
        // re-derived here and left to drift. Skipped when the schema is
        // unreadable: a null last_order then means "could not look", not "quiet".
        if (b.healthy && last.tone === 'warn') {
          reasons.push({
            kind: 'quiet',
            tone: 'warn',
            text: b.last_order ? `No order in ${last.text.replace(' ago', '')}` : 'No orders, ever',
          });
        }
        return { ...b, reasons };
      })
      .filter((b) => b.reasons.length > 0)
      .sort((a, b) =>
        REASON_RANK[a.reasons[0].kind] - REASON_RANK[b.reasons[0].kind]
        || a.name.localeCompare(b.name));
  }, [state.data]);

  const critical = errors.data?.critical || 0;

  return (
    <>
      <SectionHead title="Platform" subtitle="Read live from every boutique schema on this deployment." />

      <Async state={state} skeletonRows={4}>
        {(data) => {
          const t = data.totals;
          // created_on is a date, and a boutique that signed up this month is
          // the one whose setup is still worth watching.
          const fresh = data.boutiques.filter(
            (b) => Date.now() - new Date(b.created_on).getTime() < 30 * DAY).length;

          return (
            <>
              <div className="sa-stats">
                <Stat label="Boutiques" value={count(t.boutiques)}
                  note={`${t.active} active · ${t.suspended} suspended`}
                  onClick={() => route.go('boutiques')} />
                <Stat label="Signed up in 30 days" value={count(fresh)}
                  note="Onboarding progress"
                  onClick={() => route.go('onboarding')} />
                <Stat label="Unreadable schemas" value={count(t.unreadable)}
                  note={t.unreadable ? 'Excluded from every total below' : 'All schemas readable'}
                  tone={t.unreadable ? 'off' : undefined}
                  onClick={() => route.go('health')} />
                <Stat label="Staff accounts" value={count(t.staff)}
                  note={`${count(data.administrators)} platform administrator(s)`}
                  onClick={() => route.go('users')} />
                <Stat label="Customers" value={count(t.customers)}
                  note="Across all boutiques"
                  onClick={() => route.go('boutiques')} />
                <Stat label="Orders" value={count(t.orders)}
                  note={`${count(t.open_orders)} still open`}
                  onClick={() => route.go('orders')} />
                <Stat label="Booked" value={money(t.revenue)}
                  note="Sum of order totals"
                  onClick={() => route.go('orders')} />
                <Stat label="Collected" value={money(t.collected)}
                  note="Recorded by staff by hand"
                  onClick={() => route.go('orders')} />
                <Stat label="Demo requests" value={count(data.leads.total)}
                  note={`${data.leads.new} new · ${data.leads.last_30_days} in 30 days`}
                  tone={data.leads.new ? 'warn' : undefined}
                  onClick={() => route.go('leads')} />
                <Stat label="Unresolved errors"
                  value={errors.data ? count(errors.data.unresolved) : '—'}
                  // No invented zero: a failed count says so, and the tile still
                  // opens the screen that can answer the question properly.
                  note={errors.error ? 'Count unavailable' :
                        errors.data ? (critical ? `${critical} critical` : 'None critical') : 'Counting…'}
                  tone={critical ? 'off' : undefined}
                  onClick={() => route.go('errors')} />
              </div>

              {critical > 0 && (
                <div className="sa-note error" style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <AlertTriangle size={16} style={{ flexShrink: 0 }} />
                  <span>
                    {critical} unresolved critical error{critical === 1 ? '' : 's'}. Every one is an
                    unhandled 500 a boutique hit.
                  </span>
                  <button className="sa-btn danger" style={{ marginLeft: 'auto' }}
                    onClick={() => route.go('errors')}>
                    Open the Error Center
                  </button>
                </div>
              )}

              <div style={{ marginBottom: 24 }}>
                <Async state={health} skeletonRows={1}>
                  {(h) => {
                    // not_configured is not a fault -- see ui.jsx TONES -- so it
                    // is counted separately rather than called out as trouble.
                    const trouble = h.checks.filter(
                      (c) => c.status !== 'healthy' && c.status !== 'not_configured');
                    const absent = h.checks.filter((c) => c.status === 'not_configured');

                    return (
                      <div className="sa-card">
                        <h4>
                          <HeartPulse size={15} /> System health
                          <Pill value={h.overall} />
                          <button className="sa-btn" style={{ marginLeft: 'auto' }}
                            onClick={() => route.go('health')}>
                            All {h.checks.length} checks
                          </button>
                        </h4>

                        {trouble.length === 0 ? (
                          <p>
                            <Check size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                            Every check that can pass is passing.
                            {absent.length > 0 && ` The headline reads "${h.overall.replace(/_/g, ' ')}" because ${absent.length} integrations report not configured — they are absent from this product by design, not down.`}
                          </p>
                        ) : (
                          <div style={{ display: 'grid', gap: 8, marginTop: 8 }}>
                            {trouble.map((c) => (
                              <div key={c.key} style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                                <Pill value={c.status} />
                                <div>
                                  <div className="sa-name">{c.label}</div>
                                  <div className="sa-owner">{c.detail}</div>
                                </div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  }}
                </Async>
              </div>

              <SectionHead title="Needs attention"
                subtitle="Suspended, unreadable, or nothing ordered in 30 days." />

              <Table
                columns={[
                  {
                    key: 'name',
                    label: 'Boutique',
                    render: (b) => (
                      <>
                        <div className="sa-name">{b.name}</div>
                        <div className="sa-owner">{b.owner_email}</div>
                        <div className="sa-schema">{b.schema_name}</div>
                      </>
                    ),
                  },
                  {
                    key: 'why',
                    label: 'Why it is listed',
                    render: (b) => b.reasons.map((r) => (
                      <span key={r.kind} style={{ marginRight: 6 }}>
                        <Pill tone={r.tone} value={r.kind} label={r.text} />
                      </span>
                    )),
                  },
                  { key: 'orders', label: 'Orders', numeric: true,
                    render: (b) => (b.healthy ? count(b.orders) : '—') },
                  { key: 'revenue', label: 'Booked', numeric: true,
                    render: (b) => (b.revenue === null ? '—' : money(b.revenue)) },
                  { key: 'last_order', label: 'Last order',
                    render: (b) => (b.last_order ? day(b.last_order) : <span className="sa-muted">never</span>) },
                ]}
                rows={attention}
                keyFor={(b) => b.schema_name}
                onRowClick={(b) => route.go(`boutiques/${b.schema_name}`)}
                empty={<Empty icon={<Check size={22} />}
                  title="Nothing needs attention."
                  detail="Every boutique is active, readable, and has taken an order in the last 30 days." />}
              />

              <div className="sa-card" style={{ marginTop: 24 }}>
                <h4><Info size={14} /> What this dashboard does not show</h4>
                <p>
                  No trials or failed payments: there is no billing and no payment gateway — an
                  order&rsquo;s <code>amount_paid</code> is typed in by staff. No request volume, error
                  rate or integration counts: nothing instruments a request. No &ldquo;users active this
                  month&rdquo;: <code>login()</code> is never called anywhere in this product, so
                  <code> User.last_login</code> is never written and every account would read as never
                  seen. Tiles for those would be zeros posing as measurements.
                </p>
                <div className="sa-section-actions" style={{ marginTop: 10 }}>
                  <button className="sa-btn" onClick={() => route.go('jobs')}>Jobs &amp; Queues</button>
                  <button className="sa-btn" onClick={() => route.go('api')}>API Monitoring</button>
                  <button className="sa-btn" onClick={() => route.go('sessions')}>Sessions &amp; Tokens</button>
                </div>
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
