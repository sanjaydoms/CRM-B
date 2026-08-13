/**
 * Demo requests from the marketing site.
 *
 * Status and notes are the only writable fields, matching the server: everything
 * else on a lead was typed by a stranger and is the evidence of what they
 * actually sent, so a careless PATCH must not be able to rewrite it. The server
 * enforces that (LeadSerializer.read_only_fields); this screen simply does not
 * offer the inputs.
 */

import { useCallback, useState } from 'react';
import { Check, Mail } from 'lucide-react';

import { consoleApi } from '../api';
import { Async, Empty, Pill, SectionHead, day, useApi, useToast } from '../ui';

const STATUSES = ['NEW', 'CONTACTED', 'QUALIFIED', 'CONVERTED', 'DECLINED'];

export default function Leads() {
  const toast = useToast();
  const [saving, setSaving] = useState(null);
  const [saved, setSaved] = useState(null);

  const state = useApi(useCallback(() => consoleApi.leads(), []));

  const save = async (lead, fields) => {
    setSaving(lead.id);
    try {
      const updated = await consoleApi.updateLead(lead.id, fields);
      // Patch in place rather than refetching: the administrator is working
      // down a list and a reload would jump them back to the top of it.
      state.data.splice(state.data.indexOf(lead), 1, updated);
      setSaved(lead.id);
      setTimeout(() => setSaved((id) => (id === lead.id ? null : id)), 2000);
      toast('Lead updated.');
    } catch (e) {
      toast(e.message, 'off');
    } finally {
      setSaving(null);
    }
  };

  return (
    <>
      <SectionHead
        title="Demo requests"
        subtitle="From the form on scaleezy.com. Status and notes are yours; everything else is what they typed."
      />

      <Async
        state={state}
        isEmpty={(rows) => (rows.results || rows).length === 0}
        empty={<Empty icon={<Mail size={22} />} title="No demo requests yet."
          detail="Leads arrive from the form on the marketing site and land here." />}
      >
        {(data) => {
          const leads = data.results || data;
          return (
            <div className="sa-table-wrap">
              <table className="sa-table">
                <thead>
                  <tr>
                    <th>Received</th><th>Who</th><th>Contact</th>
                    <th>What they said</th><th>Status</th><th>Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((lead) => (
                    <tr key={lead.id}>
                      <td className="sa-schema" style={{ whiteSpace: 'nowrap' }}>{day(lead.created_at)}</td>
                      <td>
                        <div className="sa-name">{lead.name}</div>
                        <div className="sa-schema">{lead.boutique}</div>
                      </td>
                      <td>
                        <div>{lead.email}</div>
                        <div className="sa-muted" style={{ fontSize: 13 }}>{lead.phone}</div>
                      </td>
                      <td style={{ maxWidth: 320, fontSize: 13.5 }}>
                        {lead.problem || <span className="sa-muted">—</span>}
                        {(lead.makes || lead.orders_per_month || lead.people) && (
                          <div className="sa-muted" style={{ fontSize: 12.5, marginTop: 4 }}>
                            {[lead.makes,
                              lead.orders_per_month && `${lead.orders_per_month}/mo`,
                              lead.people && `${lead.people} people`].filter(Boolean).join(' · ')}
                          </div>
                        )}
                      </td>
                      <td>
                        <select className="sa-select" value={lead.status} disabled={saving === lead.id}
                          onChange={(e) => save(lead, { status: e.target.value })}>
                          {STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                        </select>
                        <div style={{ marginTop: 6 }}>
                          <Pill value={lead.status.toLowerCase()} label={lead.status} />
                          {saved === lead.id && (
                            <Check size={14} color="var(--success-color)"
                              style={{ verticalAlign: '-3px', marginLeft: 6 }} />
                          )}
                        </div>
                      </td>
                      <td style={{ minWidth: 220 }}>
                        <textarea className="sa-textarea" defaultValue={lead.notes}
                          disabled={saving === lead.id} placeholder="Add a note…"
                          // Saved on blur, not per keystroke: one PATCH when the
                          // administrator moves on, not one per character.
                          onBlur={(e) => {
                            if (e.target.value !== lead.notes) save(lead, { notes: e.target.value });
                          }} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }}
      </Async>
    </>
  );
}
