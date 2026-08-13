/**
 * Every check the platform can honestly run against itself.
 *
 * Ordered worst-first and grouped, because this page is opened when something is
 * already wrong and a red row below a green one is a red row nobody reads. The
 * server ranks the same way to pick `overall` (api_views.HealthView), so the
 * banner and the first card can never disagree.
 *
 * The third group is the point of the screen. Payments, background jobs, SMS and
 * customer messaging report not_configured permanently: there is no gateway, no
 * queue, no SMS provider, and WhatsApp messages are wa.me links the owner sends
 * from their own phone on purpose (settings.CUSTOMER_MESSAGE_BACKEND is unset by
 * design). Those are grey, sit under a heading that says they are decisions, and
 * their server-written detail is rendered word for word -- summarising "sent by
 * hand by design" into "offline" is how an on-call engineer ends up hunting an
 * integration that was never built.
 */

import { useCallback } from 'react';
import { AlertTriangle, Check, Info, RefreshCw } from 'lucide-react';

import { consoleApi } from '../api';
import { Async, Pill, SectionHead, moment, useApi } from '../ui';

/** Worst first. not_configured sorts below healthy: it is a decision, not a fault. */
const RANK = { critical: 0, offline: 1, degraded: 2, warning: 3, healthy: 4, not_configured: 5 };

// An unrecognised status sorts into the attention group rather than under the
// green ones. A word this console has never seen is not evidence of health.
const rankOf = (check) => RANK[check.status] ?? 3.5;

function Group({ title, hint, icon, checks, route }) {
  if (checks.length === 0) return null;
  return (
    <div style={{ marginBottom: 24 }}>
      <SectionHead title={`${title} (${checks.length})`} subtitle={hint} />
      <div className="sa-cards">
        {checks.map((c) => (
          <div key={c.key} className="sa-card">
            <h4>
              {icon}
              {c.label}
              <span style={{ marginLeft: 'auto' }}><Pill value={c.status} /></span>
            </h4>
            {/* Verbatim from the server. Each detail was written to explain one
                specific state and loses its meaning if it is condensed. */}
            <p>{c.detail}</p>
            {c.key === 'errors' && (
              <button className="sa-btn" style={{ marginTop: 10 }}
                onClick={() => route.go('errors')}>
                Open the Error Center
              </button>
            )}
            {c.key === 'whatsapp' && (
              <button className="sa-btn" style={{ marginTop: 10 }}
                onClick={() => route.go('messaging')}>
                Open Customer Messaging
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function Health({ route }) {
  const state = useApi(useCallback(
    // The server does not stamp a time on the response, and the checks run at
    // the moment of the request -- so the browser's own clock is the honest
    // answer to "how old is this?", labelled as the time the console asked.
    () => consoleApi.health().then((d) => ({ ...d, asked_at: new Date().toISOString() })), []));

  return (
    <>
      <SectionHead
        title="System health"
        subtitle="Run on demand, when this page loads. No check sends a message, writes a row or pokes a live integration."
      >
        {state.data && <Pill value={state.data.overall} />}
        {/* Reload keeps the old cards on screen (useApi holds data through a
            refetch), so re-running does not flash the page back to skeletons. */}
        <button className="sa-btn" onClick={state.reload} disabled={state.loading}>
          <RefreshCw size={13} /> {state.loading ? 'Checking…' : 'Re-run checks'}
        </button>
      </SectionHead>

      <Async state={state} skeletonRows={6} isEmpty={(d) => d.checks.length === 0}>
        {(data) => {
          const sorted = [...data.checks].sort((a, b) => rankOf(a) - rankOf(b));
          const attention = sorted.filter((c) => rankOf(c) < RANK.healthy);
          const healthy = sorted.filter((c) => c.status === 'healthy');
          const absent = sorted.filter((c) => c.status === 'not_configured');

          return (
            <>
              {attention.length === 0 && (
                <div className="sa-note info">
                  Nothing is failing. The headline reads{' '}
                  <strong>{data.overall.replace(/_/g, ' ')}</strong>
                  {data.overall === 'not_configured'
                    ? ' only because the worst status on the page belongs to an integration this product deliberately does not have.'
                    : '.'}
                </div>
              )}

              <Group title="Needs attention" route={route}
                icon={<AlertTriangle size={15} />}
                hint="Something is wrong, slow, or could not be checked at all."
                checks={attention} />

              <Group title="Healthy" route={route}
                icon={<Check size={15} />}
                hint="Checked just now and answering."
                checks={healthy} />

              <Group title="Not configured — by design" route={route}
                icon={<Info size={15} />}
                hint="Absent from this product on purpose. Grey, not red: there is nothing here to fix."
                checks={absent} />

              <p className="sa-muted" style={{ fontSize: 12.5 }}>
                Checked {moment(data.asked_at)} · {data.checks.length} checks
              </p>
            </>
          );
        }}
      </Async>
    </>
  );
}
