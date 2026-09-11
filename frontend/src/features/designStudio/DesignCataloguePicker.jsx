import { Layers, Sparkles } from 'lucide-react';

import { Field, InfoNote } from '../../components/ui/Atelier';
import { cataloguePayload, describePath, useDesignCatalogue } from './designCatalogue';

/**
 * The three selects that file a design in its garment's catalogue:
 * Category, then Section where the category has them, then Design option.
 *
 * Shared by both forms that create a design -- the library's upload and the
 * page header's "Add New Design" -- so they cannot disagree about what a
 * position is. Renders nothing for a garment with no catalogue.
 *
 * `onChange(value, payload)`: `value` is whatever is chosen so far, for the
 * form to hold; `payload` is the position to send, or null while the choice
 * is incomplete, so a half-chosen path is never posted and refused.
 */
export default function DesignCataloguePicker({ garmentKey, value = {}, onChange }) {
  const tree = useDesignCatalogue(garmentKey);
  const categories = tree?.categories || [];
  if (categories.length === 0) return null;

  const cat = categories.find((c) => c.key === value.category) || null;
  const sub = (cat?.subcategories || []).find((s) => s.key === value.subcategory) || null;
  const options = cat ? (cat.subcategories ? (sub?.options || []) : (cat.options || [])) : [];
  const set = (next) => onChange(next, cataloguePayload(tree, next));
  const complete = cataloguePayload(tree, value);

  return (
    <>
      <Field label="Catalogue category" icon={Layers}>
        <select className="form-control" value={value.category || ''}
                onChange={(e) => set(e.target.value ? { category: e.target.value } : {})}>
          <option value="">Not filed in the catalogue</option>
          {categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}
        </select>
      </Field>
      {cat?.subcategories && (
        <Field label="Section" icon={Layers}>
          <select className="form-control" value={value.subcategory || ''}
                  onChange={(e) => set({ category: cat.key, subcategory: e.target.value })}>
            <option value="">Choose a section</option>
            {cat.subcategories.map((s) => <option key={s.key} value={s.key}>{s.label}</option>)}
          </select>
        </Field>
      )}
      {cat && (!cat.subcategories || sub) && options.length > 0 && (
        <Field label="Design option" icon={Sparkles}>
          <select className="form-control" value={value.option || ''}
                  onChange={(e) => set({ ...value, option: e.target.value })}>
            <option value="">Choose a design option</option>
            {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
          </select>
        </Field>
      )}
      {cat && (
        <InfoNote tone={complete ? 'green' : 'amber'} style={{ gridColumn: '1 / -1' }}>
          {complete
            ? <>Filed under <strong>{tree.label} › {describePath(tree, value)}</strong>.</>
            : <>Pick the {cat.subcategories && !sub ? 'section' : 'design option'} to say exactly where this design belongs.</>}
        </InfoNote>
      )}
    </>
  );
}
