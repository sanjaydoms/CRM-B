import { useEffect, useState } from 'react';
import { Award, Clock, Eye, Image as ImageIcon, ShoppingBag, TrendingUp, Users } from 'lucide-react';

import { api } from '../../services/api';
import { resolveMediaUrl } from '../../services/media';

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
        color: accent ? 'var(--accent-color, #d4af37)' : 'var(--text-secondary)',
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

export default function DesignDashboard({ onOpenLibrary }) {
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
          Retry
        </button>
      </div>
    );
  }

  if (!data) return <div className="content-card">Loading…</div>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px' }}>
        <StatTile icon={ImageIcon} label="Total Designs" value={data.total_designs} />
        <StatTile icon={Users} label="Designers" value={data.designers} />
        <StatTile icon={Award} label="Collections" value={data.collections} />
        <StatTile
          icon={Clock}
          label="Pending Approval"
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

      <DesignStrip title="Recent Uploads" designs={data.recent_uploads} emptyText="Nothing uploaded yet." />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
        <DesignStrip title="Most Viewed" designs={data.most_viewed} metric="views" emptyText="No views recorded yet." />
        <DesignStrip title="Most Ordered" designs={data.most_ordered} metric="orders" emptyText="No orders placed from the library yet." />
      </div>
      <DesignStrip title="Trending This Week" designs={data.trending} metric="views" emptyText="Nothing trending in the last 7 days." />
    </div>
  );
}
