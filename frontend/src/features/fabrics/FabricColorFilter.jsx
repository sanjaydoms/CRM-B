import { useMemo } from 'react';
import { Palette, Search, X } from 'lucide-react';

import { isHexQuery } from './colour';

/**
 * Narrow the boutique's fabrics to one colour.
 *
 * The palette is not a list of colours written down here. It is every colour
 * the boutique's own rolls carry, read off the fabrics on screen -- so a
 * swatch can never point at nothing, and a shade the boutique stocks next
 * month shows up on its own. Each swatch is painted with the roll's exact
 * `color_hex` where Manage Fabrics recorded one, because the name a boutique
 * gives a colour ("Aqua Blue") is not the colour.
 *
 * One value drives both controls: clicking a swatch puts its name in the box,
 * and typing in the box is the same filter by hand. Empty means everything,
 * which is where the step opens.
 */

/** A plain colour name that CSS itself understands ("red", "teal"), used to
 *  paint a swatch for a roll that has a name but no recorded shade. */
const cssColourOf = (name) => {
  if (typeof CSS === 'undefined' || !CSS.supports) return null;
  const word = (name || '').trim().toLowerCase().replace(/\s+/g, '');
  return word && CSS.supports('color', word) ? word : null;
};

export default function FabricColorFilter({ fabrics = [], value = '', onChange }) {
  // One swatch per colour name, the first recorded shade standing for the
  // group. In stock only, the same rule the grid itself applies.
  const swatches = useMemo(() => {
    const seen = new Map();
    (fabrics || [])
      .filter(f => (f.color || '').trim())
      .forEach((f) => {
        const key = f.color.trim().toLowerCase();
        const entry = seen.get(key) || { name: f.color.trim(), hex: '', count: 0 };
        if (!entry.hex && f.color_hex) entry.hex = f.color_hex;
        entry.count += 1;
        seen.set(key, entry);
      });
    return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
  }, [fabrics]);

  const active = (value || '').trim().toLowerCase();
  // What the wheel shows: the picked shade, or a neutral when nothing is.
  const wheel = isHexQuery(value) ? value.trim() : '#c8a97e';

  return (
    <div style={{ marginBottom: '18px', padding: '14px 16px', borderRadius: '12px',
                  border: '1px solid var(--border-color)', background: 'var(--surface-color, #fff)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
                    marginBottom: '12px' }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px',
                       fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                       color: 'var(--text-secondary)' }}>
          <Palette size={13} /> Filter by colour
        </span>

        {/* The colour wheel -- the same control Manage Fabrics records a
            shade with, so picking a colour here feels like naming one there.
            The native input is present but invisible; the swatch is the
            button. Picking writes a hex into the one shared value. */}
        <label className="at-swatch" title="Pick any colour"
               style={{ position: 'relative', cursor: 'pointer', width: '62px', height: '36px', padding: '4px' }}>
          <i style={{ background: wheel }} />
          <input
            type="color"
            aria-label="Pick any colour"
            value={wheel}
            onChange={(e) => onChange(e.target.value)}
            style={{ position: 'absolute', width: 1, height: 1, opacity: 0, left: 0, bottom: 0 }}
          />
        </label>

        <span style={{ position: 'relative', display: 'flex', alignItems: 'center',
                       flex: '1 1 220px', maxWidth: '320px' }}>
          <Search size={13} style={{ position: 'absolute', left: '10px', color: 'var(--text-muted)' }} />
          <input
            className="form-control"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="Type a colour, e.g. maroon — or use the wheel"
            style={{ padding: '7px 30px 7px 30px', fontSize: '12.5px', borderRadius: '10px' }}
          />
          {value && (
            <button type="button" title="Show all colours" onClick={() => onChange('')}
                    style={{ position: 'absolute', right: '6px', width: '20px', height: '20px',
                             borderRadius: '50%', border: 'none', cursor: 'pointer',
                             background: 'var(--surface-inset, #f3f4f6)', color: 'var(--text-secondary)',
                             display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>
              <X size={12} />
            </button>
          )}
        </span>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', alignItems: 'center' }}>
        <button
          type="button"
          onClick={() => onChange('')}
          style={{ padding: '5px 12px', borderRadius: '999px', fontSize: '12px', fontWeight: 600,
                   cursor: 'pointer',
                   border: !active ? '1.5px solid #107c41' : '1.5px solid var(--border-color)',
                   background: !active ? '#107c41' : 'var(--surface-color, #fff)',
                   color: !active ? '#fff' : 'var(--text-primary)' }}
        >
          All colours
        </button>

        {swatches.map((sw) => {
          const isActive = active === sw.name.toLowerCase();
          const paint = sw.hex || cssColourOf(sw.name);
          return (
            <button
              key={sw.name}
              type="button"
              title={`${sw.name} · ${sw.count} fabric${sw.count === 1 ? '' : 's'}`}
              aria-pressed={isActive}
              onClick={() => onChange(isActive ? '' : sw.name)}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '7px',
                       padding: '4px 11px 4px 5px', borderRadius: '999px', cursor: 'pointer',
                       fontSize: '12px', fontWeight: 600,
                       border: isActive ? '1.5px solid #107c41' : '1.5px solid var(--border-color)',
                       background: isActive ? 'rgba(16,124,65,0.08)' : 'var(--surface-color, #fff)',
                       color: isActive ? '#107c41' : 'var(--text-primary)',
                       boxShadow: isActive ? '0 0 0 3px rgba(16,124,65,0.12)' : 'none',
                       transition: 'all 0.15s ease' }}
            >
              {/* The swatch: the exact shade where one is recorded, a plain CSS
                  colour where the name is one, and a neutral ring otherwise so
                  a name like "Peacock" still gets a button. */}
              <span aria-hidden style={{ width: '20px', height: '20px', borderRadius: '50%',
                                         flexShrink: 0, background: paint || 'var(--surface-inset, #e5e7eb)',
                                         border: '1px solid rgba(0,0,0,0.12)',
                                         boxShadow: 'inset 0 0 0 2px rgba(255,255,255,0.8)' }} />
              {sw.name}
            </button>
          );
        })}
      </div>
    </div>
  );
}
