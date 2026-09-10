import { useEffect, useRef, useState } from 'react';
import { Award, Clock, Eye, Image as ImageIcon, Key, LayoutGrid, ShoppingCart, Upload, UserPlus, Users } from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';
import { useLanguage } from '../../i18n/LanguageContext.jsx';
import { IconTile, SectionCard, StatCard } from '../../components/ui/Atelier';

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

function DesignStrip({ title, subtitle, icon, tone, designs, emptyText, metric, action, actionLabel }) {
  const ranked = metric === 'views' || metric === 'orders';
  return (
    <SectionCard icon={icon} tone={tone} title={title} subtitle={subtitle} action={action} actionLabel={actionLabel}>
      {!designs?.length ? (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)', padding: '4px 0' }}>{emptyText}</div>
      ) : ranked ? (
        <div>
          {designs.map((d, i) => (
            <div key={d.id} className="at-row">
              <span className={`at-avatar at-tile--${i === 0 ? 'rose' : i === 1 ? 'amber' : 'neutral'}`}
                    style={{ width: 28, height: 28, fontSize: 12 }}>{i + 1}</span>
              <span className="at-row-main">
                <span className="at-row-title">{d.title}</span>
                <span className="at-row-sub">
                  {d.garment_type || 'Design'} · {metric === 'views' ? `${d.view_count} views` : `${d.order_count} orders`}
                </span>
              </span>
              <img src={resolveMediaUrl(d.image_url, CARD_IMAGE_FALLBACK)} alt=""
                   style={{ width: 44, height: 56, objectFit: 'cover', borderRadius: 8, flexShrink: 0 }} />
            </div>
          ))}
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))', gap: 'var(--space-3)' }}>
          {designs.map((d) => (
            <div key={d.id} style={{ minWidth: 0 }}>
              <img src={resolveMediaUrl(d.image_url, CARD_IMAGE_FALLBACK)} alt={d.title}
                   style={{ width: '100%', aspectRatio: '4 / 5', objectFit: 'cover', borderRadius: 10, display: 'block' }} />
              <div className="at-row-title" style={{ marginTop: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {d.title}
              </div>
              <div className="at-row-sub">
                {d.garment_type || d.designer_name || 'Unattributed'}
                {d.created_at ? ` · added ${new Date(d.created_at).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}` : ''}
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionCard>
  );
}

/** Categories at a glance: counts per garment, straight from the library's
 *  own category endpoint, with a way into the library to manage them. */
function CategoriesPanel({ onOpenLibrary }) {
  const [categories, setCategories] = useState(null);
  useEffect(() => {
    api.getDesignCategories()
      .then((data) => setCategories((data.categories || []).filter((c) => c.key)))
      .catch(() => setCategories([]));
  }, []);
  return (
    <SectionCard icon={LayoutGrid} tone="neutral" title="Categories" action={onOpenLibrary} actionLabel="Manage">
      {categories === null ? (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>Loading…</div>
      ) : categories.length === 0 ? (
        <div style={{ fontSize: 'var(--text-sm)', color: 'var(--text-secondary)' }}>No garment categories yet.</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(110px, 1fr))', gap: 'var(--space-2)' }}>
          {categories.slice(0, 6).map((c) => (
            <button key={c.key} type="button" className="at-cat" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}
                    onClick={onOpenLibrary}>
              <IconTile icon={ImageIcon} tone={c.count ? 'green' : 'neutral'} size={34} iconSize={16} />
              <span className="at-cat-name">{c.name}</span>
              <span className="at-cat-count">{c.count} design{c.count === 1 ? '' : 's'}</span>
            </button>
          ))}
        </div>
      )}
    </SectionCard>
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
      <div className="content-card" style={{ color: 'var(--danger-color)', fontSize: '12.5px' }}>
        {error}
        <button className="btn-secondary" style={{ marginLeft: '10px', padding: '3px 8px', fontSize: '11px' }}
                onClick={() => { setError(null); load(); }}>Retry</button>
      </div>
    );
  }

  return (
    <SectionCard icon={Users} tone="blue" title="Designers" subtitle="Who is credited on the library, and who can sign in">

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
                <span style={{ fontSize: '11px', color: 'var(--success-color)', marginLeft: 'auto' }}>Has a login</span>
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
    </SectionCard>
  );
}

export default function DesignDashboard({ onOpenLibrary, canManageDesigners = false }) {
  const { t } = useLanguage();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  const load = () => {
    api.getDesignDashboard()
      .then((d) => { setData(d); setError(null); })
      .catch((err) => setError(err.message));
  };

  useEffect(load, []);

  if (error) {
    return (
      <div className="content-card" style={{ color: 'var(--danger-color)', fontSize: '13px' }}>
        The design dashboard could not be loaded — {error}
        <button className="btn-secondary" style={{ marginLeft: '10px', padding: '4px 10px', fontSize: '12px' }} onClick={load}>
          {t('common.retry', 'Retry')}
        </button>
      </div>
    );
  }

  if (!data) return <div className="content-card">{t('common.loading', 'Loading…')}</div>;

  return (
    <div className="at-stack">
      <div className="at-stat-grid">
        <StatCard icon={ImageIcon} tone="green" label={t('designsPage.totalDesigns', 'Total Designs')} value={data.total_designs}
                  sub={data.recent_uploads?.length ? `${data.recent_uploads.length} recent upload${data.recent_uploads.length === 1 ? '' : 's'}` : 'Nothing uploaded yet'} />
        <StatCard icon={Users} tone="amber" label={t('designsPage.designers', 'Designers')} value={data.designers} sub="Active" />
        <StatCard icon={Award} tone="violet" label={t('designsPage.collections', 'Collections')} value={data.collections}
                  sub={data.collections ? 'Curated sets' : 'Create your first'} />
        <StatCard icon={Clock} tone={data.pending_approval > 0 ? 'rose' : 'blue'} label={t('designsPage.pendingApproval', 'Pending Approval')}
                  value={data.pending_approval} sub={data.pending_approval > 0 ? 'Waiting on your review' : 'All up to date'}
                  onClick={data.pending_approval > 0 ? () => onOpenLibrary?.('pending') : undefined} />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 2fr) minmax(260px, 1fr)', gap: 'var(--space-4)' }} className="design-dashboard-grid">
        <DesignStrip icon={Upload} tone="green" title={t('designsPage.recentUploads', 'Recent Uploads')} subtitle="Your latest added designs"
                     designs={data.recent_uploads} emptyText="Nothing uploaded yet." action={onOpenLibrary} />
        <CategoriesPanel onOpenLibrary={onOpenLibrary} />
      </div>
      <div className="at-grid-2">
        <DesignStrip icon={Eye} tone="amber" title={t('designsPage.mostViewed', 'Most Viewed')} subtitle="Designs that get the most attention"
                     designs={data.most_viewed} metric="views" emptyText="No views recorded yet." action={onOpenLibrary} />
        <DesignStrip icon={ShoppingCart} tone="green" title={t('designsPage.mostOrdered', 'Most Ordered')} subtitle="Designs loved by your customers"
                     designs={data.most_ordered} metric="orders" emptyText="No orders placed from the library yet." action={onOpenLibrary} />
      </div>
      <DesignStrip icon={Clock} tone="violet" title={t('designsPage.trendingThisWeek', 'Trending This Week')} subtitle="Most viewed in the last 7 days"
                   designs={data.trending} metric="views" emptyText="Nothing trending in the last 7 days." />

      {canManageDesigners && <DesignerRoster />}
    </div>
  );
}
