import { useCallback, useEffect, useState } from 'react';

import { api } from '../../services/api';
import { useLanguage } from '../../i18n/LanguageContext.jsx';

/**
 * The sixteen figures the inventory can state.
 */

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
};

const money = (n) => `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;
const qty = (n) => Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 3 });
const rate = (n) => (n === null || n === undefined ? null : `${Number(n).toFixed(2)}%`);

export default function ReportsTab() {
  const { t } = useLanguage();
  const [data, setData] = useState(null);
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(() => {
    setLoading(true);
    api.getInventoryReport('dashboard', { since: since || undefined, until: until || undefined })
      .then((rows) => { setData(rows); setError(null); })
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [since, until]);

  useEffect(() => { load(); }, [load]);

  if (loading && !data) {
    return <div style={{ ...panel, padding: '32px', textAlign: 'center', marginTop: '20px', color: 'var(--text-muted)' }}>{t('inventoryPage.workingOutNumbers', 'Working out the numbers…')}</div>;
  }
  if (error) {
    return (
      <div style={{ ...panel, padding: '24px', textAlign: 'center', marginTop: '20px', borderColor: 'rgba(220,38,38,0.3)' }}>
        <div style={{ color: '#fca5a5', marginBottom: '12px', fontSize: '13px' }}>{error}</div>
        <button type="button" className="btn-secondary" onClick={load}>{t('common.retry', 'Retry')}</button>
      </div>
    );
  }
  if (!data) return null;

  const { stock, low_stock: low, consumption, losses, cost_per_order: costs, suppliers, movements } = data;

  return (
    <div style={{ marginTop: '20px' }}>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', alignItems: 'flex-end', marginBottom: '18px' }}>
        <label style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
          <span style={{ display: 'block', marginBottom: '4px' }}>{t('inventoryPage.reportsFrom', 'From')}</span>
          <input className="form-control" type="date" value={since} onChange={(e) => setSince(e.target.value)} />
        </label>
        <label style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
          <span style={{ display: 'block', marginBottom: '4px' }}>{t('inventoryPage.reportsTo', 'To')}</span>
          <input className="form-control" type="date" value={until} onChange={(e) => setUntil(e.target.value)} />
        </label>
        {(since || until) && (
          <button type="button" className="btn-secondary" style={{ fontSize: '12px' }}
                  onClick={() => { setSince(''); setUntil(''); }}>
            {t('inventoryPage.allTime', 'All time')}
          </button>
        )}
      </div>

      {/* Stock position: six of the sixteen */}
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '20px' }}>
        <Stat label={t('inventoryPage.stockValue', 'Stock value')} value={money(stock.inventory_value)} hint={`${stock.item_count} ${t('inventoryPage.tableItem', 'materials')}`} />
        <Stat label={t('inventoryPage.tableInStock', 'In stock')} value={qty(stock.current_stock)} />
        <Stat label={t('inventoryPage.tableReserved', 'Reserved')} value={qty(stock.reserved_stock)} />
        <Stat label={t('inventoryPage.tableAvailable', 'Available')} value={qty(stock.available_stock)} />
        <Stat label={t('inventoryPage.atReorderLevel', 'At reorder level')} value={stock.at_or_below_reorder_level}
              tone={stock.at_or_below_reorder_level ? '#f59e0b' : undefined} />
        <Stat label={t('inventoryPage.outOfStock', 'Out of stock')} value={stock.out_of_stock}
              tone={stock.out_of_stock ? '#ef4444' : undefined} />
      </div>

      <div className="mobile-stack-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(320px, 100%), 1fr))', gap: '16px' }}>
        <Section title={t('inventoryPage.lossesTitle', 'Losses')} subtitle={t('inventoryPage.lossesSubtitle', 'Waste and damage measure different things, so they have different denominators')}>
          <RateRow
            label="Waste"
            value={rate(losses.waste_percent)}
            basis={`${qty(losses.wasted)} wasted of ${qty(Number(losses.consumed) + Number(losses.wasted))} that went to production`}
            empty="Nothing has gone to production yet"
          />
          <RateRow
            label="Damage"
            value={rate(losses.damage_percent)}
            basis={`${qty(losses.damaged)} damaged of ${qty(losses.received)} taken into stock`}
            empty="Nothing has been taken into stock yet"
          />
        </Section>

        <Section title={t('inventoryPage.consumptionTitle', 'Consumption')} subtitle={t('inventoryPage.consumptionSubtitle', 'What the workroom actually used')}>
          {['fabric', 'embroidery', 'packaging'].map((scope) => (
            <div key={scope} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px',
                                      padding: '8px 0', borderTop: '1px solid var(--border-color)' }}>
              <span style={{ fontSize: '13px', textTransform: 'capitalize' }}>{scope}</span>
              <span style={{ fontSize: '13px', fontVariantNumeric: 'tabular-nums' }}>
                {qty(consumption[scope].total_quantity)}
                <span style={{ color: 'var(--text-muted)', marginLeft: '8px' }}>
                  {money(consumption[scope].total_value)}
                </span>
              </span>
            </div>
          ))}
        </Section>

        <Section title={t('inventoryPage.lowStockTitle', 'Low stock')} subtitle={t('inventoryPage.lowStockSubtitle', 'Measured on available stock — reserved material will not be there for the next order')}>
          {low.length === 0
            ? <Empty>Everything is above its reorder level.</Empty>
            : low.map((row) => (
              <div key={row.item_id} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px',
                                              padding: '8px 0', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '13px' }}>{row.name}</span>
                <span style={{ fontSize: '13px', color: Number(row.available_stock) <= 0 ? '#ef4444' : '#f59e0b' }}>
                  {qty(row.available_stock)} left · needs {qty(row.reorder_level)}
                </span>
              </div>
            ))}
        </Section>

        <Section title={t('inventoryPage.costPerOrderTitle', 'Cost per order')} subtitle={t('inventoryPage.costPerOrderSubtitle', 'Waste counts as cost; customer-supplied material does not')}>
          {costs.length === 0
            ? <Empty>No order has consumed material yet.</Empty>
            : costs.map((row) => (
              <div key={row.plan_id} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px',
                                              padding: '8px 0', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '13px' }}>{row.order_code}</span>
                <span style={{ fontSize: '13px', fontVariantNumeric: 'tabular-nums' }}>
                  {money(row.total_cost)}
                  {Number(row.waste_cost) > 0 && (
                    <span style={{ color: '#f59e0b', marginLeft: '8px', fontSize: '11.5px' }}>
                      {money(row.waste_cost)} wasted
                    </span>
                  )}
                </span>
              </div>
            ))}
        </Section>

        <Section title={t('inventoryPage.suppliersReportTitle', 'Suppliers')} subtitle={t('inventoryPage.suppliersReportSubtitle', 'On-time is judged only on orders that were both promised a date and received')}>
          {suppliers.length === 0
            ? <Empty>No purchase orders yet.</Empty>
            : suppliers.map((row) => (
              <div key={row.supplier_id} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px',
                                                  padding: '8px 0', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '13px' }}>{row.supplier}</span>
                <span style={{ fontSize: '13px' }}>
                  {row.on_time_percent === null
                    ? <span style={{ color: 'var(--text-muted)' }}>nothing to judge yet</span>
                    : <>{rate(row.on_time_percent)} on time
                        <span style={{ color: 'var(--text-muted)', marginLeft: '6px', fontSize: '11.5px' }}>
                          of {row.judged_count}
                        </span>
                      </>}
                </span>
              </div>
            ))}
        </Section>

        <Section title={t('inventoryPage.movementsReportTitle', 'Movements')} subtitle={t('inventoryPage.movementsReportSubtitle', 'Every transaction, by type')}>
          {movements.length === 0
            ? <Empty>Nothing has moved in this period.</Empty>
            : movements.map((row) => (
              <div key={row.movement_type} style={{ display: 'flex', justifyContent: 'space-between', gap: '10px',
                                                    padding: '8px 0', borderTop: '1px solid var(--border-color)' }}>
                <span style={{ fontSize: '13px' }}>{row.movement_type.replace(/_/g, ' ').toLowerCase()}</span>
                <span style={{ fontSize: '13px', fontVariantNumeric: 'tabular-nums' }}>
                  {qty(row.quantity)}
                  <span style={{ color: 'var(--text-muted)', marginLeft: '8px', fontSize: '11.5px' }}>
                    {row.count} line{row.count === 1 ? '' : 's'}
                  </span>
                </span>
              </div>
            ))}
        </Section>
      </div>
    </div>
  );
}

function Stat({ label, value, tone, hint }) {
  return (
    <div style={{ ...panel, padding: '16px 18px', flex: '1 1 150px' }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase', color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontSize: '20px', fontWeight: 600, marginTop: '6px', color: tone || 'var(--text-primary)' }}>{value}</div>
      {hint && <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginTop: '4px' }}>{hint}</div>}
    </div>
  );
}

function Section({ title, subtitle, children }) {
  return (
    <div style={{ ...panel, padding: '16px 18px' }}>
      <div style={{ fontSize: '14px', fontWeight: 600 }}>{title}</div>
      {subtitle && (
        <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '3px', marginBottom: '8px' }}>
          {subtitle}
        </div>
      )}
      {children}
    </div>
  );
}

function RateRow({ label, value, basis, empty }) {
  return (
    <div style={{ padding: '10px 0', borderTop: '1px solid var(--border-color)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', gap: '10px' }}>
        <span style={{ fontSize: '13px' }}>{label}</span>
        <span style={{ fontSize: '15px', fontWeight: 600, color: value ? 'var(--text-primary)' : 'var(--text-muted)' }}>
          {value || 'no data'}
        </span>
      </div>
      <div style={{ fontSize: '11.5px', color: 'var(--text-muted)', marginTop: '2px' }}>
        {value ? basis : empty}
      </div>
    </div>
  );
}

function Empty({ children }) {
  return (
    <div style={{ fontSize: '12.5px', color: 'var(--text-muted)', padding: '10px 0' }}>{children}</div>
  );
}
