/**
 * Switches the code itself asks about, flipped without a deploy.
 *
 * Distinct from Modules: a module is an existing surface withheld from a
 * boutique and enforced by middleware, a flag is a behaviour the application
 * queries by name (superadmin/models.py FeatureFlag.applies_to).
 *
 * The boutique list is fetched alongside the flags because `enabled_for` is
 * validated server-side against real schema names -- a free-text box here would
 * turn every typo into a 400 and every near-miss into a flag that looks targeted
 * at a boutique which does not exist. One Promise.all rather than two loading
 * states: neither half of this screen is usable without the other.
 *
 * Every write is followed by a reload rather than a local patch. There are a
 * handful of flags, the endpoint is two cheap queries, and a mirrored copy of
 * server state is how a console starts showing something the server did not say.
 */

import { useCallback, useState } from 'react';
import { Flag, Plus, Trash2 } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Confirm, Empty, Pill, SectionHead, Select, Table,
  day, moment, useApi, useToast,
} from '../ui';

// SlugField(max_length=80): letters, digits, underscores, hyphens.
const KEY_OK = /^[-\w]+$/;

/** What the three switches add up to, in the order applies_to() checks them. */
function reach(flag) {
  if (flag.enabled) return 'On for every boutique.';
  const parts = [];
  if (flag.enabled_for?.length) parts.push(`${flag.enabled_for.length} named`);
  if (flag.rollout_percent) parts.push(`${flag.rollout_percent}% of the others`);
  return parts.length ? `On for ${parts.join(' + ')}.` : 'Off everywhere.';
}

export default function Flags() {
  const toast = useToast();
  const [draft, setDraft] = useState({ key: '', description: '' });
  const [pending, setPending] = useState(null);
  const [busyKey, setBusyKey] = useState(null);

  const state = useApi(useCallback(async () => {
    const [flags, overview] = await Promise.all([consoleApi.flags(), consoleApi.overview()]);
    return { flags: flags.flags, boutiques: overview.boutiques };
  }, []));

  /** Every write: lock the row, call, say what happened, refetch. */
  const run = async (key, work, message) => {
    setBusyKey(key);
    try {
      await work();
      toast(message);
      state.reload();
      return true;
    } catch (e) {
      toast(e.message, 'off');
      return false;
    } finally {
      setBusyKey(null);
    }
  };

  const newKey = draft.key.trim();
  const keyProblem = !newKey
    ? 'A key is required — it is the name the code asks for.'
    : !KEY_OK.test(newKey)
      ? 'Letters, numbers, hyphens and underscores only.'
      : '';

  const create = async () => {
    const ok = await run('+', () => consoleApi.createFlag({
      key: newKey, description: draft.description.trim(),
    }), `Flag "${newKey}" created, switched off.`);
    if (ok) setDraft({ key: '', description: '' });
  };

  const setTargets = (flag, next) =>
    run(flag.key, () => consoleApi.updateFlag(flag.key, { enabled_for: next }),
        `${flag.key} is now targeted at ${next.length} boutique${next.length === 1 ? '' : 's'}.`);

  const columns = (boutiques) => [
    {
      key: 'key',
      label: 'Flag',
      render: (f) => (
        <>
          <div className="sa-name">{f.key}</div>
          {f.description && <div className="sa-owner">{f.description}</div>}
          <div className="sa-muted" style={{ fontSize: 12.5 }}>{reach(f)}</div>
        </>
      ),
    },
    {
      key: 'enabled',
      label: 'Global',
      render: (f) => (
        <button className={`sa-btn${f.enabled ? '' : ' danger'}`} disabled={busyKey === f.key}
          aria-pressed={f.enabled}
          onClick={() => run(f.key,
            () => consoleApi.updateFlag(f.key, { enabled: !f.enabled }),
            `${f.key} is ${f.enabled ? 'off' : 'on'} globally.`)}>
          {f.enabled ? 'On' : 'Off'}
        </button>
      ),
    },
    {
      key: 'rollout',
      label: 'Rollout',
      numeric: true,
      render: (f) => (
        <input
          className="sa-input" type="number" min="0" max="100" step="1"
          style={{ width: 82 }} disabled={busyKey === f.key}
          // Keyed on the stored value so a server-side clamp re-mounts the input.
          // Without it the box keeps showing what was typed while the flag holds
          // something else.
          key={`${f.key}:${f.rollout_percent}`}
          defaultValue={f.rollout_percent}
          aria-label={`Rollout percent for ${f.key}`}
          // On blur, not per keystroke: one PATCH when they move on.
          onBlur={(e) => {
            const next = Math.min(100, Math.max(0, Math.round(Number(e.target.value) || 0)));
            if (next !== f.rollout_percent) {
              run(f.key, () => consoleApi.updateFlag(f.key, { rollout_percent: next }),
                  `${f.key} rolled out to ${next}%.`);
            }
          }}
        />
      ),
    },
    {
      key: 'enabled_for',
      label: 'Targeted boutiques',
      render: (f) => {
        const targets = f.enabled_for || [];
        const rest = boutiques.filter((b) => !targets.includes(b.schema_name));
        return (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center', minWidth: 240 }}>
            {targets.map((schema) => {
              const known = boutiques.find((b) => b.schema_name === schema);
              return (
                <button key={schema} className="sa-btn" disabled={busyKey === f.key}
                  aria-label={`Stop targeting ${schema} with ${f.key}`}
                  onClick={() => setTargets(f, targets.filter((s) => s !== schema))}>
                  {known ? known.name : schema} ×
                </button>
              );
            })}
            {rest.length === 0 ? (
              <span className="sa-muted" style={{ fontSize: 12.5 }}>
                {boutiques.length ? 'Every boutique.' : 'No boutiques to target.'}
              </span>
            ) : (
              <Select
                value="" label={`Target a boutique with ${f.key}`}
                onChange={(schema) => schema && setTargets(f, [...targets, schema])}
                options={[{ value: '', label: 'Add a boutique…' },
                          ...rest.map((b) => ({ value: b.schema_name, label: b.name }))]}
              />
            )}
          </div>
        );
      },
    },
    {
      key: 'changed',
      label: 'Last change',
      render: (f) => (
        <>
          <div>{f.modified_by || f.created_by || <span className="sa-muted">unknown</span>}</div>
          <div className="sa-schema">{moment(f.updated_at)}</div>
          <div className="sa-muted" style={{ fontSize: 12 }}>
            created {day(f.created_at)}{f.created_by ? ` by ${f.created_by}` : ''}
          </div>
        </>
      ),
    },
    {
      key: 'delete',
      label: '',
      render: (f) => (
        <button className="sa-btn danger" disabled={busyKey === f.key}
          onClick={() => setPending(f)}>
          <Trash2 size={13} /> Delete
        </button>
      ),
    },
  ];

  return (
    <>
      <SectionHead
        title="Feature flags"
        subtitle="Checked in this order: a boutique in Targeted is on whatever else says; then Global on means everyone; then the rollout percent — a stable hash of the schema name, so a boutique inside the rollout stays inside it rather than flickering between requests."
      />

      <Async state={state}>
        {(data) => (
          <>
            {/* Above the table, and outside Async's empty state: a console with
                no flags and no way to make one is a dead end. */}
            <div className="sa-card" style={{ marginBottom: 18 }}>
              <h4><Plus size={14} /> New flag</h4>
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end', marginTop: 12 }}>
                <div className="sa-field" style={{ marginBottom: 0, flex: '0 1 220px' }}>
                  <label htmlFor="sa-flag-key">Key</label>
                  <input id="sa-flag-key" className="sa-input" value={draft.key}
                    placeholder="new_order_wizard"
                    onChange={(e) => setDraft((d) => ({ ...d, key: e.target.value }))} />
                </div>
                <div className="sa-field" style={{ marginBottom: 0, flex: '1 1 320px' }}>
                  <label htmlFor="sa-flag-desc">What it does</label>
                  <input id="sa-flag-desc" className="sa-input" value={draft.description}
                    placeholder="Who reads this in six months, and what will they need to know?"
                    onChange={(e) => setDraft((d) => ({ ...d, description: e.target.value }))} />
                </div>
                <button className="sa-btn primary-inline" disabled={Boolean(keyProblem) || busyKey === '+'}
                  onClick={create}>
                  {busyKey === '+' ? 'Creating…' : 'Create'}
                </button>
              </div>
              <p className="sa-muted" style={{ fontSize: 12.5, marginTop: 10 }}>
                {keyProblem || 'Created switched off. Turn it on, target boutiques or set a rollout below.'}
              </p>
            </div>

            <Table
              columns={columns(data.boutiques)}
              rows={data.flags}
              keyFor={(f) => f.key}
              empty={<Empty icon={<Flag size={22} />} title="No feature flags yet."
                detail="Create one above. The code asks for a flag by key; a key nothing asks for does nothing." />}
            />
          </>
        )}
      </Async>

      <Confirm
        open={Boolean(pending)}
        busy={busyKey === pending?.key}
        danger
        requireReason
        title={pending ? `Delete the flag "${pending.key}"?` : ''}
        confirmLabel="Delete flag"
        body={pending && (
          <>
            <p>
              The switch itself goes. Any code asking for <strong>{pending.key}</strong> falls back
              to its own default — off — for every boutique
              {pending.enabled_for?.length
                ? `, including the ${pending.enabled_for.length} it is targeted at`
                : ''}.
            </p>
            <p style={{ marginTop: 8 }}>
              There is no undo. Recreating it starts from off, with no targets and no rollout.
            </p>
            {pending.enabled && (
              <p style={{ marginTop: 8 }}>
                <Pill value="warning" label="Currently on for everyone" />
              </p>
            )}
          </>
        )}
        onCancel={() => setPending(null)}
        onConfirm={async (reason) => {
          await run(pending.key, () => consoleApi.deleteFlag(pending.key, reason),
                    `Flag "${pending.key}" deleted.`);
          setPending(null);
        }}
      />
    </>
  );
}
