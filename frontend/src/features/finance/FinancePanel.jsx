/**
 * Cost & P&L — the owner's money-out view.
 *
 * Two halves, one screen: the profit-and-loss summary for a month (revenue,
 * every cost, profit) and the manual-expense ledger that feeds the "manual"
 * slice of it. Salaries and inventory are NOT entered here -- they are read by
 * the server from payroll and purchasing and shown as auto-fed rows, so the
 * owner can see them without typing them twice.
 *
 * Owner-only on the server (OwnerOnly). Any non-owner who reached this tab
 * would get 403s from both endpoints; the nav already hides it from them.
 */
import { useCallback, useEffect, useState } from 'react';
import { Calendar, FileText, IndianRupee, LayoutGrid, Lightbulb, PieChart, Plus, Receipt, Shield, Trash2, TrendingUp, User, Wallet, X } from 'lucide-react';

import { api } from '../../services/api';
import { Dropzone, Field, FormModal, IconTile, InfoNote, PageHeader, SectionCard, StatCard } from '../../components/ui/Atelier';

const errorBox = {
  background: 'var(--danger-bg)',
  border: '1px solid var(--danger-color)',
  color: 'var(--danger-color)',
  borderRadius: 'var(--radius-md)',
  padding: '10px 12px',
  fontSize: 'var(--text-sm)',
  marginBottom: '12px',
};

const money = (n) =>
  `₹${Number(n || 0).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

// Manual categories only. Inventory and salaries are auto-fed and must never be
// offered here, or the same rupee would be counted twice. Mirrors
// Expense.Category on the server (minus the two it does not define).
const EXPENSE_CATEGORIES = [
  ['RENT', 'Rent'],
  ['UTILITIES', 'Utilities'],
  ['MARKETING', 'Marketing'],
  ['MAINTENANCE', 'Maintenance & repairs'],
  ['SUPPLIES', 'Shop supplies'],
  ['PROFESSIONAL', 'Professional fees'],
  ['OTHER', 'Other'],
];

// First and last day of the current month, as yyyy-mm-dd, for the default
// window. Kept in the browser's local time -- the owner means "this month here".
const monthWindow = () => {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth(), 1);
  const last = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  // Format the LOCAL date parts, never toISOString(): that converts to UTC,
  // so in a timezone ahead of UTC local Sep 1 midnight becomes Aug 31, and the
  // month's P&L would silently start and end a day early.
  const iso = (d) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return { since: iso(first), until: iso(last) };
};

function AddExpenseForm({ onCancel, onSaved }) {
  const [form, setForm] = useState({
    category: 'RENT', amount: '', incurred_on: monthWindow().until,
    paid_to: '', note: '',
  });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const submit = async (e) => {
    e.preventDefault();
    if (!(Number(form.amount) > 0)) { setError('Enter an amount greater than zero.'); return; }
    if (!form.incurred_on) { setError('Pick the date this cost is for.'); return; }
    setBusy(true); setError(null);
    try {
      // FormData only when a receipt is attached; otherwise plain JSON keeps
      // the request small and the server parses it the same way.
      let body;
      if (file) {
        body = new FormData();
        Object.entries(form).forEach(([k, v]) => body.append(k, v));
        body.append('receipt', file);
      } else {
        body = { ...form };
      }
      await api.createExpense(body);
      onSaved();
    } catch (err) {
      setError(err.message || 'Could not save this expense.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <FormModal
      icon={Receipt} tone="green" width="720px" zIndex={1000}
      title="Add a Cost"
      subtitle="Record a business expense for better tracking and reporting."
      onClose={onCancel}
      footer={(
        <>
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="submit" form="expense-form" className="btn-primary" disabled={busy}>
            <Wallet size={16} /> {busy ? 'Saving…' : 'Add cost'}
          </button>
        </>
      )}
    >
      <form id="expense-form" onSubmit={submit} className="at-stack">
        {error && <div style={errorBox}>{error}</div>}
        <div className="at-form-grid">
          <Field label="Category" required icon={LayoutGrid}>
            <select className="form-input" value={form.category} onChange={set('category')}>
              {EXPENSE_CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </Field>
          <Field label="Amount (₹)" required icon={IndianRupee} hint="Enter the total amount paid.">
            <input className="form-input" type="number" min="0" step="0.01"
                   inputMode="decimal" value={form.amount} onChange={set('amount')}
                   placeholder="0.00" />
          </Field>
        </div>
        <Field label="Date this cost is for" required icon={Calendar}>
          <input className="form-input" type="date" value={form.incurred_on}
                 onChange={set('incurred_on')} />
        </Field>
        <Field label="Paid to" optional icon={User}>
          <input className="form-input" value={form.paid_to} onChange={set('paid_to')}
                 placeholder="Landlord, electricity board, supplier name…" />
        </Field>
        <Field label="Note" optional icon={FileText}>
          <textarea className="form-input" rows={3} value={form.note} onChange={set('note')}
                    placeholder="Add any additional details about this expense…" />
        </Field>
        <div className="at-field">
          <span className="at-field-label">Receipt <span className="at-field-opt">(optional, image or PDF)</span></span>
          <div className="at-side-by-side">
            {file ? (
              <div className="at-form-section" style={{ flexDirection: 'row', alignItems: 'center', gap: 'var(--space-3)' }}>
                <IconTile icon={FileText} tone="green" size={40} iconSize={18} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 'var(--text-sm)', fontWeight: 600, color: 'var(--text-primary)', overflowWrap: 'anywhere' }}>{file.name}</div>
                  <div style={{ fontSize: 'var(--text-xs)', color: 'var(--text-secondary)' }}>{Math.round(file.size / 1024)} KB</div>
                </div>
                <button type="button" className="btn-secondary at-btn-sm" onClick={() => setFile(null)}>Remove</button>
              </div>
            ) : (
              <Dropzone
                accept="image/*,application/pdf"
                title="Drag & drop a file here" subtitle="or choose from your device"
                chooseLabel="Choose File" hint="Supported formats: JPG, PNG, PDF (Max 10MB)"
                onFiles={(files) => setFile(files[0] || null)}
              />
            )}
            <InfoNote tone="green" icon={Shield} title="Keep your records organized"
                      items={['Bills, invoices, or payment slips', 'Clear and readable images', 'Helps with reporting and audits']}>
              Upload receipts to maintain accurate financial records.
            </InfoNote>
          </div>
        </div>
      </form>
    </FormModal>
  );
}

function CostRow({ label, amount, auto }) {
  return (
    <tr>
      <td>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
          {label}
          {auto && (
            <span className="ui-badge ui-badge--neutral" style={{ textTransform: 'uppercase', letterSpacing: '0.05em' }}>auto</span>
          )}
        </span>
      </td>
      <td className="at-num" style={{ fontWeight: 600, textAlign: 'right' }}>{money(amount)}</td>
      <td style={{ color: 'var(--text-secondary)' }}>{auto ? 'Automatic' : 'Entered'}</td>
    </tr>
  );
}

export default function FinancePanel() {
  const [win, setWin] = useState(monthWindow);
  const [pnl, setPnl] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(false);
  const [tipOpen, setTipOpen] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const [report, rows] = await Promise.all([
        api.getProfitLoss(win),
        api.getExpenses(win),
      ]);
      setPnl(report);
      setExpenses(Array.isArray(rows) ? rows : (rows?.results ?? []));
    } catch (err) {
      setError(err.message || 'Could not load the P&L.');
    } finally {
      setLoading(false);
    }
  }, [win]);

  useEffect(() => {
    const t = setTimeout(refresh, 0);
    return () => clearTimeout(t);
  }, [refresh]);

  const profit = pnl ? Number(pnl.profit) : 0;
  const margin = pnl && Number(pnl.revenue.total) > 0
    ? Math.round((profit / Number(pnl.revenue.total)) * 100) : null;

  return (
    <>
      <PageHeader
        title={<>Cost &amp; P&amp;L</>}
        subtitle="What you earned, what you spent, and what is left — for the selected period."
        actions={(
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', border: '1px solid var(--border-color)',
                          borderRadius: 'var(--radius-md)', padding: '4px 10px', background: 'var(--surface-color)' }}>
              <input className="form-input" type="date" value={win.since} aria-label="From"
                     onChange={(e) => setWin({ ...win, since: e.target.value })}
                     style={{ border: 'none', background: 'transparent', padding: '6px 2px', margin: 0, width: 'auto' }} />
              <span style={{ color: 'var(--text-muted)' }}>→</span>
              <input className="form-input" type="date" value={win.until} aria-label="To"
                     onChange={(e) => setWin({ ...win, until: e.target.value })}
                     style={{ border: 'none', background: 'transparent', padding: '6px 2px', margin: 0, width: 'auto' }} />
            </div>
            <button type="button" className="btn-primary" style={{ padding: '10px 18px' }} onClick={() => setAdding(true)}>
              <Plus size={16} /> Add a cost
            </button>
          </>
        )}
      />

      {error && <div style={{ ...errorBox, marginBottom: '14px' }}>{error}</div>}

      {loading || !pnl ? (
        <div style={{ padding: '32px', color: 'var(--text-secondary)' }}>Loading…</div>
      ) : (
        <div className="at-stack">
          <div className="at-stat-grid">
            <StatCard icon={TrendingUp} tone="green" label="Revenue" value={money(pnl.revenue.total)}
                      sub="collected in this period" />
            <StatCard icon={Wallet} tone="rose" label="Total Costs" value={money(pnl.costs.total)}
                      sub={Number(pnl.costs.total) > 0 ? 'salaries, inventory and entered costs' : 'No costs recorded'} />
            <StatCard icon={PieChart} tone={profit >= 0 ? 'blue' : 'rose'} label={profit >= 0 ? 'Profit' : 'Loss'}
                      value={money(Math.abs(profit))} sub={margin === null ? 'no revenue yet' : `${margin}% margin`} />
          </div>

          <div className="at-grid-2">
            <SectionCard icon={Wallet} tone="neutral" title="Where the Money Went" subtitle="All costs recorded for this period."
                         action={() => setAdding(true)} actionLabel="Add a cost">
              <div className="at-table-wrap">
                <table className="at-table" style={{ minWidth: 0 }}>
                  <thead>
                    <tr><th>Category</th><th style={{ textAlign: 'right' }}>Amount</th><th>Mode</th></tr>
                  </thead>
                  <tbody>
                    <CostRow label="Salaries (payroll)" amount={pnl.costs.salaries} auto />
                    <CostRow label="Inventory (purchase orders)" amount={pnl.costs.inventory} auto />
                    {pnl.costs.manual.map((m) => (
                      <CostRow key={m.category} label={m.label} amount={m.amount} />
                    ))}
                    <tr style={{ background: 'var(--surface-2)' }}>
                      <td style={{ fontWeight: 700 }}>Total Costs</td>
                      <td className="at-num" style={{ fontWeight: 700, textAlign: 'right' }}>{money(pnl.costs.total)}</td>
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            </SectionCard>

            <SectionCard icon={PieChart} tone="neutral" title="Costs you entered" subtitle="Rent, utilities and the rest — with receipts.">
              {expenses.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 'var(--space-4) 0' }}>
                  <div style={{ fontWeight: 600, fontSize: 'var(--text-md)', color: 'var(--text-primary)' }}>No cost data for this period</div>
                  <div style={{ color: 'var(--text-secondary)', fontSize: 'var(--text-sm)', margin: '6px 0 14px' }}>
                    Add your costs to see a breakdown by category.
                  </div>
                  <button type="button" className="btn-primary" style={{ margin: '0 auto' }} onClick={() => setAdding(true)}>
                    <Plus size={16} /> Add a cost
                  </button>
                </div>
              ) : (
                expenses.map((x) => (
                  <div key={x.id} className="at-row">
                    <div className="at-row-main">
                      <div className="at-row-title">
                        {x.category_display}{x.paid_to ? ` · ${x.paid_to}` : ''}
                      </div>
                      <div className="at-row-sub">
                        {x.incurred_on}{x.note ? ` · ${x.note}` : ''}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      {x.receipt_url && (
                        <a className="btn-secondary at-btn-sm" href={x.receipt_url} target="_blank"
                           rel="noreferrer" style={{ textDecoration: 'none' }}>Receipt</a>
                      )}
                      <span className="at-num" style={{ fontWeight: 600, fontSize: 'var(--text-sm)' }}>{money(x.amount)}</span>
                      <button type="button" className="btn-secondary at-btn-sm" aria-label="Delete cost"
                              onClick={async () => {
                                try { await api.deleteExpense(x.id); refresh(); }
                                catch (err) { setError(err.message); }
                              }}
                              style={{ color: 'var(--danger-color)', borderColor: 'var(--danger-color)' }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </SectionCard>
          </div>

          {tipOpen && (
            <div className="at-tip">
              <span className="at-tile at-tile--green" style={{ width: 40, height: 40 }}><Lightbulb size={18} /></span>
              <div style={{ flex: 1 }}>
                <div className="at-tip-title">Costs are added automatically</div>
                <div className="at-tip-text">
                  Salaries and inventory costs are pulled in automatically. Add rent, utilities, and any other expenses manually for a complete view.
                </div>
              </div>
              <button type="button" onClick={() => setTipOpen(false)} aria-label="Dismiss"
                      style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)' }}>
                <X size={16} />
              </button>
            </div>
          )}
        </div>
      )}

      {adding && (
        <AddExpenseForm onCancel={() => setAdding(false)}
                        onSaved={() => { setAdding(false); refresh(); }} />
      )}
    </>
  );
}
