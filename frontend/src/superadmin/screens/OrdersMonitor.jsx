/**
 * What every boutique's order book is doing right now.
 *
 * The distribution panels are plain divs with a width, not a chart. This
 * project's dependencies are react, react-dom and lucide-react, and a
 * proportional bar is one CSS rule -- .sa-meter, already in the stylesheet for
 * the onboarding screen.
 *
 * The overdue count is the one number on this page that cannot be shown on its
 * own. superadmin/metrics.py ships a `caveat` string beside it precisely so the
 * frontend cannot render it bare: estimated_delivery defaults to order_date+15
 * days, so the count includes dates the system invented alongside dates a
 * boutique actually promised. It is an upper bound, and a console that prints
 * "14 overdue" without saying so has someone ringing customers about deadlines
 * nobody ever agreed to.
 *
 * Filtering is in the browser because the API returns every boutique in one
 * payload -- the server has already paid for the schema switches, and a second
 * request per filter would pay for them again.
 */

import { useCallback, useMemo, useState } from 'react';
import { AlertTriangle, MessageSquare, ShoppingBag } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Empty, Pill, SearchBox, SectionHead, Select, Stat, count, useApi,
} from '../ui';

/**
 * One bucket map as labelled bars.
 *
 * Zero-count buckets are kept, not filtered out: superadmin/metrics.py seeds the
 * known statuses so the panel's shape does not change as orders move, and a
 * column that vanishes when it hits zero is a column nobody can trust.
 */
function Breakdown({ title, counts, note }) {
  const entries = Object.entries(counts || {})
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const total = entries.reduce((n, [, value]) => n + value, 0);

  return (
    <div className="sa-card">
      <h4>{title}</h4>
      {note && <p style={{ marginBottom: 10 }}>{note}</p>}
      {entries.length === 0 ? (
        <p className="sa-muted">No orders to distribute.</p>
      ) : (
        <dl className="sa-kv" style={{ gridTemplateColumns: 'minmax(110px, max-content) 1fr 46px' }}>
          {entries.map(([label, value]) => (
            <div key={label} style={{ display: 'contents' }}>
              <dt>{label || <span className="sa-muted">(none)</span>}</dt>
              <dd style={{ alignSelf: 'center' }}>
                <div className="sa-meter" style={{ marginTop: 0 }}>
                  <span style={{ width: total ? `${(100 * value) / total}%` : '0%' }} />
                </div>
              </dd>
              <dd className="sa-num" style={{ textAlign: 'right' }}>{count(value)}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

export default function OrdersMonitor({ route }) {
  const [term, setTerm] = useState('');
  const [status, setStatus] = useState('all');

  const state = useApi(useCallback(() => consoleApi.ordersMonitor(), []));

  const rows = useMemo(() => {
    if (!state.data) return [];
    const needle = term.trim().toLowerCase();
    return state.data.boutiques.filter((b) => {
      if (status === 'active' && !b.is_active) return false;
      if (status === 'suspended' && b.is_active) return false;
      if (status === 'unreadable' && b.healthy) return false;
      if (status === 'overdue' && !(b.overdue?.count > 0)) return false;
      if (status === 'queued' && !(b.queued_messages > 0)) return false;
      if (!needle) return true;
      return `${b.name} ${b.schema_name}`.toLowerCase().includes(needle);
    });
  }, [state.data, term, status]);

  return (
    <>
      <SectionHead
        title="Orders Monitor"
        subtitle="Aggregates only — the console can see that orders are piling up at a stage without reading anybody's order book."
      />

      <Async
        state={state}
        isEmpty={(d) => d.boutiques.length === 0}
        empty={<Empty icon={<ShoppingBag size={22} />} title="No boutiques on the platform yet."
          detail="Order figures appear here once a boutique signs up." />}
      >
        {(data) => {
          const totals = data.totals || {};
          const unreadable = data.boutiques.filter((b) => !b.healthy);
          // Every boutique carries the same server-side sentence; the first one
          // that has it is the platform's copy.
          const caveat = data.boutiques.find((b) => b.overdue?.caveat)?.overdue.caveat;

          return (
            <>
              <div className="sa-stats">
                <Stat label="Orders" value={count(totals.orders)} />
                <Stat label="Overdue" value={count(totals.overdue)} tone={totals.overdue ? 'warn' : undefined}
                  note="Upper bound — read the note below" />
                <Stat label="Queued messages" value={count(totals.queued_messages)}
                  note="Waiting to be sent by hand"
                  onClick={() => route.go('messaging')} />
                <Stat label="Boutiques" value={data.boutiques.length}
                  note={`${data.boutiques.filter((b) => b.is_active).length} active`} />
              </div>

              {caveat && (
                <div className="sa-note info">
                  <AlertTriangle size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                  <strong>Overdue is an upper bound.</strong> {caveat}
                </div>
              )}

              {unreadable.length > 0 && (
                <div className="sa-note error">
                  {unreadable.length} boutique schema(s) could not be read, so every total on this
                  page excludes them: {unreadable.map((b) => b.name).join(', ')}.
                </div>
              )}

              <SectionHead title="Across the platform"
                subtitle="Every readable boutique's orders, however this page is filtered below." />
              <div className="sa-cards" style={{ marginBottom: 28 }}>
                <Breakdown title="Order status" counts={totals.by_order_status} />
                <Breakdown title="Payment status" counts={totals.by_payment_status}
                  note="Recorded by hand against the order. There is no payment gateway in this product." />
                <Breakdown title="Production status" counts={totals.by_production_status} />
                <Breakdown title="Current stage" counts={totals.by_stage}
                  note="Stage keys come from the workflow definition, so this list is open-ended." />
              </div>

              <SectionHead title="By boutique">
                <SearchBox value={term} onChange={setTerm} placeholder="Name or schema…" />
                <Select value={status} onChange={setStatus} label="Show" options={[
                  { value: 'all', label: 'All boutiques' },
                  { value: 'overdue', label: 'Has overdue orders' },
                  { value: 'queued', label: 'Has queued messages' },
                  { value: 'active', label: 'Active' },
                  { value: 'suspended', label: 'Suspended' },
                  { value: 'unreadable', label: 'Unreadable' },
                ]} />
              </SectionHead>

              {rows.length === 0 ? (
                <Empty title="No boutique matches those filters."
                  detail="Clear the search or widen the filter." />
              ) : (
                <div className="sa-table-wrap">
                  <table className="sa-table">
                    <thead>
                      <tr>
                        <th>Boutique</th>
                        <th className="sa-num">Orders</th>
                        <th className="sa-num">Today</th>
                        <th className="sa-num">This week</th>
                        <th className="sa-num">This month</th>
                        <th className="sa-num">Overdue<sup>*</sup></th>
                        <th className="sa-num">Queued messages</th>
                        <th>Busiest stage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((b) => {
                        const stages = Object.entries(b.by_stage || {})
                          .sort((x, y) => y[1] - x[1]);
                        const busiest = stages.find(([, n]) => n > 0);
                        return (
                          <tr key={b.schema_name} className={b.is_active ? '' : 'sa-suspended'}>
                            <td>
                              <button className="sa-link"
                                onClick={() => route.go(`boutiques/${b.schema_name}`)}>
                                {b.name}
                              </button>
                              <div className="sa-schema">{b.schema_name}</div>
                              {!b.healthy && (
                                <Pill value="warning" label="Unreadable" />
                              )}
                            </td>
                            <td className="sa-num">{count(b.orders)}</td>
                            <td className="sa-num">{count(b.created?.today)}</td>
                            <td className="sa-num">{count(b.created?.week)}</td>
                            <td className="sa-num">{count(b.created?.month)}</td>
                            <td className="sa-num">
                              {b.overdue?.count ? (
                                <span style={{ color: 'var(--warn-color)', fontWeight: 600 }}>
                                  {count(b.overdue.count)}
                                </span>
                              ) : count(b.overdue?.count)}
                            </td>
                            <td className="sa-num">
                              {b.queued_messages ? (
                                <button className="sa-link" onClick={() => route.go('messaging')}>
                                  {count(b.queued_messages)}
                                </button>
                              ) : count(b.queued_messages)}
                            </td>
                            <td>
                              {busiest
                                ? <>{busiest[0]} <span className="sa-muted">({count(busiest[1])})</span></>
                                : <span className="sa-muted">—</span>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <div className="sa-pager">
                    <span className="sa-muted">
                      <sup>*</sup> Overdue counts system-generated delivery dates as well as promised
                      ones — see the note above.
                    </span>
                  </div>
                </div>
              )}

              <div className="sa-note info" style={{ marginTop: 18 }}>
                <MessageSquare size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                Queued messages are not a stuck queue. Nothing sends them automatically by design —
                see Customer Messaging.
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
