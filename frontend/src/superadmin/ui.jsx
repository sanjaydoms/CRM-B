/**
 * The console's shared primitives.
 *
 * Every screen needs the same five states -- loading, empty, failed,
 * permission-denied, and loaded -- and the specification is explicit that no
 * screen may ever be blank when an API fails. Putting that in one place is what
 * makes it true on all fifteen screens rather than on the ones someone
 * remembered, so screens are expected to render <Async> rather than hand-roll
 * their own conditionals.
 *
 * No component library. lucide-react (icons) is the only UI dependency this
 * project has, and these are a few hundred lines of plain markup against the
 * tokens already in superadmin.css.
 */

import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import {
  AlertTriangle, Check, ChevronLeft, ChevronRight, Info, Lock, RefreshCw, Search, X,
} from 'lucide-react';

/* ----------------------------------------------------------- formatting */

const nf = new Intl.NumberFormat('en-IN');

export const count = (n) => (n === null || n === undefined ? '—' : nf.format(n));

export const money = (n) =>
  n === null || n === undefined
    ? '—'
    : `₹${new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 }).format(n)}`;

export const day = (iso) =>
  !iso
    ? null
    : new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });

export const moment = (iso) =>
  !iso
    ? null
    : new Date(iso).toLocaleString('en-GB', {
        day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
      });

/** How long ago, in the roughest terms that are still useful. */
export function since(iso) {
  if (!iso) return { text: 'never', tone: 'warn' };
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86400000);
  if (days <= 0) return { text: 'today', tone: 'ok' };
  if (days === 1) return { text: 'yesterday', tone: 'ok' };
  if (days < 30) return { text: `${days} days ago`, tone: 'ok' };
  return { text: `${Math.floor(days / 30)} mo ago`, tone: 'warn' };
}

/* --------------------------------------------------------------- status */

/**
 * The one place a health/severity word becomes a colour.
 *
 * `not_configured` is grey, never red. Several integrations this product does
 * not have are permanently in that state by design -- WhatsApp is a wa.me link
 * on purpose, not a broken API client -- and a red light there would send
 * someone hunting a bug that does not exist.
 */
export const TONES = {
  healthy: 'ok', ok: 'ok', active: 'ok', completed: 'ok', resolved: 'ok', enabled: 'ok',
  warning: 'warn', in_progress: 'warn', almost_complete: 'warn', acknowledged: 'warn',
  degraded: 'warn', trial: 'warn', new: 'info', not_started: 'info', info: 'info',
  critical: 'off', offline: 'off', suspended: 'off', blocked: 'off', disabled: 'off',
  high: 'off', failed: 'off',
  medium: 'warn', low: 'info',
  not_configured: 'muted', not_tracked: 'muted', ignored: 'muted', unknown: 'muted',
};

export function Pill({ value, label, tone }) {
  const resolved = tone || TONES[String(value).toLowerCase()] || 'info';
  return <span className={`sa-pill ${resolved}`}>{label ?? String(value).replace(/_/g, ' ')}</span>;
}

/* ---------------------------------------------------------------- toast */

const ToastContext = createContext(() => {});
export const useToast = () => useContext(ToastContext);

export function ToastHost({ children }) {
  const [toasts, setToasts] = useState([]);
  const seq = useRef(0);

  const push = useCallback((message, tone = 'ok') => {
    const id = ++seq.current;
    setToasts((list) => [...list, { id, message, tone }]);
    // Errors stay long enough to read and copy; confirmations get out of the way.
    setTimeout(() => setToasts((list) => list.filter((t) => t.id !== id)),
               tone === 'off' ? 8000 : 3500);
  }, []);

  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="sa-toasts" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={`sa-toast ${t.tone}`}>
            {t.tone === 'off' ? <AlertTriangle size={15} /> : <Check size={15} />}
            <span>{t.message}</span>
            <button className="sa-toast-x" onClick={() => setToasts((l) => l.filter((x) => x.id !== t.id))}
              aria-label="Dismiss">
              <X size={13} />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

/* ---------------------------------------------------------------- fetch */

/**
 * Load once, expose {data, error, loading, reload}.
 *
 * `load` MUST be a stable reference -- wrap it in useCallback at the call site,
 * with the real dependencies there. That is the whole contract, and it is the
 * standard trap with this shape: an inline arrow is a new function every render
 * and this would refetch forever.
 *
 * There is deliberately no `deps` argument. An earlier version took one and
 * forwarded it into useCallback, which cannot be statically checked and quietly
 * breaks React's hook invariant if a caller's array ever changes length.
 * Since every caller already memoises `load` on exactly those dependencies,
 * `[load]` says the same thing, is a literal, and cannot be got wrong.
 */
export function useApi(load) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const alive = useRef(true);

  const run = useCallback(async () => {
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const data = await load();
      if (alive.current) setState({ data, error: null, loading: false });
    } catch (e) {
      // The error object carries .status, which <Async> uses to tell a
      // permission failure apart from a server failure.
      if (alive.current) setState({ data: null, error: e, loading: false });
    }
  }, [load]);

  useEffect(() => {
    alive.current = true;
    run();
    return () => { alive.current = false; };
  }, [run]);

  return { ...state, reload: run };
}

/* --------------------------------------------------------------- states */

export function Skeleton({ rows = 5 }) {
  return (
    <div className="sa-skeleton" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="sa-skeleton-row" />)}
    </div>
  );
}

export function Empty({ icon, title, detail, action }) {
  return (
    <div className="sa-state">
      {icon || <Info size={22} />}
      <h3>{title}</h3>
      {detail && <p>{detail}</p>}
      {action}
    </div>
  );
}

export function Failed({ error, onRetry }) {
  const denied = error?.status === 401 || error?.status === 403;
  return (
    <div className="sa-state error">
      {denied ? <Lock size={22} /> : <AlertTriangle size={22} />}
      <h3>{denied ? 'Not permitted' : 'That did not load'}</h3>
      <p>{error?.message || 'The server did not answer.'}</p>
      {/* A retry on a permission failure just fails again; signing in is the
          only thing that helps, and the shell handles that. */}
      {!denied && onRetry && (
        <button className="sa-btn" onClick={onRetry}>
          <RefreshCw size={13} /> Try again
        </button>
      )}
    </div>
  );
}

/**
 * The five states, once.
 *
 * `isEmpty` is a predicate rather than a boolean so a screen can say what empty
 * means for it -- an empty array, a zero count, a missing key -- without
 * computing it before the data has arrived.
 */
export function Async({ state, isEmpty, empty, children, skeletonRows }) {
  if (state.loading && state.data === null) return <Skeleton rows={skeletonRows} />;
  if (state.error) return <Failed error={state.error} onRetry={state.reload} />;
  if (state.data === null) return <Skeleton rows={skeletonRows} />;
  if (isEmpty && isEmpty(state.data)) return empty || <Empty title="Nothing here yet." />;
  return children(state.data);
}

/* -------------------------------------------------------------- confirm */

/**
 * A modal confirmation for anything destructive.
 *
 * `requireReason` is what makes the audit trail worth having: the console
 * records a reason on suspensions and module changes, and a free-text box the
 * administrator must fill is the only place that reason can come from.
 */
export function Confirm({ open, title, body, confirmLabel = 'Confirm', danger, requireReason,
                          onConfirm, onCancel, busy }) {
  const [reason, setReason] = useState('');
  useEffect(() => { if (open) setReason(''); }, [open]);
  if (!open) return null;

  const blocked = busy || (requireReason && reason.trim().length < 3);

  return (
    <div className="sa-modal-backdrop" onClick={busy ? undefined : onCancel}>
      <div className="sa-modal" role="dialog" aria-modal="true" aria-label={title}
        onClick={(e) => e.stopPropagation()}>
        <h3>{title}</h3>
        <div className="sa-modal-body">{body}</div>
        {requireReason && (
          <div className="sa-field">
            <label htmlFor="sa-reason">Reason (recorded in the audit log)</label>
            <input id="sa-reason" className="sa-input" value={reason} autoFocus
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why are you doing this?" />
          </div>
        )}
        <div className="sa-modal-actions">
          <button className="sa-btn" onClick={onCancel} disabled={busy}>Cancel</button>
          <button className={`sa-btn ${danger ? 'danger-solid' : 'primary-inline'}`}
            onClick={() => onConfirm(reason.trim())} disabled={blocked}>
            {busy ? 'Working…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- table */

export function Table({ columns, rows, keyFor, empty, onRowClick }) {
  if (!rows.length) return empty || <Empty title="No rows." />;
  return (
    <div className="sa-table-wrap">
      <table className="sa-table">
        <thead>
          <tr>{columns.map((c) => (
            <th key={c.key} className={c.numeric ? 'sa-num' : undefined}>{c.label}</th>
          ))}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={keyFor ? keyFor(row, i) : i}
              className={onRowClick ? 'sa-clickable' : undefined}
              onClick={onRowClick ? () => onRowClick(row) : undefined}>
              {columns.map((c) => (
                <td key={c.key} className={c.numeric ? 'sa-num' : undefined}>
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Pager({ page, pages, onPage, total }) {
  if (pages <= 1) return total ? <div className="sa-pager"><span className="sa-muted">{count(total)} rows</span></div> : null;
  return (
    <div className="sa-pager">
      <button className="sa-btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>
        <ChevronLeft size={13} /> Previous
      </button>
      <span className="sa-muted">
        Page {page} of {pages}{total !== undefined && ` · ${count(total)} rows`}
      </span>
      <button className="sa-btn" disabled={page >= pages} onClick={() => onPage(page + 1)}>
        Next <ChevronRight size={13} />
      </button>
    </div>
  );
}

/**
 * A search box that does not fire a request per keystroke.
 *
 * 350ms: long enough that typing a word is one request, short enough that it
 * does not feel broken. The timer is cleared on unmount so a screen change
 * mid-type cannot fire a search into a component that is gone.
 */
export function SearchBox({ value, onChange, placeholder = 'Search…', delay = 350 }) {
  const [local, setLocal] = useState(value || '');
  const timer = useRef(null);

  useEffect(() => setLocal(value || ''), [value]);
  useEffect(() => () => clearTimeout(timer.current), []);

  const change = (next) => {
    setLocal(next);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => onChange(next), delay);
  };

  return (
    <div className="sa-searchbox">
      <Search size={14} />
      <input className="sa-input" value={local} placeholder={placeholder}
        onChange={(e) => change(e.target.value)} />
      {local && (
        <button className="sa-searchbox-x" aria-label="Clear"
          onClick={() => { clearTimeout(timer.current); setLocal(''); onChange(''); }}>
          <X size={13} />
        </button>
      )}
    </div>
  );
}

export function Select({ value, onChange, options, label }) {
  return (
    <select className="sa-select" value={value} onChange={(e) => onChange(e.target.value)}
      aria-label={label}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>{o.label}</option>
      ))}
    </select>
  );
}

/* ----------------------------------------------------------------- misc */

export function Stat({ label, value, note, tone, onClick }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag className={`sa-stat${onClick ? ' clickable' : ''}${tone ? ` ${tone}` : ''}`}
      onClick={onClick}>
      <div className="sa-stat-label">{label}</div>
      <div className="sa-stat-value">{value}</div>
      {note && <div className="sa-stat-note">{note}</div>}
    </Tag>
  );
}

export function SectionHead({ title, subtitle, children }) {
  return (
    <div className="sa-section-head">
      <div>
        <h2>{title}</h2>
        {subtitle && <p>{subtitle}</p>}
      </div>
      {children && <div className="sa-section-actions">{children}</div>}
    </div>
  );
}

/**
 * Says plainly that something is absent from the product rather than broken.
 *
 * Used wherever the specification asks for a screen this codebase has no data
 * for -- background jobs, payment gateways, request latency. Showing an empty
 * chart there would read as "nothing is wrong"; this reads as "nothing is
 * measured", which is the truth and is actionable.
 */
export function NotBuilt({ title, detail }) {
  return (
    <div className="sa-state muted">
      <Info size={22} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
