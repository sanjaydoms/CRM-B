import { useCallback, useEffect, useState } from 'react';
import { Calculator, Plus, Trash2 } from 'lucide-react';

import { api } from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext.jsx';

/**
 * Recipes: what each garment is made of.
 *
 * A line can carry a fixed quantity or a formula over the customer's own
 * measurements, plus a waste allowance. "Try it" evaluates the whole recipe
 * against measurements typed in here, which is the only honest way to check a
 * formula -- reading `0.15 * bust + 0.4` tells you nothing about whether it
 * produces a sane number of metres.
 */

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
};

const ROLES = [
  ['FABRIC', 'Fabric'], ['LINING', 'Lining'], ['INTERLINING', 'Interlining'],
  ['EMBROIDERY', 'Embroidery'], ['THREAD', 'Thread'], ['ACCESSORY', 'Accessory'],
  ['LABEL', 'Label'], ['PACKAGING', 'Packaging'], ['OTHER', 'Other'],
];

const qty = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 3 });

export default function RecipesTab({ items, isOwner }) {
  const { t } = useLanguage();
  const [boms, setBoms] = useState([]);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [creating, setCreating] = useState(false);

  const refresh = useCallback(async (keepId) => {
    setLoading(true);
    try {
      const rows = await api.getBoms();
      setBoms(rows || []);
      const keep = (rows || []).find((b) => b.id === (keepId || selected?.id));
      setSelected(keep || (rows || [])[0] || null);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  return (
    <div style={{ marginTop: '20px' }}>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '16px' }}>
        <div style={{ fontSize: '13px', color: 'var(--text-secondary)', flex: '1 1 auto' }}>
          {t('inventoryPage.recipesSubtitle', 'What each garment is made of. An order reserves against the recipe.')}
        </div>
        {isOwner && (
          <button type="button" className="btn-primary" style={{ fontSize: '13px' }} onClick={() => setCreating(true)}>
            <Plus size={14} style={{ marginRight: '6px', verticalAlign: 'middle' }} /> {t('inventoryPage.newRecipe', 'New recipe')}
          </button>
        )}
      </div>

      {error && (
        <div style={{ ...panel, padding: '12px 16px', marginBottom: '12px', borderColor: 'rgba(220,38,38,0.3)', color: '#fca5a5', fontSize: '13px' }}>
          {error}
        </div>
      )}

      {!loading && boms.length === 0 && (
        <div style={{ ...panel, padding: '32px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
          {t('inventoryPage.noRecipes', 'No recipes yet. A recipe lists the materials a garment needs, so an order can reserve them.')}
        </div>
      )}

      {boms.length > 0 && (
        <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: 'minmax(min(220px, 100%), 260px) 1fr', gap: '16px' }}>
          <div style={{ ...panel, overflow: 'hidden', alignSelf: 'start' }}>
            {boms.map((bom) => (
              <button key={bom.id} type="button" onClick={() => setSelected(bom)}
                      style={{
                        display: 'block', width: '100%', textAlign: 'left', cursor: 'pointer',
                        padding: '12px 14px', border: 'none', color: 'inherit',
                        borderTop: '1px solid var(--border-color)',
                        background: selected?.id === bom.id ? 'var(--accent-color, rgba(176,124,64,0.12))' : 'transparent',
                      }}>
                <div style={{ fontSize: '13px', fontWeight: 600 }}>{bom.name}</div>
                <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                  v{bom.version} · {bom.line_count} line{bom.line_count === 1 ? '' : 's'}
                  {bom.is_active ? '' : ' · superseded'}
                </div>
              </button>
            ))}
          </div>

          {selected && (
            <RecipeDetail
              bom={selected}
              items={items}
              isOwner={isOwner}
              onChanged={() => refresh(selected.id)}
            />
          )}
        </div>
      )}

      {creating && (
        <NewRecipeModal
          onClose={() => setCreating(false)}
          onCreated={(bom) => { setCreating(false); refresh(bom.id); }}
        />
      )}
    </div>
  );
}

function RecipeDetail({ bom, items, isOwner, onChanged }) {
  const [adding, setAdding] = useState(false);
  const [trying, setTrying] = useState(false);
  const [error, setError] = useState(null);

  const remove = async (line) => {
    setError(null);
    try {
      await api.deleteBomLine(line.id);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ ...panel, overflow: 'hidden' }}>
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-color)',
                    display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ flex: '1 1 auto', minWidth: 0 }}>
          <div style={{ fontSize: '14px', fontWeight: 600 }}>{bom.name}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
            Version {bom.version}{bom.is_active ? ' · active' : ' · superseded'}
          </div>
        </div>
        <button type="button" className="btn-secondary" style={{ fontSize: '11.5px', padding: '5px 11px' }}
                onClick={() => setTrying(true)}>
          <Calculator size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> Try it
        </button>
        {isOwner && bom.is_active && (
          <button type="button" className="btn-secondary" style={{ fontSize: '11.5px', padding: '5px 11px' }}
                  onClick={() => setAdding(true)}>
            <Plus size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} /> Add material
          </button>
        )}
      </div>

      {error && (
        <div style={{ padding: '10px 16px', color: '#fca5a5', fontSize: '12.5px' }}>{error}</div>
      )}

      {(bom.lines || []).length === 0 ? (
        <div style={{ padding: '28px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
          No materials yet.
        </div>
      ) : (
        <div className="responsive-table-wrapper">
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                <th style={{ padding: '12px' }}>Material</th>
                <th style={{ padding: '12px' }}>Role</th>
                <th style={{ padding: '12px', textAlign: 'right' }}>Quantity</th>
                <th style={{ padding: '12px', textAlign: 'right' }}>Waste</th>
                <th style={{ padding: '12px' }} />
              </tr>
            </thead>
            <tbody>
              {(bom.lines || []).map((line) => (
                <tr key={line.id} style={{ borderTop: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '10px 12px' }}>
                    <div style={{ fontWeight: 500 }}>{line.material_name}</div>
                    {line.is_customer_supplied && (
                      <div style={{ fontSize: '11px', color: '#60a5fa' }}>Customer brings this</div>
                    )}
                    {line.is_optional && (
                      <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Optional</div>
                    )}
                  </td>
                  <td style={{ padding: '10px 12px', color: 'var(--text-secondary)' }}>{line.role_display}</td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                    {line.quantity_formula
                      ? <code style={{ fontSize: '11.5px' }}>{line.quantity_formula}</code>
                      : qty(line.quantity)}
                    <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '4px' }}>{line.unit_display}</span>
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-muted)' }}>
                    {Number(line.waste_percent) ? `${Number(line.waste_percent)}%` : '—'}
                  </td>
                  <td style={{ padding: '10px 12px', textAlign: 'right' }}>
                    {isOwner && bom.is_active && (
                      <button type="button" className="btn-secondary"
                              style={{ fontSize: '11px', padding: '4px 8px' }}
                              onClick={() => remove(line)}>
                        <Trash2 size={11} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {adding && (
        <AddLineModal
          bom={bom} items={items}
          onClose={() => setAdding(false)}
          onAdded={() => { setAdding(false); onChanged(); }}
        />
      )}
      {trying && <TryRecipeModal bom={bom} onClose={() => setTrying(false)} />}
    </div>
  );
}

function AddLineModal({ bom, items, onClose, onAdded }) {
  const [form, setForm] = useState({
    role: 'FABRIC', inventory_item: '', quantity: '1', quantity_formula: '',
    unit: 'METER', waste_percent: '0', is_optional: false, is_customer_supplied: false,
    description: '',
  });
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const set = (key) => (e) => setForm({
    ...form, [key]: e.target.type === 'checkbox' ? e.target.checked : e.target.value,
  });

  const submit = async () => {
    setError(null);
    setSaving(true);
    try {
      await api.createBomLine({
        bom: bom.id,
        role: form.role,
        inventory_item: form.is_customer_supplied ? null : (form.inventory_item || null),
        description: form.is_customer_supplied ? form.description : null,
        quantity: form.quantity_formula ? 0 : form.quantity,
        quantity_formula: form.quantity_formula || null,
        unit: form.unit,
        waste_percent: form.waste_percent || 0,
        is_optional: form.is_optional,
        is_customer_supplied: form.is_customer_supplied,
      });
      onAdded();
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const chosen = items.find((i) => i.id === form.inventory_item);

  return (
    <Modal title="Add a material" onClose={onClose}>
      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px', marginBottom: '12px' }}>
        <input type="checkbox" checked={form.is_customer_supplied} onChange={set('is_customer_supplied')} />
        The customer brings this
      </label>

      {form.is_customer_supplied ? (
        <>
          <Field label="What the customer is bringing">
            <input className="form-control" value={form.description} onChange={set('description')}
                   placeholder="e.g. her own gold border" />
          </Field>
          <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginBottom: '12px' }}>
            Customer material is never reserved from boutique stock. It is tracked
            against the order separately.
          </div>
        </>
      ) : (
        <Field label="Material">
          <select className="form-control" value={form.inventory_item} onChange={set('inventory_item')}>
            <option value="">Choose from your inventory…</option>
            {items.map((row) => (
              <option key={row.id} value={row.id}>{row.name} ({row.item_code})</option>
            ))}
          </select>
        </Field>
      )}

      <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
        <Field label="Role">
          <select className="form-control" value={form.role} onChange={set('role')}>
            {ROLES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </Field>
        <Field label="Unit">
          <select className="form-control" value={form.unit} onChange={set('unit')}>
            {['METER', 'PIECE', 'PAIR', 'ROLL', 'PACKET', 'BOX', 'SET', 'KILOGRAM', 'GRAM', 'STRING', 'UNIT']
              .map((u) => <option key={u} value={u}>{u[0] + u.slice(1).toLowerCase()}</option>)}
          </select>
        </Field>
      </div>

      <Field label="Fixed quantity">
        <input className="form-control" type="number" step="0.001" min="0"
               value={form.quantity} onChange={set('quantity')}
               disabled={Boolean(form.quantity_formula)} />
      </Field>

      <Field label="…or a formula over the measurements">
        <input className="form-control" value={form.quantity_formula} onChange={set('quantity_formula')}
               placeholder="e.g. 0.15 * bust + 0.4" />
      </Field>
      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '-6px', marginBottom: '12px' }}>
        Arithmetic over the customer's measurements. A formula takes precedence
        over the fixed quantity.
      </div>

      <Field label="Waste allowance (%)">
        <input className="form-control" type="number" step="0.01" min="0"
               value={form.waste_percent} onChange={set('waste_percent')} />
      </Field>

      <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12.5px' }}>
        <input type="checkbox" checked={form.is_optional} onChange={set('is_optional')} />
        Optional — only included when the order asks for it
      </label>

      {chosen && form.unit !== chosen.unit && (
        <div style={{ fontSize: '11.5px', color: '#fbbf24', marginTop: '10px' }}>
          This line is in {form.unit} but {chosen.name} is stocked in {chosen.unit_display}.
          A conversion has to exist on the item, or the recipe cannot be used.
        </div>
      )}

      {error && <div style={{ color: '#fca5a5', fontSize: '12.5px', marginTop: '12px', whiteSpace: 'pre-wrap' }}>{error}</div>}

      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '20px' }}>
        <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
        <button type="button" className="btn-primary" onClick={submit} disabled={saving}>
          {saving ? 'Adding…' : 'Add material'}
        </button>
      </div>
    </Modal>
  );
}

function TryRecipeModal({ bom, onClose }) {
  const [raw, setRaw] = useState('bust=36\nwaist=30\nlength=42');
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setError(null);
    setBusy(true);
    // "bust=36" per line is what a person types; the API wants an object.
    const variables = {};
    raw.split('\n').forEach((line) => {
      const [key, value] = line.split('=').map((part) => (part || '').trim());
      if (key && value !== undefined && value !== '') variables[key] = value;
    });
    try {
      setResult(await api.getBomRequirements(bom.id, { variables, include_optional: true }));
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal title={`Try “${bom.name}”`} onClose={onClose} width="560px">
      <Field label="Measurements, one per line">
        <textarea className="form-control" rows={4} value={raw} onChange={(e) => setRaw(e.target.value)}
                  style={{ fontFamily: 'monospace', fontSize: '12.5px' }} />
      </Field>
      <button type="button" className="btn-primary" onClick={run} disabled={busy} style={{ fontSize: '13px' }}>
        {busy ? 'Working…' : 'Work out what it needs'}
      </button>

      {error && <div style={{ color: '#fca5a5', fontSize: '12.5px', marginTop: '14px', whiteSpace: 'pre-wrap' }}>{error}</div>}

      {result && (
        <div className="responsive-table-wrapper" style={{ marginTop: '16px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12.5px' }}>
            <thead>
              <tr style={{ textAlign: 'left', color: 'var(--text-muted)', fontSize: '11px', textTransform: 'uppercase' }}>
                <th style={{ padding: '8px' }}>Material</th>
                <th style={{ padding: '8px', textAlign: 'right' }}>Base</th>
                <th style={{ padding: '8px', textAlign: 'right' }}>Needed</th>
              </tr>
            </thead>
            <tbody>
              {result.requirements.map((row) => (
                <tr key={row.line_id} style={{ borderTop: '1px solid var(--border-color)' }}>
                  <td style={{ padding: '8px' }}>
                    {row.material}
                    {row.is_customer_supplied && (
                      <span style={{ color: '#60a5fa', fontSize: '11px' }}> · customer</span>
                    )}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', color: 'var(--text-muted)' }}>
                    {qty(row.base_quantity)} {row.base_unit}
                  </td>
                  <td style={{ padding: '8px', textAlign: 'right', fontWeight: 600 }}>
                    {qty(row.required_quantity)} {row.unit}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Modal>
  );
}

function NewRecipeModal({ onClose, onCreated }) {
  const [name, setName] = useState('');
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setError(null);
    if (!name.trim()) { setError('Give the recipe a name.'); return; }
    setSaving(true);
    try {
      onCreated(await api.createBom({ name: name.trim() }));
    } catch (err) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal title="New recipe" onClose={onClose}>
      <Field label="Name">
        <input className="form-control" value={name} onChange={(e) => setName(e.target.value)}
               placeholder="e.g. Bridal blouse" />
      </Field>
      {error && <div style={{ color: '#fca5a5', fontSize: '12.5px' }}>{error}</div>}
      <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end', marginTop: '20px' }}>
        <button type="button" className="btn-secondary" onClick={onClose} disabled={saving}>Cancel</button>
        <button type="button" className="btn-primary" onClick={submit} disabled={saving}>
          {saving ? 'Creating…' : 'Create'}
        </button>
      </div>
    </Modal>
  );
}

function Field({ label, children }) {
  return (
    <label style={{ display: 'block', marginBottom: '12px' }}>
      <span style={{ display: 'block', fontSize: '11px', color: 'var(--text-secondary)', marginBottom: '4px' }}>{label}</span>
      {children}
    </label>
  );
}

function Modal({ title, onClose, children, width = '480px' }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 1000,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}
         onClick={onClose}>
      <div className="search-modal-card"
           style={{ ...panel, background: 'var(--surface-color)', width: '100%', maxWidth: width,
                    padding: '22px', maxHeight: '88vh', overflowY: 'auto' }}
           onClick={(e) => e.stopPropagation()}>
        <h3 style={{ margin: '0 0 16px', fontSize: '18px' }}>{title}</h3>
        {children}
      </div>
    </div>
  );
}
