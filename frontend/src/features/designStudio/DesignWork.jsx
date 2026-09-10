import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle, Calendar, Check, ChevronRight, ClipboardList, Clock, FileText, RotateCcw, Send, Shirt, User, UserPlus,
} from 'lucide-react';

import { api } from '../../services/api';
import { orderRef } from '../../services/format';
import { resolveMediaUrl } from '../../services/media';
import { useLanguage } from '../../i18n/LanguageContext.jsx';
import { AvatarInitials, Field, FormSection, SearchBox, SectionCard } from '../../components/ui/Atelier';

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

// tone maps to a .ui-badge modifier so the pill uses the design system's
// contrast-checked colour pairs, not a raw hex on a `${colour}1f` alpha tint
// (bright shades tuned for a dark theme, low-contrast on the light one).
const STATUS_STYLE = {
  ASSIGNED: { label: 'Assigned', tone: 'neutral', icon: ClipboardList },
  SUBMITTED: { label: 'Awaiting review', tone: 'info', icon: Clock },
  APPROVED: { label: 'Approved', tone: 'success', icon: Check },
  CHANGES_REQUESTED: { label: 'Changes requested', tone: 'warning', icon: RotateCcw },
};

function StatusPill({ status }) {
  const { t } = useLanguage();
  const style = STATUS_STYLE[status] || { label: status, tone: 'neutral', icon: ClipboardList };
  const keyMap = {
    ASSIGNED: 'assigned',
    SUBMITTED: 'awaitingReview',
    APPROVED: 'approved',
    CHANGES_REQUESTED: 'changesRequested'
  };
  const label = keyMap[status] ? t(`designWorkPage.${keyMap[status]}`, style.label) : style.label;
  const Icon = style.icon;
  return (
    <span className={`ui-badge ui-badge--${style.tone}`} style={{ gap: '5px', whiteSpace: 'nowrap' }}>
      <Icon size={12} /> {label}
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
  const { t } = useLanguage();
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
      label: `${orderRef(order)} · ${job.template_name || 'Custom garment'}`,
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

  const reset = () => { setJobId(''); setDesignerId(''); setBrief(''); setDueDate(''); };

  return (
    <form onSubmit={submit} style={{ marginBottom: 'var(--space-4)' }}>
      <FormSection icon={UserPlus} tone="green" title={t('designWorkPage.assignDesignWork', 'Assign Design Work')}
                   subtitle="Select a garment, assign a designer, set a due date and add any notes."
                   style={{ background: 'var(--tone-green-bg)', borderColor: 'var(--tone-green-line)' }}>
        <div className="at-form-grid at-form-grid--3">
          <Field label={t('designWorkPage.garment', 'Garment')} required icon={Shirt}>
            <select className="form-input" value={jobId} required onChange={(e) => setJobId(e.target.value)}>
              <option value="">{t('designWorkPage.chooseGarment', 'Choose a garment…')}</option>
              {garmentOptions.map(option => (
                <option key={option.id} value={option.id}>{option.label}</option>
              ))}
            </select>
          </Field>
          <Field label={t('designWorkPage.designer', 'Designer')} required icon={User}>
            <select className="form-input" value={designerId} required onChange={(e) => setDesignerId(e.target.value)}>
              <option value="">{t('designWorkPage.chooseDesigner', 'Choose a designer…')}</option>
              {(designers || []).map(designer => (
                <option key={designer.id} value={designer.id}>{designer.name}</option>
              ))}
            </select>
          </Field>
          <Field label={t('designWorkPage.dueDate', 'Due date')} icon={Calendar}>
            <input type="date" className="form-input" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </Field>
        </div>
        <Field label={t('designWorkPage.briefOptional', 'Brief / Notes (optional)')} icon={FileText}>
          <textarea className="form-input" rows={3} value={brief}
                    placeholder={t('designWorkPage.briefPlaceholder', 'What are you asking for, beyond the spec?')}
                    onChange={(e) => setBrief(e.target.value)} />
        </Field>
        <div className="at-field-counter" style={{ marginTop: '-8px' }}>{brief.length} characters</div>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
          <button type="button" className="btn-secondary" onClick={reset} disabled={busy}>Reset</button>
          <button type="submit" className="btn-primary" disabled={busy || !jobId || !designerId}>
            <Send size={15} /> {busy ? t('designWorkPage.assigningBtn', 'Assigning…') : t('designWorkPage.assignBtn', 'Assign Work')}
          </button>
        </div>
      </FormSection>
    </form>
  );
}

/** The designer's end: choose one of your designs and hand it back. */
function SubmitPanel({ assignment, designs, onSubmitted, onError }) {
  const { t } = useLanguage();
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
        {t('designWorkPage.uploadDesignFirst', 'Upload a design in the Design Studio first, then submit it here.')}
      </p>
    );
  }

  return (
    <div style={{ marginTop: '12px', display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'flex-end' }}>
      <label style={{ flex: '1 1 200px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{t('designWorkPage.yourDesign', 'Your design')}</span>
        <select className="form-input" value={designId} onChange={(e) => setDesignId(e.target.value)}>
          <option value="">{t('designWorkPage.chooseDesign', 'Choose a design…')}</option>
          {designs.map(design => (
            <option key={design.id} value={design.id}>{design.title}</option>
          ))}
        </select>
      </label>
      <label style={{ flex: '2 1 240px' }}>
        <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{t('designWorkPage.noteOptional', 'Note (optional)')}</span>
        <input className="form-input" value={note} onChange={(e) => setNote(e.target.value)}
               placeholder={t('designWorkPage.notePlaceholderDesigner', 'Anything the owner should know')} />
      </label>
      <button className="btn-primary" disabled={busy || !designId} onClick={submit}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
        <Send size={14} /> {busy ? t('designWorkPage.submittingBtn', 'Submitting…') : t('designWorkPage.submitDesignBtn', 'Submit design')}
      </button>
    </div>
  );
}

function AssignmentCard({ assignment, isSupervisor, designs, onChanged, onError, embedded = false }) {
  const { t } = useLanguage();
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
    <div className={embedded ? '' : 'ui-card'} style={embedded ? {} : { marginBottom: '12px', padding: 'var(--space-5)' }}>
      {!embedded && (
        <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px', flexWrap: 'wrap' }}>
          <div>
            <h4 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontSize: 'var(--text-md)', fontWeight: 600, color: 'var(--text-primary)' }}>{assignment.garment_name}</h4>
            <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '3px' }}>
              {assignment.order_reference || assignment.order_id || assignment.order_ref}
              {isSupervisor && assignment.customer_name ? ` · ${assignment.customer_name}` : ''}
              {isSupervisor ? ` · ${assignment.designer_name}` : ''}
              {assignment.due_date ? ` · due ${formatDate(assignment.due_date)}` : ''}
            </div>
          </div>
          <StatusPill status={assignment.status} />
        </div>
      )}

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
              fontSize: '11px', padding: '2px 8px', borderRadius: 'var(--radius-sm)',
              background: 'var(--surface-inset)', border: '1px solid var(--border-color)', color: 'var(--text-secondary)',
            }}>
              {key.replace(/_/g, ' ')}: {String(value)}
            </span>
          ))}
        </div>
      )}

      {assignment.review_note && assignment.status === 'CHANGES_REQUESTED' && (
        <p style={{
          fontSize: '12px', marginTop: '10px', padding: '8px 10px', borderRadius: 'var(--radius-md)',
          background: 'var(--warning-bg)', color: 'var(--warning-color)',
        }}>
          <AlertCircle size={12} style={{ verticalAlign: '-2px' }} /> {assignment.review_note}
        </p>
      )}

      {design && (
        <div style={{ display: 'flex', gap: '10px', alignItems: 'center', marginTop: '12px' }}>
          {design.image_url && (
            <img src={resolveMediaUrl(design.image_url)} alt={design.title}
                 style={{ width: '56px', height: '56px', objectFit: 'cover', borderRadius: 'var(--radius-sm)' }} />
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
            <span style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{t('designWorkPage.noteOptional', 'Note (optional)')}</span>
            <input className="form-input" value={note} onChange={(e) => setNote(e.target.value)}
                   placeholder={t('designWorkPage.notePlaceholderSupervisor', 'What needs changing?')} />
          </label>
          <button className="btn-primary" disabled={busy} onClick={() => review('approve')}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <Check size={14} /> {t('designWorkPage.approveBtn', 'Approve')}
          </button>
          <button className="btn-secondary" disabled={busy} onClick={() => review('changes')}
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
            <RotateCcw size={14} /> {t('designWorkPage.requestChangesBtn', 'Request changes')}
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
    api.getOrders().then(o => setOrders(o.results || o || [])).catch(() => {});
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

  const { t } = useLanguage();
  const [search, setSearch] = useState('');
  const [openRow, setOpenRow] = useState(null);

  const needle = search.trim().toLowerCase();
  const shown = needle
    ? assignments.filter((a) => [a.garment_name, a.designer_name, a.customer_name, a.order_reference, a.order_id]
        .some((v) => (v || '').toLowerCase().includes(needle)))
    : assignments;

  return (
    <div className="at-stack">
      {/* The page title + role-specific subtitle live in the page head (App
          renders them for this tab), so this row carries only the filter. */}
      <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center', flexWrap: 'wrap', gap: '10px', marginTop: 'calc(-1 * var(--space-4))' }}>
        <label className="at-check-pill">
          <Clock size={14} style={{ color: 'var(--text-secondary)' }} />
          <input type="checkbox" checked={openOnly} onChange={(e) => setOpenOnly(e.target.checked)} />
          {t('designWorkPage.onlyOpen', 'Only work still open')}
        </label>
      </div>

      {error && (
        <div className="ui-card" style={{ color: 'var(--danger-color)', padding: 'var(--space-3) var(--space-4)' }}>
          <AlertCircle size={14} style={{ verticalAlign: '-2px' }} /> {error}
        </div>
      )}

      {isSupervisor && (
        <AssignPanel orders={orders} designers={designers}
                     onAssigned={load} onError={setError} />
      )}

      {loading ? (
        <p style={{ color: 'var(--text-secondary)' }}>{t('common.loading', 'Loading…')}</p>
      ) : isSupervisor ? (
        <SectionCard icon={ClipboardList} tone="green" title="Assigned Design Work"
                     subtitle="Track all design assignments and their status.">
          <div className="at-toolbar" style={{ margin: '0 0 var(--space-3)' }}>
            <SearchBox value={search} onChange={setSearch} placeholder="Search by garment, designer or customer…" style={{ maxWidth: '420px' }} />
            <span className="at-row-sub">{shown.length} of {assignments.length}</span>
          </div>
          {shown.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 'var(--space-6)' }}>
              <ClipboardList size={28} style={{ color: 'var(--text-secondary)' }} />
              <p style={{ marginTop: '10px', color: 'var(--text-secondary)' }}>
                {assignments.length === 0
                  ? t('designWorkPage.noWorkSupervisor', 'No design work outstanding. Assign a garment above to get started.')
                  : 'Nothing matches that search.'}
              </p>
            </div>
          ) : (
            <div className="at-table-wrap">
              <table className="at-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Garment</th>
                    <th>Designer</th>
                    <th>Due Date</th>
                    <th>Status</th>
                    <th>Notes</th>
                    <th aria-label="Open" />
                  </tr>
                </thead>
                <tbody>
                  {shown.map((assignment) => {
                    const isOpen = openRow === assignment.id;
                    const design = assignment.design_detail;
                    const toggle = () => setOpenRow(isOpen ? null : assignment.id);
                    return (
                      <React.Fragment key={assignment.id}>
                        <tr onClick={toggle} style={{ cursor: 'pointer' }}
                            aria-expanded={isOpen}>
                          <td style={{ fontWeight: 700 }}>{assignment.order_reference || assignment.order_id || assignment.order_ref}</td>
                          <td>
                            <span className="at-cell-person">
                              <span className="at-thumb at-tile--amber">
                                {design?.image_url ? <img src={resolveMediaUrl(design.image_url)} alt="" /> : <Shirt size={18} />}
                              </span>
                              <span style={{ minWidth: 0 }}>
                                <span className="at-row-title" style={{ display: 'block' }}>{assignment.garment_name}</span>
                                {assignment.customer_name && <span className="at-row-sub">Customer: {assignment.customer_name}</span>}
                              </span>
                            </span>
                          </td>
                          <td>
                            <span className="at-cell-person">
                              <AvatarInitials name={assignment.designer_name} size={32} />
                              <span>{assignment.designer_name}</span>
                            </span>
                          </td>
                          <td style={{ whiteSpace: 'nowrap' }}>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                              <Calendar size={14} style={{ color: 'var(--text-secondary)' }} />
                              {assignment.due_date ? formatDate(assignment.due_date) : '—'}
                            </span>
                          </td>
                          <td><StatusPill status={assignment.status} /></td>
                          <td style={{ color: 'var(--text-secondary)', maxWidth: '260px' }}>
                            <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {assignment.brief || assignment.submission_note || '—'}
                            </span>
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <ChevronRight size={16} style={{ color: 'var(--text-muted)', transform: isOpen ? 'rotate(90deg)' : 'none', transition: 'transform .15s' }} />
                          </td>
                        </tr>
                        {isOpen && (
                          <tr>
                            <td colSpan={7} style={{ background: 'var(--surface-2)' }}>
                              <AssignmentCard assignment={assignment} isSupervisor designs={myDesigns}
                                              onChanged={load} onError={setError} embedded />
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </SectionCard>
      ) : assignments.length === 0 ? (
        <div className="ui-card" style={{ textAlign: 'center', padding: '32px' }}>
          <ClipboardList size={28} style={{ color: 'var(--text-secondary)' }} />
          <p style={{ marginTop: '10px', color: 'var(--text-secondary)' }}>
            {t('designWorkPage.noWorkDesigner', 'Nothing on your desk right now.')}
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
