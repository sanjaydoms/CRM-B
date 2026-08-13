/**
 * Which parts of the product each boutique is allowed to reach.
 *
 * The grid is the screen: boutiques down, gateable modules across, the switch in
 * the cell. These are server gates -- tenants/middleware.py refuses the request
 * -- not hidden menu items, so the confirmation names the URL prefixes that stop
 * answering rather than saying "this feature".
 *
 * Everything comes in one request and is filtered in the browser because
 * /modules/ returns the registry plus every tenant row and offers no filters:
 * there is nothing to push to the server. Same honesty as Boutiques.jsx, and the
 * same ceiling -- past a few hundred boutiques this endpoint needs paging first.
 *
 * What is NOT switchable is rendered underneath from the same response rather
 * than left out. "Why is Orders not in the list" is the first question anyone
 * asks, and core/modules.py already answers it; this screen quotes it.
 */

import { useCallback, useMemo, useState } from 'react';
import { Info, Lock, MonitorSmartphone, PackageSearch, ShieldCheck } from 'lucide-react';

import { consoleApi } from '../api';
import { Async, Confirm, Empty, Pill, SearchBox, SectionHead, useApi, useToast } from '../ui';

/**
 * core/modules.py is_enabled(), to the letter.
 *
 * An absent key is ON: a tenant row written before a module existed has no
 * opinion about it, and reading "no opinion" as "off" would switch a new module
 * off for every existing boutique at deploy time. A non-dict value is also ON --
 * the column is a JSONField editable by hand in the Django admin, and the server
 * degrades a malformed one to "no opinion" rather than 500ing. If this screen
 * drew it as OFF it would be lying about what the middleware will do.
 */
function isEnabled(map, key) {
  if (!map || typeof map !== 'object' || Array.isArray(map)) return true;
  if (Object.keys(map).length === 0) return true;
  return map[key] !== false;
}

// Twelve columns on a laptop, so the boutique name pins to the left instead of
// scrolling out of sight and leaving a row of anonymous switches. Same problem
// .sa-sticky-end fixes for the action column on Boutiques, other edge.
const PINNED = { position: 'sticky', left: 0, background: 'var(--surface-color)', zIndex: 1 };

export default function Modules() {
  const toast = useToast();
  const [term, setTerm] = useState('');
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  // schema -> the map the server stored. The PATCH response is authoritative and
  // merged server-side, so it replaces the fetched row without a second request.
  const [stored, setStored] = useState({});

  const state = useApi(useCallback(() => consoleApi.modules(), []));

  const rows = useMemo(() => {
    if (!state.data) return [];
    const needle = term.trim().toLowerCase();
    const list = [...state.data.boutiques].sort((a, b) => a.name.localeCompare(b.name));
    if (!needle) return list;
    return list.filter((b) => `${b.name} ${b.schema_name}`.toLowerCase().includes(needle));
  }, [state.data, term]);

  const apply = async (reason) => {
    const { boutique, module, next } = pending;
    setBusy(true);
    try {
      const result = await consoleApi.setModules(
        boutique.schema_name, { [module.key]: next }, reason);
      setStored((map) => ({ ...map, [boutique.schema_name]: result.enabled_modules }));
      // Kept on the page rather than only in a toast. The five-minute lag is the
      // part someone has to act on -- it is the difference between "it worked"
      // and "it worked in the worker that answered me" -- and a toast is gone
      // before they have finished reading the grid.
      setNote([`${module.label} is now ${next ? 'on' : 'off'} for ${boutique.name}.`,
               result.note].filter(Boolean).join(' '));
      toast('Saved.');
    } catch (e) {
      toast(e.message, 'off');
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  return (
    <>
      <Async
        state={state}
        isEmpty={(d) => d.boutiques.length === 0}
        empty={<Empty icon={<PackageSearch size={22} />} title="No boutiques to configure."
          detail="Modules are set per boutique, and none have signed up yet." />}
      >
        {(data) => (
          <>
            <SectionHead
              title="Modules"
              subtitle="Enforced by the server on every request. A switch that is not set is on: a boutique nobody has edited has the whole product."
            >
              <SearchBox value={term} onChange={setTerm} placeholder="Boutique name or schema…" />
            </SectionHead>

            {note && <div className="sa-note info">{note}</div>}

            {rows.length === 0 ? (
              <Empty title="No boutique matches that search." detail="Clear the search to see them all." />
            ) : (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th style={PINNED}>Boutique</th>
                      {data.modules.map((m) => (
                        <th key={m.key} title={m.description}>
                          {m.label}
                          <div className="sa-schema">{m.prefixes.join(' ')}</div>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((b) => {
                      const map = stored[b.schema_name] ?? b.enabled_modules;
                      return (
                        <tr key={b.schema_name}>
                          <td style={PINNED}>
                            <div className="sa-name">{b.name}</div>
                            <div className="sa-schema">{b.schema_name}</div>
                            {/* A suspended boutique reaches nothing at all, so its
                                switches are still worth setting but not worth
                                reading as live. */}
                            {!b.is_active && <Pill value="suspended" />}
                          </td>
                          {data.modules.map((m) => {
                            const on = isEnabled(map, m.key);
                            return (
                              <td key={m.key}>
                                <button
                                  className={`sa-btn${on ? '' : ' danger'}`}
                                  aria-pressed={on}
                                  aria-label={`${m.label} for ${b.name}: ${on ? 'on' : 'off'}`}
                                  onClick={() => setPending({ boutique: b, module: m, next: !on })}
                                >
                                  {on ? 'On' : 'Off'}
                                </button>
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <div style={{ marginTop: 32 }}>
              <SectionHead
                title="Cannot be switched off"
                subtitle="These carry several product concerns on one URL prefix. A gate would take the others with it, so there is no switch to offer."
              />
              <div className="sa-cards">
                {data.structural.map((s) => (
                  <div key={s.key} className="sa-card">
                    <h4><Lock size={14} /> {s.label}</h4>
                    {/* Verbatim from the server. Paraphrasing a reason is how a
                        console and its middleware start disagreeing. */}
                    <p>{s.reason}</p>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ marginTop: 32 }}>
              <SectionHead
                title="No server-side switch"
                subtitle="Browser-only surfaces. A toggle here would hide a menu item and a curl would walk straight past it — which reads as a security control and is not one."
              />
              <div className="sa-cards">
                {data.client_only.map((c) => (
                  <div key={c.key} className="sa-card">
                    <h4><MonitorSmartphone size={14} /> {c.key.replace(/_/g, ' ')}</h4>
                    <p>{c.reason}</p>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ marginTop: 32 }}>
              <SectionHead title="Always on"
                subtitle="Never gateable, whatever is stored against a boutique." />
              <div className="sa-card">
                <h4><ShieldCheck size={14} /> Authentication, settings, the dashboard and this console</h4>
                <p>
                  Login shares the <code>/api/</code> mount with the business routers, so a rule
                  keyed on it would lock every boutique out of its own account with no way back
                  in — and a console that can lock itself out is a console that will.
                </p>
                <p className="sa-schema" style={{ marginTop: 10 }}>
                  {data.always_on.join('   ')}
                </p>
              </div>
            </div>
          </>
        )}
      </Async>

      <Confirm
        open={Boolean(pending)}
        busy={busy}
        danger={pending ? !pending.next : false}
        requireReason
        title={pending
          ? `Switch ${pending.module.label} ${pending.next ? 'on' : 'off'} for ${pending.boutique.name}?`
          : ''}
        confirmLabel={pending && pending.next ? 'Switch on' : 'Switch off'}
        body={pending && (pending.next ? (
          <>
            <p>
              <strong>{pending.boutique.name}</strong> can reach{' '}
              <span className="sa-schema">{pending.module.prefixes.join(' ')}</span> again.
            </p>
            <p style={{ marginTop: 8 }}>{pending.module.description}</p>
          </>
        ) : (
          <>
            <p>
              Every request from <strong>{pending.boutique.name}</strong> to{' '}
              <span className="sa-schema">{pending.module.prefixes.join(' ')}</span> is refused
              by the server until you switch it back on.
            </p>
            <p style={{ marginTop: 8 }}>
              {pending.module.description} Their screens that call those URLs will fail rather
              than disappear. Nothing is deleted, and switching it back on restores it.
            </p>
            <p style={{ marginTop: 8 }}>
              <Info size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
              Other server workers apply this within 5 minutes.
            </p>
          </>
        ))}
        onCancel={() => setPending(null)}
        onConfirm={apply}
      />
    </>
  );
}
