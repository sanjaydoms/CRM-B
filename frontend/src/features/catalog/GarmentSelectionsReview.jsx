import { useMemo } from 'react';
import { Image as ImageIcon, Layers, Scissors, Sparkles } from 'lucide-react';

import { resolveMediaUrl } from '../../services/media';
import { ACCESSORY_OPTIONS } from '../designStudio/GarmentPartPicker';

/**
 * Everything chosen for an order, dress by dress, before it is placed.
 *
 * Sits beside GarmentSummary on the review step and reads the same garment
 * jobs it does. Nothing is stored here: the designs come off
 * `job.design.parts` and `job.design.part_refs`, the fabrics and accessories
 * off `job.fabrics`, exactly where the Design Studio and Fabric steps wrote
 * them. Which is why a saree's pallu can never be listed under the blouse --
 * the selections never left the garment they were made on.
 *
 * Fabric and accessory choices share one slot map on the job. They are told
 * apart by their key: an accessory key is one the accessories picker
 * declares; every other key is a part of the garment from the fabric taxonomy.
 */

const formatKey = (key) => (key || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

const ACCESSORY_LABELS = Object.fromEntries(ACCESSORY_OPTIONS.map((o) => [o.key, o.label]));

// "m" for cloth, "pcs" for anything counted; the ledger's own unit otherwise.
const unitShort = (f) => (
  !f?.unit || f.unit === 'METER' ? 'm' : f.unit === 'PIECE' ? 'pcs' : String(f.unit).toLowerCase());

const FALLBACK =
  'https://images.unsplash.com/photo-1583391733956-3750e0ff4e8b?w=400';

function Thumb({ src, alt, size = 56 }) {
  return (
    <img src={resolveMediaUrl(src, FALLBACK)} alt={alt} loading="lazy"
         onError={(e) => { e.currentTarget.src = FALLBACK; }}
         style={{ width: size, height: size, borderRadius: '8px', objectFit: 'cover',
                  flexShrink: 0, border: '1px solid var(--border-color)', background: '#222' }} />
  );
}

function Empty({ children }) {
  return (
    <div style={{ fontSize: 'var(--text-sm, 13px)', color: 'var(--text-secondary)', padding: '2px 0' }}>
      {children}
    </div>
  );
}

/** One category inside one dress: an eyebrow, then its rows. */
function Group({ icon: Icon, title, count, children }) {
  return (
    <div style={{ marginTop: 'var(--space-3, 12px)' }}>
      <div className="ui-eyebrow garment-section-title"
           style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <Icon size={12} /> {title}
        {count > 0 && <span className="ui-badge ui-badge--neutral" style={{ marginLeft: '4px' }}>{count}</span>}
      </div>
      {children}
    </div>
  );
}

function Row({ thumb, label, value, sub }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '8px 0',
                  borderBottom: '1px solid var(--border-color)' }}>
      {thumb}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div style={{ fontSize: '11px', fontWeight: 700, textTransform: 'uppercase',
                      letterSpacing: '0.04em', color: 'var(--text-secondary)' }}>
          {label}
        </div>
        <div style={{ fontSize: '13.5px', fontWeight: 600, overflow: 'hidden',
                      textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {value}
        </div>
        {sub && (
          <div style={{ fontSize: '11.5px', color: 'var(--text-secondary)', overflow: 'hidden',
                        textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {sub}
          </div>
        )}
      </div>
    </div>
  );
}


export default function GarmentSelectionsReview({
  jobs = [], fabrics = [], taxonomy = null, onEditDesigns, onEditFabrics,
}) {
  const fabricById = useMemo(
    () => Object.fromEntries((fabrics || []).map((f) => [String(f.id), f])), [fabrics]);

  // Slot labels per garment, from the same taxonomy the fabric step reads.
  const slotLabels = useMemo(() => {
    const out = {};
    (taxonomy?.garments || []).forEach((g) => {
      out[g.key] = {};
      (g.sections || []).forEach((s) => (s.slots || []).forEach((slot) => {
        out[g.key][slot.key] = s.key && (g.sections.length > 1)
          ? `${s.label} · ${slot.label}` : slot.label;
      }));
    });
    return out;
  }, [taxonomy]);

  if (!jobs.length) {
    return <Empty>No garment was added to this order.</Empty>;
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3, 12px)' }}>
      {jobs.map((job) => {
        const garmentKey = job.template?.key || job.key;
        const garmentName = job.template?.name || job.key;

        // ---- designs: the chosen photograph per part, then the customer's own
        const parts = job.design?.parts || {};
        const refs = job.design?.part_refs || {};
        const designRows = [];
        const seenDesign = new Set();
        Object.entries(parts).forEach(([part, image]) => {
          if (!image?.image_url || seenDesign.has(`p:${part}:${image.id}`)) return;
          seenDesign.add(`p:${part}:${image.id}`);
          designRows.push({
            key: `p:${part}:${image.id}`, part,
            label: image.part_label || formatKey(part),
            value: image.design_title || 'Untitled design',
            sub: 'From the boutique catalogue',
            image_url: image.image_url,
          });
        });
        Object.entries(refs).forEach(([part, list]) => {
          (list || []).forEach((ref) => {
            if (!ref?.image_url || seenDesign.has(`r:${part}:${ref.id}`)) return;
            seenDesign.add(`r:${part}:${ref.id}`);
            designRows.push({
              key: `r:${part}:${ref.id}`, part,
              label: ref.part_label || formatKey(part),
              value: ref.design_title || (ref.source === 'customer_link' ? 'Reference link' : 'Reference photo'),
              sub: ref.source === 'customer_link' ? "Customer's link" : "Customer's photo",
              image_url: ref.image_url,
            });
          });
        });

        // ---- fabrics and accessories: one slot map, split by key
        const fabricRows = [];
        const accessoryRows = [];
        Object.entries(job.fabrics || {}).forEach(([slot, ids]) => {
          const unique = [...new Set((ids || []).map(String))];
          const isAccessory = slot in ACCESSORY_LABELS;
          unique.forEach((id) => {
            const f = fabricById[id];
            const qty = Number(job.fabric_qty?.[`${slot}:${id}`] || 0);
            const price = Number(f?.selling_price ?? f?.price_per_meter ?? 0);
            const row = {
              key: `${slot}:${id}`,
              // A placed order's job carries the labels it was placed with
              // (GarmentJob.selections), so the stage panel shows the same
              // categories to roles that cannot read the fabric taxonomy.
              label: isAccessory ? ACCESSORY_LABELS[slot]
                                 : (job.slot_labels?.[slot] || slotLabels[garmentKey]?.[slot] || formatKey(slot)),
              value: f?.name || `Item #${id}`,
              sub: [f?.material_type || f?.material, f?.color,
                    qty > 0 ? `${qty} ${unitShort(f)} needed` : null,
                    price > 0 ? `₹${price.toLocaleString('en-IN')}/${unitShort(f)}` : null]
                .filter(Boolean).join(' · ') || null,
              image_url: f?.image_url,
            };
            (isAccessory ? accessoryRows : fabricRows).push(row);
          });
        });

        const total = designRows.length + fabricRows.length + accessoryRows.length;

        return (
          <div key={job.key} className="ui-card garment-card">
            <div className="garment-card-head">
              <span className="garment-card-name">{garmentName}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2, 8px)', flexWrap: 'wrap' }}>
                <span className="ui-badge ui-badge--neutral">
                  {total} selection{total === 1 ? '' : 's'}
                </span>
                {onEditDesigns && (
                  <button type="button" className="btn-secondary"
                          style={{ padding: '4px 10px', fontSize: 'var(--text-2xs, 11px)' }}
                          onClick={() => onEditDesigns(job.key)}>
                    Edit designs
                  </button>
                )}
                {onEditFabrics && (
                  <button type="button" className="btn-secondary"
                          style={{ padding: '4px 10px', fontSize: 'var(--text-2xs, 11px)' }}
                          onClick={() => onEditFabrics(job.key)}>
                    Edit fabrics &amp; accessories
                  </button>
                )}
              </span>
            </div>

            <Group icon={Sparkles} title="Designs" count={designRows.length}>
              {designRows.length === 0 ? <Empty>No design selected</Empty> : designRows.map((r) => (
                <Row key={r.key} label={r.label} value={r.value} sub={r.sub}
                     thumb={<Thumb src={r.image_url} alt={r.label} />} />
              ))}
            </Group>

            <Group icon={Layers} title="Fabrics" count={fabricRows.length}>
              {fabricRows.length === 0 ? <Empty>No fabric selected</Empty> : fabricRows.map((r) => (
                <Row key={r.key} label={r.label} value={r.value} sub={r.sub}
                     thumb={r.image_url
                       ? <Thumb src={r.image_url} alt={r.value} size={44} />
                       : <span style={{ width: 44, height: 44, borderRadius: '8px', flexShrink: 0,
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        background: 'var(--surface-inset, #f3f4f6)', color: 'var(--text-muted)' }}>
                           <ImageIcon size={16} />
                         </span>} />
              ))}
            </Group>

            <Group icon={Scissors} title="Accessories" count={accessoryRows.length}>
              {accessoryRows.length === 0 ? <Empty>No accessories selected</Empty> : accessoryRows.map((r) => (
                <Row key={r.key} label={r.label} value={r.value} sub={r.sub}
                     thumb={r.image_url
                       ? <Thumb src={r.image_url} alt={r.value} size={44} />
                       : <span style={{ width: 44, height: 44, borderRadius: '8px', flexShrink: 0,
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        background: 'var(--surface-inset, #f3f4f6)', color: 'var(--text-muted)' }}>
                           <Scissors size={16} />
                         </span>} />
              ))}
            </Group>
          </div>
        );
      })}
    </div>
  );
}
