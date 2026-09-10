import { useCallback, useEffect, useState } from 'react';
import { Scissors } from 'lucide-react';
import { api } from '../../services/api';
import { formatDate as fmtDate, formatMoney } from '../../services/format';

/**
 * A short read-only list of alterations, fetched with whatever filter it is
 * given, and a way through to the full file in the Alterations tab.
 *
 * Two callers, one component: the tailor's own queue on My Assignments
 * (?assigned_to_me=1&open=1) and a customer's alteration history on their
 * profile (?customer=<id>). Both want the same six facts and a link; neither
 * wants a second copy of the register.
 *
 * Renders nothing at all when there is nothing to show, so it can be dropped
 * into a screen without leaving an empty card behind.
 */

const STATUS_TONE = {
  RECEIVED: '#6b7280', INSPECTION: '#3b82f6', PENDING_APPROVAL: '#f59e0b',
  APPROVED: '#8b5cf6', ASSIGNED: '#0ea5e9', IN_PROGRESS: '#f59e0b',
  QC: '#a855f7', READY_FOR_PICKUP: '#10b981', COMPLETED: '#10b981',
  CANCELLED: '#ef4444',
};

const money = (value) => formatMoney(Number(value || 0));

export default function AlterationList({ title, params, onOpenAlteration, refreshToken }) {
  const [rows, setRows] = useState(null);

  // Serialised so a fresh object literal from the parent's render does not
  // refetch on every keystroke elsewhere on the screen.
  const key = JSON.stringify(params || {});

  const load = useCallback(() => api.getAlterations(JSON.parse(key))
    .then((data) => setRows(data || []))
    .catch(() => setRows([])), [key]);

  useEffect(() => { load(); }, [load, refreshToken]);

  if (rows === null || rows.length === 0) return null;

  return (
    <div style={{
      background: 'var(--surface-color)', border: '1px solid var(--border-color)',
      borderRadius: '12px', padding: '24px',
    }}>
      <h3 style={{
        fontSize: '18px', fontWeight: 600, color: 'var(--text-primary)',
        marginBottom: '16px', borderBottom: '1px solid var(--border-color)',
        paddingBottom: '10px', display: 'flex', alignItems: 'center', gap: '8px',
      }}>
        <Scissors size={16} /> {title}
        <span style={{ fontWeight: 500, fontSize: '13px', color: 'var(--text-muted)' }}>
          ({rows.length})
        </span>
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
        {rows.map((row) => {
          const tone = STATUS_TONE[row.status] || '#6b7280';
          return (
            <div
              key={row.id}
              onClick={() => onOpenAlteration && onOpenAlteration(row.id)}
              style={{
                border: '1px solid var(--border-color)', borderRadius: '8px',
                padding: '14px 16px', cursor: onOpenAlteration ? 'pointer' : 'default',
                display: 'flex', flexDirection: 'column', gap: '6px',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                <strong style={{ fontSize: '14px' }}>{row.alteration_number}</strong>
                <span style={{
                  fontSize: '10.5px', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
                  color: tone, background: `${tone}1f`, border: `1px solid ${tone}55`,
                }}>
                  {row.status_display || row.status}
                </span>
                <span style={{ color: row.alteration_type === 'PAID_CLIENT_REQUEST' ? '#f59e0b' : '#10b981', fontSize: '12px' }}>
                  {row.alteration_type === 'PAID_CLIENT_REQUEST' ? 'Paid' : 'Free'}
                </span>
                {Number(row.outstanding_balance) > 0 && (
                  <span style={{ fontSize: '12px', color: '#ef4444' }}>
                    {money(row.outstanding_balance)} due
                  </span>
                )}
                <span style={{ marginLeft: 'auto', fontSize: '12px', color: 'var(--text-muted)' }}>
                  {fmtDate(row.received_at)}
                </span>
              </div>
              <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
                {row.customer?.name} · {row.garment_job?.template_name} · from order {row.original_order?.order_id}
                {row.assigned_to_name ? ` · ${row.assigned_to_name}` : ''}
              </div>
              {row.issue_description && (
                <div style={{ fontSize: '12.5px', fontStyle: 'italic', color: 'var(--text-muted)' }}>
                  “{row.issue_description}”
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
