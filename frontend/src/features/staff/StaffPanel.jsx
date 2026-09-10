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
import {
  Plus, Clock, Wallet, TrendingUp, Users, FileText, Trash2, Phone, Calendar, Briefcase, UserCheck,
  User, UserPlus, Smartphone, Mail, Sparkles, Scissors, Shield, Coins, MapPin, Hash, Tag, FilePlus, Upload, Eye, IndianRupee,
} from 'lucide-react';

import { api } from '../../services/api';
import {
  AvatarInitials, PageHeader, SearchBox, StatCard, FormModal, Field, Dropzone, InfoNote, FormSection, IconTile,
} from '../../components/ui/Atelier';
import { ASSIGNABLE_ROLES, DOCUMENT_KINDS } from '../../constants/roles';
import Attendance from './Attendance';
import Payroll from './Payroll';
import Performance from './Performance';

const panel = {
  background: 'var(--surface-color)',
  border: '1px solid var(--border-color)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-sm)',
};

// One themed error banner, so every form and the roster report failures the
// same way instead of each hardcoding its own red. Was rgba(220,80,60,...)
// on #c0392b -- legible, but off-palette against the refreshed tokens.
const errorBox = {
  background: 'var(--danger-bg)',
  border: '1px solid var(--danger-color)',
  color: 'var(--danger-color)',
  borderRadius: 'var(--radius-md)',
  padding: '10px 12px',
  fontSize: 'var(--text-sm)',
  marginBottom: 'var(--space-3)',
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

/**
 * A mobile number is ten national digits, whatever was typed or pasted.
 *
 * Mirrors national_mobile() in crm_api/models.py step for step -- drop
 * everything that is not a digit, an international 00, the country code when
 * more than ten digits remain, and leading zeros -- so what the field shows
 * is what the server will store. Two rules that merely looked alike were not
 * enough: "first ten digits" turned a pasted "+91 98765 43210" into
 * 9198765432, a number that passes every check and reaches nobody.
 *
 * No maxLength on the input, on purpose. It counts characters, so it would
 * cut that same paste to "+91 98765 " before this function ever saw it. The
 * limit is here; the server (core.validators) is the one that decides.
 */
const tenDigits = (e) => {
  let d = e.target.value.replace(/\D/g, '');
  if (d.startsWith('00')) d = d.slice(2);
  if (d.length > 10 && d.startsWith('91')) d = d.slice(2);
  return d.replace(/^0+/, '').slice(0, 10);
};

function Modal({ title, subtitle, icon, tone = 'green', onClose, children, width = '560px', footer }) {
  return (
    <FormModal icon={icon} tone={tone} title={title} subtitle={subtitle} onClose={onClose} width={width} footer={footer}>
      {children}
    </FormModal>
  );
}

/** A tab whose domain arrives in a later phase. Says so, rather than showing nothing. */
function NotBuiltYet({ title, blurb }) {
  return (
    <div className="ui-card" style={{ padding: 'var(--space-10) var(--space-6)', textAlign: 'center' }}>
      <h3 style={{ fontFamily: 'var(--font-serif)', fontSize: 'var(--text-lg)', fontWeight: 500,
                   margin: '0 0 var(--space-2)', color: 'var(--text-primary)' }}>{title}</h3>
      <p style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', margin: 0,
                  lineHeight: 'var(--leading-normal)' }}>
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

  return (
    <form onSubmit={submit} className="at-stack">
      {error && <div style={errorBox}>{error}</div>}

      <div className="at-form-grid">
        <Field label="Employment type" required icon={Briefcase} htmlFor="sp-type">
          <select id="sp-type" value={form.employment_type} onChange={set('employment_type')}>
            {EMPLOYMENT_TYPES.map(([value, text]) => (
              <option key={value} value={value}>{text}</option>
            ))}
          </select>
        </Field>
        <Field label="Hourly rate (₹)" required icon={IndianRupee} htmlFor="sp-rate"
               hint={`Set the hourly rate for ${member.name}.`}>
          <input id="sp-rate" type="number" min="0" step="0.01"
                 value={form.hourly_rate} onChange={set('hourly_rate')} placeholder="0.00" />
        </Field>

        <Field label="Joined on" required icon={Calendar} htmlFor="sp-joined">
          <input id="sp-joined" type="date" value={form.joined_at} onChange={set('joined_at')} />
        </Field>
        <Field label="Left on" icon={Calendar} htmlFor="sp-exit" hint="Leave blank if currently active.">
          <input id="sp-exit" type="date" value={form.exit_date} onChange={set('exit_date')} />
        </Field>

        <Field label="Expected hours a week" icon={Clock} htmlFor="sp-hours" hint="Planned working hours per week.">
          <input id="sp-hours" type="number" min="0" step="0.5"
                 value={form.weekly_hours} onChange={set('weekly_hours')} placeholder="48" />
        </Field>
        <Field label="Phone" icon={Phone} htmlFor="sp-phone">
          <input id="sp-phone" value={form.phone} inputMode="numeric" placeholder="Enter phone number"
                 onChange={(e) => setForm((f) => ({ ...f, phone: tenDigits(e) }))} />
        </Field>

        <Field label="Security deposit (₹)" icon={Shield} htmlFor="sp-dep-total">
          <input id="sp-dep-total" type="number" min="0" step="0.01"
                 value={form.deposit_total} onChange={set('deposit_total')} placeholder="0.00" />
        </Field>
        <Field label="Weekly deduction (₹)" icon={Coins} htmlFor="sp-dep-weekly">
          <input id="sp-dep-weekly" type="number" min="0" step="0.01"
                 value={form.deposit_weekly} onChange={set('deposit_weekly')} placeholder="0.00" />
        </Field>
      </div>

      <Field label="Emergency contact" icon={User} htmlFor="sp-emergency">
        <input id="sp-emergency" value={form.emergency_contact} placeholder="Name and phone number"
               onChange={set('emergency_contact')} />
      </Field>
      <Field label="Address" icon={MapPin} htmlFor="sp-address">
        <textarea id="sp-address" rows={2} value={form.address} onChange={set('address')} placeholder="Enter full address" />
      </Field>
      <Field label="Notes" icon={FileText} htmlFor="sp-notes">
        <textarea id="sp-notes" rows={2} value={form.notes} onChange={set('notes')} placeholder="Add any additional notes…" />
      </Field>

      <InfoNote tone="amber" icon={Shield}>
        <strong>Note:</strong> The weekly deduction is recovered from payroll once that is switched on, and never
        takes more than the deposit still outstanding or that week's earnings.
      </InfoNote>

      <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', paddingTop: 'var(--space-3)',
                    borderTop: '1px solid var(--border-color)' }}>
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn-primary" disabled={saving}>
          <UserPlus size={16} /> {saving ? 'Saving…' : terms ? 'Save changes' : 'Create profile'}
        </button>
      </div>
    </form>
  );
}

function AdvanceForm({ member, onCancel, onSaved }) {
  const [form, setForm] = useState({
    amount: '', weekly_recovery: '',
    issued_on: new Date().toISOString().slice(0, 10), reason: '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.issueAdvance({ ...cleaned(form), staff: member.id });
      onSaved();
    } catch (err) {
      setError(err.message || 'Could not issue this advance.');
    } finally {
      setSaving(false);
    }
  };

  const field = { display: 'flex', flexDirection: 'column', gap: '5px' };
  const label = { fontSize: '12px', color: 'var(--text-secondary)' };
  return (
    <form onSubmit={submit}>
      {error && (
        <div style={errorBox}>{error}</div>
      )}
      <div className="mobile-stack-grid"
           style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
        <div style={field}>
          <label style={label} htmlFor="adv-amount">Amount (₹)</label>
          <input id="adv-amount" type="number" min="0.01" step="0.01" required
                 value={form.amount} onChange={set('amount')} placeholder="0.00" />
        </div>
        <div style={field}>
          <label style={label} htmlFor="adv-weekly">Recover per week (₹)</label>
          <input id="adv-weekly" type="number" min="0" step="0.01"
                 value={form.weekly_recovery} onChange={set('weekly_recovery')} placeholder="0.00" />
        </div>
        <div style={field}>
          <label style={label} htmlFor="adv-date">Given on</label>
          <input id="adv-date" type="date" required value={form.issued_on} onChange={set('issued_on')} />
        </div>
        <div style={field}>
          <label style={label} htmlFor="adv-reason">Reason</label>
          <input id="adv-reason" value={form.reason} onChange={set('reason')}
                 placeholder="Emergency advance" />
        </div>
      </div>
      <p style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '14px' }}>
        Recovery is taken from payroll each week, after the security deposit and
        never more than the week earned. Oldest advance first.
      </p>
      <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end', marginTop: '18px' }}>
        <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="submit" className="btn-primary" disabled={saving}>
          {saving ? 'Saving…' : 'Issue advance'}
        </button>
      </div>
    </form>
  );
}

/**
 * Onboarding: one form for the roster row, the login and the mobile number.
 *
 * This used to be two screens. Manage Tailors created the person and minted
 * their login; Staff Management then set up their employment separately, and
 * its own empty state told the owner to go to the other screen first. Adding
 * somebody therefore meant knowing that the roster and the employment record
 * were different things, which is an implementation detail of this codebase
 * rather than a fact about hiring a tailor.
 *
 * POSTs to the roster endpoint, which is what mints the account: supply an
 * email and the server generates a password and returns it exactly once, in
 * `bootstrap_password`. It is shown here and never again -- there is no second
 * copy to read, so the modal stays open on the credential until it is
 * dismissed deliberately.
 */
function AddStaffForm({ member, onCancel, onSaved, customRoles = [] }) {
  const editing = Boolean(member);
  const [form, setForm] = useState({
    name: member?.name || '',
    phone: member?.phone || '',
    email: member?.email || '',
    specialty: member?.specialty || '',
    role: member?.role || 'Tailor',
    status: member?.status || 'Available',
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [created, setCreated] = useState(null);
  const [photo, setPhoto] = useState(null);
  // A custom role the owner types (janitor, cleaner...). The select holds the
  // sentinel '__custom__' while they type; the real value lives here.
  const knownValues = ASSIGNABLE_ROLES.map((r) => r.value);
  const memberRoleIsCustom = editing && form.role && !knownValues.includes(form.role);
  const [customRole, setCustomRole] = useState(memberRoleIsCustom ? form.role : '');
  const [roleChoice, setRoleChoice] = useState(memberRoleIsCustom ? '__custom__' : form.role);
  // Custom roles already on the roster, offered for reuse.
  const reusable = customRoles.filter((r) => !knownValues.includes(r));

  const set = (key) => (e) => setForm({ ...form, [key]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { setError('A name is needed.'); return; }
    if (roleChoice === '__custom__' && !customRole.trim()) {
      setError('Type a name for the custom role.'); return;
    }
    setBusy(true);
    setError(null);
    try {
      const payload = {
        name: form.name.trim(),
        phone: form.phone.trim(),
        email: form.email.trim(),
        // Specialty is a free-text note on the roster row and the model
        // requires it, so the role stands in when it is left blank.
        specialty: form.specialty.trim() || form.role,
        role: form.role,
        status: form.status,
      };
      let saved;
      if (form.role === 'Designer') {
        // A designer is not a roster row, so this goes to its own endpoint --
        // and the login is a second call there rather than a side effect of
        // creating the record, which is how design_studio already works.
        const designerPayload = {
          name: payload.name,
          phone: payload.phone,
          email: payload.email,
          specialisation: form.specialty.trim(),
        };
        saved = editing
          ? await api.updateDesigner(member.id, designerPayload)
          : await api.createDesigner(designerPayload);
        if (payload.email && !saved.has_login) {
          saved = await api.createDesignerLogin(saved.id, payload.email);
        }
      } else {
        // A photo makes this multipart; without one it stays plain JSON.
        let body = payload;
        if (photo) {
          body = new FormData();
          Object.entries(payload).forEach(([k, v]) => body.append(k, v));
          body.append('profile_photo', photo);
        }
        saved = editing
          ? await api.updateTailor(member.id, body)
          : await api.createTailor(body);
      }
      onSaved();
      // An edit can mint an account too -- giving an address to somebody who
      // joined without one is how a person who never had a login gets one.
      if (saved?.bootstrap_password) setCreated(saved);
      else onCancel();
    } catch (err) {
      setError(err.message || 'Could not save this person.');
    } finally {
      setBusy(false);
    }
  };

  if (created) {
    return (
      <Modal title="Account created" onClose={onCancel}>
        <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
          {created.name} can sign in with the details below. This password is
          shown once and is not stored anywhere it can be read again.
        </p>
        <div style={{ ...panel, padding: '14px 16px', marginTop: '12px' }}>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Email</div>
          <div style={{ fontWeight: 600, marginBottom: '10px' }}>{created.email}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Password</div>
          <div style={{ fontWeight: 600, fontFamily: 'monospace', fontSize: '15px' }}>
            {created.bootstrap_password}
          </div>
        </div>
        {/* Carried over from the retired Manage Tailors screen. A password
            shown once is only useful if it can be handed over in the same
            breath -- the owner is standing next to the person. */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap',
                      justifyContent: 'flex-end', marginTop: '16px' }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => {
              const text = `Atelier Staff Login Credentials:\nPortal: ${window.location.origin}\nEmail: ${created.email}\nPassword: ${created.bootstrap_password}`;
              navigator.clipboard?.writeText(text);
            }}
          >Copy</button>
          <a
            className="btn-secondary"
            style={{ textDecoration: 'none' }}
            target="_blank"
            rel="noreferrer"
            href={`https://wa.me/?text=${encodeURIComponent(
              `Hello ${created.name},\nHere are your Atelier login credentials:\nPortal: ${window.location.origin}\nEmail: ${created.email}\nPassword: ${created.bootstrap_password}`
            )}`}
          >Share on WhatsApp</a>
          <button type="button" className="btn-primary" onClick={onCancel}>Done</button>
        </div>
      </Modal>
    );
  }

  const roleHint = editing
    ? 'A person cannot be moved between the production floor and the Design Studio -- they are different records.'
    : roleChoice === '__custom__'
      ? 'A custom role gets the same access as floor staff -- attendance and their own assignments.'
      : ASSIGNABLE_ROLES.find((r) => r.value === roleChoice)?.hint;

  return (
    <Modal
      icon={UserPlus}
      title={editing ? `Edit ${member.name}` : 'Add staff'}
      subtitle={editing ? 'Update this team member’s details.' : 'Add a new team member to your atelier.'}
      onClose={onCancel}
      width="640px"
      footer={(
        <>
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="submit" form="add-staff-form" className="btn-primary" disabled={busy}>
            <UserPlus size={16} /> {busy ? 'Saving…' : (editing ? 'Save changes' : 'Add staff')}
          </button>
        </>
      )}
    >
      <form id="add-staff-form" onSubmit={submit} className="at-stack">
        {error && (
          <div style={errorBox}>{error}</div>
        )}
        <Field label="Name" icon={User}>
          <input className="form-input" value={form.name} onChange={set('name')}
                 placeholder="Full name" autoFocus />
        </Field>
        {form.role !== 'Designer' && (
          <div className="at-field">
            <span className="at-field-label">Profile photo</span>
            <div className="at-form-section" style={{ flexDirection: 'row', alignItems: 'center', gap: 'var(--space-4)', background: 'var(--surface-2)' }}>
              <div style={{ width: 64, height: 64, borderRadius: '50%', overflow: 'hidden', flexShrink: 0,
                            background: 'var(--surface-inset)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                            color: 'var(--text-muted)' }}>
                {(photo || member?.profile_photo)
                  ? <img src={photo ? URL.createObjectURL(photo) : member.profile_photo} alt=""
                         style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                  : <User size={26} />}
              </div>
              <div style={{ minWidth: 0, flex: 1, borderLeft: '1px solid var(--border-color)', paddingLeft: 'var(--space-4)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
                  <button type="button" className="btn-secondary at-btn-sm"
                          onClick={() => document.getElementById('add-staff-photo').click()}>
                    <Upload size={14} /> Choose file
                  </button>
                  <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>
                    {photo ? photo.name : 'No file chosen'}
                  </span>
                  <input id="add-staff-photo" type="file" accept="image/*" hidden
                         onChange={(e) => setPhoto(e.target.files?.[0] || null)} />
                </div>
                <div className="at-field-hint" style={{ marginTop: '6px' }}>
                  Shows on their login. They can change it themselves from My Account.
                </div>
              </div>
            </div>
          </div>
        )}
        <Field label="Mobile number" icon={Smartphone}>
          <input className="form-input" value={form.phone} inputMode="numeric"
                 onChange={(e) => setForm({ ...form, phone: tenDigits(e) })}
                 placeholder="10-digit mobile" />
        </Field>
        <Field label="Role" icon={Scissors} hint={roleHint}>
          <select className="form-input" value={roleChoice} disabled={editing}
                  onChange={(e) => {
                    const v = e.target.value;
                    setRoleChoice(v);
                    setForm({ ...form, role: v === '__custom__' ? customRole : v });
                  }}>
            {ASSIGNABLE_ROLES.map(({ value, label }) => (
              <option key={value} value={value}>{label}</option>
            ))}
            {reusable.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
            <option value="__custom__">Other (add a custom role)…</option>
          </select>
        </Field>
        {roleChoice === '__custom__' && (
          <Field label="Custom role" icon={Tag}>
            <input className="form-input" value={customRole}
                   placeholder="e.g. Janitor, Cleaner, Helper"
                   onChange={(e) => { setCustomRole(e.target.value); setForm({ ...form, role: e.target.value }); }} />
          </Field>
        )}
        <Field label="Email for their login" icon={Mail}
               hint="Give an address and a password is generated and shown once.">
          <input className="form-input" type="email" value={form.email} onChange={set('email')}
                 placeholder="Leave blank for no login" />
        </Field>
        <Field label={form.role === 'Designer' ? 'Specialisation' : 'Specialty'} optional icon={Sparkles}>
          <input className="form-input" value={form.specialty} onChange={set('specialty')}
                 placeholder="Bridal blouses, lehenga…" />
        </Field>
        {editing && form.role !== 'Designer' && (
          <Field label="Status" icon={UserCheck}>
            <select className="form-input" value={form.status} onChange={set('status')}>
              <option value="Available">Available</option>
              <option value="Busy">Busy</option>
            </select>
          </Field>
        )}
      </form>
    </Modal>
  );
}

/**
 * Identity and employment documents for one person.
 *
 * Owner-only on the server for anyone else's row, so this is rendered behind
 * the same check. The number is stored in full at the boutique's instruction;
 * it is deliberately not shown in the roster card, only here, behind a
 * deliberate click on one person.
 */
function DocumentsModal({ member, onClose }) {
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [form, setForm] = useState({ kind: 'AADHAAR', number: '', label: '' });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const rows = await api.getStaffDocuments(
        member.isDesigner ? { designer: member.id } : { staff: member.id });
      setDocs(Array.isArray(rows) ? rows : []);
    } catch (err) {
      setError(err.message || 'Could not load documents.');
    } finally {
      setLoading(false);
    }
  }, [member.id, member.isDesigner]);

  useEffect(() => {
    const t = setTimeout(refresh, 0);
    return () => clearTimeout(t);
  }, [refresh]);

  const upload = async (e) => {
    e.preventDefault();
    if (!file) { setError('Choose a file to upload.'); return; }
    setBusy(true);
    setError(null);
    try {
      // FormData rather than JSON: this request carries a file, and the
      // staff helper posts it as multipart when it sees one.
      const body = new FormData();
      body.append(member.isDesigner ? 'designer' : 'staff', member.id);
      body.append('kind', form.kind);
      body.append('number', form.number.trim());
      body.append('label', form.label.trim());
      body.append('file', file);
      await api.uploadStaffDocument(body);
      setForm({ kind: 'AADHAAR', number: '', label: '' });
      setFile(null);
      await refresh();
    } catch (err) {
      setError(err.message || 'Could not upload that document.');
    } finally {
      setBusy(false);
    }
  };

  const remove = async (doc) => {
    setError(null);
    try {
      await api.deleteStaffDocument(doc.id);
      await refresh();
    } catch (err) {
      setError(err.message || 'Could not remove that document.');
    }
  };

  return (
    <Modal
      icon={FileText}
      title={`Documents — ${member.name}`}
      subtitle="Manage identification, contracts, and other important documents."
      onClose={onClose}
      width="900px"
      footer={(
        <>
          <button type="button" className="btn-secondary" onClick={onClose}>Cancel</button>
          <button type="submit" form="staff-document-form" className="btn-primary" disabled={busy}>
            {busy ? 'Uploading…' : <><Plus size={16} /> Upload Document</>}
          </button>
        </>
      )}
    >
      {error && (
        <div style={errorBox}>{error}</div>
      )}

      {loading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 'var(--text-sm)' }}>Loading…</div>
      ) : docs.length === 0 ? (
        <div className="at-drop at-drop--compact" style={{ minHeight: '150px' }}>
          <span className="at-modal-icon at-tile at-tile--neutral" style={{ width: 56, height: 56 }}><FileText size={22} /></span>
          <div className="at-drop-title" style={{ marginTop: '6px' }}>No documents held for {member.name} yet.</div>
          <div className="at-drop-sub">Add documents below to keep their records organized.</div>
        </div>
      ) : (
        <div className="at-form-section" style={{ gap: 0, padding: 'var(--space-2) var(--space-4)' }}>
          {docs.map((doc) => (
            <div key={doc.id} className="at-row">
              <IconTile icon={FileText} tone="green" size={38} iconSize={17} />
              <div className="at-row-main">
                <div className="at-row-title">
                  {doc.kind_display}{doc.label ? ` · ${doc.label}` : ''}
                </div>
                <div className="at-row-sub">
                  {doc.number || 'No number recorded'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                {doc.file_url && (
                  <a className="btn-secondary at-btn-sm" href={doc.file_url}
                     target="_blank" rel="noreferrer" style={{ textDecoration: 'none' }}>
                    <Eye size={14} /> View
                  </a>
                )}
                <button type="button" className="btn-secondary at-btn-sm at-btn-danger" onClick={() => remove(doc)}
                        aria-label={`Remove ${doc.kind_display}`}>
                  <Trash2 size={14} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <FormSection icon={FilePlus} tone="green" title="Add a Document"
                   subtitle={`Upload and categorize a document for ${member.name}.`}>
        <form id="staff-document-form" onSubmit={upload} className="at-stack">
          <div className="at-form-grid">
            <Field label="Document Type" required icon={FileText}>
              <select className="form-input" value={form.kind}
                      onChange={(e) => setForm({ ...form, kind: e.target.value })}>
                {DOCUMENT_KINDS.map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </Field>
            <Field label="Document Number" optional icon={Hash}>
              <input className="form-input" value={form.number}
                     onChange={(e) => setForm({ ...form, number: e.target.value })}
                     placeholder="Enter document number" />
            </Field>
          </div>
          <Field label="Label / Description" optional icon={Tag}>
            <input className="form-input" value={form.label}
                   onChange={(e) => setForm({ ...form, label: e.target.value })}
                   placeholder="e.g. Aadhaar (front), 2026 contract…" />
          </Field>
          <div className="at-field">
            <span className="at-field-label">Upload File <span className="at-field-req">*</span></span>
            <div className="at-side-by-side">
              {file ? (
                <div className="at-form-section" style={{ flexDirection: 'row', alignItems: 'center', gap: 'var(--space-3)' }}>
                  <IconTile icon={FileText} tone="green" size={40} iconSize={18} />
                  <div className="at-row-main">
                    <div className="at-row-title">{file.name}</div>
                    <div className="at-row-sub">{Math.round(file.size / 1024)} KB</div>
                  </div>
                  <button type="button" className="btn-secondary at-btn-sm" onClick={() => setFile(null)}>Remove</button>
                </div>
              ) : (
                <Dropzone
                  accept="image/*,application/pdf"
                  title="Drag & drop a file here" subtitle="or choose from your device"
                  chooseLabel="Choose File" hint="Supported formats: JPG, PNG, PDF (Max 10MB)"
                  onFiles={(files) => setFile(files[0] || null)}
                />
              )}
              <InfoNote tone="green" icon={Shield} title="Keep records safe"
                        items={['Government IDs (Aadhaar, PAN, etc.)', 'Contracts & agreements', 'Certificates & other documents']}>
                Upload clear and legible documents to maintain accurate employee records.
              </InfoNote>
            </div>
          </div>
        </form>
      </FormSection>
    </Modal>
  );
}

function Roster({ isOwner, canSeeTeam }) {
  const [roster, setRoster] = useState([]);
  const [designers, setDesigners] = useState([]);
  const [terms, setTerms] = useState([]);
  const [attendanceToday, setAttendanceToday] = useState([]);
  // Owner only. The endpoint refuses everyone else, so this stays empty for a
  // Master and the deposit block simply does not render for them.
  const [deposits, setDeposits] = useState([]);
  const [advances, setAdvances] = useState([]);
  const [issuingFor, setIssuingFor] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState(null);
  const [adding, setAdding] = useState(false);
  const [person, setPerson] = useState(null);
  const [documentsFor, setDocumentsFor] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      // Independent failures: a staff member may read their own terms but not
      // the roster, so one refusal must not blank the whole screen.
      const d = new Date();
      const today = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
      const [people, designed, profiles, deposited, advanced, present] = await Promise.all([
        canSeeTeam ? api.getTailors().catch(() => []) : Promise.resolve([]),
        // Designers are a separate table with a separate endpoint. They are on
        // this screen because this is where a boutique adds a person, not
        // because they became roster rows.
        canSeeTeam ? api.getDesigners().catch(() => []) : Promise.resolve([]),
        api.getStaffProfiles().catch(() => []),
        isOwner ? api.getDeposits().catch(() => []) : Promise.resolve([]),
        isOwner ? api.getAdvances({ active: 'true' }).catch(() => []) : Promise.resolve([]),
        // Today's attendance, for the "on the floor now" figure in the overview.
        canSeeTeam ? api.getAttendance({ date: today }).catch(() => []) : Promise.resolve([]),
      ]);
      setRoster(Array.isArray(people) ? people : []);
      setDesigners(Array.isArray(designed) ? designed : []);
      setTerms(Array.isArray(profiles) ? profiles : []);
      setDeposits(Array.isArray(deposited) ? deposited : []);
      setAdvances(Array.isArray(advanced) ? advanced : []);
      setAttendanceToday(Array.isArray(present) ? present : []);
    } catch (err) {
      setLoadError(err.message || 'Could not load the staff list.');
    } finally {
      setLoading(false);
    }
  }, [canSeeTeam, isOwner]);

  // Deferred rather than called straight from the effect body, matching
  // InventoryPanel: refresh() sets loading state synchronously, and doing that
  // inside an effect is the cascading-render pattern React warns about.
  useEffect(() => {
    const t = setTimeout(refresh, 0);
    return () => clearTimeout(t);
  }, [refresh]);

  const advancesByStaff = useMemo(() => {
    const map = new Map();
    advances.forEach((a) => {
      const key = String(a.staff);
      map.set(key, [...(map.get(key) || []), a]);
    });
    return map;
  }, [advances]);

  const depositByStaff = useMemo(() => {
    const map = new Map();
    deposits.forEach((d) => map.set(String(d.staff), d));
    return map;
  }, [deposits]);

  const termsByStaff = useMemo(() => {
    const map = new Map();
    terms.forEach((t) => map.set(String(t.staff), t));
    return map;
  }, [terms]);

  /** Owners see the roster; a staff member sees only the row their own terms name. */
  const rows = useMemo(() => {
    const source = canSeeTeam
      ? [
          ...roster.map((person) => ({
            member: person, terms: termsByStaff.get(String(person.id)),
          })),
          // Marked rather than duck-typed: several things below have to know
          // which table this person came from, and `isDesigner` says it once.
          ...designers.map((d) => ({
            member: { ...d, role: 'Designer', isDesigner: true },
            terms: undefined,
          })),
        ]
      : terms.map((t) => ({
          member: { id: t.staff, name: t.staff_name, role: t.staff_role },
          terms: t,
        }));
    const needle = search.trim().toLowerCase();
    if (!needle) return source;
    return source.filter(({ member }) =>
      `${member.name} ${member.role}`.toLowerCase().includes(needle));
  }, [canSeeTeam, roster, designers, terms, termsByStaff, search]);

  const withTerms = rows.filter((r) => r.terms).length;

  // How many of each role, for the summary at the top. Production staff are
  // grouped by their Tailor role; designers are their own table, added on.
  const roleCounts = useMemo(() => {
    const counts = {};
    roster.forEach((p) => { counts[p.role] = (counts[p.role] || 0) + 1; });
    if (designers.length) counts.Designer = designers.length;
    return counts;
  }, [roster, designers]);

  // Every role string already on the roster, so a custom one (janitor, cleaner)
  // can be picked again instead of retyped.
  const rosterRoles = useMemo(
    () => [...new Set(roster.map((p) => p.role).filter(Boolean))],
    [roster]);

  // The owner's staff overview: headcount, who is available, who is on the
  // floor today, and the mix of employment terms.
  const analytics = useMemo(() => {
    const total = roster.length + designers.length;
    const busy = roster.filter((p) => (p.status || '').toLowerCase() === 'busy').length;
    const available = roster.length - busy;
    const presentIds = new Set(attendanceToday.map((s) => String(s.staff)));
    const workingNow = new Set(
      attendanceToday.filter((s) => s.is_open).map((s) => String(s.staff))).size;
    const emp = {};
    terms.forEach((t) => {
      const k = t.employment_type || 'UNSET';
      emp[k] = (emp[k] || 0) + 1;
    });
    return { total, available, busy, presentToday: presentIds.size, workingNow, emp };
  }, [roster, designers, attendanceToday, terms]);

  // "Master" -> "Masters", but roles ending in "Staff" stay as they are.
  const plural = (role, n) =>
    (n === 1 || /staff$/i.test(role)) ? role : `${role}s`;


  if (loading) {
    return <div style={{ padding: '32px', color: 'var(--text-muted)' }}>Loading staff…</div>;
  }

  return (
    <>
      {loadError && (
        <div style={errorBox}>{loadError}</div>
      )}

      {canSeeTeam && (() => {
        return (
          <div className="at-stat-grid" style={{ marginBottom: 'var(--space-5)' }}>
            <StatCard icon={Users} tone="green" label="Total staff" value={analytics.total}
                      sub={`${roster.length} on the roster`} />
            <StatCard icon={UserCheck} tone="amber" label="Available now" value={analytics.available}
                      sub={analytics.busy ? `${analytics.busy} busy` : 'nobody busy'} />
            <StatCard icon={Clock} tone="blue" label="On the floor today" value={analytics.presentToday}
                      sub={analytics.workingNow ? `${analytics.workingNow} in now` : 'from attendance'} />
            <StatCard icon={Briefcase} tone="violet" label="Employment set up" value={withTerms}
                      sub={`of ${roster.length}`} />
          </div>
        );
      })()}

      {/* Role and employment mix: a chip is a count plus a label, so it reads
          as one figure. Grouped with an eyebrow, on a well, so the eye takes
          them as a breakdown rather than four more cards. */}
      {canSeeTeam && (Object.keys(roleCounts).length > 0 || withTerms > 0) && (() => {
        const chip = (n, label) => (
          <div key={label} style={{
            background: 'var(--surface-color)', border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-md)', padding: '8px 14px',
            display: 'flex', alignItems: 'baseline', gap: 'var(--space-2)',
          }}>
            <span style={{ fontSize: 'var(--text-lg)', fontWeight: 'var(--weight-bold)',
                           fontVariantNumeric: 'tabular-nums', color: 'var(--text-primary)' }}>{n}</span>
            <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>{label}</span>
          </div>
        );
        return (
          <div style={{
            background: 'var(--surface-inset)', border: '1px solid var(--border-color)',
            borderRadius: 'var(--radius-lg)', padding: 'var(--space-4) var(--space-5)',
            marginBottom: 'var(--space-5)', display: 'flex', flexWrap: 'wrap',
            gap: 'var(--space-6)',
          }}>
            {Object.keys(roleCounts).length > 0 && (
              <div>
                <div className="ui-eyebrow" style={{ marginBottom: 'var(--space-2)' }}>By role</div>
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  {Object.entries(roleCounts).sort((a, b) => b[1] - a[1])
                    .map(([role, n]) => chip(n, plural(role, n)))}
                </div>
              </div>
            )}
            {withTerms > 0 && (
              <div>
                <div className="ui-eyebrow" style={{ marginBottom: 'var(--space-2)' }}>By employment</div>
                <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                  {EMPLOYMENT_TYPES.filter(([k]) => analytics.emp[k])
                    .map(([k, label]) => chip(analytics.emp[k], label))}
                </div>
              </div>
            )}
          </div>
        );
      })()}

      {canSeeTeam && (
        <div style={{
          display: 'flex', gap: 'var(--space-3)', alignItems: 'center',
          flexWrap: 'wrap', marginBottom: 'var(--space-4)',
        }}>
          <SearchBox value={search} onChange={setSearch} placeholder="Search staff by name, role, or phone…" />
          {isOwner && (
            <button type="button" className="btn-primary" style={{ marginLeft: 'auto', padding: '10px 18px' }} onClick={() => setAdding(true)}>
              <Plus size={16} /> Add Staff Member
            </button>
          )}
        </div>
      )}

      {rows.length === 0 ? (
        <div className="ui-card" style={{ padding: 'var(--space-8)', textAlign: 'center', color: 'var(--text-secondary)' }}>
          {canSeeTeam
            ? 'No staff on the roster yet. Add someone with the button above -- their role, mobile number and login are all set up in one go.'
            : 'Your employment details have not been set up yet. Your boutique owner can add them.'}
        </div>
      ) : (
        // Cards, not a table: a roster row is a name plus a few values, and it
        // reads correctly at 320px without a horizontal scroller.
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
          {rows.map(({ member, terms: t }) => (
            <div key={member.id} className="ui-card" style={{ padding: 'var(--space-4) var(--space-5)' }}>
              <div className="at-staff" style={{ padding: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-3)', minWidth: 0 }}>
                  <AvatarInitials name={member.name} size={44} />
                  <div style={{ minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
                      {isOwner ? (
                        <button
                          type="button"
                          onClick={() => setPerson(member)}
                          title="Edit name, role and specialty"
                          style={{
                            fontWeight: 'var(--weight-semibold)', fontSize: 'var(--text-md)',
                            background: 'none', border: 'none', padding: 0, cursor: 'pointer',
                            color: 'var(--text-primary)', textAlign: 'left', fontFamily: 'inherit',
                          }}
                        >{member.name}</button>
                      ) : (
                        <div style={{ fontWeight: 'var(--weight-semibold)', fontSize: 'var(--text-md)',
                                      color: 'var(--text-primary)' }}>{member.name}</div>
                      )}
                    </div>
                    <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', marginTop: '2px' }}>
                      {member.role}
                      {member.isDesigner && ` · ${member.design_count ?? 0} design(s)${member.has_login ? '' : ' · no login yet'}`}
                    </div>
                    {member.phone && (
                      <div className="at-contact"><span><Phone size={12} /> {member.phone}</span></div>
                    )}
                  </div>
                </div>

                <div>
                  {member.status ? (
                    <span className={`ui-badge ui-badge--${member.status === 'Available' ? 'success' : member.status === 'Busy' ? 'warning' : 'neutral'}`}>
                      ● {member.status}
                    </span>
                  ) : member.isDesigner ? (
                    <span className="ui-badge ui-badge--neutral">Designer</span>
                  ) : null}
                </div>

                <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                    <Calendar size={12} /> Joined {t?.joined_at
                      ? new Date(t.joined_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
                      : '—'}
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                    <Briefcase size={12} /> {t ? employmentLabel(t.employment_type) : 'Not set'}
                  </span>
                </div>

                {isOwner && (
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center', justifyContent: 'flex-end', flexWrap: 'wrap' }}>
                    <button
                      type="button"
                      className="btn-secondary at-btn-sm"
                      onClick={() => setDocumentsFor(member)}
                      title="Identity and employment documents"
                    >
                      <FileText size={14} /> Documents
                    </button>
                    {!member.isDesigner && (
                      <button
                        type="button"
                        className={`${t ? 'btn-secondary' : 'btn-primary'} at-btn-sm`}
                        onClick={() => setEditing({ member, terms: t })}
                      >
                        {t ? 'Edit' : <><Plus size={14} /> Set up</>}
                      </button>
                    )}
                  </div>
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

              {t && showsPay(t) && depositByStaff.get(String(member.id)) && (
                (() => {
                  const d = depositByStaff.get(String(member.id));
                  return (
                    <div style={{
                      marginTop: '12px', paddingTop: '12px',
                      borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))',
                    }}>
                      <div className="ui-eyebrow" style={{ marginBottom: '8px' }}>
                        Security deposit
                      </div>
                      <div
                        className="mobile-stack-grid"
                        style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
                                 gap: '10px' }}
                      >
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Agreed</div>
                          <div style={{ fontWeight: 600 }}>{money(d.agreed)}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Recovered</div>
                          <div style={{ fontWeight: 600 }}>{money(d.recovered)}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Remaining</div>
                          <div style={{ fontWeight: 600 }}>{money(d.remaining)}</div>
                        </div>
                      </div>
                      {d.fully_recovered && (
                        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--success-color)', marginTop: '8px' }}>
                          Security deposit fully recovered.
                        </div>
                      )}
                    </div>
                  );
                })()
              )}

              {isOwner && t && showsPay(t) && (
                <div style={{
                  marginTop: '12px', paddingTop: '12px',
                  borderTop: '1px solid var(--border-color, rgba(255,255,255,0.08))',
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between',
                                alignItems: 'center', marginBottom: '8px' }}>
                    <div className="ui-eyebrow">
                      Advances
                    </div>
                    <button type="button" className="btn-secondary"
                            onClick={() => setIssuingFor(member)}
                            style={{ minHeight: '34px', fontSize: '12px',
                                     display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <Plus size={12} /> Issue advance
                    </button>
                  </div>
                  {(advancesByStaff.get(String(member.id)) || []).length === 0 ? (
                    <div style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      No outstanding advance.
                    </div>
                  ) : (
                    (advancesByStaff.get(String(member.id)) || []).map((a) => (
                      <div key={a.id}
                           className="mobile-stack-grid"
                           style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
                                    gap: '10px', marginBottom: '6px' }}>
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            Issued {new Date(a.issued_on).toLocaleDateString([], { day: 'numeric', month: 'short' })}
                          </div>
                          <div style={{ fontWeight: 600 }}>{money(a.issued)}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Recovered</div>
                          <div style={{ fontWeight: 600 }}>{money(a.recovered)}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                            Outstanding · {money(a.weekly_recovery)}/wk
                          </div>
                          <div style={{ fontWeight: 600 }}>{money(a.outstanding)}</div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              )}

              {t && !showsPay(t) && (
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '10px' }}>
                  Employment set up. Pay details are visible to the boutique owner only.
                </div>
              )}

              {/* Only a roster row can have employment terms -- StaffProfile's
                  FK points at Tailor -- so telling a designer theirs are
                  missing describes a state they can never leave. */}
              {!t && !member.isDesigner && (
                <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '10px' }}>
                  No employment details yet — this person works exactly as before.
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {issuingFor && (
        <Modal title={`Issue advance — ${issuingFor.name}`} onClose={() => setIssuingFor(null)}>
          <AdvanceForm
            member={issuingFor}
            onCancel={() => setIssuingFor(null)}
            onSaved={() => { setIssuingFor(null); refresh(); }}
          />
        </Modal>
      )}

      {editing && (
        <Modal
          title={editing.terms
            ? `Employment details — ${editing.member.name}`
            : `Set up ${editing.member.name}`}
          icon={User}
          subtitle={`Add employment and contact details for ${editing.member.name}.`}
          width="720px"
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

      {adding && (
        <AddStaffForm
          onCancel={() => setAdding(false)}
          onSaved={refresh}
          customRoles={rosterRoles}
        />
      )}

      {person && (
        <AddStaffForm
          member={person}
          onCancel={() => setPerson(null)}
          onSaved={refresh}
          customRoles={rosterRoles}
        />
      )}

      {documentsFor && (
        <DocumentsModal
          member={documentsFor}
          onClose={() => setDocumentsFor(null)}
        />
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
      <PageHeader
        title={canSeeTeam ? 'Staff Management' : 'My Attendance'}
        subtitle={canSeeTeam
          ? 'Manage your team, track attendance, payroll and performance.'
          : 'Check in and out, and see the hours recorded for you.'}
      />

      {/* Tab strip, not pill buttons: these switch a view, and an underline on
          the active one reads as navigation rather than four call-to-actions. */}
      <div style={{
        display: 'flex', gap: 'var(--space-1)', flexWrap: 'wrap', margin: 'var(--space-5) 0 var(--space-6)',
        borderBottom: '1px solid var(--border-color)',
      }}>
        {(isOwner
            ? TABS
            : canSeeTeam
              ? TABS.filter((t) => t.key !== 'payroll')
              : TABS.filter((t) => ['attendance', 'roster', 'performance'].includes(t.key)))
          .map(({ key, label, icon: Icon }) => {
          const active = tab === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setTab(key)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px',
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '10px 14px', marginBottom: '-1px',
                fontSize: 'var(--text-base)',
                fontWeight: active ? 'var(--weight-semibold)' : 'var(--weight-medium)',
                color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                borderBottom: `2px solid ${active ? 'var(--primary-color)' : 'transparent'}`,
              }}
            >
              <Icon size={15} /> {canSeeTeam || key !== 'roster' ? label : 'My details'}
            </button>
          );
        })}
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
        <Performance isOwner={isOwner} canSeeTeam={canSeeTeam} />
      )}
    </>
  );
}
