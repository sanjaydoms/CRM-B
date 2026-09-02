import { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle, Check, ClipboardList, Clock, RotateCcw, Send, UserPlus,
} from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';

/**
 * Design work as a job on someone's desk.
 *
 * One component for both audiences, because it is one loop seen from two ends:
 * a supervisor assigns a garment and reviews what comes back, a designer sees
 * what they have been asked for and submits it. Splitting it into two screens
 * would duplicate the card, the status vocabulary and the empty states, and let
 * the two drift until "submitted" meant something different on each.
 *
 * The role split is NOT enforced here. The API scopes the list to the caller
 * (a designer's request comes back as their own desk, and their payload carries
 * no customer identity at all -- see DesignerAssignmentSerializer), so this
 * renders what it is given rather than filtering what it should not have asked
 * for. `isSupervisor` decides which controls to draw, not which data to trust.
 */

const STATUS_STYLE = {
  ASSIGNED: { label: 'Assigned', colour: '#d4af37', icon: ClipboardList },
  SUBMITTED: { label: 'Awaiting review', colour: '#4a9eff', icon: Clock },
  APPROVED: { label: 'Approved', colour: '#3fb950', icon: Check },
  CHANGES_REQUESTED: { label: 'Changes requested', colour: '#f0883e', icon: RotateCcw },
};

function StatusPill({ status }) {
  const style = STATUS_STYLE[status] || { label: status, colour: 'var(--text-secondary)', icon: ClipboardList };
  const Icon = style.icon;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '3px 9px', borderRadius: '99px', fontSize: '11px', fontWeight: 600,
      color: style.colour, background: `${style.colour}1f`, whiteSpace: 'nowrap',
    }}>
      <Icon size={12} /> {style.label}
    </span>
  );
}

function formatDate(value) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
}

/** The supervisor's assign form: pick a garment, pick a designer, send it. */
function AssignPanel({ orders, designers, onAssigned, onError }) {
  const [jobId, setJobId] = useState('');
  const [designerId, setDesignerId] = useState('');
  const [brief, setBrief] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [busy, setBusy] = useState(false);

  // Every garment on every open order, flattened, because the unit of
  // assignment is the garment and not the order it arrived on. An order with a
  // lehenga and a blouse offers two rows here, and they can go to two people.
  const garmentOptions = (orders || []).flatMap(order =>
    (order.garment_jobs || []).map(job => ({
      id: job.id,
      label: `${order.order_id} · ${job.template_name || 'Custom garment'}`,
    })));

  const submit = async (event) => {
    event.preventDefault();
    if (!jobId || !designerId) return;
    setBusy(true);
    try {
      await api.assignDesignWork({
        garment_job: jobId,
        designer: designerId,
        brief,
        ...(dueDate ? { due_date: dueDate } : {}),
      });
      setJobId(''); setDesignerId(''); setBrief(''); setDueDate('');
      onAssigned();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="content-card" onSubmit={submit} style={{ marginBottom: '18px' }}>
      <h3 style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '14px' }}>
        <UserPlus size={16} /> Assign design work
      </h3>
      <div style={{ display: 'grid', gap: '12px', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))' }}>
        <label style={{ display: 'block' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Garment</span>
          <select className="form-input" value={jobId} required
                  onChange={(e) => setJobId(e.target.value)}>
            <option value="">Choose a garment…</option>
            {garmentOptions.map(option => (
              <option key={option.id} value={option.id}>{option.label}</option>
            ))}
          </select>
        </label>
        <label style={{ display: 'block' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Designer</span>
          <select className="form-input" value={designerId} required
                  onChange={(e) => setDesignerId(e.target.value)}>
            <option value="">Choose a designer…</option>
            {(designers || []).map(designer => (
              <option key={designer.id} value={designer.id}>{designer.name}</option>
            ))}
          </select>
        </label>
        <label style={{ display: 'block' }}>
          <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Due date</span>
          <input type="date" className="form-input" value={dueDate}
                 onChange={(e) => setDueDate(e.target.value)} />
        </label>
      </div>
      <label style={{ display: 'block', marginTop: '12px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Brief (optional)</span>
        <textarea className="form-input" rows={2} value={brief}
                  placeholder="What are you asking for, beyond the spec?"
                  onChange={(e) => setBrief(e.target.value)} />
      </label>
      <button type="submit" className="btn-primary" disabled={busy || !jobId || !designerId}
              style={{ marginTop: '12px' }}>
        {busy ? 'Assigning…' : 'Assign'}
      </button>
    </form>
  );
}

/** The designer's end: choose one of your designs and hand it back. */
function SubmitPanel({ assignment, designs, onSubmitted, onError }) {
  const [designId, setDesignId] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!designId) return;
    setBusy(true);
    try {
      await api.submitDesignAssignment(assignment.id, designId, note);
      onSubmitted();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy(false);
    }
  };

  if (!designs.length) {
    return (
      <p style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '10px' }}>
        Upload a design in the Design Studio first, then submit it here.
      </p>
    );
  }

  return (
    <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'flex-end' }}>
      <label style={{ flex: '1 1 200px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Your design</span>
        <select className="form-input" value={designId} onChange={(e) => setDesignId(e.target.value)}>
          <option value="">Choose a design…</option>
          {designs.map(design => (
            <option key={design.id} value={design.id}>{design.title}</option>
          ))}
        </select>
      </label>
      <label style={{ flex: '2 1 240px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Note (optional)</span>
        <input className="form-input" value={note} onChange={(e) => setNote(e.target.value)}
               placeholder="Anything the owner should know" />
      </label>
      <button className="btn-primary" disabled={busy || !designId} onClick={submit}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
        <Send size={14} /> {busy ? 'Submitting…' : 'Submit design'}
      </button>
    </div>
  );
}

function AssignmentCard({ assignment, isSupervisor, designs, onChanged, onError }) {
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const design = assignment.design_detail;

  const review = async (decision) => {
    setBusy(true);
    try {
      await api.reviewDesignAssignment(assignment.id, decision, note);
      setNote('');
      onChanged();
    } catch (error) {
      onError(error.message);
    } finally {
      setBusy(false);
    }
  };

  // The spec is what a designer needs to do the work at all, so it is shown to
  // them rather than left behind on an order screen their role cannot open.
  const spec = assignment.spec || {};
  const measurements = assignment.measurements || {};

  return (
    <div className="content-card" style={{ marginBottom: '12px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
        <div>
          <h4 style={{ margin: 0 }}>{assignment.garment_name}</h4>
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '3px' }}>
            {assignment.order_id || assignment.order_ref}
            {isSupervisor && assignment.customer_name ? ` · ${assignment.customer_name}` : ''}
            {isSupervisor ? ` · ${assignment.designer_name}` : ''}
            {assignment.due_date ? ` · due ${formatDate(assignment.due_date)}` : ''}
          </div>
        </div>
        <StatusPill status={assignment.status} />
      </div>

      {assignment.brief && (
        <p style={{ fontSize: '13px', marginTop: '10px' }}>{assignment.brief}</p>
      )}

      {!isSupervisor && (Object.keys(spec).length > 0 || Object.keys(measurements).length > 0) && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginTop: '10px' }}>
          {Object.entries({ ...spec, ...measurements })
            // Material fields hold inventory-item UUIDs; a designer cannot read
            // a UUID and the materials themselves are the store's concern.
            .filter(([, value]) => !/^[0-9a-f]{8}-[0-9a-f]{4}/.test(String(value)))
            .map(([key, value]) => (
            <span key={key} style={{
              fontSize: '11px', padding: '2px 8px', borderRadius: '4px',
              background: 'rgba(255,255,255,0.05)', color: 'var(--text-secondary)',
            }}>
              {key.replace(/_/g, ' ')}: {String(value)}
            </span>
          ))}
        </div>
      )}

      {assignment.review_note && assignment.status === 'CHANGES_REQUESTED' && (
        <p style={{
          fontSize: '12px', marginTop: '10px', padding: '8px 10px', borderRadius: '6px',
          background: 'rgba(240,136,62,0.12)', color: '#f0883e',
        }}>
          <AlertCircle size={12} style={{ verticalAlign: '-2px' }} /> {assignment.review_note}
        </p>
      )}

      {design && (
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '12px' }}>
          {design.image_url && (
            <img src={resolveMediaUrl(design.image_url)} alt={design.title}
                 style={{ width: '56px', height: '56px', objectFit: 'cover', borderRadius: '6px' }} />
          )}
          <div>
            <div style={{ fontWeight: 600, fontSize: '13px' }}>{design.title}</div>
            {assignment.submission_note && (
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                {assignment.submission_note}
              </div>
            )}
          </div>
        </div>
      )}

      {/* A designer submits while the work is theirs to do -- assigned, or sent
          back for changes. Approved work is finished and offers no control. */}
      {!isSupervisor && ['ASSIGNED', 'CHANGES_REQUESTED', 'SUBMITTED'].includes(assignment.status) && (
        <SubmitPanel assignment={assignment} designs={designs}
                     onSubmitted={onChanged} onError={onError} />
      )}

      {isSupervisor && assignment.status === 'SUBMITTED' && (
        <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'flex-end' }}>
          <label style={{ flex: '1 1 240px' }}>
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>Note (optional)</span>
            <input className="form-input" value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder="What needs changing?" />
          </label>
          <button className="btn-primary" disabled={busy} onClick={() => review('approve')}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <Check size={14} /> Approve
          </button>
          <button className="btn-secondary" disabled={busy} onClick={() => review('changes')}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <RotateCcw size={14} /> Request changes
          </button>
        </div>
      )}
    </div>
  );
}

export default function DesignWork({ currentUser }) {
  const isSupervisor = ['Owner', 'Master'].includes(currentUser?.role);

  const [assignments, setAssignments] = useState([]);
  const [designers, setDesigners] = useState([]);
  const [orders, setOrders] = useState([]);
  const [myDesigns, setMyDesigns] = useState([]);
  const [openOnly, setOpenOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setError('');
    try {
      const rows = await api.getDesignAssignments(openOnly ? { open: '1' } : {});
      setAssignments(rows.results || rows || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [openOnly]);

  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    // Supervisors need the pickers to assign with. A designer must not be
    // pulling the order book down just to render a page, so neither call is
    // made for the role that has no use for it.
    if (!isSupervisor) return;
    api.getDesigners().then(d => setDesigners(d.results || d || [])).catch(() => {});
    api.getOpenOrders().then(o => setOrders(o.results || o || [])).catch(() => {});
  }, [isSupervisor]);

  // A designer's own library, to submit from. Their id comes off their own
  // assignments rather than from a separate profile call -- every row in this
  // list is theirs by construction, so the first one already names them. Uploads
  // are credited to the uploader's profile by default (DesignAssetViewSet.create),
  // which is what makes this filter find their own work.
  const myDesignerId = assignments[0]?.designer || null;
  useEffect(() => {
    if (isSupervisor || !myDesignerId) return;
    api.getDesignLibrary({ designer: myDesignerId })
      .then(d => setMyDesigns(d.results || d || []))
      .catch(() => {});
  }, [isSupervisor, myDesignerId]);

  const heading = isSupervisor ? 'Design work' : 'My design work';

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px', flexWrap: 'wrap', gap: '10px' }}>
        <h2 style={{ margin: 0 }}>{heading}</h2>
        <label style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} />
          Only work still open
        </label>
      </div>

      {error && (
        <div className="content-card" style={{ marginBottom: '12px', color: '#f85149' }}>
          <AlertCircle size={14} style={{ verticalAlign: '-2px' }} /> {error}
        </div>
      )}

      {isSupervisor && (
        <AssignPanel orders={orders} designers={designers}
                     onAssigned={load} onError={setError} />
      )}

      {loading ? (
        <p style={{ color: 'var(--text-secondary)' }}>Loading…</p>
      ) : assignments.length === 0 ? (
        <div className="content-card" style={{ textAlign: 'center', padding: '32px' }}>
          <ClipboardList size={28} style={{ color: 'var(--text-secondary)' }} />
          <p style={{ marginTop: '10px', color: 'var(--text-secondary)' }}>
            {isSupervisor
              ? 'No design work outstanding. Assign a garment above to get started.'
              : 'Nothing on your desk right now.'}
          </p>
        </div>
      ) : (
        assignments.map(assignment => (
          <AssignmentCard key={assignment.id} assignment={assignment}
                          isSupervisor={isSupervisor} designs={myDesigns}
                          onChanged={load} onError={setError} />
        ))
      )}
    </div>
  );
}
