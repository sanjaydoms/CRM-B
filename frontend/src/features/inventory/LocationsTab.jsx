import { useCallback, useEffect, useState } from 'react';
import { ArrowRight, MapPin } from 'lucide-react';

import { api } from '../../services/api';

/**
 * Where stock physically is, and moving it between places.
 *
 * The total on an item is authoritative; this is the breakdown of where that
 * total sits. A transfer never changes the total -- material stops being in one
 * place and starts being in another -- which is why the form asks for a source
 * as well as a destination and refuses to send material from somewhere that
 * does not hold it.
 */

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
};

const qty = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 3 });

export default function LocationsTab({ items, isOwner, onMoved }) {
  const [locations, setLocations] = useState([]);
  const [selected, setSelected] = useState(null);
  const [held, setHeld] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [transferring, setTransferring] = useState(false);

  useEffect(() => {
    api.getStockLocations({ active: 'true' })
      .then((rows) => {
        setLocations(rows || []);
        setSelected((rows || []).find((l) => l.is_default) || (rows || [])[0] || null);
      })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const loadHeld = useCallback((location) => {
    if (!location) { setHeld([]); return; }
    api.getLocationStock(location.id)
      .then((rows) => setHeld(rows || []))
      .catch((err) => setError(err.message));
  }, []);

  useEffect(() => { loadHeld(selected); }, [selected, loadHeld]);

  return (
    <div style={{ marginTop: '20px' }}>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '16px' }}>
        <div style={{ fontSize: '13px', color: 'var(--text-secondary)', flex: '1 1 auto' }}>
          Material moves between units as it is worked on. Every transfer is recorded.
        </div>
        {isOwner && (
          <button type="button" className="btn-primary" style={{ fontSize: '13px' }}
                  onClick={() => setTransferring(true)}>
            <ArrowRight size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} />
            Transfer stock
          </button>
        )}
      </div>

      {error && (
        <div style={{ ...panel, padding: '12px 16px', marginBottom: '12px', borderColor: 'rgba(220,38,38,0.3)', color: '#fca5a5', fontSize: '13px' }}>
          {error}
        </div>
      )}

      <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(190px, 100%), 1fr))', gap: '10px' }}>
        {locations.map((location) => (
          <button
            key={location.id}
            type="button"
            onClick={() => setSelected(location)}
            style={{
              ...panel, padding: '14px 16px', textAlign: 'left', cursor: 'pointer', color: 'inherit',
              borderColor: selected?.id === location.id ? 'var(--accent-text, #b07c40)' : 'var(--border-color)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '13.5px', fontWeight: 600 }}>
              <MapPin size={13} /> {location.name}
            </div>
            <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>
              {location.kind_display}{location.is_default ? ' · default' : ''}
            </div>
          </button>
        ))}
      </div>

      {selected && (
        <div style={{ ...panel, marginTop: '18px', overflow: 'hidden' }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-color)', fontSize: '13px', fontWeight: 600 }}>
            Held at {selected.name}
            <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: '8px' }}>
              {held.length} material{held.length === 1 ? '' : 's'}
            </span>
          </div>
          {held.length === 0 ? (
            <div style={{ padding: '28px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              Nothing is here at the moment.
            </div>
          ) : (
            <div className="responsive-table-wrapper">
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                <thead>
                  <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    <th style={{ padding: '12px' }}>Material</th>
                    <th style={{ padding: '12px', textAlign: 'right' }}>Quantity</th>
                  </tr>
                </thead>
                <tbody>
                  {held.map((row) => (
                    <tr key={row.id} style={{ borderTop: '1px solid var(--border-color)' }}>
                      <td style={{ padding: '10px 12px' }}>
                        <div style={{ fontWeight: 500 }}>{row.item_name}</div>
                        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{row.item_code}</div>
                      </td>
                      <td style={{ padding: '10px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                        {qty(row.quantity)} <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>{row.unit_display}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {transferring && (
        <TransferModal
          items={items}
          locations={locations}
          onClose={() => setTransferring(false)}
          onDone={() => { setTransferring(false); loadHeld(selected); onMoved?.(); }}
        />
      )}
    </div>
  );
}

function TransferModal({ items, locations, onClose, onDone }) {
  const [item, setItem] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [quantity, setQuantity] = useState('');
  const [breakdown, setBreakdown] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  // Showing where the chosen item actually is turns "transfer 20 from the
  // warehouse" from a guess into a decision.
  useEffect(() => {
    if (!item) { setBreakdown(null); return; }
    api.getItemLocations(item).then(setBreakdown).catch(() => setBreakdown(null));
  }, [item]);

  const submit = async () => {
    setError(null);
    if (!item || !from || !to || !quantity) {
      setError('Choose a material, both locations and a quantity.');
      return;
    }
    if (from === to) {
      setError('The source and the destination are the same place.');
      return;
    }
    setSaving(true);
    try {
      await api.transferStock(item, { quantity, from_location: from, to_location: to });
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}
         onClick={onClose}>
      <div className="search-modal-card" style={{ ...panel, background: 'var(--surface-color)', width: '100%', maxWidth: '480px', padding: '22px' }}
           onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>Transfer stock</h3>

        <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Material</label>
        <select className="form-control" value={item} onChange={(e) => setItem(e.target.value)} style={{ marginBottom: '12px' }}>
          <option value="">Choose a material…</option>
          {items.map((row) => (
            <option key={row.id} value={row.id}>{row.name} ({row.item_code})</option>
          ))}
        </select>

        {breakdown && breakdown.breakdown?.length > 0 && (
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginBottom: '12px' }}>
            Currently:{' '}
            {breakdown.breakdown.map((row) => `${row.quantity} at ${row.location}`).join(' · ')}
          </div>
        )}

        <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>From</label>
            <select className="form-control" value={from} onChange={(e) => setFrom(e.target.value)}>
              <option value="">Source…</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>To</label>
            <select className="form-control" value={to} onChange={(e) => setTo(e.target.value)}>
              <option value="">Destination…</option>
              {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
            </select>
          </div>
        </div>

        <label style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>Quantity</label>
        <input className="form-control" type="number" step="0.001" min="0" value={quantity}
               onChange={(e) => setQuantity(e.target.value)} placeholder="e.g. 12.5" />

        {error && <div style={{ color: '#fca5a5', fontSize: '12.5px', marginTop: '12px' }}>{error}</div>}

        <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '20px' }}>
          <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
          <button type="button" className="btn-primary" onClick={submit} disabled={saving}>
            {saving ? 'Moving…' : 'Transfer'}
          </button>
        </div>
      </div>
    </div>
  );
}
