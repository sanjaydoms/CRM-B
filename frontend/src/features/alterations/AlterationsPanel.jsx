import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle, ArrowLeft, CheckCircle2, ClipboardList, History, IndianRupee,
  Package, RotateCw, Scissors, Search, User, X,
} from 'lucide-react';
import { api } from '../../services/api';
import { formatDate as fmtDate, formatDateTime as fmtDateTime, formatMoney } from '../../services/format';
import { formatAdjustments, parseAdjustments } from './adjustments';

/**
 * The alterations register and one alteration's whole file.
 *
 * A lazily-loaded feature panel like InventoryPanel and StaffPanel, mounted
 * from its own dashboard tab. It never draws a button the server would refuse:
 * every control is keyed off `available_actions`, which the API derives from
 * the same state machine it enforces, so this file holds no copy of the
 * workflow rules and cannot drift from them.
 */

const STATUS_TONE = {
  RECEIVED: '#6b7280',
  INSPECTION: '#3b82f6',
  PENDING_APPROVAL: '#f59e0b',
  APPROVED: '#8b5cf6',
  ASSIGNED: '#0ea5e9',
  IN_PROGRESS: '#f59e0b',
  QC: '#a855f7',
  READY_FOR_PICKUP: '#10b981',
  COMPLETED: '#10b981',
  CANCELLED: '#ef4444',
};

const STATUS_ORDER = [
  'RECEIVED', 'INSPECTION', 'PENDING_APPROVAL', 'APPROVED', 'ASSIGNED',
  'IN_PROGRESS', 'QC', 'READY_FOR_PICKUP', 'COMPLETED',
];

// Titlecasing the status key renders QC as "Qc". Spelled out here rather than
// fought with CSS, and it is also the place to say "Quality check" in full
// where there is room for it.
const STATUS_LABELS = {
  RECEIVED: 'Received',
  INSPECTION: 'Inspection',
  PENDING_APPROVAL: 'Pending approval',
  APPROVED: 'Approved',
  ASSIGNED: 'Assigned',
  IN_PROGRESS: 'In progress',
  QC: 'Quality check',
  READY_FOR_PICKUP: 'Ready for pickup',
  COMPLETED: 'Completed',
  CANCELLED: 'Cancelled',
};

const statusLabel = (status) =>
  STATUS_LABELS[status] || String(status || '').replace(/_/g, ' ').toLowerCase();

const ACTION_LABELS = {
  'start-inspection': 'Start inspection',
  'submit-for-approval': 'Send estimate for approval',
  approve: 'Approve',
  assign: 'Assign to a tailor',
  'start-work': 'Start work',
  'send-to-qc': 'Send to quality check',
  'pass-qc': 'Pass quality check',
  'fail-qc': 'Fail quality check',
  complete: 'Complete & hand back',
  cancel: 'Cancel alteration',
};

const PAYMENT_METHODS = [
  ['CASH', 'Cash'], ['UPI', 'UPI / QR'], ['CARD', 'Credit / Debit Card'],
  ['BANK_TRANSFER', 'Bank Transfer'], ['OTHER', 'Other'],
];

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
};

const money = (value) => formatMoney(Number(value || 0));


function Pill({ status, label }) {
  const tone = STATUS_TONE[status] || '#6b7280';
  return (
    <span style={{
      fontSize: '11px', fontWeight: 700, padding: '3px 10px', borderRadius: '999px',
      color: tone, background: `${tone}1f`, border: `1px solid ${tone}55`,
      whiteSpace: 'nowrap',
    }}>
      {label || status}
    </span>
  );
}

function Stat({ label, value, tone, hint }) {
  return (
    <div style={{ ...panel, padding: '14px 16px', flex: '1 1 150px' }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontSize: '20px', fontWeight: 600, marginTop: '6px', color: tone || 'var(--text-primary)' }}>{value}</div>
      {hint && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '2px' }}>{hint}</div>}
    </div>
  );
}

function Modal({ title, onClose, children, width = '460px' }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          ...panel, background: 'var(--surface-color, #17181a)', width: '100%',
          maxWidth: width, maxHeight: '86vh', overflowY: 'auto', padding: '20px',
        }}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px' }}>
          <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>{title}</h3>
          <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function ErrorNote({ error, onDismiss }) {
  if (!error) return null;
  return (
    <div style={{
      display: 'flex', gap: '8px', alignItems: 'flex-start', padding: '10px 12px',
      borderRadius: '8px', background: 'rgba(239,68,68,0.08)',
      border: '1px solid rgba(239,68,68,0.3)', color: '#ef4444', fontSize: '13px',
      marginBottom: '12px', whiteSpace: 'pre-line',
    }}>
      <AlertTriangle size={15} style={{ flexShrink: 0, marginTop: '1px' }} />
      <span style={{ flex: 1 }}>{error}</span>
      {onDismiss && (
        <button type="button" onClick={onDismiss} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>
          <X size={14} />
        </button>
      )}
    </div>
  );
}

function StatusTrack({ status }) {
  if (status === 'CANCELLED') {
    return <Pill status="CANCELLED" label="Cancelled" />;
  }
  const current = STATUS_ORDER.indexOf(status);
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
      {STATUS_ORDER.map((step, index) => {
        const done = index < current;
        const here = index === current;
        return (
          <span key={step} style={{
            fontSize: '10px', fontWeight: 600, padding: '4px 8px', borderRadius: '6px',
            color: here ? '#fff' : done ? '#10b981' : 'var(--text-muted)',
            background: here ? (STATUS_TONE[step] || '#6b7280') : done ? 'rgba(16,185,129,0.12)' : 'transparent',
            border: `1px solid ${here ? 'transparent' : done ? 'rgba(16,185,129,0.3)' : 'var(--border-color)'}`,
          }}>
            {statusLabel(step)}
          </span>
        );
      })}
    </div>
  );
}

function KeyValues({ data }) {
  const entries = Object.entries(data || {});
  if (!entries.length) return <span style={{ color: 'var(--text-muted)', fontSize: '13px' }}>—</span>;
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
      {entries.map(([key, value]) => (
        <span key={key} style={{
          fontSize: '12px', padding: '3px 8px', borderRadius: '6px',
          background: 'rgba(255,255,255,0.04)', border: '1px solid var(--border-color)',
        }}>
          <strong style={{ textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</strong>: {String(value)}
        </span>
      ))}
    </div>
  );
}

function Section({ icon: Icon, title, children, right }) {
  return (
    <div style={{ ...panel, padding: '16px 18px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', gap: '10px' }}>
        <h4 style={{ margin: 0, fontSize: '13px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '7px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          <Icon size={14} /> {title}
        </h4>
        {right}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------

function AlterationDetail({ alterationId, currentUser, tailors, onBack, onChanged }) {
  const [alteration, setAlteration] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);
  const [dialog, setDialog] = useState(null); // {kind, ...}
  const [items, setItems] = useState([]);

  const isOwner = !currentUser?.role || currentUser.role === 'Owner';

  const refresh = useCallback(() => api.getAlteration(alterationId)
    .then((data) => { setAlteration(data); setError(null); })
    .catch((err) => setError(err.message))
    .finally(() => setLoading(false)), [alterationId]);

  useEffect(() => { refresh(); }, [refresh]);

  // The item picker is Owner-only because the inventory API itself is; asking
  // for it as anyone else would only produce a 403 nobody can act on.
  useEffect(() => {
    if (!isOwner) return undefined;
    let live = true;
    api.getInventoryItems()
      .then((data) => { if (live) setItems(data?.results || data || []); })
      .catch(() => { if (live) setItems([]); });
    return () => { live = false; };
  }, [isOwner]);

  const run = async (key, call) => {
    setBusy(key);
    setError(null);
    try {
      const updated = await call();
      // Workflow actions hand back the whole alteration; recording a payment
      // or a material hands back that row instead, so key off a field only
      // the alteration has rather than on the presence of an id.
      setAlteration(updated?.alteration_number
        ? updated
        : await api.getAlteration(alterationId));
      setDialog(null);
      if (onChanged) onChanged();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  if (loading) return <div style={{ padding: '32px', color: 'var(--text-muted)' }}>Loading alteration…</div>;
  if (!alteration) return (
    <div style={{ padding: '24px' }}>
      <ErrorNote error={error} />
      <button type="button" className="btn-secondary" onClick={onBack}>Back to alterations</button>
    </div>
  );

  const actions = alteration.available_actions || [];
  const isPaid = alteration.alteration_type === 'PAID_CLIENT_REQUEST';
  const outstanding = Number(alteration.outstanding_balance || 0);
  // The server allows findings only while the garment is in Inspection, and
  // only to the roles that also run the estimate -- which is exactly the
  // condition under which submit-for-approval is offered.
  const canRecordInspection = alteration.status === 'INSPECTION'
    && actions.includes('submit-for-approval');

  const act = (key) => {
    if (['submit-for-approval', 'assign', 'fail-qc', 'cancel', 'complete'].includes(key)) {
      setDialog({ kind: key });
      return;
    }
    const calls = {
      'start-inspection': () => api.startAlterationInspection(alteration.id, ''),
      approve: () => api.approveAlteration(alteration.id, ''),
      'start-work': () => api.startAlterationWork(alteration.id),
      'send-to-qc': () => api.sendAlterationToQC(alteration.id),
      'pass-qc': () => api.passAlterationQC(alteration.id, ''),
    };
    if (calls[key]) run(key, calls[key]);
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <button type="button" className="btn-secondary" onClick={onBack} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', padding: '6px 12px' }}>
          <ArrowLeft size={14} /> All alterations
        </button>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>{alteration.alteration_number}</h2>
        <Pill status={alteration.status} label={alteration.status_display} />
        <span style={{
          fontSize: '11px', fontWeight: 600, padding: '3px 10px', borderRadius: '999px',
          background: isPaid ? 'rgba(245,158,11,0.14)' : 'rgba(16,185,129,0.14)',
          color: isPaid ? '#f59e0b' : '#10b981',
        }}>
          {alteration.alteration_type_display}
        </span>
        <button type="button" className="btn-secondary" onClick={refresh} style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', padding: '6px 12px' }}>
          <RotateCw size={13} /> Refresh
        </button>
      </div>

      <ErrorNote error={error} onDismiss={() => setError(null)} />

      <div style={{ ...panel, padding: '16px 18px' }}>
        <StatusTrack status={alteration.status} />
        {(actions.length > 0 || canRecordInspection) && (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '14px' }}>
            {/* Not a transition, so it is not in available_actions: it writes
                what the inspection found and leaves the status alone, and can
                be done more than once while the garment is on the table. */}
            {canRecordInspection && (
              <button
                type="button"
                className="btn-secondary"
                disabled={busy !== null}
                onClick={() => setDialog({ kind: 'record-inspection' })}
                style={{ fontSize: '12.5px', padding: '7px 14px' }}
              >
                Record inspection findings
              </button>
            )}
            {actions.filter((key) => ACTION_LABELS[key]).map((key) => (
              <button
                key={key}
                type="button"
                className={key === 'cancel' || key === 'fail-qc' ? 'btn-secondary' : 'btn-primary'}
                disabled={busy !== null}
                onClick={() => act(key)}
                style={{ fontSize: '12.5px', padding: '7px 14px' }}
              >
                {busy === key ? 'Working…' : ACTION_LABELS[key]}
              </button>
            ))}
          </div>
        )}
        {actions.length === 0 && !canRecordInspection && (
          <div style={{ marginTop: '12px', fontSize: '12.5px', color: 'var(--text-muted)' }}>
            No further action is available to you on this alteration.
          </div>
        )}
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
        <Section icon={ClipboardList} title="The request">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', fontSize: '13px' }}>
            <div><span style={{ color: 'var(--text-muted)' }}>Customer</span><br /><strong>{alteration.customer?.name}</strong> · {alteration.customer?.mobile_number}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>Original order</span><br /><strong>{alteration.original_order?.order_id}</strong> · {alteration.original_order?.order_status} · delivered {fmtDate(alteration.original_order?.order_date)}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>Garment</span><br /><strong>{alteration.garment_job?.template_name}</strong></div>
            <div><span style={{ color: 'var(--text-muted)' }}>Issue</span><br />{alteration.issue_description || '—'}</div>
            <div><span style={{ color: 'var(--text-muted)' }}>Requested adjustments</span><br /><KeyValues data={alteration.requested_adjustments} /></div>
            {(alteration.inspection_notes || Object.keys(alteration.inspection_adjustments || {}).length > 0) && (
              <div>
                <span style={{ color: 'var(--text-muted)' }}>Inspection findings</span><br />
                {alteration.inspection_notes || '—'}
                <div style={{ marginTop: '6px' }}><KeyValues data={alteration.inspection_adjustments} /></div>
              </div>
            )}
          </div>
        </Section>

        <Section icon={User} title="Assignment">
          {alteration.tasks?.length ? alteration.tasks.map((task) => (
            <div key={task.id} style={{ fontSize: '13px', display: 'flex', flexDirection: 'column', gap: '4px', paddingBottom: '10px' }}>
              <div><strong>{task.title}</strong> — <Pill status={task.status} label={statusLabel(task.status)} /></div>
              <div style={{ color: 'var(--text-muted)' }}>
                {task.assigned_to_name ? `${task.assigned_to_name} (${task.assigned_to_role})` : 'Unassigned'}
              </div>
              {task.started_at && <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Started {fmtDateTime(task.started_at)}</div>}
              {task.completed_at && <div style={{ color: 'var(--text-muted)', fontSize: '12px' }}>Finished {fmtDateTime(task.completed_at)}</div>}
              {task.notes && <div style={{ fontSize: '12px' }}>{task.notes}</div>}
            </div>
          )) : <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>Not assigned to anyone yet.</div>}
        </Section>

        {isPaid && (
          <Section
            icon={IndianRupee}
            title="Charges"
            right={actions.includes('record-payment') && outstanding > 0 && (
              <button type="button" className="btn-primary" style={{ fontSize: '12px', padding: '5px 11px' }} onClick={() => setDialog({ kind: 'payment' })}>
                Record payment
              </button>
            )}
          >
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', marginBottom: '12px' }}>
              <Stat label="Charge" value={money(alteration.charge_amount)} />
              <Stat label="Paid" value={money(alteration.amount_paid)} tone="#10b981" />
              <Stat label="Outstanding" value={money(outstanding)} tone={outstanding > 0 ? '#ef4444' : '#10b981'} />
            </div>
            {alteration.payments?.length ? (
              <table style={{ width: '100%', fontSize: '12.5px', borderCollapse: 'collapse' }}>
                <tbody>
                  {alteration.payments.map((payment) => (
                    <tr key={payment.id} style={{ borderTop: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '6px 0', fontWeight: 600 }}>{money(payment.amount)}</td>
                      <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>{payment.payment_method_display}</td>
                      <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>{payment.transaction_reference || '—'}</td>
                      <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>{fmtDate(payment.received_at)}</td>
                      <td style={{ padding: '6px 0', color: 'var(--text-muted)' }}>{payment.received_by_name}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No payments recorded.</div>}
          </Section>
        )}

        {!isPaid && (
          <Section icon={CheckCircle2} title="Charges">
            <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
              Boutique fault — nothing is charged to the customer for this alteration.
            </div>
          </Section>
        )}

        <Section
          icon={Package}
          title="Materials used"
          right={actions.includes('record-material') && (
            <button type="button" className="btn-secondary" style={{ fontSize: '12px', padding: '5px 11px' }} onClick={() => setDialog({ kind: 'material' })}>
              Record usage
            </button>
          )}
        >
          {alteration.material_lines?.length ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '12.5px' }}>
              {alteration.material_lines.map((line) => (
                <div key={line.id} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px', borderTop: '1px solid var(--border-color)', paddingTop: '8px' }}>
                  <span><strong>{line.material_name}</strong>{line.remarks ? ` — ${line.remarks}` : ''}</span>
                  <span style={{ color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{line.quantity} {line.unit}</span>
                </div>
              ))}
            </div>
          ) : <div style={{ fontSize: '13px', color: 'var(--text-muted)' }}>No extra materials were used.</div>}
        </Section>
      </div>

      <Section icon={History} title="Activity">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {(alteration.activities || []).map((activity) => (
            <div key={activity.id} style={{ display: 'flex', gap: '10px', fontSize: '12.5px', borderTop: '1px solid var(--border-color)', paddingTop: '8px' }}>
              <span style={{ color: 'var(--text-muted)', minWidth: '150px' }}>{fmtDateTime(activity.timestamp)}</span>
              <span style={{ flex: 1 }}>
                <strong>{activity.event_type.replace(/_/g, ' ').toLowerCase()}</strong>
                {activity.from_status && activity.to_status && activity.from_status !== activity.to_status && (
                  <span style={{ color: 'var(--text-muted)' }}> · {activity.from_status.toLowerCase()} → {activity.to_status.toLowerCase()}</span>
                )}
                {activity.metadata?.reason && <div style={{ color: '#ef4444' }}>{activity.metadata.reason}</div>}
                {activity.metadata?.notes && <div style={{ color: 'var(--text-muted)' }}>{activity.metadata.notes}</div>}
              </span>
              <span style={{ color: 'var(--text-muted)' }}>{activity.performed_by_name}</span>
            </div>
          ))}
        </div>
      </Section>

      {dialog && (
        <ActionDialog
          dialog={dialog}
          alteration={alteration}
          tailors={tailors}
          items={items}
          busy={busy !== null}
          onClose={() => setDialog(null)}
          onSubmit={(key, call) => run(key, call)}
        />
      )}
    </div>
  );
}

function ActionDialog({ dialog, alteration, tailors, items, busy, onClose, onSubmit }) {
  const [form, setForm] = useState({
    charge_amount: alteration.charge_amount,
    inspection_notes: alteration.inspection_notes || '',
    inspection_adjustments: formatAdjustments(alteration.inspection_adjustments),
    notes: '',
    reason: '',
    tailor_id: '',
    title: 'Alteration work',
    amount: alteration.outstanding_balance,
    payment_method: 'CASH',
    transaction_reference: '',
    item_id: '',
    quantity: '',
    remarks: '',
  });
  const set = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const field = { width: '100%', marginBottom: '12px' };
  const label = { fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' };

  const config = {
    'record-inspection': {
      title: 'Record what the inspection found',
      submit: 'Save findings',
      body: (
        <>
          <div style={field}>
            <label style={label}>Findings</label>
            <textarea className="form-control" rows={3} value={form.inspection_notes} onChange={set('inspection_notes')} />
          </div>
          <div style={field}>
            <label style={label}>Measurement / specification changes — one per line, e.g. “waist: +1 inch”</label>
            <textarea className="form-control" rows={3} value={form.inspection_adjustments} onChange={set('inspection_adjustments')} />
          </div>
          <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '0 0 8px' }}>
            Stored on the alteration. The garment’s original specification is
            left exactly as it was made.
          </p>
        </>
      ),
      call: () => api.recordAlterationInspection(alteration.id, {
        inspection_notes: form.inspection_notes,
        adjustments: parseAdjustments(form.inspection_adjustments),
      }),
    },
    'submit-for-approval': {
      title: 'Send the estimate for approval',
      submit: 'Send for approval',
      body: (
        <>
          {alteration.alteration_type === 'PAID_CLIENT_REQUEST' && (
            <div style={field}>
              <label style={label}>Charge for this alteration</label>
              <input className="form-control" type="number" min="0" step="0.01" value={form.charge_amount} onChange={set('charge_amount')} />
            </div>
          )}
          <div style={field}>
            <label style={label}>Notes (optional)</label>
            <textarea className="form-control" rows={3} value={form.notes} onChange={set('notes')} />
          </div>
        </>
      ),
      call: () => api.submitAlterationForApproval(alteration.id, {
        charge_amount: alteration.alteration_type === 'PAID_CLIENT_REQUEST' ? form.charge_amount : undefined,
        notes: form.notes,
      }),
    },
    assign: {
      title: 'Assign this alteration',
      submit: 'Assign',
      disabled: !form.tailor_id,
      body: (
        <>
          <div style={field}>
            <label style={label}>Tailor</label>
            <select className="form-control" value={form.tailor_id} onChange={set('tailor_id')}>
              <option value="">Choose someone…</option>
              {tailors.map((tailor) => (
                <option key={tailor.id} value={tailor.id}>{tailor.name} — {tailor.role}</option>
              ))}
            </select>
          </div>
          <div style={field}>
            <label style={label}>What needs doing</label>
            <input className="form-control" value={form.title} onChange={set('title')} />
          </div>
          <div style={field}>
            <label style={label}>Notes for the tailor (optional)</label>
            <textarea className="form-control" rows={3} value={form.notes} onChange={set('notes')} />
          </div>
        </>
      ),
      call: () => api.assignAlteration(alteration.id, {
        tailor_id: Number(form.tailor_id), title: form.title, notes: form.notes,
      }),
    },
    'fail-qc': {
      title: 'Fail the quality check',
      submit: 'Send back for rework',
      disabled: !form.reason.trim(),
      body: (
        <div style={field}>
          <label style={label}>What is wrong? (required)</label>
          <textarea className="form-control" rows={3} value={form.reason} onChange={set('reason')} />
        </div>
      ),
      call: () => api.failAlterationQC(alteration.id, form.reason),
    },
    cancel: {
      title: 'Cancel this alteration',
      submit: 'Cancel alteration',
      disabled: !form.reason.trim(),
      body: (
        <div style={field}>
          <label style={label}>Why is it being cancelled? (required)</label>
          <textarea className="form-control" rows={3} value={form.reason} onChange={set('reason')} />
        </div>
      ),
      call: () => api.cancelAlteration(alteration.id, form.reason),
    },
    complete: {
      title: 'Complete and hand back',
      submit: 'Complete',
      body: (
        <>
          {Number(alteration.outstanding_balance) > 0 && (
            <ErrorNote error={`${money(alteration.outstanding_balance)} is still outstanding. Record the payment first.`} />
          )}
          <div style={field}>
            <label style={label}>Notes (optional)</label>
            <textarea className="form-control" rows={3} value={form.notes} onChange={set('notes')} />
          </div>
        </>
      ),
      call: () => api.completeAlteration(alteration.id, form.notes),
    },
    payment: {
      title: 'Record a payment',
      submit: 'Record payment',
      disabled: !form.amount,
      body: (
        <>
          <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', marginBottom: '12px' }}>
            Outstanding: <strong style={{ color: 'var(--text-primary)' }}>{money(alteration.outstanding_balance)}</strong>
          </div>
          <div style={field}>
            <label style={label}>Amount</label>
            <input className="form-control" type="number" min="0" step="0.01" max={alteration.outstanding_balance} value={form.amount} onChange={set('amount')} />
          </div>
          <div style={field}>
            <label style={label}>Method</label>
            <select className="form-control" value={form.payment_method} onChange={set('payment_method')}>
              {PAYMENT_METHODS.map(([value, text]) => <option key={value} value={value}>{text}</option>)}
            </select>
          </div>
          <div style={field}>
            <label style={label}>Transaction reference (optional, but it prevents duplicates)</label>
            <input className="form-control" value={form.transaction_reference} onChange={set('transaction_reference')} />
          </div>
          <div style={field}>
            <label style={label}>Notes (optional)</label>
            <input className="form-control" value={form.notes} onChange={set('notes')} />
          </div>
        </>
      ),
      call: () => api.recordAlterationPayment(alteration.id, {
        amount: form.amount, payment_method: form.payment_method,
        transaction_reference: form.transaction_reference, notes: form.notes,
      }),
    },
    material: {
      title: 'Record material used',
      submit: 'Record usage',
      disabled: !form.item_id || !form.quantity,
      body: (
        <>
          <div style={field}>
            <label style={label}>Item</label>
            <select className="form-control" value={form.item_id} onChange={set('item_id')}>
              <option value="">Choose an item…</option>
              {items.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name} ({item.available_stock ?? item.current_stock} {item.unit_display || item.unit} available)
                </option>
              ))}
            </select>
          </div>
          <div style={field}>
            <label style={label}>Quantity</label>
            <input className="form-control" type="number" min="0" step="0.001" value={form.quantity} onChange={set('quantity')} />
          </div>
          <div style={field}>
            <label style={label}>What it was for (optional)</label>
            <input className="form-control" value={form.remarks} onChange={set('remarks')} />
          </div>
        </>
      ),
      call: () => api.recordAlterationMaterial(alteration.id, {
        item_id: form.item_id, quantity: form.quantity, remarks: form.remarks,
      }),
    },
  }[dialog.kind];

  if (!config) return null;

  return (
    <Modal title={config.title} onClose={onClose}>
      {config.body}
      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '8px' }}>
        <button type="button" className="btn-secondary" onClick={onClose}>Close</button>
        <button
          type="button"
          className="btn-primary"
          disabled={busy || config.disabled}
          onClick={() => onSubmit(dialog.kind, config.call)}
        >
          {busy ? 'Working…' : config.submit}
        </button>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------------------

export default function AlterationsPanel({ currentUser, initialAlterationId = null,
                                          onBackToList }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState('OPEN');
  const [typeFilter, setTypeFilter] = useState('');
  const [search, setSearch] = useState('');
  const [selectedId, setSelectedId] = useState(initialAlterationId);
  const [tailors, setTailors] = useState([]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = {};
      if (statusFilter === 'OPEN') params.open = '1';
      else if (statusFilter) params.status = statusFilter;
      if (typeFilter) params.alteration_type = typeFilter;
      if (search.trim()) params.search = search.trim();
      setRows(await api.getAlterations(params));
      setError(null);
    } catch (err) {
      setError(err.message);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [statusFilter, typeFilter, search]);

  useEffect(() => {
    const timer = setTimeout(load, search ? 300 : 0);
    return () => clearTimeout(timer);
  }, [load, search]);

  useEffect(() => {
    api.getTailors().then(setTailors).catch(() => setTailors([]));
  }, []);

  const totals = useMemo(() => ({
    open: rows.filter((row) => !['COMPLETED', 'CANCELLED'].includes(row.status)).length,
    awaitingPickup: rows.filter((row) => row.status === 'READY_FOR_PICKUP').length,
    owed: rows.reduce((sum, row) => sum + Number(row.outstanding_balance || 0), 0),
  }), [rows]);

  if (selectedId) {
    return (
      <AlterationDetail
        alterationId={selectedId}
        currentUser={currentUser}
        tailors={tailors}
        onBack={() => {
          setSelectedId(null);
          // Also clears the deep link the order card or customer file set, so
          // leaving and coming back to the tab lands on the register.
          if (onBackToList) onBackToList();
          load();
        }}
        onChanged={load}
      />
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <header className="portal-header">
        <div className="portal-header-left">
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>Alterations</h1>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              Garments that came back after delivery. Each one is its own job — the original order stays as it was.
            </p>
          </div>
        </div>
        <div className="portal-header-right">
          <button type="button" className="btn-secondary" onClick={load} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13px', padding: '8px 14px' }}>
            <RotateCw size={15} className={loading ? 'spin' : ''} /> {loading ? 'Loading…' : 'Refresh'}
          </button>
        </div>
      </header>

      <ErrorNote error={error} onDismiss={() => setError(null)} />

      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        <Stat label="In progress" value={totals.open} />
        <Stat label="Ready for pickup" value={totals.awaitingPickup} tone="#10b981" />
        <Stat label="Outstanding" value={money(totals.owed)} tone={totals.owed > 0 ? '#f59e0b' : undefined} />
      </div>

      <div style={{ ...panel, padding: '14px 16px', display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap' }}>
          {[['OPEN', 'Open'], ['', 'All'],
            ...STATUS_ORDER.map((s) => [s, statusLabel(s)]),
            ['CANCELLED', statusLabel('CANCELLED')]].map(([value, text]) => (
            <button
              key={value || 'all'}
              type="button"
              onClick={() => setStatusFilter(value)}
              className={statusFilter === value ? 'btn-primary' : 'btn-secondary'}
              style={{ padding: '5px 12px', fontSize: '12px' }}
            >
              {text}
            </button>
          ))}
        </div>
        <select className="form-control" style={{ width: '190px', margin: 0, fontSize: '13px' }} value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
          <option value="">Free and paid</option>
          <option value="FREE_BOUTIQUE_FAULT">Free / boutique fault</option>
          <option value="PAID_CLIENT_REQUEST">Paid / customer request</option>
        </select>
        <div className="search-bar-container" style={{ maxWidth: '280px', margin: 0, flex: '1 1 200px' }}>
          <Search className="search-icon" size={16} />
          <input className="search-input" placeholder="Number, customer, order…" value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
      </div>

      {loading && rows.length === 0 ? (
        <div style={{ ...panel, padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>Loading alterations…</div>
      ) : rows.length === 0 ? (
        <div style={{ ...panel, padding: '40px', textAlign: 'center', color: 'var(--text-muted)' }}>
          <Scissors size={22} style={{ marginBottom: '10px' }} />
          <div style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Nothing here</div>
          <div style={{ fontSize: '13px', marginTop: '6px', maxWidth: '46ch', marginInline: 'auto', lineHeight: 1.5 }}>
            Alterations are raised from a delivered order — open the order in Manage Orders and use “Request alteration”.
          </div>
        </div>
      ) : (
        <div style={{ ...panel, overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px', minWidth: '900px' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                {['Alteration', 'Customer', 'Order', 'Garment', 'Type', 'Status', 'Tailor', 'Charge', 'Outstanding', 'Received'].map((heading) => (
                  <th key={heading} style={{ padding: '12px 14px', fontWeight: 600 }}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => setSelectedId(row.id)}
                  style={{ borderTop: '1px solid var(--border-color)', cursor: 'pointer' }}
                >
                  <td style={{ padding: '12px 14px', fontWeight: 600 }}>{row.alteration_number}</td>
                  <td style={{ padding: '12px 14px' }}>{row.customer?.name}</td>
                  <td style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>{row.original_order?.order_id}</td>
                  <td style={{ padding: '12px 14px' }}>{row.garment_job?.template_name}</td>
                  <td style={{ padding: '12px 14px', color: row.alteration_type === 'PAID_CLIENT_REQUEST' ? '#f59e0b' : '#10b981' }}>
                    {row.alteration_type === 'PAID_CLIENT_REQUEST' ? 'Paid' : 'Free'}
                  </td>
                  <td style={{ padding: '12px 14px' }}><Pill status={row.status} label={row.status_display} /></td>
                  <td style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>{row.assigned_to_name || '—'}</td>
                  <td style={{ padding: '12px 14px' }}>{money(row.charge_amount)}</td>
                  <td style={{ padding: '12px 14px', color: Number(row.outstanding_balance) > 0 ? '#ef4444' : 'var(--text-muted)' }}>
                    {money(row.outstanding_balance)}
                  </td>
                  <td style={{ padding: '12px 14px', color: 'var(--text-muted)' }}>{fmtDate(row.received_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
