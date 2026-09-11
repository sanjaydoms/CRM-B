import { ChevronRight } from 'lucide-react';

import { describePath, useDesignCatalogue } from './designCatalogue';

/**
 * Walking a garment's design catalogue: category, then sub-category where the
 * category has them, then design option. Each level is a row of chips; the
 * chosen path is what the library filters by and what an upload is filed
 * under.
 *
 * The tree comes from the server, the same one the serializer validates
 * against, so the browser can never offer a position an upload would be
 * refused at. A garment with no catalogue yet renders nothing at all, which is
 * how every garment other than the saree looks today.
 *
 * `value` is {category, subcategory, option}; every key optional. Changing a
 * level clears the levels beneath it -- a Cotton option makes no sense under
 * Silk / Pattu.
 */

function Chip({ active, onClick, children, title }) {
  return (
    <button type="button" onClick={onClick} title={title} aria-pressed={active}
            // No nowrap: a long name must fold inside its chip rather than push
            // the page sideways on a phone.
            style={{ padding: '6px 12px', borderRadius: '999px', fontSize: '12px', fontWeight: 600,
                     cursor: 'pointer', maxWidth: '100%', textAlign: 'left', lineHeight: 1.3,
                     border: active ? '1.5px solid #107c41' : '1.5px solid var(--border-color)',
                     background: active ? '#107c41' : 'var(--surface-color, #fff)',
                     color: active ? '#fff' : 'var(--text-primary)',
                     boxShadow: active ? '0 2px 8px rgba(16,124,65,0.25)' : 'none',
                     transition: 'all 0.15s ease' }}>
      {children}
    </button>
  );
}

function Level({ label, children }) {
  return (
    // The label sits beside the chips where there is room and above them
    // where there is not: the chip row asks for 260px and wraps under the
    // label rather than being squeezed to one chip per line.
    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px 10px', flexWrap: 'wrap' }}>
      <span style={{ fontSize: '11px', fontWeight: 700, letterSpacing: '0.04em', textTransform: 'uppercase',
                     color: 'var(--text-secondary)', paddingTop: '8px', flex: '0 0 92px' }}>
        {label}
      </span>
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', flex: '1 1 260px', minWidth: 0 }}>
        {children}
      </div>
    </div>
  );
}


export default function DesignCatalogueBrowser({ garmentKey, value = {}, onChange, allLabel = 'All designs' }) {
  const tree = useDesignCatalogue(garmentKey);
  const categories = tree?.categories || [];
  if (categories.length === 0) return null;

  const category = categories.find((c) => c.key === value.category) || null;
  const subcategory = (category?.subcategories || []).find((s) => s.key === value.subcategory) || null;
  const options = category
    ? (category.subcategories ? (subcategory?.options || []) : (category.options || []))
    : [];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '14px 16px',
                  marginBottom: '16px', borderRadius: '12px', border: '1px solid var(--border-color)',
                  background: 'var(--surface-color, #fff)' }}>
      <Level label="Category">
        <Chip active={!category} onClick={() => onChange({})}>{allLabel}</Chip>
        {categories.map((c) => (
          <Chip key={c.key} active={category?.key === c.key} title={c.label}
                onClick={() => onChange({ category: c.key })}>
            {c.short || c.label}
          </Chip>
        ))}
      </Level>

      {category?.subcategories && (
        <Level label="Section">
          {category.subcategories.map((s) => (
            <Chip key={s.key} active={subcategory?.key === s.key}
                  onClick={() => onChange({ category: category.key, subcategory: s.key })}>
              {s.label}
            </Chip>
          ))}
        </Level>
      )}

      {category && (!category.subcategories || subcategory) && (
        options.length > 0 ? (
          <Level label="Design">
            {options.map((o) => (
              <Chip key={o.key} active={value.option === o.key}
                    onClick={() => onChange({ category: category.key, subcategory: subcategory?.key,
                                              option: value.option === o.key ? undefined : o.key })}>
                {o.label}
              </Chip>
            ))}
          </Level>
        ) : (
          <div style={{ fontSize: '12px', color: 'var(--text-secondary)', paddingLeft: 0 }}>
            {category.note || 'No design options are listed here yet.'}
          </div>
        )
      )}

      {category && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px',
                      color: 'var(--text-secondary)', paddingLeft: 0 }}>
          {category.note && !category.subcategories && options.length > 0 && (
            <span style={{ marginRight: '8px', fontStyle: 'italic' }}>{category.note}</span>
          )}
          <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{tree.label}</span>
          <ChevronRight size={12} />
          <span>{describePath(tree, value).split(' › ').join(' › ')}</span>
        </div>
      )}
    </div>
  );
}
