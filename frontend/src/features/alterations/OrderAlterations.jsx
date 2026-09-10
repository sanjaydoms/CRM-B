import { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Scissors, X } from 'lucide-react';
import { api } from '../../services/api';
import { formatDate as fmtDate, formatMoney } from '../../services/format';
import { parseAdjustments } from './adjustments';

/**
 * The alteration strip that lives inside an order card and a customer's order
 * history: what has come back on this order, and the way to take a garment in.
 *
 * Deliberately a small inline block rather than a second order screen. The
 * whole alteration file lives in the Alterations tab; this is the door to it
 * from where a customer is actually standing.
 *
 * "Request alteration" only appears on a Delivered order, and only for the
 * roles that run the counter. The server enforces both again -- this just
 * avoids drawing a button that would be refused.
 */

const COUNTER_ROLES = ['Owner', 'Master'];

const STATUS_TONE = {
  RECEIVED: '#6b7280', INSPECTION: '#3b82f6', PENDING_APPROVAL: '#f59e0b',
  APPROVED: '#8b5cf6', ASSIGNED: '#0ea5e9', IN_PROGRESS: '#f59e0b',
  QC: '#a855f7', READY_FOR_PICKUP: '#10b981', COMPLETED: '#10b981',
  CANCELLED: '#ef4444',
};

const money = (value) => formatMoney(Number(value || 0));

function RequestAlterationModal({ order, customerId, onClose, onCreated }) {
  const garments = order.garment_jobs || [];
  const [form, setForm] = useState({
    garment_job_id: garments.length === 1 ? garments[0].id : '',
    alteration_type: 'PAID_CLIENT_REQUEST',
    issue_description: '',
    adjustments: '',
    charge_amount: '',
    notes: '',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));
  const isPaid = form.alteration_type === 'PAID_CLIENT_REQUEST';

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.createAlteration({
        customer_id: customerId,
        order_id: order.order_id,
        garment_job_id: form.garment_job_id,
        alteration_type: form.alteration_type,
        issue_description: form.issue_description,
        requested_adjustments: parseAdjustments(form.adjustments),
        charge_amount: isPaid && form.charge_amount ? form.charge_amount : '0.00',
        notes: form.notes,
      });
      onCreated(created);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const field = { width: '100%', marginBottom: '12px' };
  const label = { fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' };

  return (
    <div
      onClick={onClose}
      style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{ background: 'var(--surface-color, #17181a)', border: '1px solid var(--border-color)', borderRadius: '12px', width: '100%', maxWidth: '520px', maxHeight: '88vh', overflowY: 'auto', padding: '20px' }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>Take a garment back for alteration</h3>
          <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}><X size={18} /></button>
        </div>
        <p style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginTop: 0, marginBottom: '16px', lineHeight: 1.5 }}>
          Order {order.order_id} stays exactly as it is. This opens a separate alteration job against the garment you pick.
        </p>

        {error && (
          <div style={{ display: 'flex', gap: '8px', padding: '10px 12px', borderRadius: '8px', background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: '13px', marginBottom: '12px', whiteSpace: 'pre-line' }}>
            <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
            <span>{error}</span>
          </div>
        )}

        <div style={field}>
          <label style={label}>Which garment came back?</label>
          {garments.length === 0 ? (
            <div style={{ fontSize: '13px', color: '#ef4444' }}>
              This order has no garment records, so an alteration cannot be raised against it.
            </div>
          ) : (
            <select className="form-control" value={form.garment_job_id} onChange={set('garment_job_id')}>
              <option value="">Choose the garment…</option>
              {garments.map((garment) => (
                <option key={garment.id} value={garment.id}>
                  {garment.template_name || garment.template?.name || 'Garment'}
                </option>
              ))}
            </select>
          )}
        </div>

        <div style={field}>
          <label style={label}>Who is paying for it?</label>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {[
              ['FREE_BOUTIQUE_FAULT', 'Free — our fault', 'Wrong measurement, stitching or fit on our side.'],
              ['PAID_CLIENT_REQUEST', 'Paid — customer request', 'They have changed their mind or want something different.'],
            ].map(([value, text, hint]) => (
              <button
                key={value}
                type="button"
                onClick={() => setForm((prev) => ({ ...prev, alteration_type: value, charge_amount: value === 'FREE_BOUTIQUE_FAULT' ? '' : prev.charge_amount }))}
                className={form.alteration_type === value ? 'btn-primary' : 'btn-secondary'}
                style={{ flex: '1 1 180px', textAlign: 'left', padding: '10px 12px', fontSize: '12.5px' }}
                title={hint}
              >
                {text}
              </button>
            ))}
          </div>
        </div>

        <div style={field}>
          <label style={label}>What is wrong?</label>
          <textarea className="form-control" rows={3} placeholder="The waist is loose…" value={form.issue_description} onChange={set('issue_description')} />
        </div>

        <div style={field}>
          <label style={label}>Adjustments asked for — one per line, e.g. “waist: let out 1 inch”</label>
          <textarea className="form-control" rows={3} value={form.adjustments} onChange={set('adjustments')} />
        </div>

        {isPaid && (
          <div style={field}>
            <label style={label}>Charge (optional now — it can be set after inspection)</label>
            <input className="form-control" type="number" min="0" step="0.01" value={form.charge_amount} onChange={set('charge_amount')} />
          </div>
        )}

        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '6px' }}>
          <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
          <button type="button" className="btn-primary" disabled={busy || !form.garment_job_id} onClick={submit}>
            {busy ? 'Creating…' : 'Create alteration'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function OrderAlterations({ order, customerId, currentUser, onOpenAlteration, compact = false }) {
  const [rows, setRows] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [error, setError] = useState(null);

  const canRequest = order.order_status === 'Delivered'
    && (!currentUser?.role || COUNTER_ROLES.includes(currentUser.role));

  const isDelivered = order.order_status === 'Delivered';

  const refresh = useCallback(() => {
    if (!isDelivered) return Promise.resolve();
    return api.getAlterations({ order: order.order_id })
      .then((data) => { setRows(data || []); setError(null); })
      .catch((err) => { setRows([]); setError(err.message); });
  }, [order.order_id, isDelivered]);

  // Only a delivered order can have any, so nothing else pays for the request.
  useEffect(() => { refresh(); }, [refresh]);

  // Nothing to fetch and nothing to show: an order still in production has no
  // alterations by definition, and no way to raise one.
  if (!isDelivered) return null;

  if (rows === null) {
    return <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Loading alterations…</div>;
  }
  if (!canRequest && rows.length === 0) return null;

  return (
    <div style={{
      padding: compact ? '10px 0 0' : '14px 16px',
      border: compact ? 'none' : '1px solid var(--border-color)',
      borderRadius: '8px', textAlign: 'left',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '10px', flexWrap: 'wrap' }}>
        <h4 style={{ fontSize: '13px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Scissors size={14} /> Alterations
          {rows.length > 0 && (
            <span style={{ fontWeight: 500, color: 'var(--text-muted)' }}>({rows.length})</span>
          )}
        </h4>
        {canRequest && (
          <button
            type="button"
            className="btn-secondary"
            style={{ fontSize: '12px', padding: '5px 12px' }}
            onClick={(e) => { e.stopPropagation(); setShowModal(true); }}
          >
            Request alteration
          </button>
        )}
      </div>

      {error && <div style={{ fontSize: '12px', color: '#ef4444', marginTop: '6px' }}>{error}</div>}

      {rows.length === 0 ? (
        <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '6px' }}>
          Nothing has come back on this order.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', marginTop: '10px' }}>
          {rows.map((row) => {
            const tone = STATUS_TONE[row.status] || '#6b7280';
            return (
              <div
                key={row.id}
                onClick={(e) => { e.stopPropagation(); if (onOpenAlteration) onOpenAlteration(row.id); }}
                style={{
                  display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap',
                  fontSize: '12.5px', padding: '8px 10px', borderRadius: '6px',
                  background: 'rgba(255,255,255,0.03)', border: '1px solid var(--border-color)',
                  cursor: onOpenAlteration ? 'pointer' : 'default',
                }}
              >
                <strong>{row.alteration_number}</strong>
                <span style={{ color: 'var(--text-muted)' }}>{row.garment_job?.template_name}</span>
                <span style={{
                  fontSize: '10.5px', fontWeight: 700, padding: '2px 8px', borderRadius: '999px',
                  color: tone, background: `${tone}1f`, border: `1px solid ${tone}55`,
                }}>
                  {row.status_display || row.status}
                </span>
                <span style={{ color: row.alteration_type === 'PAID_CLIENT_REQUEST' ? '#f59e0b' : '#10b981' }}>
                  {row.alteration_type === 'PAID_CLIENT_REQUEST' ? 'Paid' : 'Free'}
                </span>
                {Number(row.outstanding_balance) > 0 && (
                  <span style={{ color: '#ef4444' }}>{money(row.outstanding_balance)} due</span>
                )}
                <span style={{ marginLeft: 'auto', color: 'var(--text-muted)' }}>{fmtDate(row.received_at)}</span>
              </div>
            );
          })}
        </div>
      )}

      {showModal && (
        <RequestAlterationModal
          order={order}
          customerId={customerId || order.customer}
          onClose={() => setShowModal(false)}
          onCreated={(created) => {
            setShowModal(false);
            refresh();
            if (onOpenAlteration && created?.id) onOpenAlteration(created.id);
          }}
        />
      )}
    </div>
  );
}
