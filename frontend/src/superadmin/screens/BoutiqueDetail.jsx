/**
 * One boutique, drilled into: what it is doing, and everything it holds.
 *
 * The Data half knows about no model in particular. The server derives the
 * table list and every column from Django's own introspection
 * (superadmin/datasets.py), so a model added to a tenant app appears here the
 * day it ships with nothing changed in this file -- which is the only version of
 * this screen that does not silently fall behind the product.
 *
 * Read-only, deliberately. Every rule that keeps a boutique's data correct lives
 * in that boutique's own API, and none of it would run on a write from here.
 *
 * Two columns can never arrive: auth.User.password and every authtoken row. The
 * server drops the whole token model rather than the one field, so a column
 * added to it later cannot reopen the hole, and any field whose name looks like
 * a credential comes back as bullets. The lock icon in the header says so rather
 * than leaving an administrator to wonder why a column is dots.
 */

import { useCallback, useState } from 'react';
import {
  ArrowLeft, ArrowUpRight, Database, Lock, Table2, Wrench,
} from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Empty, Pager, Pill, SearchBox, SectionHead, Stat,
  count, day, money, useApi,
} from '../ui';

/** See core.modules.is_enabled -- absent and malformed both mean ON. */
const moduleOn = (enabled, key) => {
  if (!enabled || typeof enabled !== 'object' || Array.isArray(enabled)
      || Object.keys(enabled).length === 0) return true;
  return enabled[key] !== false;
};

/**
 * One cell.
 *
 * Long text is clipped rather than allowed to set the column width: these tables
 * are as wide as the model has fields -- forty on an order -- and one notes
 * field can push every other column off the screen.
 */
function Cell({ value }) {
  if (value === null || value === undefined) return <span className="sa-muted">—</span>;
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  if (typeof value === 'object') {
    return <span className="sa-json" title={JSON.stringify(value)}>{JSON.stringify(value)}</span>;
  }
  const text = String(value);
  if (text.length > 120) {
    return <span className="sa-json" title={text}>{`${text.slice(0, 117)}…`}</span>;
  }
  return text;
}

/** A page of one table. Mounted only once a dataset is chosen, so `key` is real. */
function DataPane({ schema, dataset }) {
  const [page, setPage] = useState(1);
  const [term, setTerm] = useState('');

  const state = useApi(
    useCallback(() => consoleApi.dataset(schema, dataset.key, { page, search: term }),
                [schema, dataset.key, page, term]),
    [schema, dataset.key, page, term],
  );

  // A new search must start at page 1 or a two-page result read from page 5
  // renders as empty and looks like "no matches".
  const search = (next) => { setTerm(next); setPage(1); };

  return (
    <div className="sa-pane">
      <div className="sa-pane-head">
        <span className="sa-pane-title">{dataset.label}</span>
        <span className="sa-schema">{dataset.key}</span>
        <SearchBox value={term} onChange={search} placeholder="Search this table…" />
      </div>

      <Async
        state={state}
        isEmpty={(d) => d.rows.length === 0}
        empty={<Empty icon={<Table2 size={22} />}
          title={term ? 'Nothing in this table matches that.' : 'This table is empty.'}
          detail={term ? 'The search covers every text column the server will return.'
            : 'No rows have been written here yet.'} />}
      >
        {(data) => {
          const redacted = data.columns.filter((c) => c.redacted);
          return (
            <>
              {redacted.length > 0 && (
                <div className="sa-note info">
                  <Lock size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                  {redacted.map((c) => c.label).join(', ')} {redacted.length === 1 ? 'is' : 'are'} never
                  sent by the server. Password hashes and API tokens are replaced before the response
                  leaves the process, so there is nothing here to reveal.
                </div>
              )}

              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      {data.columns.map((column) => (
                        <th key={column.name} title={column.type}>
                          {column.redacted && (
                            <Lock size={11} style={{ verticalAlign: '-1px', marginRight: 4 }} />
                          )}
                          {column.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.rows.map((row, i) => (
                      <tr key={i}>
                        {data.columns.map((column) => (
                          <td key={column.name}><Cell value={row[column.name]} /></td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pager page={data.page} pages={data.pages} total={data.count} onPage={setPage} />
              </div>
            </>
          );
        }}
      </Async>
    </div>
  );
}

/** The table list, grouped by app, with the row counts that make it worth having. */
function DataBrowser({ schema }) {
  const [chosen, setChosen] = useState(null);
  const state = useApi(useCallback(() => consoleApi.datasets(schema), [schema]));

  return (
    <Async
      state={state}
      isEmpty={(d) => d.datasets.length === 0}
      empty={<Empty icon={<Database size={22} />} title="Nothing browsable in this schema."
        detail="Either the schema is not migrated or every model in it is excluded." />}
    >
      {(data) => {
        // Default to the first table that actually has rows: an administrator
        // opening this wants a boutique's data, not an empty pane.
        const active = chosen
          || data.datasets.find((d) => d.count > 0)
          || data.datasets[0];

        const groups = data.datasets.reduce((acc, item) => {
          (acc[item.app] = acc[item.app] || []).push(item);
          return acc;
        }, {});

        return (
          <div className="sa-split">
            <aside className="sa-side">
              {Object.entries(groups).map(([app, items]) => (
                <div key={app} className="sa-side-group">
                  <div className="sa-side-title">{app}</div>
                  {items.map((item) => (
                    <button key={item.key} className="sa-side-item"
                      aria-current={item.key === active?.key ? 'page' : undefined}
                      onClick={() => setChosen(item)}>
                      <span>{item.label}</span>
                      <span className={`sa-side-count${item.count ? '' : ' zero'}`}>
                        {/* null means the table is missing from this schema --
                            a migration not applied there, not an empty table. */}
                        {item.count === null ? '?' : count(item.count)}
                      </span>
                    </button>
                  ))}
                </div>
              ))}
            </aside>

            {active
              ? <DataPane schema={schema} dataset={active} />
              : <Empty title="Pick a table." />}
          </div>
        );
      }}
    </Async>
  );
}

/** Usage, onboarding and modules. Everything else links out. */
function Overview({ schema, route }) {
  const state = useApi(useCallback(() => consoleApi.support(schema), [schema]));

  return (
    <Async state={state} skeletonRows={6}>
      {({ boutique, usage, onboarding, modules }) => {
        const off = (modules.modules || [])
          .filter((m) => !moduleOn(boutique.enabled_modules, m.key));

        return (
          <>
            {!usage.healthy && (
              <div className="sa-note error">
                This boutique&apos;s schema could not be read, so the figures below are blank rather
                than zero. A missing or half-migrated schema is an engineering repair, not a quiet
                boutique.
              </div>
            )}

            <div className="sa-stats">
              <Stat label="Staff" value={count(usage.staff)} />
              <Stat label="Customers" value={count(usage.customers)} />
              <Stat label="Orders" value={count(usage.orders)}
                note={`${count(usage.open_orders)} still open`} />
              <Stat label="Booked" value={usage.revenue === null ? '—' : money(usage.revenue)}
                note="Sum of order totals" />
              <Stat label="Collected" value={usage.collected === null ? '—' : money(usage.collected)}
                note="Sum of amounts actually paid" />
              <Stat label="Last order" value={usage.last_order ? day(usage.last_order) : '—'} />
            </div>

            <div className="sa-cards">
              <div className="sa-card">
                <h4>Onboarding</h4>
                {onboarding.readable ? (
                  <>
                    <p style={{ marginBottom: 8 }}>
                      <strong>{onboarding.percent}%</strong> — {onboarding.percent_basis}
                    </p>
                    <div className="sa-meter">
                      <span style={{ width: `${onboarding.percent}%` }} />
                    </div>
                    {onboarding.blocked_on ? (
                      <div style={{ marginTop: 10 }}>
                        <div className="sa-name">Waiting on: {onboarding.blocked_on.label}</div>
                        <p>{onboarding.blocked_on.detail}</p>
                      </div>
                    ) : <p style={{ marginTop: 10 }}>Nothing outstanding.</p>}
                    <button className="sa-btn" style={{ marginTop: 10 }}
                      onClick={() => route.go('onboarding')}>
                      Full checklist <ArrowUpRight size={13} />
                    </button>
                  </>
                ) : <p>{onboarding.detail}</p>}
              </div>

              <div className="sa-card">
                <h4>Modules</h4>
                {off.length === 0 ? (
                  <p>
                    Every switchable module is on. A key absent from the stored map counts as on,
                    which is what the middleware does — see core.modules.is_enabled.
                  </p>
                ) : (
                  <>
                    <p style={{ marginBottom: 8 }}>
                      Switched off, so this boutique&apos;s staff are refused those URLs outright:
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
                <h4><Wrench size={14} /> Going further</h4>
                <p>
                  Errors, the audit trail and every account in this boutique are on the Diagnostics
                  screen, which fetches them in the same request as the figures above.
                </p>
                <button className="sa-btn" style={{ marginTop: 10 }}
                  onClick={() => route.go(`support/${schema}`)}>
                  Diagnostics <ArrowUpRight size={13} />
                </button>
              </div>
            </div>
          </>
        );
      }}
    </Async>
  );
}

export default function BoutiqueDetail({ route }) {
  const schema = route.parts[1];
  const tab = route.parts[2] === 'data' ? 'data' : 'overview';

  if (!schema) {
    return <Empty title="No boutique named in the address."
      detail="Open one from the boutiques list."
      action={<button className="sa-btn" onClick={() => route.go('boutiques')}>Boutiques</button>} />;
  }

  return (
    <>
      <button className="sa-link" style={{ marginBottom: 12, display: 'inline-flex', gap: 6 }}
        onClick={() => route.go('boutiques')}>
        <ArrowLeft size={14} /> All boutiques
      </button>

      <SectionHead
        title={schema}
        subtitle={tab === 'overview'
          // Said plainly: /support/ writes a data.view row, and this tab calls it.
          ? 'Usage, onboarding and modules. Opening this records a data.view entry in the audit log against your account.'
          : "Every table in this boutique's schema, read live. Read-only — the rules that keep this data correct live in the boutique's own API."}
      >
        <div className="sa-tabs">
          <button className="sa-tab" aria-current={tab === 'overview' ? 'page' : undefined}
            onClick={() => route.go(`boutiques/${schema}`)}>
            Overview
          </button>
          <button className="sa-tab" aria-current={tab === 'data' ? 'page' : undefined}
            onClick={() => route.go(`boutiques/${schema}/data`)}>
            <Database size={13} style={{ verticalAlign: '-2px', marginRight: 5 }} />
            Data
          </button>
        </div>
      </SectionHead>

      {tab === 'overview'
        ? <Overview key={schema} schema={schema} route={route} />
        : <DataBrowser key={schema} schema={schema} />}
    </>
  );
}
