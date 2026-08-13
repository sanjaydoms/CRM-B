/**
 * The customer-message backlog -- the one real queue in this product.
 *
 * There is no worker and no sender. CUSTOMER_MESSAGE_BACKEND is unset by design
 * (the comment above it in settings.py is the reasoning: the WhatsApp Business
 * API needs a Meta Business account per boutique and pre-approved templates,
 * while a wa.me link costs nothing and goes out from the number the customer
 * already knows). So rows pile up in each boutique's CustomerMessage table with
 * status QUEUED until the owner opens the order and taps send on their own
 * phone.
 *
 * That makes a large backlog a person who has stopped sending messages, not a
 * broken integration -- which is why this screen ranks boutiques by depth and
 * says the design decision out loud, in the server's own words, rather than
 * painting a red light.
 *
 * No threshold turns a number amber here. Any "50 is a lot" would be invented in
 * this file and would be the only place on the platform that believed it; the
 * bar shows each boutique's share of the backlog, which is measured.
 */

import { useCallback } from 'react';
import { MessageSquare, Send } from 'lucide-react';

import { consoleApi } from '../api';
import { Async, Empty, Pill, SectionHead, Stat, count, useApi } from '../ui';

export default function Messaging({ route }) {
  const state = useApi(useCallback(
    () => Promise.all([consoleApi.ordersMonitor(), consoleApi.health()])
      .then(([orders, health]) => ({ orders, health })),
    [],
  ));

  return (
    <>
      <SectionHead
        title="Customer Messaging"
        subtitle="Messages queue in each boutique's own schema and are sent by hand. This is the backlog waiting on somebody's phone."
      />

      <Async
        state={state}
        isEmpty={({ orders }) => orders.boutiques.length === 0}
        empty={<Empty icon={<MessageSquare size={22} />} title="No boutiques on the platform yet."
          detail="A messaging backlog appears here once a boutique starts taking orders." />}
      >
        {({ orders, health }) => {
          const whatsapp = (health.checks || []).find((c) => c.key === 'whatsapp');
          const totals = orders.totals || {};
          const unreadable = orders.boutiques.filter((b) => !b.healthy);

          // Largest first. A boutique whose schema could not be read reports
          // null rather than 0 and sorts to the bottom, because "nobody is
          // sending" and "we could not count" are different findings.
          const rows = [...orders.boutiques]
            .sort((a, b) => (b.queued_messages ?? -1) - (a.queued_messages ?? -1));
          const deepest = rows[0]?.queued_messages || 0;
          const withBacklog = rows.filter((b) => b.queued_messages > 0);

          return (
            <>
              <div className="sa-stats">
                <Stat label="Queued, platform-wide" value={count(totals.queued_messages)}
                  note="Written, never sent" />
                <Stat label="Boutiques with a backlog" value={withBacklog.length}
                  note={`of ${orders.boutiques.length}`} />
                <Stat label="Deepest single backlog" value={count(deepest)}
                  note={rows[0]?.queued_messages ? rows[0].name : undefined} />
              </div>

              {/* The health check's own sentence, verbatim: it carries both the
                  design decision and the note about schemas it could not read. */}
              {whatsapp && (
                <div className="sa-note info">
                  <Send size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                  <strong>Nothing sends these automatically, and that is deliberate.</strong>{' '}
                  {whatsapp.detail}
                </div>
              )}

              {unreadable.length > 0 && (
                <div className="sa-note error">
                  {unreadable.length} boutique schema(s) could not be read, so the platform total
                  is a floor rather than the real backlog: {unreadable.map((b) => b.name).join(', ')}.
                </div>
              )}

              <SectionHead title="Backlog by boutique"
                subtitle="Deepest first. The bar is each boutique's share of the largest backlog, not of a target." />

              {withBacklog.length === 0 ? (
                <Empty icon={<MessageSquare size={22} />} title="Nothing is waiting to be sent."
                  detail="Every queued customer message has been marked sent, or no order has generated one yet." />
              ) : (
                <div className="sa-table-wrap">
                  <table className="sa-table">
                    <thead>
                      <tr>
                        <th>Boutique</th>
                        <th className="sa-num">Queued</th>
                        <th style={{ width: '40%' }}>Share of the deepest backlog</th>
                        <th className="sa-num">Orders</th>
                        <th />
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((b) => (
                        <tr key={b.schema_name} className={b.is_active ? '' : 'sa-suspended'}>
                          <td>
                            <button className="sa-link"
                              onClick={() => route.go(`boutiques/${b.schema_name}`)}>
                              {b.name}
                            </button>
                            <div className="sa-schema">{b.schema_name}</div>
                            {!b.is_active && <Pill value="suspended" />}
                          </td>
                          <td className="sa-num">
                            {b.healthy ? count(b.queued_messages)
                              : <Pill value="warning" label="Unreadable" />}
                          </td>
                          <td>
                            {b.healthy && deepest > 0 && (
                              <div className="sa-meter" style={{ marginTop: 0 }}>
                                <span style={{ width: `${(100 * (b.queued_messages || 0)) / deepest}%` }} />
                              </div>
                            )}
                          </td>
                          <td className="sa-num">{count(b.orders)}</td>
                          <td className="sa-actions">
                            <button className="sa-btn"
                              onClick={() => route.go(`support/${b.schema_name}`)}>
                              Diagnose
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <div className="sa-cards" style={{ marginTop: 22 }}>
                <div className="sa-card">
                  <h4>There is no send button here</h4>
                  <p>
                    The console cannot send these. A message goes out as a wa.me link from the
                    boutique owner&apos;s own WhatsApp, opened from the order in their workspace —
                    the platform has no number to send from and no template approval to send under.
                    A button here would either do nothing or forge a message from a boutique.
                  </p>
                </div>
                <div className="sa-card">
                  <h4>What a large backlog means</h4>
                  <p>
                    Rows queue themselves on order events, so their existence proves nothing. Only
                    the QUEUED count above is outstanding work, and the person who has to clear it
                    is the owner of that boutique, not anyone on this console.
                  </p>
                </div>
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
