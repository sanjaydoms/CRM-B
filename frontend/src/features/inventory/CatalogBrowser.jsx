import { useCallback, useEffect, useMemo, useState } from 'react';
import { Check, Package, Plus, Search } from 'lucide-react';

import { api } from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext.jsx';

/**
 * The published catalogue: 732 materials across 49 sections.
 *
 * Browsed by section rather than listed flat, because 732 rows in one scroll is
 * not a list anyone reads -- and the sections are the vocabulary the trade
 * already uses ("Beads", "Traditional Zardosi Materials"), so they are how
 * someone actually looks for a material.
 *
 * Items are not stock. A boutique creates an InventoryItem from a row when it
 * decides to hold that material, which is what the "Stock this" button does;
 * everything else stays here rather than filling the stock screen with hundreds
 * of zero rows.
 */

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
};

//: Rows the documents catalogue but which cannot hold stock -- a payment
//: gateway, a garment category. Shown, because the catalogue is meant to be
//: complete, but not offered a "Stock this" button.
const TYPE_LABEL = {
  MATERIAL: 'Material', CONSUMABLE: 'Consumable', TOOL: 'Tool', MACHINE: 'Machine',
  ASSET: 'Asset', DOCUMENT: 'Document', SYSTEM: 'System', PRODUCT_CATEGORY: 'Garment type',
};

export default function CatalogBrowser({ isOwner, onStocked }) {
  const { t } = useLanguage();
  const [sections, setSections] = useState([]);
  const [openSection, setOpenSection] = useState(null);
  const [items, setItems] = useState([]);
  const [search, setSearch] = useState('');
  const [stockableOnly, setStockableOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.getCatalogSections()
      .then((rows) => setSections(rows || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  const loadItems = useCallback((section, term) => {
    if (!section && !term) { setItems([]); return; }
    setLoading(true);
    api.getCatalogItems({
      section: section ? section.id : undefined,
      search: term || undefined,
      stockable: stockableOnly ? 'true' : undefined,
    })
      .then((rows) => setItems(rows || []))
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [stockableOnly]);

  useEffect(() => {
    const term = search.trim();
    const timer = setTimeout(() => loadItems(openSection, term), term ? 250 : 0);
    return () => clearTimeout(timer);
  }, [search, openSection, loadItems]);

  const byDoc = useMemo(() => {
    const groups = { MAGGAM: [], APPAREL: [] };
    sections.forEach((section) => (groups[section.doc] || groups.APPAREL).push(section));
    return groups;
  }, [sections]);

  const stock = async (item) => {
    setBusy(item.id);
    setError(null);
    try {
      await api.stockCatalogItem(item.id, {});
      loadItems(openSection, search.trim());
      onStocked?.();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  };

  const total = sections.reduce((sum, s) => sum + (s.item_count || 0), 0);

  return (
    <div style={{ marginTop: '20px' }}>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '16px' }}>
        <div style={{ position: 'relative', flex: '1 1 260px' }}>
          <Search size={14} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
          <input
            className="form-control"
            style={{ paddingLeft: '30px', fontSize: '13px' }}
            placeholder={`Search all ${total} catalogue materials…`}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)' }}>
          <input type="checkbox" checked={stockableOnly} onChange={(e) => setStockableOnly(e.target.checked)} />
          {t('inventoryPage.onlyStockable', 'Only what can be stocked')}
        </label>
        {openSection && (
          <button type="button" className="btn-secondary" style={{ fontSize: '12px', padding: '6px 12px' }}
                  onClick={() => { setOpenSection(null); setSearch(''); }}>
            {t('inventoryPage.allSections', 'All sections')}
          </button>
        )}
      </div>

      {error && (
        <div style={{ ...panel, padding: '12px 16px', marginBottom: '12px', borderColor: 'rgba(220,38,38,0.3)', color: '#fca5a5', fontSize: '13px' }}>
          {error}
        </div>
      )}

      {!openSection && !search.trim() && (
        <div>
          {[['MAGGAM', t('inventoryPage.maggamSection', 'Maggam · Aari · Zardosi')], ['APPAREL', t('inventoryPage.apparelSection', 'Apparel ecosystem')]].map(([doc, label]) => (
            <div key={doc} style={{ marginBottom: '24px' }}>
              <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)', marginBottom: '10px' }}>
                {label}
              </div>
              <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(min(220px, 100%), 1fr))', gap: '10px' }}>
                {byDoc[doc].map((section) => (
                  <button
                    key={section.id}
                    type="button"
                    onClick={() => setOpenSection(section)}
                    style={{ ...panel, padding: '14px 16px', textAlign: 'left', cursor: 'pointer', color: 'inherit' }}
                  >
                    <div style={{ fontSize: '13.5px', fontWeight: 600 }}>{section.full_name}</div>
                    <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '4px' }}>
                      {section.item_count} {t('inventoryPage.tableItem', 'material')}
                    </div>
                  </button>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {(openSection || search.trim()) && (
        <div style={{ ...panel, overflow: 'hidden' }}>
          <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--border-color)', fontSize: '13px', fontWeight: 600 }}>
            {openSection ? openSection.full_name : `Search: “${search.trim()}”`}
            <span style={{ fontWeight: 400, color: 'var(--text-muted)', marginLeft: '8px' }}>
              {loading ? 'loading…' : `${items.length} shown`}
            </span>
          </div>
          {!loading && items.length === 0 && (
            <div style={{ padding: '28px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '13px' }}>
              {t('inventoryPage.nothingMatches', 'Nothing matches.')}
            </div>
          )}
          <div>
            {items.map((item) => (
              <div key={item.id} style={{
                display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap',
                padding: '10px 16px', borderTop: '1px solid var(--border-color)',
              }}>
                <div style={{ flex: '1 1 200px', minWidth: 0 }}>
                  <div style={{ fontSize: '13.5px', fontWeight: 500 }}>{item.name}</div>
                  <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                    {item.section_full_name} · {TYPE_LABEL[item.item_type] || item.item_type}
                  </div>
                </div>
                {item.stocked_item_id ? (
                  <span style={{ fontSize: '11.5px', color: '#34d399', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                    <Check size={13} /> {t('inventoryPage.inYourInventory', 'In your inventory')}
                  </span>
                ) : !item.is_stockable ? (
                  <span style={{ fontSize: '11.5px', color: 'var(--text-muted)' }}>
                    {t('inventoryPage.notStockableMaterial', 'Not a stockable material')}
                  </span>
                ) : isOwner ? (
                  <button type="button" className="btn-secondary"
                          style={{ fontSize: '11.5px', padding: '5px 11px' }}
                          disabled={busy === item.id}
                          onClick={() => stock(item)}>
                    <Plus size={12} style={{ marginRight: '4px', verticalAlign: 'middle' }} />
                    {busy === item.id ? t('inventoryPage.adding', 'Adding…') : t('inventoryPage.stockThis', 'Stock this')}
                  </button>
                ) : null}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
