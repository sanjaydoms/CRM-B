/**
 * Attendance: check in, check out, and read the week back.
 *
 * Two audiences on one tab, deliberately not two screens:
 *   - a staff member gets one big button and their own week,
 *   - the owner or a supervisor gets the floor's day and anyone's timesheet.
 *
 * The server is authoritative about time. Nothing here sends a timestamp for a
 * check-in or a check-out; the elapsed counter is display only, recomputed from
 * the server's own check_in stamp, so a device with a wrong clock shows a wrong
 * counter and still records the right hours.
 */

import { useState, useEffect, useCallback } from 'react';
import { Clock, LogIn, LogOut, Pencil, Plus, X } from 'lucide-react';

import { api } from '../../services/api';

const panel = {
  background: 'var(--surface-color)',
  boxShadow: 'var(--shadow-sm)',
  border: '1px solid var(--border-color)',
  borderRadius: '12px',
};

/** 565 -> "9h 25m". Minutes are the stored unit; hours are only ever display. */
const hoursText = (minutes) => {
  const total = Number(minutes || 0);
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m}m`;
  return m ? `${h}h ${m}m` : `${h}h`;
};

const clockText = (iso) =>
  iso ? new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';

const dayText = (iso) =>
  iso ? new Date(iso).toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' }) : '—';

/** The Monday of the week a date falls in, as yyyy-mm-dd. */
const mondayOf = (value) => {
  const d = new Date(value);
  const shift = (d.getDay() + 6) % 7;
  d.setDate(d.getDate() - shift);
  return d.toISOString().slice(0, 10);
};

const todayISO = () => new Date().toISOString().slice(0, 10);

/** Local yyyy-mm-dd -- never toISOString(), which shifts to UTC and can land a
 *  day early in a timezone ahead of it. */
const localISO = (d) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;

const PERIODS = [['day', 'Day'], ['week', 'Week'], ['month', 'Month']];
const PERIOD_LABEL = { day: 'Today', week: 'This week', month: 'This month' };

/** First and last day of the current month -- the muster grid spans the whole
 *  month, with future days shown blank. */
const monthGridBounds = () => {
  const now = new Date();
  return {
    since: localISO(new Date(now.getFullYear(), now.getMonth(), 1)),
    until: localISO(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
  };
};

/** [since, until] for the chosen period, inclusive, ending today -- future days
 *  hold no attendance, so a period never reaches past today. */
const periodBounds = (period) => {
  const now = new Date();
  const until = localISO(now);
  if (period === 'week') {
    const d = new Date(now);
    d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); // back to Monday
    return { since: localISO(d), until };
  }
  if (period === 'month') {
    return { since: localISO(new Date(now.getFullYear(), now.getMonth(), 1)), until };
  }
  return { since: until, until };
};

function Banner({ text, tone = 'error' }) {
  const colours = tone === 'error'
    ? { bg: 'rgba(220,80,60,0.12)', border: 'rgba(220,80,60,0.35)', fg: '#c0392b' }
    : { bg: 'rgba(46,180,120,0.12)', border: 'rgba(46,180,120,0.35)', fg: '#1e8a5c' };
  return (
    <div style={{
      background: colours.bg, border: `1px solid ${colours.border}`, color: colours.fg,
      borderRadius: '8px', padding: '10px 12px', fontSize: '13px', marginBottom: '14px',
    }}>
      {text}
    </div>
  );
}

function Modal({ title, onClose, children, width = '520px' }) {
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

/**
 * The staff member's own card: one button, and what it did.
 *
 * The elapsed figure ticks locally off the server's check_in. It is a comfort
 * display -- the minutes that get paid are computed server-side at check-out
 * from two server stamps, and never from this number.
 */
function MyDay({ onChanged }) {
  const [state, setState] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [now, setNow] = useState(() => Date.now());

  const load = useCallback(async () => {
    try {
      setState(await api.getCurrentAttendance());
    } catch (err) {
      setError(err.message || 'Could not load your attendance.');
    }
  }, []);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  // Only while a session is open, and only once a minute -- the display shows
  // minutes, so a faster tick would repaint for nothing.
  useEffect(() => {
    if (state?.state !== 'WORKING') return undefined;
    const id = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(id);
  }, [state?.state]);

  const act = async (fn) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
      onChanged?.();
    } catch (err) {
      setError(err.message || 'That did not work. Please try again.');
    } finally {
      setBusy(false);
    }
  };

  if (!state || state.state === 'NOT_STAFF') return null;

  const session = state.session;
  const elapsed = session && state.state === 'WORKING'
    ? Math.max(0, Math.floor((now - new Date(session.check_in).getTime()) / 60000))
    : 0;

  return (
    <div style={{ ...panel, padding: '20px', marginBottom: '18px' }}>
      {error && <Banner text={error} />}

      <div style={{
        fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
        color: 'var(--text-muted)', marginBottom: '10px',
      }}>
        Today
      </div>

      {state.state === 'NOT_CHECKED_IN' && (
        <>
          <div style={{ fontSize: '18px', fontWeight: 600, marginBottom: '14px' }}>
            Not checked in
          </div>
          <button
            type="button" className="btn-primary" disabled={busy}
            onClick={() => act(() => api.checkIn())}
            style={{ width: '100%', minHeight: '48px', fontSize: '16px',
                     display: 'inline-flex', alignItems: 'center',
                     justifyContent: 'center', gap: '8px' }}
          >
            <LogIn size={18} /> {busy ? 'Checking in…' : 'Check in'}
          </button>
        </>
      )}

      {state.state === 'WORKING' && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
            <span style={{ width: '9px', height: '9px', borderRadius: '50%',
                           background: '#2ec4b6', display: 'inline-block' }} />
            <span style={{ fontSize: '18px', fontWeight: 600 }}>You&rsquo;re checked in</span>
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '14px' }}>
            Since {clockText(session.check_in)} · {hoursText(elapsed)} so far
          </div>
          <button
            type="button" className="btn-primary" disabled={busy}
            onClick={() => act(() => api.checkOut())}
            style={{ width: '100%', minHeight: '48px', fontSize: '16px',
                     display: 'inline-flex', alignItems: 'center',
                     justifyContent: 'center', gap: '8px' }}
          >
            <LogOut size={18} /> {busy ? 'Checking out…' : 'Check out'}
          </button>
        </>
      )}

      {state.state === 'CHECKED_OUT' && (
        <>
          <div style={{ fontSize: '18px', fontWeight: 600 }}>
            {clockText(session.check_in)} → {clockText(session.check_out)}
          </div>
          <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginTop: '4px',
                        marginBottom: '14px' }}>
            {hoursText(state.today_minutes)} today
          </div>
          <button
            type="button" className="btn-secondary" disabled={busy}
            onClick={() => act(() => api.checkIn())}
            style={{ width: '100%', minHeight: '44px',
                     display: 'inline-flex', alignItems: 'center',
                     justifyContent: 'center', gap: '8px' }}
          >
            <LogIn size={16} /> Start another session
          </button>
        </>
      )}
    </div>
  );
}

function CorrectionForm({ session, onCancel, onSaved }) {
  // datetime-local wants "YYYY-MM-DDTHH:mm" with no zone; the server reads a
  // naive value in the boutique's own timezone, which is what the person typing
  // it means.
  const forInput = (iso) => {
    if (!iso) return '';
    const d = new Date(iso);
    const pad = (n) => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  };

  const [checkIn, setCheckIn] = useState(() => forInput(session.check_in));
  const [checkOut, setCheckOut] = useState(() => forInput(session.check_out));
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.correctAttendance(session.id, {
        check_in: checkIn || undefined,
        check_out: checkOut || undefined,
        reason,
      });
      onSaved();
    } catch (err) {
      setError(err.message || 'Could not save that correction.');
    } finally {
      setBusy(false);
    }
  };

  const label = { fontSize: '12px', color: 'var(--text-secondary)' };

  return (
    <form onSubmit={submit}>
      {error && <Banner text={error} />}
      <div
        className="mobile-stack-grid"
        style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={label} htmlFor="corr-in">Check in</label>
          <input id="corr-in" type="datetime-local" value={checkIn}
                 onChange={(e) => setCheckIn(e.target.value)} required />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={label} htmlFor="corr-out">Check out</label>
          <input id="corr-out" type="datetime-local" value={checkOut}
                 onChange={(e) => setCheckOut(e.target.value)} />
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '14px' }}>
        <label style={label} htmlFor="corr-reason">Reason for the change</label>
        <input id="corr-reason" value={reason} onChange={(e) => setReason(e.target.value)}
               placeholder="Forgot to check in" required />
      </div>
      <p style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '12px' }}>
        The original times stay on the record, along with who changed them and why.
      </p>
      <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '18px' }}>
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Save correction'}
        </button>
      </div>
    </form>
  );
}

function RecordForm({ roster, onCancel, onSaved }) {
  const [staff, setStaff] = useState(roster[0]?.id || '');
  const [checkIn, setCheckIn] = useState('');
  const [checkOut, setCheckOut] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api.recordAttendance({
        staff, check_in: checkIn, check_out: checkOut || undefined, note,
      });
      onSaved();
    } catch (err) {
      setError(err.message || 'Could not record that attendance.');
    } finally {
      setBusy(false);
    }
  };

  const label = { fontSize: '12px', color: 'var(--text-secondary)' };

  return (
    <form onSubmit={submit}>
      {error && <Banner text={error} />}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginBottom: '14px' }}>
        <label style={label} htmlFor="rec-staff">Staff member</label>
        <select id="rec-staff" value={staff} onChange={(e) => setStaff(e.target.value)} required>
          {roster.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
        </select>
      </div>
      <div
        className="mobile-stack-grid"
        style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={label} htmlFor="rec-in">Check in</label>
          <input id="rec-in" type="datetime-local" value={checkIn}
                 onChange={(e) => setCheckIn(e.target.value)} required />
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={label} htmlFor="rec-out">Check out</label>
          <input id="rec-out" type="datetime-local" value={checkOut}
                 onChange={(e) => setCheckOut(e.target.value)} />
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '5px', marginTop: '14px' }}>
        <label style={label} htmlFor="rec-note">Note</label>
        <input id="rec-note" value={note} onChange={(e) => setNote(e.target.value)}
               placeholder="Manual entry" />
      </div>
      <p style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '12px' }}>
        Recorded as entered by you, so it stays distinguishable from a staff check-in.
      </p>
      <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '18px' }}>
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn-primary" disabled={busy}>
          {busy ? 'Saving…' : 'Record attendance'}
        </button>
      </div>
    </form>
  );
}

/** The floor, today: who is in, who has gone home, who never arrived. */
function TodayOnTheFloor({ isOwner, roster, sessions, onCorrect, onRecord, loading, period }) {
  const ranged = period !== 'day';
  const byStaff = new Map();
  sessions.forEach((s) => {
    const list = byStaff.get(String(s.staff)) || [];
    list.push(s);
    byStaff.set(String(s.staff), list);
  });

  const rows = roster.map((person) => {
    const own = byStaff.get(String(person.id)) || [];
    const open = own.find((s) => s.is_open);
    const minutes = own.reduce((sum, s) => sum + Number(s.minutes || 0), 0);
    const days = new Set(own.map((s) => s.date)).size;
    let status = 'Not in';
    if (open) status = 'Working';
    else if (own.length) status = 'Checked out';
    return { person, own, open, minutes, days, status, latest: own[0] };
  });

  const working = rows.filter((r) => r.status === 'Working').length;
  const done = rows.filter((r) => r.status === 'Checked out').length;
  const absent = rows.filter((r) => r.own.length === 0).length;
  const withHours = rows.filter((r) => r.own.length > 0).length;
  const totalMinutes = rows.reduce((sum, r) => sum + r.minutes, 0);

  const tile = (label, value) => (
    <div style={{ ...panel, padding: '14px 16px', flex: '1 1 130px' }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
                    color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontSize: '22px', fontWeight: 600, marginTop: '4px' }}>{value}</div>
    </div>
  );

  const statusColour = (status) =>
    status === 'Working' ? '#2ec4b6' : status === 'Checked out' ? 'var(--text-secondary)' : '#c0864b';

  return (
    <>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
        {ranged ? (
          <>
            {tile('Working now', working)}
            {tile('With hours', withHours)}
            {tile('No hours', absent)}
            {tile('Total hours', totalMinutes ? hoursText(totalMinutes) : '0h')}
          </>
        ) : (
          <>
            {tile('Present today', working + done)}
            {tile('Working now', working)}
            {tile('Checked out', done)}
            {tile('Not in', absent)}
          </>
        )}
      </div>

      {isOwner && (
        <button type="button" className="btn-secondary" onClick={onRecord}
                style={{ marginBottom: '14px', display: 'inline-flex',
                         alignItems: 'center', gap: '6px' }}>
          <Plus size={14} /> Record attendance
        </button>
      )}

      {loading ? (
        <div style={{ padding: '24px', color: 'var(--text-muted)' }}>Loading attendance…</div>
      ) : rows.length === 0 ? (
        <div style={{ ...panel, padding: '28px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          No staff on the roster yet.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {rows.map(({ person, open, minutes, days, own, status, latest }) => (
            <div key={person.id} style={{ ...panel, padding: '14px 16px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between',
                            alignItems: 'flex-start', gap: '12px', flexWrap: 'wrap' }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontWeight: 600, fontSize: '15px' }}>{person.name}</div>
                  <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginTop: '2px' }}>
                    {person.role}
                  </div>
                </div>
                <span style={{ fontSize: '12px', fontWeight: 600, color: statusColour(status) }}>
                  {ranged ? (status === 'Working' ? 'Working now' : (own.length ? `${days} day${days === 1 ? '' : 's'}` : 'No hours')) : status}
                </span>
              </div>

              <div
                className="mobile-stack-grid"
                style={{
                  display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px',
                  marginTop: '12px', paddingTop: '12px',
                  borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))',
                }}
              >
                {ranged ? (
                  <>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Days</div>
                      <div style={{ fontWeight: 600 }}>{days || '—'}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Sessions</div>
                      <div style={{ fontWeight: 600 }}>{own.length || '—'}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Total hours</div>
                      <div style={{ fontWeight: 600 }}>{minutes ? hoursText(minutes) : '—'}</div>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Check in</div>
                      <div style={{ fontWeight: 600 }}>{clockText(latest?.check_in)}</div>
                    </div>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Check out</div>
                      <div style={{ fontWeight: 600 }}>
                        {open ? '—' : clockText(latest?.check_out)}
                      </div>
                    </div>
                    <div>
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Hours</div>
                      <div style={{ fontWeight: 600 }}>{minutes ? hoursText(minutes) : '—'}</div>
                    </div>
                  </>
                )}
              </div>

              {isOwner && latest && (
                <button type="button" className="btn-secondary"
                        onClick={() => onCorrect(latest)}
                        style={{ marginTop: '12px', display: 'inline-flex',
                                 alignItems: 'center', gap: '6px', minHeight: '38px' }}>
                  <Pencil size={13} /> Correct
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </>
  );
}

function Timesheet({ canSeeTeam, isOwner, roster, onCorrect }) {
  const [staff, setStaff] = useState('');
  const [week, setWeek] = useState(() => mondayOf(todayISO()));
  const [sheet, setSheet] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Derived, not defaulted through an effect: the first roster entry IS the
  // selection until someone picks another, so there is no state to synchronise
  // and no render where the select and the request disagree about who is shown.
  const selected = staff || String(roster[0]?.id || '');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setSheet(await api.getTimesheet({
        staff: canSeeTeam ? (selected || undefined) : undefined,
        week,
      }));
    } catch (err) {
      setError(err.message || 'Could not load that timesheet.');
      setSheet(null);
    } finally {
      setLoading(false);
    }
  }, [canSeeTeam, selected, week]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load]);

  const label = { fontSize: '12px', color: 'var(--text-secondary)' };

  return (
    <div style={{ marginTop: '22px' }}>
      <h3 style={{ fontSize: '15px', fontWeight: 600, margin: '0 0 12px' }}>Weekly timesheet</h3>

      <div
        className="mobile-stack-grid"
        style={{ display: 'grid', gridTemplateColumns: canSeeTeam ? '1fr 1fr' : '1fr',
                 gap: '12px', marginBottom: '14px', maxWidth: '520px' }}
      >
        {canSeeTeam && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
            <label style={label} htmlFor="ts-staff">Staff member</label>
            <select id="ts-staff" value={selected} onChange={(e) => setStaff(e.target.value)}>
              {roster.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </div>
        )}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '5px' }}>
          <label style={label} htmlFor="ts-week">Week of</label>
          <input id="ts-week" type="date" value={week}
                 onChange={(e) => setWeek(mondayOf(e.target.value))} />
        </div>
      </div>

      {error && <Banner text={error} />}

      {loading ? (
        <div style={{ padding: '20px', color: 'var(--text-muted)' }}>Loading timesheet…</div>
      ) : !sheet ? null : (
        <>
          <div style={{ ...panel, padding: '14px 16px', marginBottom: '12px' }}>
            <div style={{ fontSize: '11px', letterSpacing: '0.08em',
                          textTransform: 'uppercase', color: 'var(--text-muted)' }}>
              {sheet.staff_name} · week total
            </div>
            <div style={{ fontSize: '24px', fontWeight: 600, marginTop: '4px' }}>
              {hoursText(sheet.total_minutes)}
            </div>
            {sheet.open_sessions > 0 && (
              <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '4px' }}>
                {sheet.open_sessions} session{sheet.open_sessions > 1 ? 's' : ''} still open —
                not counted until checked out.
              </div>
            )}
          </div>

          {sheet.sessions.length === 0 ? (
            <div style={{ ...panel, padding: '24px', textAlign: 'center',
                          color: 'var(--text-secondary)' }}>
              No attendance recorded for this week.
            </div>
          ) : (
            // Cards rather than a table: at 320px a five-column table either
            // scrolls sideways or crushes, and this is read on a phone.
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {sheet.sessions.map((s) => (
                <div key={s.id} style={{ ...panel, padding: '12px 14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between',
                                gap: '10px', flexWrap: 'wrap' }}>
                    <div style={{ fontWeight: 600, fontSize: '14px' }}>{dayText(s.check_in)}</div>
                    <div style={{ fontWeight: 600 }}>
                      {s.is_open ? 'In progress' : hoursText(s.minutes)}
                    </div>
                  </div>
                  <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', marginTop: '4px' }}>
                    {clockText(s.check_in)} → {s.is_open ? '—' : clockText(s.check_out)}
                    {' · '}
                    {s.source === 'OWNER' ? 'Entered by owner' : 'Self'}
                    {s.was_corrected && ' · corrected'}
                  </div>
                  {isOwner && (
                    <button type="button" className="btn-secondary"
                            onClick={() => onCorrect(s)}
                            style={{ marginTop: '10px', display: 'inline-flex',
                                     alignItems: 'center', gap: '6px', minHeight: '38px' }}>
                      <Pencil size={13} /> Correct
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}

/* The monthly muster roll: staff down the side, every date across the top,
 * one status letter per cell.
 *
 *   P  present   -- an attendance session exists that day (never editable here)
 *   L  leave     -- owner-marked
 *   WO weekly off -- owner-marked
 *   A  absent    -- a past day with none of the above
 *   (blank)      -- a future day, nothing to show yet
 *
 * The owner cycles a non-present cell A -> L -> WO -> A by clicking it; present
 * cells are real attendance and cannot be overwritten from here.
 */
const STATUS_STYLE = {
  P: { bg: 'rgba(46,196,182,0.18)', fg: '#1e8a5c' },
  L: { bg: 'rgba(240,136,62,0.18)', fg: '#c0864b' },
  WO: { bg: 'rgba(120,120,140,0.18)', fg: 'var(--text-secondary)' },
  A: { bg: 'rgba(220,80,60,0.12)', fg: '#c0392b' },
  '': { bg: 'transparent', fg: 'var(--text-muted)' },
};

const eachDate = (since, until) => {
  const out = [];
  const [ys, ms, ds] = since.split('-').map(Number);
  const [yu, mu, du] = until.split('-').map(Number);
  const cur = new Date(ys, ms - 1, ds);
  const end = new Date(yu, mu - 1, du);
  while (cur <= end) {
    out.push({
      iso: localISO(cur),
      day: cur.getDate(),
      weekend: cur.getDay() === 0 || cur.getDay() === 6,
    });
    cur.setDate(cur.getDate() + 1);
  }
  return out;
};

function MusterGrid({ isOwner, roster, sessions, dayMarks, since, until, onChanged }) {
  const today = localISO(new Date());
  const dates = eachDate(since, until);

  const presentByStaff = new Map();
  sessions.forEach((s) => {
    const set = presentByStaff.get(String(s.staff)) || new Set();
    set.add(s.date);
    presentByStaff.set(String(s.staff), set);
  });

  const markByKey = new Map(); // `${staff}|${date}` -> { id, kind }
  dayMarks.forEach((m) => markByKey.set(`${m.staff}|${m.date}`, m));

  const statusFor = (staffId, iso) => {
    if (iso > today) return '';
    if (presentByStaff.get(String(staffId))?.has(iso)) return 'P';
    const mark = markByKey.get(`${staffId}|${iso}`);
    if (mark) return mark.kind === 'LEAVE' ? 'L' : 'WO';
    return 'A';
  };

  // A -> Leave -> Weekly off -> cleared. Present and future cells do nothing.
  const cycle = async (staffId, iso, current, mark) => {
    if (!isOwner || current === 'P' || iso > today) return;
    try {
      if (current === 'A') {
        await api.createDayMark({ staff: staffId, date: iso, kind: 'LEAVE' });
      } else if (current === 'L') {
        await api.createDayMark({ staff: staffId, date: iso, kind: 'WEEKLY_OFF' });
      } else if (current === 'WO' && mark) {
        await api.deleteDayMark(mark.id);
      }
      onChanged();
    } catch { /* a failed mark just leaves the cell as it was */ }
  };

  const th = {
    position: 'sticky', top: 0, background: 'var(--surface-color, #fff)',
    padding: '6px 4px', fontSize: '11px', color: 'var(--text-muted)',
    fontWeight: 600, textAlign: 'center', zIndex: 1,
  };
  const nameCell = {
    position: 'sticky', left: 0, background: 'var(--surface-color, #fff)',
    padding: '8px 12px', fontSize: '13px', fontWeight: 600, whiteSpace: 'nowrap',
    borderRight: '1px solid var(--border-color, rgba(255,255,255,0.12))', zIndex: 1,
  };

  const legend = [['P', 'Present'], ['L', 'Leave'], ['WO', 'Weekly off'], ['A', 'Absent']];

  return (
    <div style={{ ...panel, padding: '14px' }}>
      <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', marginBottom: '10px' }}>
        {legend.map(([k, label]) => (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: '6px',
                                 fontSize: '12px', color: 'var(--text-secondary)' }}>
            <span style={{ width: '20px', height: '20px', borderRadius: '4px',
                           display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                           fontSize: '10px', fontWeight: 700,
                           background: STATUS_STYLE[k].bg, color: STATUS_STYLE[k].fg }}>{k}</span>
            {label}
          </span>
        ))}
        {isOwner && (
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: 'auto' }}>
            Tap a cell to mark leave or a weekly off.
          </span>
        )}
      </div>

      {roster.length === 0 ? (
        <div style={{ padding: '24px', textAlign: 'center', color: 'var(--text-secondary)' }}>
          No staff on the roster yet.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ borderCollapse: 'collapse', width: '100%' }}>
            <thead>
              <tr>
                <th style={{ ...nameCell, ...th, textAlign: 'left' }}>Staff</th>
                {dates.map((d) => (
                  <th key={d.iso} style={{ ...th, color: d.weekend ? 'var(--text-secondary)' : 'var(--text-muted)' }}
                      title={d.iso}>{d.day}</th>
                ))}
                <th style={{ ...th }}>P</th>
              </tr>
            </thead>
            <tbody>
              {roster.map((person) => {
                const present = presentByStaff.get(String(person.id))?.size || 0;
                return (
                  <tr key={person.id}>
                    <td style={nameCell}>
                      {person.name}
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontWeight: 400 }}>
                        {person.role}
                      </div>
                    </td>
                    {dates.map((d) => {
                      const status = statusFor(person.id, d.iso);
                      const mark = markByKey.get(`${person.id}|${d.iso}`);
                      const clickable = isOwner && status !== 'P' && d.iso <= today;
                      return (
                        <td key={d.iso} style={{ padding: '2px', textAlign: 'center' }}>
                          <button type="button" disabled={!clickable}
                                  onClick={() => cycle(person.id, d.iso, status, mark)}
                                  title={`${person.name} · ${d.iso}`}
                                  style={{
                                    width: '26px', height: '26px', borderRadius: '4px', border: 'none',
                                    fontSize: '10px', fontWeight: 700,
                                    cursor: clickable ? 'pointer' : 'default',
                                    background: STATUS_STYLE[status].bg, color: STATUS_STYLE[status].fg,
                                  }}>
                            {status}
                          </button>
                        </td>
                      );
                    })}
                    <td style={{ textAlign: 'center', fontWeight: 600, fontSize: '13px' }}>{present}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

export default function Attendance({ isOwner, canSeeTeam }) {
  const [roster, setRoster] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [dayMarks, setDayMarks] = useState([]);
  const [loading, setLoading] = useState(true);
  const [correcting, setCorrecting] = useState(null);
  const [recording, setRecording] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const [period, setPeriod] = useState('day');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const bounds = period === 'month' ? monthGridBounds() : periodBounds(period);
      const [people, today, marks] = await Promise.all([
        canSeeTeam ? api.getTailors().catch(() => []) : Promise.resolve([]),
        canSeeTeam ? api.getAttendance(bounds).catch(() => []) : Promise.resolve([]),
        canSeeTeam && period === 'month'
          ? api.getDayMarks(bounds).catch(() => []) : Promise.resolve([]),
      ]);
      setRoster(Array.isArray(people) ? people : []);
      setSessions(Array.isArray(today) ? today : []);
      setDayMarks(Array.isArray(marks) ? marks : []);
    } finally {
      setLoading(false);
    }
  }, [canSeeTeam, period]);

  useEffect(() => {
    const t = setTimeout(load, 0);
    return () => clearTimeout(t);
  }, [load, reloadKey]);

  const refresh = () => setReloadKey((n) => n + 1);

  return (
    <>
      <MyDay onChanged={refresh} />

      {canSeeTeam && (
        <>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px',
                        flexWrap: 'wrap', margin: '0 0 12px' }}>
            <h3 style={{ fontSize: '15px', fontWeight: 600, margin: 0,
                         display: 'flex', alignItems: 'center', gap: '7px' }}>
              <Clock size={15} /> On the floor · {PERIOD_LABEL[period]}
            </h3>
            <div role="group" aria-label="Attendance period"
                 style={{ display: 'inline-flex', borderRadius: '8px', overflow: 'hidden',
                          border: '1px solid var(--border-color, rgba(255,255,255,0.12))' }}>
              {PERIODS.map(([value, label]) => (
                <button key={value} type="button" onClick={() => setPeriod(value)}
                        aria-pressed={period === value}
                        style={{
                          padding: '6px 14px', fontSize: '13px', border: 'none', cursor: 'pointer',
                          background: period === value ? 'var(--accent, #2ec4b6)' : 'transparent',
                          color: period === value ? '#fff' : 'var(--text-secondary)',
                          fontWeight: period === value ? 600 : 400,
                        }}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          {period === 'month' ? (
            <MusterGrid
              isOwner={isOwner}
              roster={roster}
              sessions={sessions}
              dayMarks={dayMarks}
              since={monthGridBounds().since}
              until={monthGridBounds().until}
              onChanged={refresh}
            />
          ) : (
            <TodayOnTheFloor
              isOwner={isOwner}
              roster={roster}
              sessions={sessions}
              loading={loading}
              period={period}
              onCorrect={setCorrecting}
              onRecord={() => setRecording(true)}
            />
          )}
        </>
      )}

      <Timesheet
        key={reloadKey}
        canSeeTeam={canSeeTeam}
        isOwner={isOwner}
        roster={roster}
        onCorrect={setCorrecting}
      />

      {correcting && (
        <Modal title="Correct attendance" onClose={() => setCorrecting(null)}>
          <CorrectionForm
            session={correcting}
            onCancel={() => setCorrecting(null)}
            onSaved={() => { setCorrecting(null); refresh(); }}
          />
        </Modal>
      )}

      {recording && (
        <Modal title="Record attendance" onClose={() => setRecording(false)}>
          <RecordForm
            roster={roster}
            onCancel={() => setRecording(false)}
            onSaved={() => { setRecording(false); refresh(); }}
          />
        </Modal>
      )}
    </>
  );
}
