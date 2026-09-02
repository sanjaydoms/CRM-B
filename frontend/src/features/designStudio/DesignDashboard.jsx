import { useEffect, useRef, useState } from 'react';
import { Award, Clock, Image as ImageIcon, Key, UserPlus, Users } from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';
import { useLanguage } from '../../i18n/LanguageContext.jsx';

// The password now comes back from create-login, generated for that one
// account and returned on that one response. The constant that used to live
// here held a literal shared by every designer on the platform -- shipped in
// this bundle, and a working credential against any boutique, because login
// resolves an account by scanning every schema for the username.

/**
 * The module's landing counters and leaderboards.
 *
 * One request. The library opens on a gallery deliberately fetched narrowly
 * (see DesignLibrary); this screen is the same idea applied to the numbers --
 * a single endpoint rather than the main dashboard's pattern of firing one
 * request per widget.
 */

const CARD_IMAGE_FALLBACK =
  'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400';

function StatTile({ icon: Icon, label, value, accent }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '12px', padding: '16px',
      border: '1px solid var(--border-color)', borderRadius: '10px',
      background: 'var(--surface-color)',
    }}>
      <div style={{
        width: '38px', height: '38px', borderRadius: '8px', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: accent ? 'rgba(212,175,55,0.12)' : 'rgba(255,255,255,0.05)',
        color: accent ? 'var(--accent-text, #b07c40)' : 'var(--text-secondary)',
      }}>
        <Icon size={18} />
      </div>
      <div>
        <div style={{ fontSize: '20px', fontWeight: 700 }}>{value}</div>
        <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{label}</div>
      </div>
    </div>
  );
}

function DesignStrip({ title, designs, emptyText, metric }) {
  return (
    <div className="content-card">
      <div className="card-title" style={{ fontSize: '14px' }}>{title}</div>
      {!designs?.length ? (
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)', padding: '8px 0' }}>{emptyText}</div>
      ) : (
        <div style={{ display: 'flex', gap: '12px', overflowX: 'auto', paddingBottom: '4px' }}>
          {designs.map((d) => (
            <div key={d.id} style={{ minWidth: '140px', flexShrink: 0 }}>
              <img src={resolveMediaUrl(d.image_url, CARD_IMAGE_FALLBACK)} alt={d.title}
                   style={{ width: '100%', height: '110px', objectFit: 'cover', borderRadius: '6px' }} />
              <div style={{ fontSize: '12px', fontWeight: 600, marginTop: '6px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {d.title}
              </div>
              <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                {metric === 'views' ? `${d.view_count} views` : metric === 'orders' ? `${d.order_count} orders` : d.designer_name || 'Unattributed'}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * Owner-only: the roster of credited designers, where one is added and where a
 * login is switched on. There is no separate "Manage Designers" screen yet, so
 * this is where both step 7's account-creation and the roster itself get used
 * from.
 *
 * Adding is here rather than on its own screen because until it was, a
 * boutique had no way to add a designer at all: the POST endpoint existed and
 * was Owner-gated, but nothing called it, so the only rows that ever existed
 * were the ones migration 0003 backfilled out of free-text credits. A studio
 * set up after that migration ran had an empty roster with no way to fill it.
 */
function DesignerRoster() {
  const [designers, setDesigners] = useState([]);
  const [error, setError] = useState(null);
  const [emailDrafts, setEmailDrafts] = useState({});
  const [granting, setGranting] = useState(null);
  const [issued, setIssued] = useState(null);   // { name, email } just granted
  const [draft, setDraft] = useState({ name: '', email: '' });
  const [adding, setAdding] = useState(false);
  const inFlight = useRef(false);

  const load = () => {
    api.getDesigners().then(setDesigners).catch((err) => setError(err.message));
  };

  useEffect(load, []);

  // An email typed when the designer was added is what the Grant login box
  // starts from, so the Owner is not asked for the same address twice. `??`
  // rather than `||` so clearing the box stays cleared.
  const draftEmail = (designer) => emailDrafts[designer.id] ?? designer.email ?? '';

  const add = async (event) => {
    event.preventDefault();
    const name = draft.name.trim();
    if (!name || adding) return;
    setAdding(true);
    try {
      await api.createDesigner({ name, email: draft.email.trim() });
      setDraft({ name: '', email: '' });
      load();
    } catch (err) {
      setError(`Could not add ${name} — ${err.message}`);
    } finally {
      setAdding(false);
    }
  };

  const grant = async (designer) => {
    const email = draftEmail(designer).trim();
    if (!email || inFlight.current) return;   // one click, one call
    inFlight.current = true;
    setGranting(designer.id);
    try {
      const created = await api.createDesignerLogin(designer.id, email);
      setIssued({ name: designer.name, email,
                  password: created && created.bootstrap_password });
      load();
    } catch (err) {
      setError(`Could not grant a login to ${designer.name} — ${err.message}`);
    } finally {
      inFlight.current = false;
      setGranting(null);
    }
  };

  if (error) {
    return (
      <div className="content-card" style={{ color: '#c0392b', fontSize: '12.5px' }}>
        {error}
        <button className="btn-secondary" style={{ marginLeft: '10px', padding: '3px 8px', fontSize: '11px' }}
                onClick={() => { setError(null); load(); }}>Retry</button>
      </div>
    );
  }

  return (
    <div className="content-card">
      <div className="card-title" style={{ fontSize: '14px' }}>Designers</div>

      <form onSubmit={add}
            style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', margin: '4px 0 12px' }}>
        <input
          className="form-control" placeholder="Designer name" required
          style={{ padding: '5px 8px', fontSize: '12px', flex: '1 1 140px' }}
          value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
        />
        <input
          className="form-control" type="email" placeholder="Email (optional)"
          style={{ padding: '5px 8px', fontSize: '12px', flex: '1 1 170px' }}
          value={draft.email} onChange={(e) => setDraft({ ...draft, email: e.target.value })}
        />
        <button className="btn-secondary" type="submit"
                style={{ padding: '5px 10px', fontSize: '11px', whiteSpace: 'nowrap' }}
                disabled={adding || !draft.name.trim()}>
          <UserPlus size={11} /> {adding ? 'Adding…' : 'Add designer'}
        </button>
      </form>

      {designers.length === 0 ? (
        <div style={{ fontSize: '12.5px', color: 'var(--text-secondary)' }}>
          No designers yet. Add one above to credit them on a design.
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {designers.map((d) => (
            <div key={d.id} style={{
              display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 10px', flexWrap: 'wrap',
              border: '1px solid var(--border-color)', borderRadius: '6px',
            }}>
              <span style={{ fontSize: '13px', fontWeight: 600, flex: '0 0 130px' }}>{d.name}</span>
              <span style={{ fontSize: '11px', color: 'var(--text-secondary)', flex: '0 0 90px' }}>
                {d.design_count} design{d.design_count === 1 ? '' : 's'}
              </span>
              {d.has_login ? (
                <span style={{ fontSize: '11px', color: '#34d399', marginLeft: 'auto' }}>Has a login</span>
              ) : (
                <span style={{ display: 'flex', gap: '6px', marginLeft: 'auto', flex: '1 1 auto', maxWidth: '360px' }}>
                  <input
                    className="form-control" type="email" placeholder="designer@boutique.com"
                    style={{ padding: '5px 8px', fontSize: '12px' }}
                    value={draftEmail(d)}
                    onChange={(e) => setEmailDrafts({ ...emailDrafts, [d.id]: e.target.value })}
                  />
                  <button className="btn-secondary" style={{ padding: '5px 10px', fontSize: '11px', whiteSpace: 'nowrap' }}
                          disabled={granting === d.id || !draftEmail(d).trim()}
                          onClick={() => grant(d)}>
                    <Key size={11} /> {granting === d.id ? 'Granting…' : 'Grant login'}
                  </button>
                </span>
              )}
            </div>
          ))}
        </div>
      )}

      {issued && (
        <div className="accent-banner" style={{ marginTop: '12px', fontSize: '12.5px' }}>
          <div style={{ marginBottom: '4px' }}>
            Login created for <strong>{issued.name}</strong>. Share these credentials with them directly --
            this is the only time the password is shown here.
          </div>
          <div>
            Email: <strong>{issued.email}</strong>
            {issued.password ? (
              <> &nbsp;·&nbsp; Password: <strong style={{ fontFamily: 'ui-monospace, monospace' }}>{issued.password}</strong></>
            ) : (
              // create-login linked an account this person already had, so
              // their existing password still stands and there is none to give.
              <> &nbsp;·&nbsp; They already had an account — their existing password still works.</>
            )}
          </div>
          {issued.password && (
            <div style={{ marginTop: '6px', fontSize: '12px', opacity: 0.75 }}>
              Shown once. Copy it now — closing this panel is the last time it can be read.
            </div>
          )}
          <button className="btn-secondary" style={{ marginTop: '8px', padding: '4px 10px', fontSize: '11px' }}
                  onClick={() => setIssued(null)}>Close</button>
        </div>
      )}
    </div>
  );
}

export default function DesignDashboard({ onOpenLibrary, canManageDesigners = false }) {
  const { t } = useLanguage();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    setError(null);
    api.getDesignDashboard().then(setData).catch((err) => setError(err.message));
  };

  useEffect(load, []);

  if (error) {
    return (
      <div className="content-card" style={{ color: '#c0392b', fontSize: '13px' }}>
        The design dashboard could not be loaded — {error}
        <button className="btn-secondary" style={{ marginLeft: '10px', padding: '4px 10px', fontSize: '12px' }} onClick={load}>
          {t('common.retry', 'Retry')}
        </button>
      </div>
    );
  }

  if (!data) return <div className="content-card">{t('common.loading', 'Loading…')}</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px' }}>
        <StatTile icon={ImageIcon} label={t('designsPage.totalDesigns', 'Total Designs')} value={data.total_designs} />
        <StatTile icon={Users} label={t('designsPage.designers', 'Designers')} value={data.designers} />
        <StatTile icon={Award} label={t('designsPage.collections', 'Collections')} value={data.collections} />
        <StatTile
          icon={Clock}
          label={t('designsPage.pendingApproval', 'Pending Approval')}
          value={data.pending_approval}
          accent={data.pending_approval > 0}
        />
      </div>

      {data.pending_approval > 0 && (
        <div className="accent-banner" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer' }}
             onClick={() => onOpenLibrary?.('pending')}>
          <span>{data.pending_approval} design{data.pending_approval === 1 ? '' : 's'} waiting on your review.</span>
          <span style={{ fontWeight: 600, textDecoration: 'underline' }}>Open the queue</span>
        </div>
      )}

      <DesignStrip title={t('designsPage.recentUploads', 'Recent Uploads')} designs={data.recent_uploads} emptyText="Nothing uploaded yet." />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
        <DesignStrip title={t('designsPage.mostViewed', 'Most Viewed')} designs={data.most_viewed} metric="views" emptyText="No views recorded yet." />
        <DesignStrip title={t('designsPage.mostOrdered', 'Most Ordered')} designs={data.most_ordered} metric="orders" emptyText="No orders placed from the library yet." />
      </div>
      <DesignStrip title={t('designsPage.trendingThisWeek', 'Trending This Week')} designs={data.trending} metric="views" emptyText="Nothing trending in the last 7 days." />

      {canManageDesigners && <DesignerRoster />}
    </div>
  );
}
