/**
 * Staff Management.
 *
 * Phase 1 is the roster and each person's employment terms. The Attendance,
 * Payroll and Performance tabs are declared here because they are what this
 * screen is for, and each says plainly that it is not built yet rather than
 * pretending with an empty table -- the pattern the platform console already
 * uses for specified-but-absent surfaces.
 *
 * The roster is `api.getTailors()` -- the SAME list the existing Manage Tailors
 * screen reads. There is no staff roster endpoint and there should not be one:
 * the boutique has one roster, and a second copy of it would be a second answer
 * to who works here. Employment terms are fetched separately and joined by
 * staff id, which is also what keeps rates off the roster response.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { X, Plus, Clock, Wallet, TrendingUp, Users } from 'lucide-react';

import { api } from '../../services/api';
import Attendance from './Attendance';
import Payroll from './Payroll';

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
};

const money = (n) =>
  `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

/**
 * Whether this row actually carries pay, as opposed to having had it removed.
 *
 * The API strips hourly_rate, deposit_total and deposit_weekly from anyone
 * else's record for a non-owner, so a supervisor's copy of a colleague's row
 * simply has no such keys. Rendering it anyway would put `money(undefined)`
 * on screen -- and money() coerces to 0, so the card would state that a
 * colleague earns ₹0 an hour. Absent is not zero, and saying so wrongly about
 * someone's wage is worse than saying nothing.
 */
const showsPay = (terms) => terms?.hourly_rate !== undefined;

const EMPLOYMENT_TYPES = [
  ['FULL_TIME', 'Full time'],
  ['PART_TIME', 'Part time'],
  ['CONTRACT', 'Contract'],
  ['APPRENTICE', 'Apprentice'],
];

const employmentLabel = (value) =>
  (EMPLOYMENT_TYPES.find(([key]) => key === value) || [null, '—'])[1];

function Modal({ title, onClose, children, width = '560px' }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.45)', zIndex: 1200,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--modal-bg, #fff)', borderRadius: '12px', width: '100%',
          maxWidth: width, maxHeight: '88vh', overflowY: 'auto', padding: '24px',
          border: '1px solid var(--border-color)',
        }}
      >
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: '18px',
        }}>
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

/** A tab whose domain arrives in a later phase. Says so, rather than showing nothing. */
function NotBuiltYet({ title, blurb }) {
  return (
    <div style={{ ...panel, padding: '40px 24px', textAlign: 'center' }}>
      <h3 style={{ fontSize: '16px', fontWeight: 600, margin: '0 0 8px' }}>{title}</h3>
      <p style={{ fontSize: '13px', color: 'var(--text-secondary)', margin: 0, lineHeight: 1.6 }}>
        {blurb}
      </p>
    </div>
  );
}

const EMPTY_FORM = {
  employment_type: 'FULL_TIME',
  joined_at: '',
  exit_date: '',
  hourly_rate: '',
  weekly_hours: '',
  deposit_total: '',
  deposit_weekly: '',
  phone: '',
  emergency_contact: '',
  address: '',
  notes: '',
};

/** Blank strings are not zero. Sending '' for a Decimal is a 400. */
const cleaned = (form) => {
  const payload = {};
  Object.entries(form).forEach(([key, value]) => {
    if (value !== '' && value !== null && value !== undefined) payload[key] = value;
  });
  return payload;
};

function TermsForm({ member, terms, onCancel, onSaved }) {
  const [form, setForm] = useState(() =>
    terms
      ? {
          ...EMPTY_FORM,
          ...Object.fromEntries(
            Object.keys(EMPTY_FORM).map((k) => [k, terms[k] ?? '']),
          ),
        }
      : EMPTY_FORM,
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const payload = cleaned(form);
      if (terms) {
        await api.updateStaffProfile(terms.id, payload);
      } else {
        await api.createStaffProfile({ ...payload, staff: member.id });
      }
      onSaved();
    } catch (err) {
      // Inline, never alert() -- the house rule the newer screens follow.
      setError(err.message || 'Could not save these employment details.');
    } finally {
      setSaving(false);
    }
  };

  const field = { display: 'flex', flexDirection: 'column', gap: '5px' };
  const label = { fontSize: '12px', color: 'var(--text-secondary)' };

  return (
    <form onSubmit={submit}>
      {error && (
        <div style={{
          background: 'rgba(220,80,60,0.12)', border: '1px solid rgba(220,80,60,0.35)',
          color: '#c0392b', borderRadius: '8px', padding: '10px 12px',
          fontSize: '13px', marginBottom: '14px',
        }}>
          {error}
        </div>
      )}

      {/* mobile-stack-grid: the app sets grid columns inline, which no
          stylesheet rule can beat, so the shared !important rule keys off this
          class to stack these pairs on a phone. */}
      <div
        className="mobile-stack-grid"
        style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}
      >
        <div style={field}>
          <label style={label} htmlFor="sp-type">Employment type</label>
          <select id="sp-type" value={form.employment_type} onChange={set('employment_type')}>
            {EMPLOYMENT_TYPES.map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </div>
        <div style={field}>
          <label style={label} htmlFor="sp-rate">Hourly rate (₹)</label>
          <input id="sp-rate" type="number" min="0" step="0.01"
                 value={form.hourly_rate} onChange={set('hourly_rate')} placeholder="0.00" />
        </div>

        <div style={field}>
          <label style={label} htmlFor="sp-joined">Joined on</label>
          <input id="sp-joined" type="date" value={form.joined_at} onChange={set('joined_at')} />
        </div>
        <div style={field}>
          <label style={label} htmlFor="sp-exit">Left on</label>
          <input id="sp-exit" type="date" value={form.exit_date} onChange={set('exit_date')} />
        </div>

        <div style={field}>
          <label style={label} htmlFor="sp-hours">Expected hours a week</label>
          <input id="sp-hours" type="number" min="0" step="0.5"
                 value={form.weekly_hours} onChange={set('weekly_hours')} placeholder="48" />
        </div>
        <div style={field}>
          <label style={label} htmlFor="sp-phone">Phone</label>
          <input id="sp-phone" value={form.phone} onChange={set('phone')} />
        </div>

        <div style={field}>
          <label style={label} htmlFor="sp-dep-total">Security deposit (₹)</label>
          <input id="sp-dep-total" type="number" min="0" step="0.01"
                 value={form.deposit_total} onChange={set('deposit_total')} placeholder="0.00" />
        </div>
        <div style={field}>
          <label style={label} htmlFor="sp-dep-weekly">Weekly deduction (₹)</label>
          <input id="sp-dep-weekly" type="number" min="0" step="0.01"
                 value={form.deposit_weekly} onChange={set('deposit_weekly')} placeholder="0.00" />
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '14px' }}>
        <label style={label} htmlFor="sp-emergency">Emergency contact</label>
        <input id="sp-emergency" value={form.emergency_contact}
               onChange={set('emergency_contact')} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '14px' }}>
        <label style={label} htmlFor="sp-address">Address</label>
        <textarea id="sp-address" rows={2} value={form.address} onChange={set('address')} />
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '14px' }}>
        <label style={label} htmlFor="sp-notes">Notes</label>
        <textarea id="sp-notes" rows={2} value={form.notes} onChange={set('notes')} />
      </div>

      <p style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '14px' }}>
        The weekly deduction is recovered from payroll once that is switched on, and never
        takes more than the deposit still outstanding or that week's earnings.
      </p>

      <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '18px' }}>
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : terms ? 'Save changes' : 'Create profile'}
        </button>
      </div>
    </form>
  );
}

function Roster({ isOwner, canSeeTeam }) {
  const [roster, setRoster] = useState([]);
  const [terms, setTerms] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      // Independent failures: a staff member may read their own terms but not
      // the roster, so one refusal must not blank the whole screen.
      const [people, profiles] = await Promise.all([
        canSeeTeam ? api.getTailors().catch(() => []) : Promise.resolve([]),
        api.getStaffProfiles().catch(() => []),
      ]);
      setRoster(Array.isArray(people) ? people : []);
      setTerms(Array.isArray(profiles) ? profiles : []);
    } catch (err) {
      setLoadError(err.message || 'Could not load the staff list.');
    } finally {
      setLoading(false);
    }
  }, [canSeeTeam]);

  // Deferred rather than called straight from the effect body, matching
  // InventoryPanel: refresh() sets loading state synchronously, and doing that
  // inside an effect is the cascading-render pattern React warns about.
  useEffect(() => {
    const t = setTimeout(refresh, 0);
    return () => clearTimeout(t);
  }, [refresh]);

  const termsByStaff = useMemo(() => {
    const map = new Map();
    terms.forEach((t) => map.set(String(t.staff), t));
    return map;
  }, [terms]);

  /** Owners see the roster; a staff member sees only the row their own terms name. */
  const rows = useMemo(() => {
    const source = canSeeTeam
      ? roster.map((person) => ({ member: person, terms: termsByStaff.get(String(person.id)) }))
      : terms.map((t) => ({
          member: { id: t.staff, name: t.staff_name, role: t.staff_role },
          terms: t,
        }));
    const needle = search.trim().toLowerCase();
    if (!needle) return source;
    return source.filter(({ member }) =>
      `${member.name} ${member.role}`.toLowerCase().includes(needle));
  }, [canSeeTeam, roster, terms, termsByStaff, search]);

  const withTerms = rows.filter((r) => r.terms).length;

  if (loading) {
    return <div style={{ padding: '32px', color: 'var(--text-muted)' }}>Loading staff…</div>;
  }

  return (
    <>
      {loadError && (
        <div style={{
          background: 'rgba(220,80,60,0.12)', border: '1px solid rgba(220,80,60,0.35)',
          color: '#c0392b', borderRadius: '8px', padding: '10px 12px',
          fontSize: '13px', marginBottom: '14px',
        }}>
          {loadError}
        </div>
      )}

      {canSeeTeam && (
        <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', marginBottom: '18px' }}>
          <div style={{ ...panel, padding: '16px 18px', flex: '1 1 170px' }}>
            <div style={{
              fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
              color: 'var(--text-muted)',
            }}>On the roster</div>
            <div style={{ fontSize: '22px', fontWeight: 600, marginTop: '6px' }}>{roster.length}</div>
          </div>
          <div style={{ ...panel, padding: '16px 18px', flex: '1 1 170px' }}>
            <div style={{
              fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
              color: 'var(--text-muted)',
            }}>Employment set up</div>
            <div style={{ fontSize: '22px', fontWeight: 600, marginTop: '6px' }}>
              {withTerms}
              <span style={{ fontSize: '13px', color: 'var(--text-muted)', fontWeight: 400 }}>
                {' '}of {roster.length}
              </span>
            </div>
          </div>
        </div>
      )}

      {canSeeTeam && (
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search staff by name or role"
          style={{ width: '100%', maxWidth: '340px', marginBottom: '16px' }}
        />
      )}

      {rows.length === 0 ? (
        <div style={{ ...panel, padding: '32px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          {canSeeTeam
            ? 'No staff on the roster yet. Add people in Manage Tailors, then set up their employment details here.'
            : 'Your employment details have not been set up yet. Your boutique owner can add them.'}
        </div>
      ) : (
        // Cards, not a table: a roster row is a name plus a few values, and it
        // reads correctly at 320px without a horizontal scroller.
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {rows.map(({ member, terms: t }) => (
            <div key={member.id} style={{ ...panel, padding: '14px 16px' }}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                gap: '12px', flexWrap: 'wrap',
              }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '15px' }}>{member.name}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    {member.role}
                    {t && <> · {employmentLabel(t.employment_type)}</>}
                  </div>
                </div>
                {isOwner && (
                  <button
                    type="button"
                    className={t ? 'btn-secondary' : 'btn-primary'}
                    onClick={() => setEditing({ member, terms: t })}
                  >
                    {t ? 'Edit' : <><Plus size={14} /> Set up</>}
                  </button>
                )}
              </div>

              {t && showsPay(t) && (
                <div
                  className="mobile-stack-grid"
                  style={{
                    display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px',
                    marginTop: '12px', paddingTop: '12px',
                    borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Hourly rate</div>
                    <div style={{ fontWeight: 600 }}>{money(t.hourly_rate)}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Deposit</div>
                    <div style={{ fontWeight: 600 }}>{money(t.deposit_total)}</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Weekly deduction</div>
                    <div style={{ fontWeight: 600 }}>{money(t.deposit_weekly)}</div>
                  </div>
                </div>
              )}

              {t && !showsPay(t) && (
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '10px' }}>
                  Employment set up. Pay details are visible to the boutique owner only.
                </div>
              )}

              {!t && (
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '10px' }}>
                  No employment details yet — this person works exactly as before.
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {editing && (
        <Modal
          title={editing.terms
            ? `Employment details — ${editing.member.name}`
            : `Set up ${editing.member.name}`}
          onClose={() => setEditing(null)}
        >
          <TermsForm
            member={editing.member}
            terms={editing.terms}
            onCancel={() => setEditing(null)}
            onSaved={() => { setEditing(null); refresh(); }}
          />
        </Modal>
      )}
    </>
  );
}

const TABS = [
  { key: 'roster', label: 'Staff', icon: Users },
  { key: 'attendance', label: 'Attendance', icon: Clock },
  { key: 'payroll', label: 'Payroll', icon: Wallet },
  { key: 'performance', label: 'Performance', icon: TrendingUp },
];

export default function StaffPanel({ currentUser }) {
  // Mirrors the backend: the owner manages, a Master supervises (reads the team
  // without its pay), everyone else sees themselves. This is UX only -- every
  // one of these boundaries is enforced again server-side, and the buttons
  // hidden here are refused there too.
  const isOwner = !currentUser?.role || currentUser.role === 'Owner';
  const isSupervisor = currentUser?.role === 'Master';
  const canSeeTeam = isOwner || isSupervisor;

  // A tailor opens this to record their hours, not to browse a roster of one.
  // Managers open it on the team. Same screen, different first thing.
  const [tab, setTab] = useState(canSeeTeam ? 'roster' : 'attendance');

  return (
    <>
      <header className="portal-header">
        <div className="portal-header-left">
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
              {canSeeTeam ? 'Staff Management' : 'My Attendance'}
            </h1>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
              {canSeeTeam
                ? 'Employment terms, attendance, payroll and performance for your team.'
                : 'Check in and out, and see the hours recorded for you.'}
            </p>
          </div>
        </div>
      </header>

      <div style={{
        display: 'flex', gap: '6px', flexWrap: 'wrap', margin: '18px 0',
        borderBottom: '1px solid var(--border-color, rgba(255,255,255,0.08))',
        paddingBottom: '10px',
      }}>
        {(isOwner
            ? TABS
            : canSeeTeam
              ? TABS.filter((t) => t.key !== 'payroll')
              : TABS.filter((t) => t.key === 'attendance' || t.key === 'roster'))
          .map(({ key, label, icon: Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setTab(key)}
            className={tab === key ? 'btn-primary' : 'btn-secondary'}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          >
            <Icon size={14} /> {canSeeTeam || key !== 'roster' ? label : 'My details'}
          </button>
        ))}
      </div>

      {tab === 'roster' && <Roster isOwner={isOwner} canSeeTeam={canSeeTeam} />}
      {tab === 'attendance' && (
        <Attendance isOwner={isOwner} canSeeTeam={canSeeTeam} />
      )}
      {tab === 'payroll' && (
        // Owner-only, and only the owner can reach this tab at all: the Payroll
        // button is not rendered for anyone else (see TABS filtering above).
        isOwner ? <Payroll /> : (
          <NotBuiltYet
            title="Payroll is not yours to see"
            blurb="Weekly pay runs are visible to the boutique owner only."
          />
        )
      )}
      {tab === 'performance' && (
        <NotBuiltYet
          title="Performance is not switched on yet"
          blurb="Completion rates, on-time delivery and rework are calculated from work already recorded against each person. Reviews arrive in a later phase."
        />
      )}
    </>
  );
}
