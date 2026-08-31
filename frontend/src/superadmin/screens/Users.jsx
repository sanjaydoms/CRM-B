/**
 * Every account on the platform, and the four things the console can do to one.
 *
 * Filtering and paging are the server's (superadmin/users.py). That list is one
 * queryset per boutique merged into a total order over (schema, username), so
 * re-slicing it in the browser would mean pulling every row of every boutique to
 * draw one page of fifty. Filters go into the query string; `qs()` in api.js
 * drops the empty ones so a cleared filter matches everything rather than
 * nothing.
 *
 * Two facts about this product decide what the table is allowed to say:
 *
 * `last_login` is never written. Nothing in this codebase calls Django's
 * login() -- the API issues DRF tokens instead -- so that column is NULL for
 * every account that has ever existed here. The envelope states it in
 * `last_login_tracked`, and this screen follows the envelope: "not tracked",
 * never "never signed in", which would be a false claim about the whole
 * platform rather than a fact about an account.
 *
 * `has_token` is a boolean and there is no token value beside it. The server
 * sends whether a key exists and never which key (superadmin/users.py:_rows_for)
 * -- otherwise read access to this console would be the ability to act as any
 * user in any boutique.
 */

import { useCallback, useMemo, useState } from 'react';
import { KeyRound, Link2, Mail, Pause, Play, Users as UsersIcon } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Confirm, Empty, OneTimeLink, Pager, Pill, SearchBox, SectionHead, Select,
  day, moment, useApi, useToast,
} from '../ui';

const PAGE_SIZE = 50;

/**
 * The role vocabulary, copied from the server that defines it.
 *
 * `role` is not a column anywhere -- superadmin/users.py resolves it per row
 * from three tables and the registry, and filters the merged list in Python --
 * so there is no endpoint to read the choices from. The list is
 * Tailor.ROLE_CHOICES (crm_api/models.py) plus the two roles that are not
 * Tailor profiles at all: OWNER and DESIGNER in core/roles.py. Keep it in step
 * with those two files; the server matches case-insensitively.
 */
const ROLES = [
  'Owner', 'Designer', 'Master', 'Tailor', 'Measurement Master', 'Pattern Master',
  'Cutting Master', 'Maggam Master', 'Finishing Master', 'Pressing Staff', 'QC Master',
];

/**
 * What each action does, in the words someone needs before confirming it.
 *
 * Every one of them is audited with the typed reason (UserActionView.post), so
 * every one of them asks for a reason -- including the two that are not
 * destructive, because "who reset this person's password and why" is the
 * question the log exists to answer.
 */
const ACTIONS = {
  deactivate: {
    verb: 'Deactivate',
    danger: true,
    body: 'They cannot sign in from anywhere. Their token is left in place — '
      + 'DRF refuses an inactive user at the next request, so the key stops '
      + 'working without being deleted, and starts working again if you '
      + 'reactivate them. A boutique owner cannot be deactivated: the server '
      + 'refuses, because there would be no route back in for them.',
  },
  activate: {
    verb: 'Activate',
    body: 'They can sign in again straight away. Any token they already had '
      + 'starts working again with them.',
  },
  revoke: {
    verb: 'Revoke sessions',
    danger: true,
    body: 'Deletes their API token, which signs them out of every device. They '
      + 'can sign in again a second later and get a fresh key — this ends the '
      + 'current sessions, it does not lock the account. Deactivate does that.',
  },
  'reset-password': {
    verb: 'Send password reset',
    body: 'Sends the boutique\'s own reset email to the address on the account. '
      + 'Their current password keeps working until they use the link.',
  },
  'access-link': {
    verb: 'Get sign-in link',
    body: 'Creates a one-time link that lets them choose their own password, and '
      + 'shows it to you so you can send it however you normally reach them. '
      + 'This is how you hand a boutique its access without anybody having to '
      + 'know a password: you never see one, and neither does the audit log. '
      + 'Their current password, if they have one, keeps working until the link '
      + 'is used. It is also emailed automatically when the platform has a mail '
      + 'server configured and the account has an address.',
  },
};

export default function Users({ route }) {
  const toast = useToast();
  const [filters, setFilters] = useState({ q: '', boutique: '', role: '', status: '' });
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState(null);
  const [issued, setIssued] = useState(null);
  const [busy, setBusy] = useState(false);

  // Any filter change returns to page 1. Page 4 of the old filter is usually
  // past the end of the new one, and an empty table there reads as "no such
  // user" when it means "wrong page".
  const set = (key) => (value) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };

  const state = useApi(
    useCallback(() => consoleApi.users({ ...filters, page, page_size: PAGE_SIZE }),
                [filters, page]),
    [filters, page],
  );

  // Read only for the boutique filter's options. It is deliberately not fed to
  // <Async>: if the overview fails, the console loses one dropdown, not the
  // list of users.
  const overview = useApi(useCallback(() => consoleApi.overview(), []));

  const boutiques = useMemo(() => [
    { value: '', label: 'All boutiques' },
    ...(overview.data?.boutiques || []).map((b) => ({ value: b.schema_name, label: b.name })),
  ], [overview.data]);

  const run = async (reason) => {
    const { user, action } = pending;
    setBusy(true);
    try {
      const result = action === 'access-link'
        ? await consoleApi.accessLink(user.boutique, user.username, reason)
        : await consoleApi.userAction(user.boutique, user.username, action, reason);
      toast(result.message);
      // The link is held in state only long enough to be copied, and only ever
      // here -- never in localStorage, never in the URL. Closing the panel
      // drops it, which is the same lifetime the server gives the token.
      if (action === 'access-link' && result.link) setIssued({ user, ...result });
      state.reload();
    } catch (e) {
      // A refusal arrives as HTTP 400 carrying the server's own sentence --
      // deactivating an owner, resetting a password on an address that resolves
      // to a different boutique. That is an answer to the question, not a
      // fault, so it is shown as written and nothing is retried.
      toast(e.message, 'off');
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  const act = ACTIONS[pending?.action];

  return (
    <>
      <SectionHead
        title="Users"
        subtitle="Staff accounts, read live from every boutique's own schema. This product
                  keeps no sign-in history — nothing writes last_login — so that column says
                  not tracked rather than claiming nobody has ever signed in."
      >
        <SearchBox value={filters.q} onChange={set('q')} placeholder="Name, username or email…" />
        <Select value={filters.boutique} onChange={set('boutique')} label="Boutique"
          options={boutiques} />
        <Select value={filters.role} onChange={set('role')} label="Role" options={[
          { value: '', label: 'All roles' },
          ...ROLES.map((r) => ({ value: r, label: r })),
        ]} />
        <Select value={filters.status} onChange={set('status')} label="Status" options={[
          { value: '', label: 'Active and deactivated' },
          { value: 'active', label: 'Active only' },
          { value: 'inactive', label: 'Deactivated only' },
        ]} />
      </SectionHead>

      {overview.error && (
        <div className="sa-note info">
          The boutique list did not load, so that filter only offers “All boutiques”.
          Everything else on this screen is unaffected.
        </div>
      )}

      <Async
        state={state}
        // Not `users.length === 0` alone: a sweep where every boutique failed
        // returns no users and a full `unreadable` list, and "no accounts yet"
        // would be the wrong answer to that.
        isEmpty={(d) => d.users.length === 0 && d.unreadable.length === 0}
        empty={<Empty icon={<UsersIcon size={22} />} title="No staff accounts anywhere yet."
          detail="Accounts appear here as boutiques sign up and add their team." />}
      >
        {(data) => (
          <>
            {data.unreadable.length > 0 && (
              <div className="sa-note error">
                {data.unreadable.length} boutique schema(s) could not be read, so nobody from
                them is listed or counted below: {data.unreadable.join(', ')}.
              </div>
            )}

            {data.users.length === 0 ? (
              <Empty title="No account matches those filters."
                detail="Clear the search, or widen the boutique, role and status filters." />
            ) : (
              <div className="sa-table-wrap">
                <table className="sa-table">
                  <thead>
                    <tr>
                      <th>Account</th><th>Boutique</th><th>Role</th><th>Status</th>
                      <th>API token</th><th>Joined</th><th>Last sign-in</th>
                      <th className="sa-sticky-end" />
                    </tr>
                  </thead>
                  <tbody>
                    {data.users.map((u) => {
                      const name = [u.first_name, u.last_name].filter(Boolean).join(' ');
                      return (
                        <tr key={`${u.boutique}/${u.username}`}
                          className={u.is_active ? '' : 'sa-suspended'}>
                          <td>
                            <div className="sa-name">{name || u.username}</div>
                            {name && <div className="sa-schema">{u.username}</div>}
                            <div className="sa-owner">{u.email || <span className="sa-muted">no email on file</span>}</div>
                          </td>
                          <td>
                            <button className="sa-link" onClick={() => route.go(`boutiques/${u.boutique}`)}>
                              {u.boutique_name}
                            </button>
                            <div className="sa-schema">{u.boutique}</div>
                          </td>
                          <td>
                            {u.role || <span className="sa-muted">—</span>}
                            {/* Where the role came from. Owner is resolved from the
                                registry, everything else from one of these two. */}
                            {u.tailor_id && <div className="sa-schema">tailor #{u.tailor_id}</div>}
                            {u.designer_id && <div className="sa-schema">designer profile</div>}
                          </td>
                          <td>
                            <Pill value={u.is_active ? 'active' : 'disabled'}
                              label={u.is_active ? 'Active' : 'Deactivated'} />
                          </td>
                          <td>
                            {/* A boolean. There is no key to show and there must
                                not be one -- see the file header. */}
                            <Pill value="token" tone={u.has_token ? 'ok' : 'muted'}
                              label={u.has_token ? 'Live token' : 'None'} />
                          </td>
                          <td style={{ whiteSpace: 'nowrap' }}>{day(u.date_joined) || '—'}</td>
                          <td>
                            {data.last_login_tracked
                              ? (moment(u.last_login) || <span className="sa-muted">—</span>)
                              : <Pill value="not_tracked" label="not tracked" />}
                          </td>
                          {/* Sticky, like Boutiques: this table is wide enough to
                              scroll on a laptop and the actions are the point of it. */}
                          <td className="sa-actions sa-sticky-end">
                            <button className={`sa-btn ${u.is_active ? 'danger' : ''}`}
                              onClick={() => setPending({
                                user: u, action: u.is_active ? 'deactivate' : 'activate',
                              })}>
                              {u.is_active
                                ? <><Pause size={13} /> Deactivate</>
                                : <><Play size={13} /> Activate</>}
                            </button>
                            <button className="sa-btn" style={{ marginLeft: 6 }}
                              disabled={!u.has_token}
                              title={u.has_token ? undefined : 'No live token to revoke.'}
                              onClick={() => setPending({ user: u, action: 'revoke' })}>
                              <KeyRound size={13} /> Revoke
                            </button>
                            {/* The reset view skips inactive users silently, so
                                offering it here would promise an email nobody sends. */}
                            {/* Works with no email address on file and with no
                                mail server, which is why it sits before Reset:
                                it is the one that always has an answer. */}
                            <button className="sa-btn" style={{ marginLeft: 6 }}
                              disabled={!u.is_active}
                              title={u.is_active ? 'Create a one-time link you can send them'
                                : 'Reactivate the account first.'}
                              onClick={() => setPending({ user: u, action: 'access-link' })}>
                              <Link2 size={13} /> Sign-in link
                            </button>
                            <button className="sa-btn" style={{ marginLeft: 6 }}
                              disabled={!u.is_active}
                              title={u.is_active ? undefined
                                : 'Reactivate the account first — password resets skip deactivated users.'}
                              onClick={() => setPending({ user: u, action: 'reset-password' })}>
                              <Mail size={13} /> Reset
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            <Pager page={data.page} pages={data.pages} onPage={setPage} total={data.count} />
          </>
        )}
      </Async>

      {issued && (
        <div className="sa-modal-backdrop" onClick={() => setIssued(null)}>
          <div className="sa-modal" role="dialog" aria-modal="true"
            aria-label="Sign-in link" onClick={(e) => e.stopPropagation()}>
            <h3>Sign-in link for {issued.user.username}</h3>
            <div className="sa-modal-body">
              <p style={{ marginBottom: 10 }}>
                Send this to <strong>{issued.user.username}</strong> at{' '}
                {issued.boutique || issued.user.boutique_name}. Opening it lets them
                set their own password and signs them in.
                {issued.emailed
                  ? ` It has also been emailed to ${issued.email_address}.`
                  : ' The platform has no mail server configured, so it has not been'
                    + ' emailed — you need to deliver it yourself.'}
              </p>
              <OneTimeLink value={issued.link} expiresMinutes={issued.expires_minutes} />
            </div>
            <div className="sa-modal-actions">
              <button className="sa-btn primary-inline" onClick={() => setIssued(null)}>
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      <Confirm
        open={Boolean(pending)}
        danger={act?.danger}
        requireReason
        busy={busy}
        title={pending && `${act.verb}: ${pending.user.username}?`}
        body={pending && (
          <>
            <p style={{ marginBottom: 8 }}>
              <strong>{pending.user.username}</strong> at {pending.user.boutique_name}
              {pending.user.role && ` · ${pending.user.role}`}
            </p>
            {act.body}
          </>
        )}
        confirmLabel={act?.verb}
        onCancel={() => setPending(null)}
        onConfirm={run}
      />
    </>
  );
}
