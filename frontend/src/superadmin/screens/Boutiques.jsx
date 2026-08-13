/**
 * Every boutique on the platform, with its live figures.
 *
 * The counts are read from inside each boutique's own Postgres schema, which is
 * why nothing here can be sorted or filtered by the server: they are not columns
 * in the table being listed. Sorting and searching therefore happen in the
 * browser over an already-complete list, which is honest at the tens of
 * boutiques this product has. Past a few hundred the list itself needs
 * server-side paging and the counts need a rollup table -- the server says the
 * same thing in superadmin/metrics.py.
 */

import { useCallback, useMemo, useState } from 'react';
import { Building2, Database, Pause, Play } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Confirm, Empty, Pill, SearchBox, SectionHead, Select, Stat,
  count, day, money, since, useApi, useToast,
} from '../ui';

const SORTS = [
  { value: 'name', label: 'Name' },
  { value: 'orders', label: 'Orders' },
  { value: 'revenue', label: 'Order value' },
  { value: 'customers', label: 'Customers' },
  { value: 'last_order', label: 'Last order' },
  { value: 'created_on', label: 'Signed up' },
];

export default function Boutiques({ route }) {
  const toast = useToast();
  const [term, setTerm] = useState('');
  const [status, setStatus] = useState('all');
  const [sort, setSort] = useState('name');
  const [pending, setPending] = useState(null);

  const state = useApi(useCallback(() => consoleApi.overview(), []));

  const rows = useMemo(() => {
    if (!state.data) return [];
    const needle = term.trim().toLowerCase();
    return state.data.boutiques
      .filter((b) => {
        if (status === 'active' && !b.is_active) return false;
        if (status === 'suspended' && b.is_active) return false;
        if (status === 'unreadable' && b.healthy) return false;
        if (!needle) return true;
        return `${b.name} ${b.owner_email} ${b.schema_name}`.toLowerCase().includes(needle);
      })
      .sort((a, b) => {
        if (sort === 'name') return a.name.localeCompare(b.name);
        if (sort === 'created_on') return String(b.created_on).localeCompare(String(a.created_on));
        if (sort === 'last_order') return String(b.last_order || '').localeCompare(String(a.last_order || ''));
        return (b[sort] || 0) - (a[sort] || 0);
      });
  }, [state.data, term, status, sort]);

  const apply = async (reason) => {
    const { boutique, next } = pending;
    try {
      await (next ? consoleApi.reactivate : consoleApi.suspend)(boutique.schema_name, reason);
      toast(`${boutique.name} ${next ? 'reactivated' : 'suspended'}.`);
      setPending(null);
      state.reload();
    } catch (e) {
      toast(e.message, 'off');
      setPending(null);
    }
  };

  return (
    <>
      <Async
        state={state}
        isEmpty={(d) => d.boutiques.length === 0}
        empty={<Empty icon={<Building2 size={22} />} title="No boutiques have signed up yet." />}
      >
        {(data) => (
          <>
            <div className="sa-stats">
              <Stat label="Boutiques" value={count(data.totals.boutiques)}
                note={`${data.totals.active} active · ${data.totals.suspended} suspended`} />
              <Stat label="Staff accounts" value={count(data.totals.staff)} />
              <Stat label="Customers" value={count(data.totals.customers)} />
              <Stat label="Orders" value={count(data.totals.orders)}
                note={`${count(data.totals.open_orders)} still open`} />
              <Stat label="Booked" value={money(data.totals.revenue)}
                note="Sum of order totals" />
              <Stat label="Collected" value={money(data.totals.collected)}
                note="Sum of amounts actually paid" />
            </div>

            {data.totals.unreadable > 0 && (
              <div className="sa-note error">
                {data.totals.unreadable} boutique schema(s) could not be read, so the totals
                above exclude them. They are marked <em>Unreadable</em> below.
              </div>
            )}

            <SectionHead title="Boutiques"
              subtitle="Counts are read live from each boutique's own schema.">
              <SearchBox value={term} onChange={setTerm} placeholder="Name, owner or schema…" />
              <Select value={status} onChange={setStatus} label="Status" options={[
                { value: 'all', label: 'All statuses' },
                { value: 'active', label: 'Active' },
                { value: 'suspended', label: 'Suspended' },
                { value: 'unreadable', label: 'Unreadable' },
              ]} />
              <Select value={sort} onChange={setSort} label="Sort by"
                options={SORTS.map((s) => ({ value: s.value, label: `Sort: ${s.label}` }))} />
            </SectionHead>

            {rows.length === 0 ? (
              <Empty title="No boutique matches those filters."
                detail="Clear the search or widen the status filter." />
            ) : (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th>Boutique</th><th>Status</th>
                      <th className="sa-num">Staff</th><th className="sa-num">Customers</th>
                      <th className="sa-num">Orders</th><th className="sa-num">Open</th>
                      <th className="sa-num">Booked</th><th className="sa-num">Collected</th>
                      <th>Last order</th><th className="sa-sticky-end" />
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((b) => {
                      const last = since(b.last_order);
                      return (
                        <tr key={b.schema_name} className={b.is_active ? '' : 'sa-suspended'}>
                          <td>
                            <button className="sa-link"
                              onClick={() => route.go(`boutiques/${b.schema_name}`)}>
                              {b.name}
                            </button>
                            <div className="sa-owner">{b.owner_email}</div>
                            <div className="sa-schema">{b.schema_name}</div>
                          </td>
                          <td>
                            <Pill value={b.is_active ? 'active' : 'suspended'} />
                            {!b.healthy && (
                              <span style={{ marginLeft: 6 }}><Pill value="warning" label="Unreadable" /></span>
                            )}
                          </td>
                          <td className="sa-num">{count(b.staff)}</td>
                          <td className="sa-num">{count(b.customers)}</td>
                          <td className="sa-num">{count(b.orders)}</td>
                          <td className="sa-num">{count(b.open_orders)}</td>
                          <td className="sa-num">{b.revenue === null ? '—' : money(b.revenue)}</td>
                          <td className="sa-num">{b.collected === null ? '—' : money(b.collected)}</td>
                          <td>
                            <Pill value={last.tone === 'ok' ? 'healthy' : 'warning'} label={last.text} />
                            {b.last_order && <div className="sa-schema">{day(b.last_order)}</div>}
                          </td>
                          <td className="sa-actions sa-sticky-end">
                            <button className="sa-btn"
                              onClick={() => route.go(`boutiques/${b.schema_name}/data`)}>
                              <Database size={13} /> Data
                            </button>
                            <button className={`sa-btn ${b.is_active ? 'danger' : ''}`}
                              style={{ marginLeft: 6 }}
                              onClick={() => setPending({ boutique: b, next: !b.is_active })}>
                              {b.is_active ? <><Pause size={13} /> Suspend</> : <><Play size={13} /> Reactivate</>}
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Async>

      <Confirm
        open={Boolean(pending)}
        danger={pending && !pending.next}
        requireReason
        title={pending && (pending.next ? `Reactivate ${pending.boutique.name}?` : `Suspend ${pending.boutique.name}?`)}
        body={pending && (pending.next
          ? 'Their team can sign in again straight away. Nothing else changes.'
          : 'Everyone there is signed out of the app and the API until you reactivate it. No data is deleted, and reactivating restores the boutique exactly as it was.')}
        confirmLabel={pending && (pending.next ? 'Reactivate' : 'Suspend')}
        onCancel={() => setPending(null)}
        onConfirm={apply}
      />
    </>
  );
}
