/**
 * Staff performance: how the floor is working, and the reviews written about it.
 *
 * Operational only. Nothing on this screen is compensation, because the
 * endpoint behind it has no access to a rate, a payslip or a ledger -- which is
 * what lets a Master read it without a filter anyone could forget.
 *
 * A metric arrives as {value, available, reason}. `available: false` means
 * there was no data, which is NOT the same as zero: reporting 0% completion for
 * somebody who was never assigned work would accuse them of failing work they
 * never had. Every figure here renders through `Metric`, which honours that.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { AlertCircle, Check, ChevronLeft, Lock, Star, X } from 'lucide-react';

import { api } from '../../services/api';

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
};

const RATINGS = [
  [1, 'Needs significant improvement'],
  [2, 'Needs improvement'],
  [3, 'Meets expectations'],
  [4, 'Exceeds expectations'],
  [5, 'Outstanding'],
];

const COMPONENTS = [
  ['productivity_rating', 'Productivity'],
  ['quality_rating', 'Quality'],
  ['timeliness_rating', 'Timeliness'],
  ['attendance_rating', 'Attendance'],
  ['reliability_rating', 'Reliability'],
];

const LABELS = {
  'attendance.worked_hours': 'Hours worked',
  'attendance.days_attended': 'Days attended',
  'attendance.average_hours_per_day': 'Avg hours/day',
  'productivity.in_period': 'Worked on',
  'productivity.completed': 'Work completed',
  'productivity.completion_rate': 'Completion',
  'productivity.performed_by_them': 'Done by them',
  'timeliness.on_time_rate': 'On time',
  'timeliness.on_time': 'On-time jobs',
  'timeliness.overdue': 'Overdue',
  'timeliness.average_delay_hours': 'Avg delay',
  'quality.inspected': 'Inspections done',
  'quality.checked': 'Their work checked',
  'quality.pass_rate': 'QC pass rate',
  'quality.rework_rate': 'Rework rate',
  'reliability.outstanding_assignments': 'Outstanding',
  'reliability.overdue_open_assignments': 'Overdue open',
  'reliability.completion_consistency': 'Consistency',
};

const SUFFIX = {
  completion_rate: '%', on_time_rate: '%', pass_rate: '%', rework_rate: '%',
  completion_consistency: '%', worked_hours: 'h', average_hours_per_day: 'h',
  average_delay_hours: 'h',
};

const todayISO = () => new Date().toISOString().slice(0, 10);
const daysAgoISO = (n) =>
  new Date(Date.now() - n * 86400000).toISOString().slice(0, 10);
const dayText = (iso) =>
  iso ? new Date(iso).toLocaleDateString([], { day: 'numeric', month: 'short', year: 'numeric' }) : '—';

/** One figure, honouring "no data" as distinct from zero. */
function Metric({ name, metric, label }) {
  if (!metric) return null;
  const text = metric.available
    ? `${metric.value}${SUFFIX[name] || ''}`
    : 'No data';
  return (
    <div>
      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{label}</div>
      <div style={{
        fontWeight: 600,
        color: metric.available ? 'inherit' : 'var(--text-muted)',
        fontStyle: metric.available ? 'normal' : 'italic',
      }}
        title={metric.available ? undefined : metric.reason}
      >
        {text}
      </div>
    </div>
  );
}

function Banner({ text, tone = 'info', icon: Icon }) {
  const c = tone === 'error'
    ? { bg: 'rgba(220,80,60,0.12)', bd: 'rgba(220,80,60,0.35)', fg: '#c0392b' }
    : { bg: 'rgba(140,140,140,0.10)', bd: 'var(--border-color, rgba(255,255,255,0.08))', fg: 'var(--text-secondary)' };
  return (
    <div style={{
      background: c.bg, border: `1px solid ${c.bd}`, color: c.fg,
      borderRadius: '8px', padding: '10px 12px', fontSize: '12.5px',
      marginBottom: '14px', display: 'flex', gap: '8px', alignItems: 'flex-start',
    }}>
      {Icon && <Icon size={15} style={{ flexShrink: 0, marginTop: '1px' }} />}
      <span>{text}</span>
    </div>
  );
}

function Modal({ title, onClose, children, width = '580px' }) {
  return (
    <div onClick={onClose} style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1200,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px',
    }}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: 'var(--modal-bg, #fff)', borderRadius: '12px', width: '100%',
        maxWidth: width, maxHeight: '88vh', overflowY: 'auto', padding: '24px',
        border: '1px solid var(--border-color)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', marginBottom: '18px' }}>
          <h3 style={{ fontSize: '18px', fontWeight: 600, margin: 0 }}>{title}</h3>
          <button type="button" className="close-btn" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function StatusPill({ status }) {
  const tone = status === 'ACKNOWLEDGED'
    ? { bg: 'rgba(47,74,122,0.15)', fg: '#2f4a7a', label: 'Acknowledged' }
    : status === 'FINAL'
      ? { bg: 'rgba(46,180,120,0.15)', fg: '#1e8a5c', label: 'Finalised' }
      : { bg: 'rgba(140,140,140,0.15)', fg: 'var(--text-secondary)', label: 'Draft' };
  return (
    <span style={{
      fontSize: '11px', fontWeight: 600, letterSpacing: '0.04em',
      textTransform: 'uppercase', padding: '3px 8px', borderRadius: '4px',
      background: tone.bg, color: tone.fg, display: 'inline-flex',
      alignItems: 'center', gap: '4px',
    }}>
      {status !== 'DRAFT' && <Lock size={10} />} {tone.label}
    </span>
  );
}

function ReviewForm({ member, period, existing, onCancel, onSaved }) {
  const [form, setForm] = useState(() => ({
    review_type: existing?.review_type || 'MONTHLY',
    period_start: existing?.period_start || period.start,
    period_end: existing?.period_end || period.end,
    productivity_rating: existing?.productivity_rating ?? '',
    quality_rating: existing?.quality_rating ?? '',
    timeliness_rating: existing?.timeliness_rating ?? '',
    attendance_rating: existing?.attendance_rating ?? '',
    reliability_rating: existing?.reliability_rating ?? '',
    strengths: existing?.strengths || '',
    improvement_areas: existing?.improvement_areas || '',
    goals: existing?.goals || '',
    manager_notes: existing?.manager_notes || '',
  }));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = { ...form };
      COMPONENTS.forEach(([key]) => {
        payload[key] = payload[key] === '' ? null : Number(payload[key]);
      });
      if (existing) await api.updateReview(existing.id, payload);
      else await api.createReview({ ...payload, staff: member.staff });
      onSaved();
    } catch (err) {
      setError(err.message || 'Could not save this review.');
    } finally {
      setSaving(false);
    }
  };

  const label = { fontSize: '12px', color: 'var(--text-secondary)' };
  return (
    <form onSubmit={submit}>
      {error && <Banner tone="error" icon={AlertCircle} text={error} />}
      {!existing && (
        <div className="mobile-stack-grid"
             style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px',
                      marginBottom: '14px' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={label} htmlFor="rv-type">Period type</label>
            <select id="rv-type" value={form.review_type} onChange={set('review_type')}>
              <option value="WEEKLY">Weekly</option>
              <option value="MONTHLY">Monthly</option>
              <option value="QUARTERLY">Quarterly</option>
              <option value="CUSTOM">Custom</option>
            </select>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={label} htmlFor="rv-start">From</label>
            <input id="rv-start" type="date" value={form.period_start}
                   onChange={set('period_start')} required />
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={label} htmlFor="rv-end">To</label>
            <input id="rv-end" type="date" value={form.period_end}
                   onChange={set('period_end')} required />
          </div>
        </div>
      )}

      <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
                    color: 'var(--text-muted)', margin: '4px 0 8px' }}>
        Ratings · leave blank to skip
      </div>
      <div className="mobile-stack-grid"
           style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        {COMPONENTS.map(([key, text]) => (
          <div key={key} style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={label} htmlFor={`rv-${key}`}>{text}</label>
            <select id={`rv-${key}`} value={form[key]} onChange={set(key)}>
              <option value="">Not rated</option>
              {RATINGS.map(([n, desc]) => (
                <option key={n} value={n}>{n} — {desc}</option>
              ))}
            </select>
          </div>
        ))}
      </div>

      {[['strengths', 'Strengths'], ['improvement_areas', 'Areas to improve'],
        ['goals', 'Goals'], ['manager_notes', 'Notes']].map(([key, text]) => (
        <div key={key} style={{ display: 'flex', flexDirection: 'column',
                                gap: '5px', marginTop: '14px' }}>
          <label style={label} htmlFor={`rv-${key}`}>{text}</label>
          <textarea id={`rv-${key}`} rows={2} value={form[key]} onChange={set(key)} />
        </div>
      ))}

      <p style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '14px' }}>
        The overall score is the average of the ratings you give; anything left
        blank is left out rather than counted as zero.
      </p>
      <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '18px' }}>
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : existing ? 'Save draft' : 'Create review'}
        </button>
      </div>
    </form>
  );
}

function StaffDetail({ member, reviews, isOwner, canReview, onBack, onChanged }) {
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try { await fn(); onChanged(); }
    catch (err) { setError(err.message || 'That did not work.'); }
    finally { setBusy(false); }
  };

  const groups = [
    ['attendance', 'Attendance', ['worked_hours', 'days_attended', 'average_hours_per_day']],
    ['productivity', 'Productivity', ['in_period', 'completed', 'completion_rate']],
    ['timeliness', 'Timeliness', ['on_time', 'overdue', 'on_time_rate']],
    ['quality', 'Quality', ['inspected', 'checked', 'pass_rate', 'rework_rate']],
    ['reliability', 'Reliability', ['outstanding_assignments', 'overdue_open_assignments',
                                    'completion_consistency']],
  ];

  return (
    <>
      <button type="button" className="btn-secondary" onClick={onBack}
              style={{ marginBottom: '14px', display: 'inline-flex',
                       alignItems: 'center', gap: '6px', minHeight: '38px' }}>
        <ChevronLeft size={15} /> Back to team
      </button>

      {error && <Banner tone="error" icon={AlertCircle} text={error} />}

      <div style={{ ...panel, padding: '18px', marginBottom: '14px' }}>
        <div style={{ fontSize: '18px', fontWeight: 600 }}>{member.staff_name}</div>
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
          {member.role} · {dayText(member.period_start)} to {dayText(member.period_end)}
        </div>
        {!member.employed_in_period && (
          <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '8px' }}>
            Not employed during this period.
          </div>
        )}
      </div>

      {groups.map(([key, title, names]) => (
        <div key={key} style={{ ...panel, padding: '16px 18px', marginBottom: '12px' }}>
          <div style={{ fontSize: '11px', letterSpacing: '0.08em',
                        textTransform: 'uppercase', color: 'var(--text-muted)',
                        marginBottom: '10px' }}>
            {title}
          </div>
          <div className="mobile-stack-grid"
               style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
            {names.map((name) => (
              <Metric key={name} name={name} metric={member[key]?.[name]}
                      label={LABELS[`${key}.${name}`] || name} />
            ))}
          </div>
        </div>
      ))}

      <div style={{ display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', margin: '18px 0 10px' }}>
        <h4 style={{ fontSize: '13px', fontWeight: 600, margin: 0 }}>Reviews</h4>
        {canReview && (
          <button type="button" className="btn-secondary" onClick={() => setCreating(true)}
                  style={{ minHeight: '36px', fontSize: '12px' }}>
            New review
          </button>
        )}
      </div>

      {reviews.length === 0 ? (
        <div style={{ ...panel, padding: '24px', textAlign: 'center',
                      color: 'var(--text-secondary)', fontSize: '13px' }}>
          No reviews yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {reviews.map((r) => (
            <div key={r.id} style={{ ...panel, padding: '14px 16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                            gap: '10px', flexWrap: 'wrap' }}>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '14px' }}>
                    {dayText(r.period_start)} – {dayText(r.period_end)}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                    {r.review_type} · as {r.role_snapshot || r.staff_role || '—'}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontWeight: 600, fontSize: '16px',
                                display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                    {r.overall_rating ? <><Star size={13} /> {r.overall_rating}</> : '—'}
                  </div>
                  <div><StatusPill status={r.status} /></div>
                </div>
              </div>

              <div className="mobile-stack-grid"
                   style={{ display: 'grid', gridTemplateColumns: 'repeat(5, 1fr)',
                            gap: '8px', marginTop: '12px', paddingTop: '12px',
                            borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))' }}>
                {COMPONENTS.map(([key, text]) => (
                  <div key={key}>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{text}</div>
                    <div style={{ fontWeight: 600 }}>{r[key] ?? '—'}</div>
                  </div>
                ))}
              </div>

              {[['strengths', 'Strengths'], ['improvement_areas', 'Areas to improve'],
                ['goals', 'Goals']].filter(([k]) => r[k]).map(([k, t]) => (
                <div key={k} style={{ fontSize: '12.5px', marginTop: '8px' }}>
                  <span style={{ color: 'var(--text-muted)' }}>{t}: </span>{r[k]}
                </div>
              ))}

              <div style={{ display: 'flex', gap: '8px', marginTop: '12px', flexWrap: 'wrap' }}>
                {canReview && r.status === 'DRAFT' && (
                  <>
                    <button type="button" className="btn-secondary" disabled={busy}
                            onClick={() => setEditing(r)} style={{ minHeight: '36px' }}>
                      Edit draft
                    </button>
                    <button type="button" className="btn-primary" disabled={busy}
                            onClick={() => act(() => api.finaliseReview(r.id))}
                            style={{ minHeight: '36px', display: 'inline-flex',
                                     alignItems: 'center', gap: '5px' }}>
                      <Check size={13} /> Finalise
                    </button>
                  </>
                )}
                {!isOwner && r.status === 'FINAL' && (
                  <button type="button" className="btn-primary" disabled={busy}
                          onClick={() => act(() => api.acknowledgeReview(r.id))}
                          style={{ minHeight: '36px' }}>
                    I have read this
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {(creating || editing) && (
        <Modal title={editing ? 'Edit draft review' : `New review — ${member.staff_name}`}
               onClose={() => { setCreating(false); setEditing(null); }}>
          <ReviewForm
            member={member}
            existing={editing}
            period={{ start: member.period_start, end: member.period_end }}
            onCancel={() => { setCreating(false); setEditing(null); }}
            onSaved={() => { setCreating(false); setEditing(null); onChanged(); }}
          />
        </Modal>
      )}
    </>
  );
}

export default function Performance({ isOwner, canSeeTeam }) {
  const [start, setStart] = useState(() => daysAgoISO(29));
  const [end, setEnd] = useState(todayISO);
  const [role, setRole] = useState('');
  const [data, setData] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [openStaff, setOpenStaff] = useState(null);
  const [reloadKey, setReloadKey] = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [perf, revs] = await Promise.all([
        api.getPerformance({ start, end, role: role || undefined }),
        api.getReviews().catch(() => []),
      ]);
      setData(perf);
      setReviews(Array.isArray(revs) ? revs : []);
    } catch (err) {
      setError(err.message || 'Could not load performance.');
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [start, end, role]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load, reloadKey]);

  const reviewsByStaff = useMemo(() => {
    const map = new Map();
    reviews.forEach((r) => {
      const key = String(r.staff);
      map.set(key, [...(map.get(key) || []), r]);
    });
    return map;
  }, [reviews]);

  const roles = useMemo(() => {
    const set = new Set((data?.results || []).map((r) => r.role).filter(Boolean));
    return [...set].sort();
  }, [data]);

  if (openStaff && data) {
    const member = data.results.find((r) => String(r.staff) === String(openStaff));
    if (member) {
      return (
        <StaffDetail
          member={member}
          reviews={reviewsByStaff.get(String(openStaff)) || []}
          isOwner={isOwner}
          canReview={isOwner}
          onBack={() => setOpenStaff(null)}
          onChanged={() => setReloadKey((n) => n + 1)}
        />
      );
    }
  }

  const label = { fontSize: '12px', color: 'var(--text-secondary)' };
  return (
    <>
      <div className="mobile-stack-grid"
           style={{ display: 'grid', gridTemplateColumns: canSeeTeam ? '1fr 1fr 1fr' : '1fr 1fr',
                    gap: '12px', maxWidth: '640px', marginBottom: '16px' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={label} htmlFor="pf-start">From</label>
          <input id="pf-start" type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={label} htmlFor="pf-end">To</label>
          <input id="pf-end" type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
        </div>
        {canSeeTeam && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={label} htmlFor="pf-role">Role</label>
            <select id="pf-role" value={role} onChange={(e) => setRole(e.target.value)}>
              <option value="">All roles</option>
              {roles.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
        )}
      </div>

      {error && <Banner tone="error" icon={AlertCircle} text={error} />}

      {loading ? (
        <div style={{ padding: '28px', color: 'var(--text-muted)' }}>Loading performance…</div>
      ) : !data || data.results.length === 0 ? (
        <div style={{ ...panel, padding: '32px', textAlign: 'center',
                      color: 'var(--text-secondary)' }}>
          No staff with employment details in this period.
        </div>
      ) : (
        <>
          {!data.quality_available && (
            <Banner icon={AlertCircle} text={data.quality_note} />
          )}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {data.results.map((member) => {
              const theirReviews = reviewsByStaff.get(String(member.staff)) || [];
              const latest = theirReviews[0];
              return (
                <div
                  key={member.staff}
                  role="button"
                  tabIndex={0}
                  onClick={() => setOpenStaff(member.staff)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') setOpenStaff(member.staff);
                  }}
                  style={{ ...panel, padding: '14px 16px', cursor: 'pointer' }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between',
                                alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: '15px' }}>
                        {member.staff_name}
                      </div>
                      <div style={{ fontSize: '12px', color: 'var(--text-secondary)',
                                    marginTop: '2px' }}>
                        {member.role}
                      </div>
                    </div>
                    {latest ? (
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontWeight: 600, display: 'inline-flex',
                                      alignItems: 'center', gap: '4px' }}>
                          {latest.overall_rating
                            ? <><Star size={13} /> {latest.overall_rating}</> : '—'}
                        </div>
                        <div><StatusPill status={latest.status} /></div>
                      </div>
                    ) : (
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        No review
                      </span>
                    )}
                  </div>

                  <div
                    className="mobile-stack-grid"
                    style={{
                      display: 'grid',
                      gridTemplateColumns: `repeat(${Math.min((member.headline || []).length, 4) || 1}, 1fr)`,
                      gap: '10px', marginTop: '12px', paddingTop: '12px',
                      borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))',
                    }}
                  >
                    {(member.headline || []).slice(0, 4).map((h) => (
                      <Metric key={h.key} name={h.name} metric={h}
                              label={LABELS[h.key] || h.name} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </>
  );
}
