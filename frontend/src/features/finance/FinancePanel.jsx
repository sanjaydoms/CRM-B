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
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';

import { api } from '../../services/api';

const panel = {
  background: 'var(--card-bg, rgba(255,255,255,0.03))',
  border: '1px solid var(--border-color, rgba(255,255,255,0.08))',
  borderRadius: '12px',
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

function Modal({ title, onClose, children }) {
  return (
    <div onClick={onClose}
         style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  zIndex: 1000, padding: '16px' }}>
      <div onClick={(e) => e.stopPropagation()}
           style={{ ...panel, background: 'var(--bg-primary, #1a1a1a)',
                    width: '100%', maxWidth: '520px', padding: '20px',
                    maxHeight: '90vh', overflowY: 'auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', marginBottom: '14px' }}>
          <h3 style={{ margin: 0, fontFamily: 'var(--font-serif)', fontWeight: 500 }}>{title}</h3>
          <button type="button" onClick={onClose}
                  style={{ background: 'none', border: 'none', fontSize: '20px',
                           cursor: 'pointer', color: 'var(--text-secondary)' }}>×</button>
        </div>
        {children}
      </div>
    </div>
  );
}

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
    <Modal title="Add a cost" onClose={onCancel}>
      <form onSubmit={submit}>
        {error && (
          <div style={{ background: 'rgba(220,80,60,0.12)',
                        border: '1px solid rgba(220,80,60,0.35)', color: '#c0392b',
                        borderRadius: '8px', padding: '10px 12px', fontSize: '13px',
                        marginBottom: '12px' }}>{error}</div>
        )}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <label>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Category</span>
            <select className="form-input" value={form.category} onChange={set('category')}>
              {EXPENSE_CATEGORIES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </label>
          <label>
            <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Amount (₹)</span>
            <input className="form-input" type="number" min="0" step="0.01"
                   inputMode="decimal" value={form.amount} onChange={set('amount')}
                   placeholder="0.00" />
          </label>
        </div>
        <label style={{ display: 'block', marginTop: '10px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Date this cost is for</span>
          <input className="form-input" type="date" value={form.incurred_on}
                 onChange={set('incurred_on')} />
        </label>
        <label style={{ display: 'block', marginTop: '10px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Paid to (optional)</span>
          <input className="form-input" value={form.paid_to} onChange={set('paid_to')}
                 placeholder="Landlord, electricity board…" />
        </label>
        <label style={{ display: 'block', marginTop: '10px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Note (optional)</span>
          <input className="form-input" value={form.note} onChange={set('note')} />
        </label>
        <label style={{ display: 'block', marginTop: '10px' }}>
          <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>Receipt (optional, image or PDF)</span>
          <input className="form-input" type="file" accept="image/*,application/pdf"
                 onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '16px' }}>
          <button type="button" className="btn-secondary" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn-primary" disabled={busy}>
            {busy ? 'Saving…' : 'Add cost'}
          </button>
        </div>
      </form>
    </Modal>
  );
}

function Stat({ label, value, tone }) {
  const color = tone === 'good' ? '#1e8a5c' : tone === 'bad' ? '#c0392b' : 'inherit';
  return (
    <div style={{ ...panel, padding: '16px 18px', flex: '1 1 180px' }}>
      <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
                    color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontSize: '22px', fontWeight: 600, marginTop: '6px', color }}>{value}</div>
    </div>
  );
}

function CostRow({ label, amount, auto }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0',
                  borderBottom: '1px solid var(--border-color, rgba(255,255,255,0.06))' }}>
      <span style={{ fontSize: '13px' }}>
        {label}
        {auto && (
          <span style={{ fontSize: '10px', marginLeft: '8px', padding: '1px 6px',
                         borderRadius: '4px', background: 'rgba(120,120,255,0.15)',
                         color: 'var(--text-muted)', textTransform: 'uppercase',
                         letterSpacing: '0.05em' }}>auto</span>
        )}
      </span>
      <span style={{ fontWeight: 600, fontSize: '13px' }}>−{money(amount)}</span>
    </div>
  );
}

export default function FinancePanel() {
  const [win, setWin] = useState(monthWindow);
  const [pnl, setPnl] = useState(null);
  const [expenses, setExpenses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(false);

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

  const profitTone = useMemo(
    () => (pnl && Number(pnl.profit) >= 0 ? 'good' : 'bad'), [pnl]);

  return (
    <>
      <header className="portal-header">
        <div className="portal-header-left">
          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: '28px', fontWeight: 400 }}>
            Cost &amp; P&amp;L
          </h1>
          <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
            What you earned, what you spent, and what is left — for the period below.
          </p>
        </div>
      </header>

      <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'flex-end',
                    margin: '4px 0 18px' }}>
        <label>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>From</span>
          <input className="form-input" type="date" value={win.since}
                 onChange={(e) => setWin({ ...win, since: e.target.value })} />
        </label>
        <label>
          <span style={{ fontSize: '11px', color: 'var(--text-muted)', display: 'block' }}>To</span>
          <input className="form-input" type="date" value={win.until}
                 onChange={(e) => setWin({ ...win, until: e.target.value })} />
        </label>
        <button type="button" className="btn-primary" onClick={() => setAdding(true)}
                style={{ marginLeft: 'auto' }}>
          <Plus size={16} /> Add a cost
        </button>
      </div>

      {error && (
        <div style={{ background: 'rgba(220,80,60,0.12)', border: '1px solid rgba(220,80,60,0.35)',
                      color: '#c0392b', borderRadius: '8px', padding: '10px 12px',
                      fontSize: '13px', marginBottom: '14px' }}>{error}</div>
      )}

      {loading || !pnl ? (
        <div style={{ padding: '32px', color: 'var(--text-muted)' }}>Loading…</div>
      ) : (
        <>
          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', marginBottom: '18px' }}>
            <Stat label="Revenue" value={money(pnl.revenue.total)} tone="good" />
            <Stat label="Total costs" value={money(pnl.costs.total)} tone="bad" />
            <Stat label={Number(pnl.profit) >= 0 ? 'Profit' : 'Loss'}
                  value={money(Math.abs(Number(pnl.profit)))} tone={profitTone} />
          </div>

          <div style={{ display: 'flex', gap: '14px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
            <div style={{ ...panel, padding: '16px 18px', flex: '1 1 300px' }}>
              <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
                            color: 'var(--text-muted)', marginBottom: '8px' }}>
                Where the money went
              </div>
              <CostRow label="Salaries (payroll)" amount={pnl.costs.salaries} auto />
              <CostRow label="Inventory (purchase orders)" amount={pnl.costs.inventory} auto />
              {pnl.costs.manual.map((m) => (
                <CostRow key={m.category} label={m.label} amount={m.amount} />
              ))}
              <div style={{ display: 'flex', justifyContent: 'space-between', paddingTop: '10px',
                            fontWeight: 700 }}>
                <span>Total costs</span><span>−{money(pnl.costs.total)}</span>
              </div>
            </div>

            <div style={{ ...panel, padding: '16px 18px', flex: '1 1 300px' }}>
              <div style={{ fontSize: '11px', letterSpacing: '0.08em', textTransform: 'uppercase',
                            color: 'var(--text-muted)', marginBottom: '8px' }}>
                Costs you entered
              </div>
              {expenses.length === 0 ? (
                <div style={{ color: 'var(--text-secondary)', fontSize: '13px', padding: '10px 0' }}>
                  No manual costs in this period. Salaries and inventory above are pulled in
                  automatically — add rent, utilities and the rest with “Add a cost”.
                </div>
              ) : (
                expenses.map((x) => (
                  <div key={x.id} style={{ display: 'flex', justifyContent: 'space-between',
                                           alignItems: 'center', padding: '8px 0',
                                           borderBottom: '1px solid var(--border-color, rgba(255,255,255,0.06))' }}>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px' }}>
                        {x.category_display}{x.paid_to ? ` · ${x.paid_to}` : ''}
                      </div>
                      <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>
                        {x.incurred_on}{x.note ? ` · ${x.note}` : ''}
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                      {x.receipt_url && (
                        <a className="btn-secondary" href={x.receipt_url} target="_blank"
                           rel="noreferrer" style={{ textDecoration: 'none', fontSize: '12px' }}>Receipt</a>
                      )}
                      <span style={{ fontWeight: 600, fontSize: '13px' }}>{money(x.amount)}</span>
                      <button type="button" className="btn-secondary" aria-label="Delete cost"
                              onClick={async () => {
                                try { await api.deleteExpense(x.id); refresh(); }
                                catch (err) { setError(err.message); }
                              }}
                              style={{ color: '#b91c1c', borderColor: '#b91c1c' }}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </>
      )}

      {adding && (
        <AddExpenseForm onCancel={() => setAdding(false)}
                        onSaved={() => { setAdding(false); refresh(); }} />
      )}
    </>
  );
}
