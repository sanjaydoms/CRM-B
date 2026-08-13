/**
 * The Error Center: one row per distinct bug, not one per crash.
 *
 * The server groups by fingerprint (exception class + normalised path + the
 * last in-project frame), so `count` is the number of times this one bug has
 * fired and the feed shows fifty problems rather than the same problem fifty
 * times. That is the whole design of superadmin.models.ErrorEvent, and this
 * screen is only useful if it makes the grouping obvious -- hence the count in
 * its own wide column and first/last seen next to it, rather than a timestamp
 * per row that would read like a log tail.
 *
 * Every filter and the page go to the server. This table is the one in the
 * console most likely to run to thousands of rows, and it is the one someone
 * opens when the platform is already unwell -- fetching all of it to filter in
 * the browser is exactly the wrong time to be doing that.
 */

import { Fragment, useCallback, useState } from 'react';
import { AlertTriangle, Bug, ChevronDown, ChevronRight, ShieldCheck } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Confirm, Empty, Pager, Pill, SearchBox, SectionHead, Select, Stat,
  count, moment, since, useApi, useToast,
} from '../ui';

const PAGE_SIZE = 25;

const STATUSES = [
  { value: '', label: 'All statuses' },
  { value: 'new', label: 'New' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'ignored', label: 'Ignored' },
];

const SEVERITIES = [
  { value: '', label: 'All severities' },
  { value: 'critical', label: 'Critical' },
  { value: 'high', label: 'High' },
  { value: 'medium', label: 'Medium' },
  { value: 'low', label: 'Low' },
];

/**
 * The four transitions the server accepts, and what each one actually means.
 *
 * `confirm` is present exactly where the move takes a live problem off the
 * feed, because those are the two the audit log needs a reason for. Acknowledge
 * and Reopen only say who is looking, and a modal in front of those would train
 * people to dismiss modals.
 *
 * The wording is not decoration: core/exceptions.py reopens a *resolved* error
 * on the next occurrence and deliberately leaves an *ignored* one alone, so
 * "resolve" and "ignore" behave differently in a way nobody can guess from the
 * button.
 */
const MOVES = [
  {
    value: 'acknowledged',
    label: 'Acknowledge',
    already: 'Someone has already acknowledged this.',
  },
  {
    value: 'resolved',
    label: 'Resolve',
    already: 'This is already resolved.',
    confirm: {
      title: 'Resolve this error?',
      body: 'Your name and the time are recorded against it. If the same bug fires again the '
        + 'server reopens it as New and keeps that resolution visible, so the feed reads '
        + '"closed on the 1st, back on the 12th" rather than quietly staying green.',
      confirmLabel: 'Resolve',
    },
  },
  {
    value: 'ignored',
    label: 'Ignore',
    already: 'This is already ignored.',
    confirm: {
      title: 'Ignore this error permanently?',
      danger: true,
      body: 'Ignored is a standing decision, not a snooze: the count keeps rising but a new '
        + 'occurrence will never reopen it and it stays out of the unresolved badge. Nobody '
        + 'will be told about this bug again unless someone reopens it here.',
      confirmLabel: 'Ignore it',
    },
  },
  { value: 'new', label: 'Reopen', already: 'This error is already open.' },
];

/** The in-project frames, or an honest sentence about why there are none. */
function Traceback({ text }) {
  if (!text) {
    return (
      <p className="sa-muted" style={{ fontSize: 13 }}>
        No frames from this codebase were captured — the exception was raised entirely inside
        Django or a library, so there is nothing here that a diff would explain.
      </p>
    );
  }
  return (
    <pre style={{
      fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
      fontSize: 12, lineHeight: 1.6, margin: 0, padding: '12px 14px',
      background: 'var(--bg-color)', border: '1px solid var(--border-color)',
      borderRadius: 'var(--radius-md)', maxHeight: 300, overflow: 'auto',
    }}>
      {text}
    </pre>
  );
}

export default function Errors({ route, onBadges }) {
  const toast = useToast();
  const [filters, setFilters] = useState({ status: '', severity: '', boutique: '', q: '', page: 1 });
  const [open, setOpen] = useState(null);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);

  const state = useApi(
    useCallback(() => consoleApi.errors({ ...filters, page_size: PAGE_SIZE }), [filters]),
    [filters],
  );

  // Every filter change goes back to page 1. Page 4 of the previous result set
  // is a different set of rows, and usually no rows at all.
  const set = (patch) => setFilters((f) => ({ ...f, page: 1, ...patch }));
  const anyFilter = Boolean(filters.status || filters.severity || filters.boutique || filters.q);
  const clear = () => setFilters({ status: '', severity: '', boutique: '', q: '', page: 1 });

  const move = async (error, status, reason = '') => {
    setBusy(true);
    try {
      await consoleApi.updateError(error.id, { status, reason });
      toast(`${error.exception_type} marked ${status === 'new' ? 'open' : status}.`);
      setPending(null);
      // The navigation badge counts unresolved errors, so it is stale the
      // instant this returns until something asks the server again.
      if (onBadges) onBadges();
      state.reload();
    } catch (e) {
      toast(e.message, 'off');
    } finally {
      setBusy(false);
    }
  };

  const saveNotes = async (error, notes) => {
    try {
      await consoleApi.updateError(error.id, { notes });
      // Patched in place rather than reloaded: the feed is ordered by last seen
      // and a reload would move the row out from under whoever just typed in it.
      error.notes = notes;
      toast('Note saved.');
    } catch (e) {
      toast(e.message, 'off');
    }
  };

  return (
    <>
      <SectionHead
        title="Error Center"
        subtitle="Unhandled server exceptions, grouped into one row per distinct bug."
      >
        <SearchBox value={filters.q} onChange={(q) => set({ q })}
          placeholder="Exception, message or path…" />
        <Select value={filters.status} onChange={(status) => set({ status })}
          label="Status" options={STATUSES} />
        <Select value={filters.severity} onChange={(severity) => set({ severity })}
          label="Severity" options={SEVERITIES} />
      </SectionHead>

      {filters.boutique && (
        <div className="sa-filters">
          <span className="sa-muted" style={{ fontSize: 13 }}>Only errors last seen in</span>
          <span className="sa-schema">{filters.boutique}</span>
          <button className="sa-btn" onClick={() => set({ boutique: '' })}>Clear</button>
        </div>
      )}

      <Async
        state={state}
        isEmpty={(d) => d.count === 0 && !anyFilter}
        empty={(
          <Empty
            icon={<ShieldCheck size={22} />}
            title="Nothing has crashed."
            detail="Every unhandled 500 in this project is captured with a fingerprint, a count
                    and its in-project stack frames. An empty feed means there is nothing to
                    capture, not that nothing is watching."
          />
        )}
      >
        {(data) => (
          <>
            <div className="sa-stats">
              <Stat label="Unresolved" value={count(data.summary.unresolved)}
                tone={data.summary.unresolved > 0 ? 'warn' : undefined}
                note="Whole feed, ignoring the filters" />
              <Stat label="Critical & open" value={count(data.summary.critical)}
                tone={data.summary.critical > 0 ? 'off' : undefined}
                note="Database errors only" />
              <Stat label="Distinct bugs" value={count(data.count)}
                note={anyFilter ? 'Matching these filters' : 'Every bug ever recorded'} />
            </div>

            {data.summary.critical > 0 && (
              <div className="sa-note error">
                <AlertTriangle size={14} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                {count(data.summary.critical)} critical error
                {data.summary.critical === 1 ? ' is' : 's are'} open. Critical is set only for a
                database error — either a constraint the code does not know about, so writes are
                being lost, or the database itself, which in this single-database deployment is
                every boutique at once.
              </div>
            )}

            {data.errors.length === 0 ? (
              <Empty
                icon={<Bug size={22} />}
                title="No error matches those filters."
                detail="The feed is not empty — these filters are just too narrow."
                action={<button className="sa-btn" onClick={clear}>Clear the filters</button>}
              />
            ) : (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th style={{ width: 28 }} />
                      <th>Bug</th>
                      <th>Severity</th>
                      <th>Status</th>
                      <th className="sa-num">Occurrences</th>
                      <th>First seen</th>
                      <th>Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.errors.map((e) => {
                      const expanded = open === e.id;
                      const last = since(e.last_seen);
                      // The server has this capped, so it is a floor on the
                      // distinct boutiques rather than the total. Missing
                      // entirely on an older payload, hence the fallback.
                      const seenIn = e.boutiques || [];
                      return (
                        // A detail row is a second <tr>, so the pair is wrapped
                        // rather than nested -- a <div> between <tbody> and <tr>
                        // is not valid table markup and browsers hoist it out.
                        <Fragment key={e.id}>
                          <tr className="sa-clickable"
                            onClick={() => setOpen(expanded ? null : e.id)}>
                            <td>
                              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </td>
                            <td style={{ maxWidth: 420 }}>
                              <div className="sa-name">{e.exception_type}</div>
                              <div style={{ fontSize: 13, color: 'var(--text-secondary)' }}>
                                {e.message}
                              </div>
                              <div className="sa-schema">
                                {e.method} {e.path} · {e.status_code}
                              </div>
                            </td>
                            <td><Pill value={e.severity} /></td>
                            <td>
                              <Pill value={e.status} />
                              {e.resolved_by && (
                                <div className="sa-schema" style={{ marginTop: 4 }}>
                                  {e.resolved_by}, {moment(e.resolved_at)}
                                </div>
                              )}
                            </td>
                            {/* The count is the point of this table -- it is what
                                separates a bug that fired once from the one
                                breaking a boutique's checkout all morning. */}
                            <td className="sa-num" style={{ fontSize: 19, fontWeight: 600 }}>
                              {count(e.count)}
                            </td>
                            <td style={{ whiteSpace: 'nowrap' }}>
                              <div style={{ fontSize: 13 }}>{moment(e.first_seen)}</div>
                              <div className="sa-schema">{since(e.first_seen).text}</div>
                            </td>
                            {/* Inverted against every other screen on purpose:
                                a boutique that ordered today is healthy, a bug
                                that fired today is not. */}
                            <td style={{ whiteSpace: 'nowrap' }}>
                              <Pill value={last.tone === 'ok' ? 'warning' : 'healthy'}
                                label={last.text} />
                              <div className="sa-schema" style={{ marginTop: 4 }}>
                                {moment(e.last_seen)}
                              </div>
                            </td>
                          </tr>

                          {expanded && (
                            <tr>
                              <td colSpan={7} style={{ background: 'var(--bg-color)' }}>
                                <div style={{ display: 'grid', gap: 16, padding: '4px 0 8px' }}>
                                  <Traceback text={e.traceback} />

                                  <dl className="sa-kv">
                                    <dt>Seen in</dt>
                                    <dd>
                                      {seenIn.length === 0 ? (
                                        <span className="sa-muted">
                                          No boutique — this fired on a public-schema request.
                                        </span>
                                      ) : (
                                        <>
                                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                            {seenIn.map((schema) => (
                                              <button key={schema} className="sa-btn"
                                                style={{ fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 }}
                                                onClick={() => set({ boutique: schema })}>
                                                {schema}
                                              </button>
                                            ))}
                                          </div>
                                          <div className="sa-muted" style={{ fontSize: 12.5, marginTop: 4 }}>
                                            {count(seenIn.length)} boutique(s), and the list is
                                            capped server-side — read it as a floor, not a total.
                                          </div>
                                        </>
                                      )}
                                    </dd>

                                    <dt>Most recent occurrence</dt>
                                    <dd>
                                      {e.boutique ? (
                                        <button className="sa-link"
                                          onClick={() => route.go(`boutiques/${e.boutique}`)}>
                                          {e.boutique}
                                        </button>
                                      ) : <span className="sa-muted">public schema</span>}
                                      {e.username && <span className="sa-muted"> · as {e.username}</span>}
                                    </dd>

                                    <dt>Fingerprint</dt>
                                    <dd className="sa-schema">{e.fingerprint}</dd>
                                  </dl>

                                  <div>
                                    <label htmlFor={`note-${e.id}`}
                                      style={{ display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6 }}>
                                      Internal notes
                                    </label>
                                    <textarea id={`note-${e.id}`} className="sa-textarea"
                                      defaultValue={e.notes} placeholder="What you found, what you tried…"
                                      // Saved on blur, not per keystroke: one
                                      // PATCH when the writer moves on.
                                      onBlur={(ev) => {
                                        if (ev.target.value !== e.notes) saveNotes(e, ev.target.value);
                                      }} />
                                  </div>

                                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                    {MOVES.map((m) => (
                                      <button key={m.value}
                                        className={`sa-btn${m.confirm?.danger ? ' danger' : ''}`}
                                        disabled={busy || e.status === m.value}
                                        title={e.status === m.value ? m.already : undefined}
                                        onClick={() => (m.confirm
                                          ? setPending({ error: e, move: m })
                                          : move(e, m.value))}>
                                        {m.label}
                                      </button>
                                    ))}
                                    {/* Every button above is either live or
                                        disabled with its reason in the tooltip;
                                        this repeats the reason in text, because
                                        a tooltip is not an explanation on a
                                        touch screen. */}
                                    <span className="sa-muted" style={{ fontSize: 12.5, alignSelf: 'center' }}>
                                      {MOVES.find((m) => m.value === e.status)?.already}
                                    </span>
                                  </div>
                                </div>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>

                <Pager page={data.page} pages={data.pages} total={data.count}
                  onPage={(page) => { setOpen(null); setFilters((f) => ({ ...f, page })); }} />
              </div>
            )}
          </>
        )}
      </Async>

      <Confirm
        open={Boolean(pending)}
        requireReason
        busy={busy}
        danger={pending?.move.confirm.danger}
        title={pending?.move.confirm.title}
        body={pending && (
          <>
            <div className="sa-schema" style={{ marginBottom: 8 }}>
              {pending.error.exception_type} at {pending.error.path}
              {' '}· {count(pending.error.count)} occurrence(s)
            </div>
            {pending.move.confirm.body}
          </>
        )}
        confirmLabel={pending?.move.confirm.confirmLabel}
        onCancel={() => setPending(null)}
        onConfirm={(reason) => move(pending.error, pending.move.value, reason)}
      />
    </>
  );
}
