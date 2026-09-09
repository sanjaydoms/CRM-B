/**
 * Error Handling: what the product does when something goes wrong and it does
 * *not* crash.
 *
 * The Error Center next door shows one thing -- an exception nothing caught,
 * which became a 500. That is the rarest way this product fails. The four kinds
 * on this screen are the common ways, and until the capture work behind it they
 * were all invisible from here:
 *
 *   Handled   the code caught it, logged it and carried on. A boutique's order
 *             emails could fail for a week behind a clean Error Center.
 *   Refusals  a platform control said no -- suspension, a switched-off module,
 *             maintenance. The console could switch a module off and had no way
 *             to see it bite.
 *   Client    a 4xx the API returned on purpose. Noise one at a time; a signal
 *             when one endpoint refuses the same boutique four hundred times.
 *   Frontend  a React crash. The server answered every request correctly and
 *             the user still saw a white page.
 *
 * They are four tabs rather than four screens because they share every filter,
 * the same lifecycle and the same table -- and one screen makes the point the
 * Error Center cannot: these are all the same table, separated only by how the
 * product met them.
 *
 * The tab lives in the route (`#/handling/refusal`), not in component state, so
 * a link to a specific kind can be pasted into a conversation and the browser
 * Back button steps between kinds.
 */

import { Fragment, useCallback, useState } from 'react';
import {
  Ban, Bug, ChevronDown, ChevronRight, MessageSquareWarning, MonitorX, PackageX,
  ShieldCheck,
} from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Confirm, Empty, Pager, Pill, SearchBox, SectionHead, Select, Stat,
  count, moment, since, useApi, useToast,
} from '../ui';

const PAGE_SIZE = 25;

/* ------------------------------------------------------------------ kinds */

/**
 * `resolvable` is the one behavioural difference between the tabs, and it is a
 * claim about meaning rather than a UI preference.
 *
 * "Resolved" asserts the problem is fixed and reopens itself if the same thing
 * happens again. That is true of a swallowed exception and of a frontend crash:
 * somebody changes code, and a recurrence means they were wrong. It is not true
 * of a refusal or a client 4xx. A boutique you suspended will go on being
 * refused for exactly as long as you leave it suspended, and validation will go
 * on rejecting bad sizes forever. Offering "Resolve" there would invite an
 * operator to mark as fixed something that is working correctly -- and then
 * reopen it at them a minute later. Those two tabs get Ignore instead, which is
 * the honest verb: "I know, stop listing it."
 */
const KINDS = [
  {
    key: 'handled',
    noun: 'a swallowed failure',
    label: 'Handled',
    icon: PackageX,
    resolvable: true,
    title: 'Failures the code caught and carried on from',
    blurb: 'Each row is a place the product decided it could continue. That decision is '
      + 'usually right — an order should not fail to save because its confirmation email '
      + 'did not send — but the failure is real and the customer was never told. These are '
      + 'captured from every logger.exception() in the project, so the module that '
      + 'swallowed it is named in the row.',
    empty: 'Nothing has been caught and swallowed. Every logger.exception() in the project '
      + 'lands here, so an empty tab means the product is not quietly absorbing failures — '
      + 'not that nobody is watching. An except block that logs nothing at all stays '
      + 'invisible, and no amount of capture fixes that.',
    columns: [
      {
        label: 'Failure',
        width: 400,
        render: (e) => (
          <>
            <div className="sa-name">{e.exception_type}</div>
            <div style={SUB}>{e.message}</div>
          </>
        ),
      },
      {
        label: 'Swallowed by',
        render: (e) => (e.source
          ? <span className="sa-schema">{e.source}</span>
          : <span className="sa-muted">not recorded</span>),
      },
    ],
  },
  {
    key: 'refusal',
    noun: 'a refusal',
    label: 'Refusals',
    icon: Ban,
    resolvable: false,
    title: 'Your own controls, saying no',
    blurb: 'Not defects — the platform working as you configured it. This is the feedback '
      + 'loop the console was missing: a module you switched off, a boutique you suspended '
      + 'and maintenance mode all produce refusals, and until now none of them left a '
      + 'trace. A row here climbing fast usually means somebody is locked out and does not '
      + 'know why.',
    empty: 'No control has refused a request. Nothing is suspended, no module is switched '
      + 'off in a way anyone has hit, and maintenance mode is not turning traffic away.',
    columns: [
      {
        label: 'Control',
        width: 260,
        render: (e) => (
          <>
            <div className="sa-name">{e.exception_type}</div>
            <div style={SUB}>{e.message}</div>
          </>
        ),
      },
      {
        label: 'Refused',
        render: (e) => (
          <>
            <div className="sa-schema">{e.method} {e.path}</div>
            <Pill value={e.status_code === 403 ? 'blocked' : 'warning'}
              label={String(e.status_code)} />
          </>
        ),
      },
    ],
  },
  {
    key: 'client',
    noun: 'a deliberate 4xx',
    label: 'Client 4xx',
    icon: MessageSquareWarning,
    resolvable: false,
    title: 'Requests the API refused on purpose',
    blurb: 'Mostly validation, and mostly the system working. Read this tab in aggregate, '
      + 'never row by row: one endpoint rejecting the same boutique hundreds of times is a '
      + 'screen that is asking people for something they cannot give, and that is a product '
      + 'problem wearing a 400.',
    empty: 'No 4xx has been returned. That is unusual enough to be worth a second look at '
      + 'whether traffic is reaching the API at all.',
    columns: [
      {
        label: 'Endpoint',
        width: 320,
        render: (e) => (
          <>
            <div className="sa-name">{e.method} {e.path}</div>
            <div style={SUB}>{e.message}</div>
          </>
        ),
      },
      {
        label: 'Refused with',
        render: (e) => (
          <>
            <Pill value="info" label={String(e.status_code)} />
            <div className="sa-schema" style={{ marginTop: 4 }}>{e.exception_type}</div>
          </>
        ),
      },
    ],
  },
  {
    key: 'frontend',
    noun: 'a browser crash',
    label: 'Frontend',
    icon: MonitorX,
    resolvable: true,
    title: 'Crashes in the browser',
    blurb: 'The server answered every one of these requests correctly. The screen still went '
      + 'blank. Reported by the error boundary around the boutique workspace, so the stack '
      + 'below is a React component stack, not this project’s Python.',
    empty: 'No browser has reported a crash. The boutique workspace and this console both '
      + 'report through the same endpoint, so this covers both — but only crashes during '
      + 'render. A broken click handler that throws into the void is not caught by any '
      + 'error boundary and will not appear here.',
    columns: [
      {
        label: 'Crash',
        width: 400,
        render: (e) => (
          <>
            <div className="sa-name">{e.exception_type}</div>
            <div style={SUB}>{e.message}</div>
          </>
        ),
      },
      {
        label: 'Screen',
        render: (e) => (e.path
          ? <span className="sa-schema">{e.path}</span>
          : <span className="sa-muted">route not reported</span>),
      },
    ],
  },
];

const SUB = { fontSize: 13, color: 'var(--text-secondary)' };

const byKey = (key) => KINDS.find((k) => k.key === key) || KINDS[0];

const STATUSES = [
  { value: '', label: 'All statuses' },
  { value: 'new', label: 'New' },
  { value: 'acknowledged', label: 'Acknowledged' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'ignored', label: 'Ignored' },
];

/* ------------------------------------------------------------------ moves */

const ACKNOWLEDGE = {
  value: 'acknowledged', label: 'Acknowledge',
  already: 'Someone has already acknowledged this.',
};

const RESOLVE = {
  value: 'resolved', label: 'Resolve', already: 'This is already resolved.',
  confirm: {
    title: 'Resolve this?',
    body: 'Your name and the time are recorded against it. If the same failure happens '
      + 'again the server reopens it as New and keeps that resolution visible, so the feed '
      + 'reads "closed on the 1st, back on the 12th" rather than quietly staying green.',
    confirmLabel: 'Resolve',
  },
};

const IGNORE = {
  value: 'ignored', label: 'Ignore', already: 'This is already ignored.',
  confirm: {
    title: 'Ignore this permanently?',
    danger: true,
    body: 'Ignored is a standing decision, not a snooze: the count keeps rising but a new '
      + 'occurrence will never reopen it. Right for a refusal you have decided is correct — '
      + 'a boutique that stays suspended, a module you meant to switch off.',
    confirmLabel: 'Ignore it',
  },
};

const REOPEN = { value: 'new', label: 'Reopen', already: 'This is already open.' };

const movesFor = (kind) => (kind.resolvable
  ? [ACKNOWLEDGE, RESOLVE, IGNORE, REOPEN]
  : [ACKNOWLEDGE, IGNORE, REOPEN]);

/* ----------------------------------------------------------------- screen */

function Stack({ text, kind }) {
  if (kind.key === 'refusal') {
    return (
      <p className="sa-muted" style={{ fontSize: 13, margin: 0 }}>
        A refusal has no stack. Nothing went wrong: a control was consulted and it said no.
        The row above is the whole event.
      </p>
    );
  }
  if (!text) {
    return (
      <p className="sa-muted" style={{ fontSize: 13, margin: 0 }}>
        {kind.key === 'client'
          ? 'A 4xx raised and handled by the framework carries no stack worth keeping — the '
            + 'view above is the address.'
          : 'No frames from this codebase were captured.'}
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

export default function ErrorHandling({ route, onBadges }) {
  const toast = useToast();
  const kind = byKey(route.parts[1]);

  const [filters, setFilters] = useState({ status: '', boutique: '', q: '', page: 1 });
  const [open, setOpen] = useState(null);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);

  const state = useApi(
    useCallback(
      () => consoleApi.errors({ ...filters, kind: kind.key, page_size: PAGE_SIZE }),
      [filters, kind.key],
    ),
    [filters, kind.key],
  );

  const set = (patch) => setFilters((f) => ({ ...f, page: 1, ...patch }));
  const anyFilter = Boolean(filters.status || filters.boutique || filters.q);
  const clear = () => setFilters({ status: '', boutique: '', q: '', page: 1 });

  // Switching tab resets the filters and the expanded row. A status filter that
  // survived the move would silently hide most of the tab someone just opened.
  const goKind = (next) => {
    if (next === kind.key) return;
    clear();
    setOpen(null);
    route.go(`handling/${next}`);
  };

  const move = async (error, status, reason = '') => {
    setBusy(true);
    try {
      await consoleApi.updateError(error.id, { status, reason });
      toast(`${error.exception_type} marked ${status === 'new' ? 'open' : status}.`);
      setPending(null);
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

  const moves = movesFor(kind);

  return (
    <>
      <SectionHead title="Error Handling" subtitle={kind.title}>
        <SearchBox value={filters.q} onChange={(q) => set({ q })}
          placeholder="Exception, message or path…" />
        <Select value={filters.status} onChange={(status) => set({ status })}
          label="Status" options={STATUSES} />
      </SectionHead>

      <div className="sa-tabs" style={{ marginLeft: 0, marginBottom: 14, flexWrap: 'wrap' }}>
        {KINDS.map((k) => {
          const Icon = k.icon;
          return (
            <button key={k.key} className="sa-tab"
              aria-current={k.key === kind.key ? 'page' : undefined}
              onClick={() => goKind(k.key)}>
              <Icon size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
              {k.label}
              {/* The count comes from the summary, which is unfiltered on
                  purpose: a tab label that moved with the filters would make
                  the other tabs look empty whenever one was narrowed. */}
              {state.data?.summary?.by_kind?.[k.key] > 0 && (
                <span style={{ marginLeft: 7, opacity: 0.75 }}>
                  {count(state.data.summary.by_kind[k.key])}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div className="sa-note" style={{ marginBottom: 16 }}>{kind.blurb}</div>

      {filters.boutique && (
        <div className="sa-filters">
          <span className="sa-muted" style={{ fontSize: 13 }}>Only rows last seen in</span>
          <span className="sa-schema">{filters.boutique}</span>
          <button className="sa-btn" onClick={() => set({ boutique: '' })}>Clear</button>
        </div>
      )}

      <Async
        state={state}
        isEmpty={(d) => d.count === 0 && !anyFilter}
        empty={<Empty icon={<ShieldCheck size={22} />}
          title={`Nothing under ${kind.label.toLowerCase()}.`} detail={kind.empty} />}
      >
        {(data) => (
          <>
            <div className="sa-stats">
              <Stat label="Open in this tab" value={count(data.summary.by_kind?.[kind.key])}
                note="Not resolved or ignored" />
              <Stat label="Distinct rows" value={count(data.count)}
                note={anyFilter ? 'Matching these filters' : 'Ever recorded, this kind'} />
              {/* Deliberately shown next to every tab: this screen exists
                  because these kinds were being confused with crashes, and the
                  crash count is the number they must not be added to. */}
              <Stat label="Unresolved crashes" value={count(data.summary.unresolved)}
                tone={data.summary.unresolved > 0 ? 'warn' : undefined}
                note="The Error Center, not this screen"
                onClick={() => route.go('errors')} />
            </div>

            {data.errors.length === 0 ? (
              <Empty icon={<Bug size={22} />} title="Nothing matches those filters."
                detail="This tab is not empty — the filters are just too narrow."
                action={<button className="sa-btn" onClick={clear}>Clear the filters</button>} />
            ) : (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th style={{ width: 28 }} />
                      {kind.columns.map((c) => <th key={c.label}>{c.label}</th>)}
                      <th>Status</th>
                      <th className="sa-num">Occurrences</th>
                      <th>Last seen</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.errors.map((e) => {
                      const expanded = open === e.id;
                      const last = since(e.last_seen);
                      const seenIn = e.boutiques || [];
                      return (
                        <Fragment key={e.id}>
                          <tr className="sa-clickable"
                            onClick={() => setOpen(expanded ? null : e.id)}>
                            <td>
                              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </td>
                            {kind.columns.map((c) => (
                              <td key={c.label} style={c.width ? { maxWidth: c.width } : undefined}>
                                {c.render(e)}
                              </td>
                            ))}
                            <td>
                              <Pill value={e.status} />
                              {e.resolved_by && (
                                <div className="sa-schema" style={{ marginTop: 4 }}>
                                  {e.resolved_by}, {moment(e.resolved_at)}
                                </div>
                              )}
                            </td>
                            <td className="sa-num" style={{ fontSize: 19, fontWeight: 600 }}>
                              {count(e.count)}
                            </td>
                            <td style={{ whiteSpace: 'nowrap' }}>
                              {/* Inverted against the boutique screens on
                                  purpose: a boutique that ordered today is
                                  healthy, a failure that fired today is not. */}
                              <Pill value={last.tone === 'ok' ? 'warning' : 'healthy'}
                                label={last.text} />
                              <div className="sa-schema" style={{ marginTop: 4 }}>
                                {moment(e.last_seen)}
                              </div>
                            </td>
                          </tr>

                          {expanded && (
                            <tr>
                              <td colSpan={kind.columns.length + 4}
                                style={{ background: 'var(--bg-color)' }}>
                                <div style={{ display: 'grid', gap: 16, padding: '4px 0 8px' }}>
                                  <Stack text={e.traceback} kind={kind} />

                                  <dl className="sa-kv">
                                    <dt>Seen in</dt>
                                    <dd>
                                      {seenIn.length === 0 ? (
                                        <span className="sa-muted">
                                          No boutique — this happened on a public-schema request.
                                        </span>
                                      ) : (
                                        <>
                                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                            {seenIn.map((schema) => (
                                              <button key={schema} className="sa-btn"
                                                style={MONO}
                                                onClick={() => set({ boutique: schema })}>
                                                {schema}
                                              </button>
                                            ))}
                                          </div>
                                          <div className="sa-muted" style={{ fontSize: 12.5, marginTop: 4 }}>
                                            {count(seenIn.length)} boutique(s), capped
                                            server-side — read it as a floor, not a total.
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

                                    <dt>First seen</dt>
                                    <dd>{moment(e.first_seen)}</dd>

                                    <dt>Fingerprint</dt>
                                    <dd className="sa-schema">{e.fingerprint}</dd>
                                  </dl>

                                  <div>
                                    <label htmlFor={`hnote-${e.id}`} style={LABEL}>
                                      Internal notes
                                    </label>
                                    <textarea id={`hnote-${e.id}`} className="sa-textarea"
                                      defaultValue={e.notes}
                                      placeholder="What you found, what you tried…"
                                      onBlur={(ev) => {
                                        if (ev.target.value !== e.notes) saveNotes(e, ev.target.value);
                                      }} />
                                  </div>

                                  <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                                    {moves.map((m) => (
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
                                    {!kind.resolvable && (
                                      <span className="sa-muted" style={HINT}>
                                        No “Resolve” here: {kind.noun} is the system working,
                                        and it will go on happening for as long as the reason
                                        holds. Ignore is the honest verb.
                                      </span>
                                    )}
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
              {pending.error.exception_type} at {pending.error.path || '—'}
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

const MONO = { fontFamily: 'ui-monospace, Menlo, monospace', fontSize: 12 };
const LABEL = { display: 'block', fontSize: 13, fontWeight: 500, marginBottom: 6 };
const HINT = { fontSize: 12.5, alignSelf: 'center', maxWidth: 460 };
