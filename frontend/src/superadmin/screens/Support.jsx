/**
 * One boutique, everything a support call needs, on one page.
 *
 * The server assembles this in a single request rather than the console firing
 * six, because it is opened while somebody is on the phone. It also records a
 * `data.view` audit entry every time it is opened -- the console reaching into
 * one customer's data is exactly the access an audit trail exists to make
 * reviewable -- which is why nothing here loads until a boutique is chosen, and
 * why the subtitle says so. A person should know when their own use of a tool is
 * being written down.
 *
 * Every section ends in a link rather than an action. Suspending a boutique,
 * switching a module, resolving an error and deactivating a user all live on
 * screens that already do them properly, with their own confirmations and their
 * own audit reasons. A second copy here would be a second set of rules to keep
 * in step.
 */

import { useCallback } from 'react';
import {
  AlertTriangle, ArrowUpRight, Building2, ScrollText, Users, Wrench,
} from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Empty, Pill, SectionHead, Select, Stat,
  count, day, money, moment, useApi,
} from '../ui';

/**
 * Mirrors core.modules.is_enabled exactly, including its two odd cases.
 *
 * An absent key means ON (a tenant row written before a module existed has no
 * opinion, and no opinion must not read as off), and a malformed column -- the
 * field is a JSONField editable as free text in the Django admin -- also reads
 * as on, because that is what the middleware will actually do. Guessing
 * differently here would show a switch as off while every request sails through.
 */
const moduleOn = (enabled, key) => {
  if (!enabled || typeof enabled !== 'object' || Array.isArray(enabled)
      || Object.keys(enabled).length === 0) return true;
  return enabled[key] !== false;
};

function Picker({ value, onChange }) {
  const state = useApi(useCallback(() => consoleApi.overview(), []));
  return (
    <Async state={state} skeletonRows={1}>
      {(data) => (
        <Select value={value} onChange={onChange} label="Boutique" options={[
          { value: '', label: 'Choose a boutique…' },
          ...data.boutiques.map((b) => ({
            value: b.schema_name,
            label: b.is_active ? b.name : `${b.name} (suspended)`,
          })),
        ]} />
      )}
    </Async>
  );
}

function Diagnostics({ schema, route }) {
  const state = useApi(useCallback(() => consoleApi.support(schema), [schema]));

  return (
    <Async state={state} skeletonRows={8}>
      {(data) => {
        const { boutique, usage, operations, onboarding, users, errors, audit, modules } = data;
        const off = (modules.modules || [])
          .filter((m) => !moduleOn(boutique.enabled_modules, m.key));

        return (
          <>
            <SectionHead title={boutique.name}
              subtitle={`${boutique.owner_email} · ${boutique.schema_name} · signed up ${day(boutique.created_on)}`}>
              <Pill value={boutique.is_active ? 'active' : 'suspended'} />
              <button className="sa-btn" onClick={() => route.go(`boutiques/${schema}`)}>
                Open boutique <ArrowUpRight size={13} />
              </button>
            </SectionHead>

            {!usage.healthy && (
              <div className="sa-note error">
                This boutique&apos;s schema could not be read, so every usage figure below is blank
                rather than zero. That is a missing or half-migrated schema — an engineering repair,
                not a boutique that has done nothing.
              </div>
            )}

            <div className="sa-stats">
              <Stat label="Staff" value={count(usage.staff)} />
              <Stat label="Customers" value={count(usage.customers)} />
              <Stat label="Orders" value={count(usage.orders)}
                note={`${count(usage.open_orders)} still open`} />
              <Stat label="Booked" value={usage.revenue === null ? '—' : money(usage.revenue)} />
              <Stat label="Collected" value={usage.collected === null ? '—' : money(usage.collected)} />
              <Stat label="Last order" value={usage.last_order ? day(usage.last_order) : '—'} />
            </div>

            <div className="sa-cards" style={{ marginBottom: 24 }}>
              <div className="sa-card">
                <h4><Wrench size={14} /> Onboarding</h4>
                {onboarding.readable ? (
                  <>
                    <p style={{ marginBottom: 8 }}>
                      <strong>{onboarding.percent}%</strong> — {onboarding.percent_basis}
                    </p>
                    <div className="sa-meter">
                      <span style={{ width: `${onboarding.percent}%` }} />
                    </div>
                    <div style={{ marginTop: 10 }}>
                      {onboarding.blocked_on ? (
                        <>
                          <div className="sa-name">Waiting on: {onboarding.blocked_on.label}</div>
                          <p>{onboarding.blocked_on.detail}</p>
                        </>
                      ) : <p>Nothing outstanding.</p>}
                    </div>
                    <button className="sa-btn" style={{ marginTop: 10 }}
                      onClick={() => route.go('onboarding')}>
                      Full checklist <ArrowUpRight size={13} />
                    </button>
                  </>
                ) : (
                  <p>{onboarding.detail}</p>
                )}
              </div>

              <div className="sa-card">
                <h4>Modules</h4>
                {off.length === 0 ? (
                  <p>
                    Every switchable module is on. Absent keys count as on — see
                    core.modules.is_enabled.
                  </p>
                ) : (
                  <>
                    <p style={{ marginBottom: 8 }}>
                      {off.length} module(s) are switched off, so this boutique&apos;s staff get a 403
                      on those URLs and any onboarding step behind them is excluded from its
                      percentage rather than counted as failed:
                    </p>
                    <div>
                      {off.map((m) => (
                        <span key={m.key} style={{ marginRight: 6 }}>
                          <Pill value="disabled" label={m.label} />
                        </span>
                      ))}
                    </div>
                  </>
                )}
                <button className="sa-btn" style={{ marginTop: 10 }}
                  onClick={() => route.go('modules')}>
                  Change modules <ArrowUpRight size={13} />
                </button>
              </div>

              <div className="sa-card">
                <h4>Order operations</h4>
                <dl className="sa-kv">
                  <dt>Orders</dt><dd>{count(operations.orders)}</dd>
                  <dt>Created today</dt><dd>{count(operations.created?.today)}</dd>
                  <dt>Overdue</dt><dd>{count(operations.overdue?.count)}</dd>
                  <dt>Queued messages</dt><dd>{count(operations.queued_messages)}</dd>
                </dl>
                {/* The caveat travels with the number from superadmin/metrics.py
                    so that no screen can print the count on its own. */}
                {operations.overdue?.caveat && (
                  <p style={{ marginTop: 8 }}>
                    <strong>Overdue is an upper bound.</strong> {operations.overdue.caveat}
                  </p>
                )}
                <button className="sa-btn" style={{ marginTop: 10 }}
                  onClick={() => route.go('orders')}>
                  Orders monitor <ArrowUpRight size={13} />
                </button>
              </div>
            </div>

            <SectionHead title="Recent errors"
              subtitle="Server exceptions captured for this boutique, newest first.">
              <button className="sa-btn" onClick={() => route.go('errors')}>
                Error Center <ArrowUpRight size={13} />
              </button>
            </SectionHead>
            {errors.length === 0 ? (
              <Empty icon={<AlertTriangle size={22} />} title="No errors recorded for this boutique."
                detail="Unhandled server exceptions would appear here with a count and a fingerprint." />
            ) : (
              <div className="sa-table-wrap" style={{ marginBottom: 24 }}>
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th>Exception</th><th>Path</th><th className="sa-num">Seen</th>
                      <th>Severity</th><th>Status</th><th>Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {errors.map((e) => (
                      <tr key={e.id}>
                        <td className="sa-name">{e.exception_type}</td>
                        <td className="sa-schema">{e.path}</td>
                        <td className="sa-num">{count(e.count)}</td>
                        <td><Pill value={e.severity} /></td>
                        <td><Pill value={e.status} /></td>
                        <td className="sa-schema" style={{ whiteSpace: 'nowrap' }}>{moment(e.last_seen)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <SectionHead title="Accounts"
              subtitle={users.last_login_tracked ? undefined
                : 'Last sign-in is not recorded anywhere in this product, so there is no column for it.'}>
              <button className="sa-btn" onClick={() => route.go('users')}>
                All users <ArrowUpRight size={13} />
              </button>
            </SectionHead>
            {users.users.length === 0 ? (
              <Empty icon={<Users size={22} />} title="No accounts could be read in this boutique." />
            ) : (
              <div className="sa-table-wrap" style={{ marginBottom: 24 }}>
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th>Username</th><th>Name</th><th>Email</th><th>Role</th>
                      <th>Status</th><th>Token</th><th>Joined</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.users.map((u) => (
                      <tr key={u.username} className={u.is_active ? '' : 'sa-suspended'}>
                        <td className="sa-name">{u.username}</td>
                        <td>{`${u.first_name} ${u.last_name}`.trim() || <span className="sa-muted">—</span>}</td>
                        <td>{u.email || <span className="sa-muted">—</span>}</td>
                        <td>{u.role}</td>
                        <td><Pill value={u.is_active ? 'active' : 'disabled'} /></td>
                        {/* Whether a token exists, never which token it is. */}
                        <td>{u.has_token
                          ? <Pill value="active" label="Signed in" />
                          : <span className="sa-muted">none</span>}</td>
                        <td className="sa-schema" style={{ whiteSpace: 'nowrap' }}>{day(u.date_joined)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <SectionHead title="What the console has done here"
              subtitle="Every administrator action recorded against this boutique, newest first.">
              <button className="sa-btn" onClick={() => route.go('audit')}>
                Audit log <ArrowUpRight size={13} />
              </button>
            </SectionHead>
            {audit.length === 0 ? (
              <Empty icon={<ScrollText size={22} />} title="Nothing has been done to this boutique."
                detail="Suspensions, module changes and account actions are recorded here with the reason typed at the time." />
            ) : (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th>When</th><th>Who</th><th>What</th><th>Target</th><th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {audit.map((a, i) => (
                      <tr key={`${a.created_at}-${i}`}>
                        <td className="sa-schema" style={{ whiteSpace: 'nowrap' }}>{moment(a.created_at)}</td>
                        <td>{a.actor}</td>
                        <td>{a.action_label}</td>
                        <td className="sa-schema">{a.target}</td>
                        <td style={{ maxWidth: 340 }}>
                          {a.reason || <span className="sa-muted">— none given</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        );
      }}
    </Async>
  );
}

export default function Support({ route }) {
  const schema = route.parts[1] || '';

  return (
    <>
      <SectionHead
        title="Diagnostics"
        subtitle="Everything about one boutique in a single request. Opening this records a data.view entry in the audit log against your account — reaching into a customer's data is meant to leave a trace."
      >
        <Picker value={schema}
          onChange={(next) => route.go(next ? `support/${next}` : 'support')} />
      </SectionHead>

      {schema
        ? <Diagnostics key={schema} schema={schema} route={route} />
        : <Empty icon={<Building2 size={22} />} title="Choose a boutique."
            detail="Nothing is fetched until you do, because fetching writes an audit entry against the boutique you look at." />}
    </>
  );
}
