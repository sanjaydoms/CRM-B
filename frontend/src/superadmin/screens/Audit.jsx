/**
 * The audit trail: who did what, to what, and why they said they were doing it.
 *
 * Read-only, and the note at the top of the screen says so out loud rather than
 * leaving it to be inferred from the absence of a delete button. The claim is
 * scoped carefully: the console exposes no write route (superadmin.api_views
 * has a GET and nothing else), and the table is written by superadmin.audit
 * .record alone. That is append-only by convention and by API surface, not by a
 * database grant -- Postgres can be told to refuse UPDATE and DELETE here, and
 * has not been. Saying "append-only" without that qualifier would be a stronger
 * promise than the code keeps.
 *
 * Everything is filtered and paged server-side, including free text. The
 * interesting queries on this table are all "what did this person do" and "what
 * happened to this boutique", and both are indexed columns.
 */

import { Fragment, useCallback, useState } from 'react';
import { ChevronDown, ChevronRight, ScrollText } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Empty, Pager, SearchBox, SectionHead, Select, moment, useApi,
} from '../ui';

const PAGE_SIZE = 50;

/** JSON as one line a human can scan, rather than as pretty-printed prose. */
const show = (value) => {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value || '""';
  if (Array.isArray(value)) return value.length ? value.join(', ') : '(empty)';
  return JSON.stringify(value);
};

const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

const isPlainObject = (value) =>
  value !== null && typeof value === 'object' && !Array.isArray(value);

/**
 * What changed, rather than the two objects it changed between.
 *
 * before/after are free-form JSON on this model -- a dict of module switches, a
 * bare setting value, `{ok, result}` from a user action -- so a changed-key
 * table is only possible when both sides are objects. When they are not, the
 * pair is shown side by side, which is the honest fallback: better a small
 * amount of JSON than a diff that quietly invents structure.
 */
function Diff({ before, after }) {
  if (before === null && after === null) {
    return (
      <p className="sa-muted" style={{ fontSize: 13 }}>
        This action recorded no before/after state — the reason is the whole record of it.
      </p>
    );
  }

  if (!isPlainObject(before) || !isPlainObject(after)) {
    return (
      <div className="sa-cards">
        <div className="sa-card">
          <h4>Before</h4>
          <p className="sa-schema" style={{ whiteSpace: 'pre-wrap' }}>{show(before)}</p>
        </div>
        <div className="sa-card">
          <h4>After</h4>
          <p className="sa-schema" style={{ whiteSpace: 'pre-wrap' }}>{show(after)}</p>
        </div>
      </div>
    );
  }

  const keys = [...new Set([...Object.keys(before), ...Object.keys(after)])]
    .filter((key) => !same(before[key], after[key]))
    .sort();

  if (keys.length === 0) {
    return (
      <p className="sa-muted" style={{ fontSize: 13 }}>
        Nothing changed. The request was recorded because it was made, not because it had an
        effect — which is itself worth knowing.
      </p>
    );
  }

  return (
    <table className="sa-table" style={{ background: 'var(--surface-color)' }}>
      <thead>
        <tr><th>Field</th><th>Before</th><th>After</th></tr>
      </thead>
      <tbody>
        {keys.map((key) => (
          <tr key={key}>
            <td className="sa-name">{key}</td>
            <td className="sa-schema" style={{ color: 'var(--danger-color)' }}>
              {key in before ? show(before[key]) : <span className="sa-muted">not set</span>}
            </td>
            <td className="sa-schema" style={{ color: 'var(--success-color)' }}>
              {key in after ? show(after[key]) : <span className="sa-muted">removed</span>}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export default function Audit() {
  const [filters, setFilters] = useState({ actor: '', action: '', boutique: '', q: '', page: 1 });
  const [open, setOpen] = useState(null);

  const state = useApi(
    useCallback(() => consoleApi.audit({ ...filters, page_size: PAGE_SIZE }), [filters]),
    [filters],
  );

  // Any filter change goes back to page 1: page 3 of the old result set is a
  // different set of rows.
  const set = (patch) => setFilters((f) => ({ ...f, page: 1, ...patch }));
  const anyFilter = Boolean(filters.actor || filters.action || filters.boutique || filters.q);
  const clear = () => setFilters({ actor: '', action: '', boutique: '', q: '', page: 1 });

  return (
    <>
      <SectionHead
        title="Audit Log"
        subtitle="Every sensitive action the console can take, with the reason its operator typed."
      >
        <SearchBox value={filters.q} onChange={(q) => set({ q })}
          placeholder="Actor, target, action or reason…" />
      </SectionHead>

      <div className="sa-note info">
        This trail is append-only: it is written by one function on the server and the console
        offers no route that edits or deletes an entry — a record the credential that took the
        action can rewrite is not an audit trail. That is enforced by the API surface and by
        convention, not by the database, which still permits an UPDATE from a Postgres session.
      </div>

      <Async
        state={state}
        isEmpty={(d) => d.count === 0 && !anyFilter}
        empty={(
          <Empty icon={<ScrollText size={22} />} title="Nothing has been recorded yet."
            detail="Suspensions, module changes, feature flags, user actions, password resets and
                    console sign-ins all land here the moment one happens." />
        )}
      >
        {(data) => (
          <>
            {/* The action list comes from the server's own choices field, so a
                new action type appears in this dropdown without an edit here. */}
            <div className="sa-filters">
              <Select value={filters.action} onChange={(action) => set({ action })} label="Action"
                options={[{ value: '', label: 'All actions' }, ...data.actions]} />
              {/* Both of these filter on an exact match server-side, which is
                  why the rows below are clickable: typing a schema name exactly
                  is a worse way to get one than clicking the one you can see.
                  Free text is what `q` is for. */}
              {filters.actor && (
                <button className="sa-btn" onClick={() => set({ actor: '' })}>
                  Actor: {filters.actor} ✕
                </button>
              )}
              {filters.boutique && (
                <button className="sa-btn" onClick={() => set({ boutique: '' })}>
                  Boutique: {filters.boutique} ✕
                </button>
              )}
              {anyFilter && (
                <button className="sa-btn" onClick={clear}>Clear all filters</button>
              )}
            </div>

            {data.entries.length === 0 ? (
              <Empty title="No entry matches those filters."
                detail="The trail is not empty — these filters are just too narrow."
                action={<button className="sa-btn" onClick={clear}>Clear the filters</button>} />
            ) : (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th style={{ width: 28 }} />
                      <th>When</th>
                      <th>Who</th>
                      <th>What</th>
                      <th>Target</th>
                      <th>Boutique</th>
                      <th>Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.entries.map((entry) => {
                      const expanded = open === entry.id;
                      return (
                        <Fragment key={entry.id}>
                          <tr className="sa-clickable"
                            onClick={() => setOpen(expanded ? null : entry.id)}>
                            <td>
                              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                            </td>
                            <td style={{ whiteSpace: 'nowrap', fontSize: 13 }}>
                              {moment(entry.created_at)}
                            </td>
                            <td>
                              <button className="sa-link"
                                onClick={(e) => { e.stopPropagation(); set({ actor: entry.actor }); }}>
                                {entry.actor || <span className="sa-muted">no actor</span>}
                              </button>
                              {entry.ip && <div className="sa-schema">{entry.ip}</div>}
                            </td>
                            <td className="sa-name">{entry.action_label}</td>
                            <td className="sa-schema">{entry.target || '—'}</td>
                            <td>
                              {entry.boutique ? (
                                <button className="sa-link"
                                  onClick={(e) => { e.stopPropagation(); set({ boutique: entry.boutique }); }}>
                                  <span className="sa-schema">{entry.boutique}</span>
                                </button>
                              ) : <span className="sa-muted">—</span>}
                            </td>
                            {/* The reason is the only part of a row that was
                                typed by a person, so it gets room rather than a
                                tooltip. Blank is stated, not left as a gap: the
                                API requires a reason on the destructive actions
                                and not on the rest. */}
                            <td style={{ maxWidth: 300, fontSize: 13.5 }}>
                              {entry.reason || <span className="sa-muted">none given</span>}
                            </td>
                          </tr>

                          {expanded && (
                            <tr>
                              <td colSpan={7} style={{ background: 'var(--bg-color)' }}>
                                <div style={{ padding: '4px 0 8px' }}>
                                  <Diff before={entry.before} after={entry.after} />
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
    </>
  );
}
