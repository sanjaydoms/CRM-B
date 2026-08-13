/**
 * How far every boutique has actually got with setting itself up.
 *
 * The list is sorted so the boutiques somebody should ring are at the top, and
 * the ordering encodes two decisions the server already made and this screen
 * must not contradict:
 *
 * An unreadable schema sorts FIRST and never shows a percentage. `readable:
 * false` and `0%` look identical on a progress bar and mean opposite things --
 * "this boutique has done nothing" versus "we could not look" -- and only one
 * of them is a job for an engineer rather than for whoever chases signups.
 *
 * A suspended boutique sorts LAST. superadmin/onboarding.py reports it as
 * `blocked` precisely because its unfinished steps are not work it failed to
 * do: TenantHeaderMiddleware refuses it, so it could not have done them.
 * Putting it in the middle of the queue by percentage would send someone to
 * chase a boutique that the platform itself switched off.
 */

import { useCallback, useMemo, useState } from 'react';
import { Check, ChevronDown, ChevronRight, Minus, Sparkles, X } from 'lucide-react';

import { consoleApi } from '../api';
import { Async, Empty, Pill, SearchBox, SectionHead, Select, Stat, day, useApi } from '../ui';

/** Sort order: loudest finding first, the ones nobody should chase last. */
const RANK = {
  unreadable: 0,
  not_started: 1,
  in_progress: 2,
  almost_complete: 3,
  completed: 4,
  blocked: 5,
};

/**
 * Meter colour from the server's own word rather than from a threshold here.
 * ALMOST_COMPLETE_PERCENT lives in superadmin/onboarding.py and is what decides
 * `almost_complete`; a second threshold in this file would drift from it.
 */
const METER_TONE = {
  completed: '', almost_complete: '', in_progress: 'warn', not_started: 'off', blocked: 'off',
};

/** A step's icon and label, from `state`. Never a red cross on `tracked: false`. */
function StepMark({ step }) {
  if (step.state === 'done') return <Check size={15} color="var(--success-color)" />;
  if (step.state === 'todo') return <X size={15} color="var(--danger-color)" />;
  // module_off and untracked both arrive with done: null. A cross against
  // something nothing can measure -- or something an administrator switched off
  // -- is an accusation, so both render grey.
  return <Minus size={15} color="var(--text-muted)" />;
}

function Meter({ percent, status }) {
  const tone = METER_TONE[status] ?? '';
  return (
    <div className={`sa-meter ${tone}`}>
      <span style={{ width: `${Math.max(0, Math.min(100, percent))}%` }} />
    </div>
  );
}

/**
 * The full checklist for one boutique, fetched only when its row is opened.
 *
 * A separate component so useApi has a stable schema to key on: the list
 * endpoint deliberately returns the summary rather than every step for every
 * boutique, and fetching fifty checklists to show one is fifty schema switches.
 */
function Checklist({ schema }) {
  const state = useApi(useCallback(() => consoleApi.onboardingFor(schema), [schema]));

  return (
    <Async state={state} skeletonRows={3}>
      {(data) => {
        if (!data.readable) {
          return <div className="sa-note error">{data.detail}</div>;
        }
        return (
          <>
            <div className="sa-note info">
              <strong>{data.completed_steps} of {data.tracked_steps} tracked steps.</strong>{' '}
              {data.percent_basis}
            </div>
            <div className="sa-cards">
              {data.steps.map((step) => (
                <div key={step.key} className="sa-card">
                  <h4>
                    <StepMark step={step} />
                    {step.label}
                    {step.state === 'module_off' && <Pill value="not_configured" label="Module off" />}
                    {step.state === 'untracked' && <Pill value="not_tracked" label="Not tracked" />}
                  </h4>
                  <p>{step.detail}</p>
                </div>
              ))}
            </div>
          </>
        );
      }}
    </Async>
  );
}

export default function Onboarding({ route }) {
  const [term, setTerm] = useState('');
  const [status, setStatus] = useState('all');
  const [open, setOpen] = useState(null);

  const state = useApi(useCallback(() => consoleApi.onboarding(), []));

  const rows = useMemo(() => {
    if (!state.data) return [];
    const needle = term.trim().toLowerCase();
    return state.data.boutiques
      .map((b) => ({ ...b, status: b.readable ? b.status : 'unreadable' }))
      .filter((b) => {
        if (status === 'stuck' && (b.status === 'completed' || b.status === 'blocked')) return false;
        if (status !== 'all' && status !== 'stuck' && b.status !== status) return false;
        if (!needle) return true;
        return `${b.name} ${b.owner_email} ${b.schema_name}`.toLowerCase().includes(needle);
      })
      .sort((a, b) => (RANK[a.status] ?? 9) - (RANK[b.status] ?? 9)
        || (a.percent ?? 0) - (b.percent ?? 0)
        || a.name.localeCompare(b.name));
  }, [state.data, term, status]);

  return (
    <>
      <SectionHead
        title="Onboarding"
        subtitle="Signup seeds tailors, fabrics and hundreds of catalogue rows, so none of those count here. Every step below is something no seeder could have written."
      />

      <Async
        state={state}
        isEmpty={(d) => d.boutiques.length === 0}
        empty={<Empty icon={<Sparkles size={22} />} title="No boutiques have signed up yet."
          detail="Onboarding progress appears here as soon as one does." />}
      >
        {(data) => {
          const all = data.boutiques;
          const tally = (fn) => all.filter(fn).length;
          return (
            <>
              <div className="sa-stats">
                <Stat label="Boutiques" value={all.length} />
                <Stat label="Not started" value={tally((b) => b.readable && b.status === 'not_started')}
                  tone="warn" note="Zero of the tracked steps done" />
                <Stat label="In progress" value={tally((b) => b.readable && b.status === 'in_progress')} />
                <Stat label="Completed" value={tally((b) => b.status === 'completed')} />
                <Stat label="Unreadable" value={tally((b) => !b.readable)}
                  tone={tally((b) => !b.readable) ? 'off' : undefined}
                  note="Schema missing or half-migrated" />
              </div>

              <div className="sa-filters">
                <SearchBox value={term} onChange={setTerm} placeholder="Name, owner or schema…" />
                <Select value={status} onChange={setStatus} label="Progress" options={[
                  { value: 'all', label: 'All boutiques' },
                  { value: 'stuck', label: 'Still outstanding' },
                  { value: 'unreadable', label: 'Unreadable' },
                  { value: 'not_started', label: 'Not started' },
                  { value: 'in_progress', label: 'In progress' },
                  { value: 'almost_complete', label: 'Almost complete' },
                  { value: 'completed', label: 'Completed' },
                  { value: 'blocked', label: 'Suspended' },
                ]} />
              </div>

              {rows.length === 0 ? (
                <Empty title="No boutique matches those filters."
                  detail="Clear the search or widen the progress filter." />
              ) : (
                <div className="sa-table-wrap">
                  <table className="sa-table">
                    <thead>
                      <tr>
                        <th />
                        <th>Boutique</th>
                        <th>Progress</th>
                        <th>State</th>
                        <th>Waiting on</th>
                        <th>Signed up</th>
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((b) => {
                        const expanded = open === b.schema_name;
                        return [
                          <tr key={b.schema_name} className="sa-clickable"
                            onClick={() => setOpen(expanded ? null : b.schema_name)}>
                            <td style={{ width: 26, paddingRight: 0 }}>
                              {expanded ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
                            </td>
                            <td>
                              {/* stopPropagation, or opening a boutique also
                                  toggles the row underneath it. */}
                              <button className="sa-link"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  route.go(`boutiques/${b.schema_name}`);
                                }}>
                                {b.name}
                              </button>
                              <div className="sa-owner">{b.owner_email}</div>
                              <div className="sa-schema">{b.schema_name}</div>
                            </td>
                            <td style={{ minWidth: 150 }}>
                              {b.readable ? (
                                <>
                                  <span style={{ fontVariantNumeric: 'tabular-nums' }}>{b.percent}%</span>
                                  <Meter percent={b.percent} status={b.status} />
                                </>
                              ) : (
                                // Not 0%. The schema could not be read, which is a
                                // different finding from a boutique that has done nothing.
                                <span className="sa-muted">Not measured</span>
                              )}
                            </td>
                            <td>
                              {b.readable
                                ? <Pill value={b.status} />
                                : <Pill value="warning" label="Unreadable" />}
                              {!b.is_active && b.readable && (
                                <div className="sa-schema">suspended</div>
                              )}
                            </td>
                            <td style={{ maxWidth: 380 }}>
                              {!b.readable ? (
                                <span className="sa-muted">{b.detail}</span>
                              ) : b.blocked_on ? (
                                <>
                                  <div className="sa-name">{b.blocked_on.label}</div>
                                  {/* The detail is the entire point of this screen: the
                                      label says what is missing, this says why. */}
                                  <div className="sa-owner">{b.blocked_on.detail}</div>
                                </>
                              ) : (
                                <span className="sa-muted">Nothing outstanding.</span>
                              )}
                            </td>
                            <td className="sa-schema" style={{ whiteSpace: 'nowrap' }}>
                              {day(b.created_on)}
                            </td>
                          </tr>,
                          expanded && (
                            <tr key={`${b.schema_name}-steps`}>
                              <td colSpan={6} style={{ background: 'var(--bg-color)' }}>
                                <Checklist schema={b.schema_name} />
                              </td>
                            </tr>
                          ),
                        ];
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          );
        }}
      </Async>
    </>
  );
}
