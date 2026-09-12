import { SlidersHorizontal, X } from 'lucide-react';

import { describePath, useDesignCatalogue } from './designCatalogue';

/**
 * Narrowing the Design Studio's list to one catalogue position: Category,
 * then Section where the category has them, then Design option.
 *
 * One compact row of selects rather than the library's chip rows: the chips
 * are a browser, made for a page whose whole job is the catalogue, and above
 * a part-tab strip and a grid they were three rows of buttons before a single
 * photograph. Here the filter is a tool at the top of the picker, so it takes
 * the strip's own well and one line.
 *
 * Same tree, same {category, subcategory, option} value as the browser, so
 * the picker filters by exactly what an upload was filed under. Renders
 * nothing for a garment with no catalogue.
 */
export default function DesignCatalogueFilter({ garmentKey, value = {}, onChange }) {
  const tree = useDesignCatalogue(garmentKey);
  const categories = tree?.categories || [];
  if (categories.length === 0) return null;

  const cat = categories.find((c) => c.key === value.category) || null;
  const sub = (cat?.subcategories || []).find((s) => s.key === value.subcategory) || null;
  const options = cat ? (cat.subcategories ? (sub?.options || []) : (cat.options || [])) : [];
  const active = Boolean(cat);

  const selectStyle = {
    flex: '1 1 150px', width: 'auto', minWidth: 0, height: '32px', padding: '0 28px 0 10px', fontSize: '12.5px',
    fontWeight: 500, color: 'var(--text-primary)', background: 'var(--surface-color, #fff)',
    border: '1px solid var(--border-color, #e4e4e7)', borderRadius: '7px', cursor: 'pointer',
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: '8px',
                  padding: '6px 8px 6px 12px', marginBottom: '10px', borderRadius: '10px',
                  border: '1px solid var(--border-color, #e4e4e7)',
                  background: 'var(--background-secondary, #f4f4f5)' }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px',
                     fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                     color: 'var(--text-secondary)', flex: '0 0 auto' }}>
        <SlidersHorizontal size={13} /> Filter
      </span>

      <select className="form-control" style={selectStyle} aria-label="Category"
              value={value.category || ''}
              onChange={(e) => onChange(e.target.value ? { category: e.target.value } : {})}>
        <option value="">All categories</option>
        {categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
      </select>

      {cat?.subcategories && (
        <select className="form-control" style={selectStyle} aria-label="Section"
                value={value.subcategory || ''}
                onChange={(e) => onChange(e.target.value
                  ? { category: cat.key, subcategory: e.target.value } : { category: cat.key })}>
          <option value="">All sections</option>
          {cat.subcategories.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
        </select>
      )}

      {cat && (!cat.subcategories || sub) && options.length > 0 && (
        <select className="form-control" style={selectStyle} aria-label="Design"
                value={value.option || ''}
                onChange={(e) => onChange({ category: cat.key, subcategory: sub?.key,
                                            option: e.target.value || undefined })}>
          <option value="">All designs</option>
          {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
        </select>
      )}

      {active && (
        <>
          <span title={`${tree.label} › ${describePath(tree, value)}`}
                style={{ fontSize: '11.5px', fontWeight: 600, color: '#107c41',
                         background: 'rgba(16,124,65,0.10)', padding: '5px 10px', borderRadius: '999px',
                         maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis',
                         whiteSpace: 'nowrap' }}>
            {describePath(tree, value)}
          </span>
          <button type="button" onClick={() => onChange({})} title="Clear filter"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', height: '28px',
                           padding: '0 10px', fontSize: '11.5px', fontWeight: 600, cursor: 'pointer',
                           border: '1px solid var(--border-color, #e4e4e7)', borderRadius: '7px',
                           background: 'var(--surface-color, #fff)', color: 'var(--text-secondary)',
                           marginLeft: 'auto' }}>
            <X size={12} /> Clear
          </button>
        </>
      )}
    </div>
  );
}
