/**
 * Platform configuration: the rows this console can write, the environment it
 * cannot, and whether a credential exists.
 *
 * The three sections are deliberately different shapes because they are three
 * different kinds of thing. Settings are rows in a table and a click changes
 * them. The environment is settings.py, read back so nobody has to guess -- it
 * changes by deploy, not by click, so there is nothing to edit here. Credentials
 * are booleans and only booleans: the API sends presence and never a value, and
 * an operations console that prints an API key is a credential store with a
 * login page in front of it.
 *
 * maintenance_mode is lifted out of the settings table into its own control. It
 * is the one row here that takes the whole platform down, and editing it as raw
 * JSON in a list of five would let someone do that without being told.
 */

import { useCallback, useState } from 'react';
import { Info, Lock, Power, Server } from 'lucide-react';

import { consoleApi } from '../api';
import { Async, Confirm, Empty, Pill, SectionHead, Table, moment, useApi, useToast } from '../ui';

const MAINTENANCE = 'maintenance_mode';

/**
 * The middleware's reading of the stored value, not a friendlier one.
 *
 * tenants/middleware.py switches on `isinstance(value, dict) and value['enabled']`
 * -- anything else is off. If this screen were more generous than that it would
 * show a lock that is not there.
 */
function maintenanceOf(settings) {
  const raw = settings.find((s) => s.key === MAINTENANCE)?.value;
  const value = raw && typeof raw === 'object' && !Array.isArray(raw) ? raw : {};
  return {
    on: Boolean(value.enabled),
    message: typeof value.message === 'string' ? value.message : '',
  };
}

export default function Config() {
  const toast = useToast();
  const [draft, setDraft] = useState(null); // null = show whatever is stored
  const [edits, setEdits] = useState({});
  const [asking, setAsking] = useState(false);
  const [busy, setBusy] = useState(null);
  const [note, setNote] = useState('');

  const state = useApi(useCallback(() => consoleApi.config(), []));

  const write = async (key, value, reason, said) => {
    setBusy(key);
    try {
      const result = await consoleApi.setConfig(key, value, reason);
      // The lag is kept on the page rather than in a toast. Turning maintenance
      // OFF is the direction that matters: each worker caches this for five
      // minutes, so some traffic keeps getting 503 after the console has said
      // "saved" -- and somebody watching a dashboard needs to know that is
      // expected rather than raise a second incident.
      setNote([said, result?.note].filter(Boolean).join(' '));
      toast('Saved.');
      state.reload();
      return true;
    } catch (e) {
      toast(e.message, 'off');
      return false;
    } finally {
      setBusy(null);
    }
  };

  const saveSetting = async (setting) => {
    let value;
    try {
      value = JSON.parse(edits[setting.key]);
    } catch {
      // Not sent. A setting saved as the string "false" instead of the boolean
      // is the kind of thing that is found weeks later.
      toast('That is not valid JSON — text has to be inside double quotes.', 'off');
      return;
    }
    if (await write(setting.key, value, '', `${setting.key} saved.`)) {
      setEdits((all) => {
        const next = { ...all };
        delete next[setting.key];
        return next;
      });
    }
  };

  return (
    <>
      <Async state={state}>
        {(data) => {
          const stored = maintenanceOf(data.settings);
          const message = draft ?? stored.message;
          const rows = data.settings.filter((s) => s.key !== MAINTENANCE);
          const env = data.environment || {};

          return (
            <>
              {stored.on && (
                <div className="sa-note error">
                  <strong>Maintenance mode is on.</strong> Every boutique is being refused with a
                  503. This console, sign-in and the Django admin stay reachable — that exemption
                  is the only reason it can be switched off from here.
                </div>
              )}
              {note && <div className="sa-note info">{note}</div>}

              <SectionHead title="Maintenance mode"
                subtitle="Platform-wide. Refuses every boutique request until it is switched off." />

              <div className="sa-card" style={{ marginBottom: 32 }}>
                <h4>
                  <Power size={14} />
                  <Pill value={stored.on ? 'critical' : 'healthy'}
                    label={stored.on ? 'Locked down' : 'Serving normally'} />
                </h4>

                <div className="sa-field" style={{ marginTop: 14, marginBottom: 10 }}>
                  <label htmlFor="sa-maint-message">Message every boutique sees</label>
                  <textarea id="sa-maint-message" className="sa-textarea" value={message}
                    placeholder="Back at 03:00 UTC. Nothing has been lost."
                    disabled={busy === MAINTENANCE}
                    onChange={(e) => setDraft(e.target.value)} />
                </div>

                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                  {stored.on ? (
                    <button className="sa-btn" disabled={busy === MAINTENANCE}
                      onClick={() => write(MAINTENANCE, { enabled: false, message: message.trim() },
                        '', 'Maintenance mode is off. Boutiques are being let back in.')}>
                      <Power size={13} /> Turn maintenance off
                    </button>
                  ) : (
                    <button className="sa-btn danger" disabled={busy === MAINTENANCE}
                      onClick={() => setAsking(true)}>
                      <Power size={13} /> Turn maintenance on
                    </button>
                  )}
                  <button className="sa-btn"
                    disabled={message === stored.message || busy === MAINTENANCE}
                    onClick={() => write(MAINTENANCE, { enabled: stored.on, message: message.trim() },
                      '', 'Maintenance message saved.')}>
                    Save message
                  </button>
                  <span className="sa-muted" style={{ fontSize: 12.5 }}>
                    {message === stored.message
                      ? 'The message is saved. Editing it enables the button.'
                      : 'Unsaved message.'}
                  </span>
                </div>
              </div>

              <SectionHead title="Platform settings"
                subtitle="Rows in the database, read by the application. Values are JSON — text goes in double quotes." />

              <Table
                columns={[
                  {
                    key: 'key',
                    label: 'Setting',
                    render: (s) => (
                      <>
                        <div className="sa-name">{s.key}</div>
                        {s.description && <div className="sa-owner">{s.description}</div>}
                      </>
                    ),
                  },
                  {
                    key: 'value',
                    label: 'Value',
                    render: (s) => (
                      <textarea className="sa-textarea" style={{ minWidth: 260 }}
                        aria-label={`Value of ${s.key}`} disabled={busy === s.key}
                        value={edits[s.key] ?? JSON.stringify(s.value ?? null)}
                        onChange={(e) => setEdits((all) => ({ ...all, [s.key]: e.target.value }))} />
                    ),
                  },
                  {
                    key: 'updated',
                    label: 'Last change',
                    render: (s) => (
                      <>
                        <div>{s.updated_by || <span className="sa-muted">unknown</span>}</div>
                        <div className="sa-schema">{moment(s.updated_at)}</div>
                      </>
                    ),
                  },
                  {
                    key: 'save',
                    label: '',
                    render: (s) => (
                      <button className="sa-btn"
                        disabled={edits[s.key] === undefined || busy === s.key}
                        onClick={() => saveSetting(s)}>
                        {busy === s.key ? 'Saving…' : 'Save'}
                      </button>
                    ),
                  },
                ]}
                rows={rows}
                keyFor={(s) => s.key}
                empty={<Empty title="No platform settings have been written yet."
                  detail="Rows appear here once something writes one. The application reads settings.py for anything it needs at import time — those are below, and they are not editable from a console." />}
              />

              <div style={{ marginTop: 32 }}>
                <SectionHead title="Environment"
                  subtitle="Read back from settings.py. Changing any of these is a deploy, not a click." />
                <div className="sa-card">
                  <dl className="sa-kv">
                    <dt>DEBUG</dt>
                    <dd>
                      <Pill value={env.debug ? 'warning' : 'healthy'} label={env.debug ? 'on' : 'off'} />
                      {env.debug && (
                        <span className="sa-muted" style={{ marginLeft: 8, fontSize: 12.5 }}>
                          Stack traces go back to whoever triggered the error.
                        </span>
                      )}
                    </dd>
                    <dt>Allowed hosts</dt>
                    <dd className="sa-schema">{(env.allowed_hosts || []).join(', ') || '—'}</dd>
                    <dt>Time zone</dt>
                    <dd>{env.time_zone || '—'}</dd>
                    <dt>Tracking base URL</dt>
                    <dd className="sa-schema">{env.tracking_base_url || '—'}</dd>
                    <dt>WhatsApp country code</dt>
                    <dd>{env.whatsapp_country_code || '—'}</dd>
                  </dl>
                </div>
              </div>

              <div style={{ marginTop: 32 }}>
                <SectionHead title="Credentials"
                  subtitle="Whether each one is set, and nothing else. The API sends a boolean — no endpoint here returns a key, and none should be asked to." />
                <div className="sa-cards">
                  {Object.entries(data.credentials || {}).map(([key, present]) => (
                    <div key={key} className="sa-card">
                      <h4 style={{ textTransform: 'capitalize' }}>
                        {present ? <Lock size={14} /> : <Server size={14} />}
                        {key.replace(/_/g, ' ')}
                      </h4>
                      {/* not_configured is grey. Several of these are absent by
                          design, and a red light would send someone hunting a
                          bug that does not exist. */}
                      <Pill value={present ? 'ok' : 'not_configured'}
                        label={present ? 'configured' : 'not configured'} />
                    </div>
                  ))}
                </div>
                <p className="sa-muted" style={{ fontSize: 12.5, marginTop: 10 }}>
                  <Info size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                  Values are never displayed here because they are never sent here. Set them in the
                  deployment environment.
                </p>
              </div>
            </>
          );
        }}
      </Async>

      <Confirm
        open={asking}
        busy={busy === MAINTENANCE}
        danger
        requireReason
        title="Turn maintenance mode on?"
        confirmLabel="Lock every boutique out"
        body={(
          <>
            <p>
              Every boutique request is refused with a 503 until you turn this back off. Staff
              cannot sign in to their workspace, the mobile app stops, and the public order
              tracking page stops with it.
            </p>
            <p style={{ marginTop: 8 }}>
              This console stays reachable, and so do sign-in and the Django admin — that is what
              lets you switch it off again from here.
            </p>
            <p style={{ marginTop: 8 }}>
              <Info size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
              Other server workers apply this within 5 minutes, in both directions.
            </p>
          </>
        )}
        onCancel={() => setAsking(false)}
        onConfirm={async (reason) => {
          const stored = maintenanceOf(state.data?.settings || []);
          await write(MAINTENANCE, { enabled: true, message: (draft ?? stored.message).trim() },
                      reason, 'Maintenance mode is ON. Every boutique is locked out.');
          setAsking(false);
        }}
      />
    </>
  );
}
