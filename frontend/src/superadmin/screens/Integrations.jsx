/**
 * Every seam between this product and something outside it.
 *
 * Most of these rows are permanently grey, and that is the finding rather than a
 * gap in the screen. Payments, SMS and background jobs do not exist anywhere in
 * this codebase; customer messaging is a wa.me link the boutique owner taps on
 * their own phone, which is a product decision (CUSTOMER_MESSAGE_BACKEND is
 * unset on purpose) and not a broken API client. `not_configured` is grey in
 * ui.jsx TONES for exactly this reason: a red light here sends somebody hunting
 * a bug that does not exist, and a green one claims a capability the product
 * does not have.
 *
 * No credential value is displayed, and none is requested. /config/ returns
 * `credentials` as booleans -- presence, never the secret -- and an operations
 * console that prints an API key is a credential store with a login page in
 * front of it.
 *
 * There is no test-connection endpoint and no Test button. Every check in
 * superadmin/health.py is deliberately side-effect free: a health page that
 * sends a test message becomes a page people are afraid to open.
 */

import { useCallback } from 'react';
import { Lock, Plug } from 'lucide-react';

import { consoleApi } from '../api';
import { Async, Pill, SectionHead, useApi } from '../ui';

/**
 * The seams, in the order an administrator would ask about them.
 *
 * `check` names a row in /health/; `credential` names a boolean in
 * /config/ credentials. Pinterest and Google have a credential but no health
 * check -- nothing in superadmin/health.py probes them -- so their status is
 * derived below from the provider code instead of invented.
 */
const SEAMS = [
  { key: 'email', label: 'Outbound email', check: 'email', credential: 'email_host',
    credentialLabel: 'EMAIL_HOST' },
  { key: 'supabase_storage', label: 'Supabase storage', check: 'supabase_storage',
    credential: 'supabase', credentialLabel: 'SUPABASE_URL + SUPABASE_KEY' },
  { key: 'whatsapp', label: 'Customer messaging (WhatsApp)', check: 'whatsapp',
    credential: 'customer_message_backend', credentialLabel: 'CUSTOMER_MESSAGE_BACKEND' },
  { key: 'payments', label: 'Payments', check: 'payments', credential: null },
  { key: 'sms', label: 'SMS', check: 'sms', credential: null },
  { key: 'background_jobs', label: 'Background jobs', check: 'background_jobs', credential: null },
  { key: 'design_studio_pinterest', label: 'Design Studio — Pinterest', check: null,
    credential: 'design_studio_pinterest', credentialLabel: 'DESIGN_STUDIO_PINTEREST_TOKEN' },
  { key: 'design_studio_google', label: 'Design Studio — Google Images', check: null,
    credential: 'design_studio_google', credentialLabel: 'DESIGN_STUDIO_GOOGLE_API_KEY' },
];

/**
 * The two design-studio providers, which /health/ does not check.
 *
 * Read off apps/design_studio/providers/external.py rather than guessed: both
 * subclass _CredentialGatedProvider, which reports `available()` from the
 * credential alone and whose `search()` raises NotImplementedError the moment it
 * is called with one set. So a credential here does NOT mean the seam works --
 * it means the gallery will stop skipping a provider that then raises.
 */
function providerStatus(configured) {
  if (!configured) {
    return ['not_configured', 'No credential set. The provider reports itself unavailable and '
      + 'Design Studio search skips it, so the gallery shows it as not connected. Nothing is broken.'];
  }
  return ['warning', 'A credential IS set, and that is the problem: '
    + '_CredentialGatedProvider.search() in apps/design_studio/providers/external.py raises '
    + 'NotImplementedError once available() is true. No client was ever written. Unset the '
    + 'credential to return the provider to its dormant state.'];
}

export default function Integrations() {
  const state = useApi(useCallback(
    () => Promise.all([consoleApi.health(), consoleApi.config()])
      .then(([health, config]) => ({ health, config })),
    [],
  ));

  return (
    <>
      <SectionHead
        title="Integrations"
        subtitle="One row per seam with something outside this process. Statuses are read from the health checks, which never touch a live service — there is no test-connection endpoint, and adding a Test button that does nothing would be worse than not having one."
      />

      <Async state={state}>
        {({ health, config }) => {
          const checks = Object.fromEntries((health.checks || []).map((c) => [c.key, c]));
          const credentials = config.credentials || {};

          return (
            <>
              <div className="sa-note info">
                <Lock size={13} style={{ verticalAlign: '-2px', marginRight: 6 }} />
                The server sends whether a credential is present, never its value. Nothing on this
                page can reveal a secret, and nothing here asks for one.
              </div>

              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th>Seam</th>
                      <th>Status</th>
                      <th>Credential</th>
                      <th>What this actually is</th>
                    </tr>
                  </thead>
                  <tbody>
                    {SEAMS.map((seam) => {
                      const check = seam.check ? checks[seam.check] : null;
                      const configured = seam.credential
                        ? Boolean(credentials[seam.credential]) : null;
                      const [status, detail] = check
                        ? [check.status, check.detail]
                        : providerStatus(configured);

                      return (
                        <tr key={seam.key}>
                          <td>
                            <div className="sa-name">{seam.label}</div>
                            {!seam.check && (
                              <div className="sa-schema">no health check</div>
                            )}
                          </td>
                          <td><Pill value={status} /></td>
                          <td>
                            {configured === null ? (
                              <span className="sa-muted">none to set</span>
                            ) : (
                              <>
                                <Pill value={configured ? 'active' : 'not_configured'}
                                  label={configured ? 'Present' : 'Absent'} />
                                <div className="sa-schema">{seam.credentialLabel}</div>
                              </>
                            )}
                          </td>
                          <td style={{ maxWidth: 560, whiteSpace: 'normal', fontSize: 13.5 }}>
                            {detail}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="sa-cards" style={{ marginTop: 22 }}>
                <div className="sa-card">
                  <h4><Plug size={14} /> Why so much grey</h4>
                  <p>
                    Grey is <em>not configured</em>, and for most of these rows it is permanent by
                    design rather than pending. Payments, SMS and background jobs have no
                    implementation anywhere in this codebase — an order&apos;s <code>amount_paid</code> is
                    what staff typed, and every operation runs inside the request that asked for it.
                    Colouring those red would invent an outage.
                  </p>
                </div>
                <div className="sa-card">
                  <h4>Environment</h4>
                  <dl className="sa-kv">
                    <dt>DEBUG</dt>
                    <dd>{String(config.environment?.debug)}</dd>
                    <dt>Time zone</dt>
                    <dd>{config.environment?.time_zone}</dd>
                    <dt>Tracking base URL</dt>
                    <dd className="sa-schema">{config.environment?.tracking_base_url}</dd>
                    <dt>WhatsApp country code</dt>
                    <dd>{config.environment?.whatsapp_country_code}</dd>
                  </dl>
                </div>
              </div>
            </>
          );
        }}
      </Async>
    </>
  );
}
