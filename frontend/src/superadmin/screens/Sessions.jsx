/**
 * Security > Sessions & Tokens.
 *
 * The same accounts the Users screen lists, asked a different question: who can
 * reach the API right now. Three facts about this product decide the whole
 * shape of the screen, and all three are worth saying out loud rather than
 * designing around.
 *
 * DRF tokens do not expire. rest_framework.authtoken has no TTL and nothing
 * here rotates one, so a key issued at sign-up is still valid today and will
 * still be valid next year.
 *
 * There are no sessions. django.contrib.auth.login() is never called anywhere
 * in this codebase, so there is nothing to time out, no "signed in 20 minutes
 * ago", and no login history at all -- last_login is NULL for every account on
 * the platform (superadmin/users.py returns `last_login_tracked: false`).
 *
 * So deleting the token row is the only real sign-out this product has, and
 * Revoke below is that delete. It is also the only lever here: there is nothing
 * to show about *when* a token was used, because nothing records it.
 *
 * The API has no has_token filter -- it is computed per row inside each
 * boutique's schema -- so "live token only" narrows the page that was loaded
 * rather than the platform. The page is the server's maximum for that reason,
 * and the screen says so whenever more than one page exists.
 */

import { useCallback, useMemo, useState } from 'react';
import { KeyRound } from 'lucide-react';

import { consoleApi } from '../api';
import {
  Async, Confirm, Empty, Pager, Pill, SearchBox, SectionHead, Select, Stat, Table,
  count, useApi, useToast,
} from '../ui';

// MAX_PAGE_SIZE in superadmin/users.py. The token flag is filtered here, so a
// bigger page is a truer answer; the server clamps anything larger anyway.
const PAGE_SIZE = 200;

export default function Sessions({ route }) {
  const toast = useToast();
  const [filters, setFilters] = useState({ q: '', boutique: '' });
  const [tokenOnly, setTokenOnly] = useState('token');
  const [page, setPage] = useState(1);
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);

  const set = (key) => (value) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };

  const state = useApi(
    useCallback(() => consoleApi.users({ ...filters, page, page_size: PAGE_SIZE }),
                [filters, page]),
    [filters, page],
  );

  // Only for the boutique filter. A failure costs the dropdown, not the screen.
  const overview = useApi(useCallback(() => consoleApi.overview(), []));

  const boutiques = useMemo(() => [
    { value: '', label: 'All boutiques' },
    ...(overview.data?.boutiques || []).map((b) => ({ value: b.schema_name, label: b.name })),
  ], [overview.data]);

  const revoke = async (reason) => {
    setBusy(true);
    try {
      const result = await consoleApi.userAction(pending.boutique, pending.username, 'revoke', reason);
      toast(result.message);
      state.reload();
    } catch (e) {
      // The server answers a refusal with HTTP 400 and a sentence. Show the
      // sentence.
      toast(e.message, 'off');
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  const columns = [
    {
      key: 'who',
      label: 'Account',
      render: (u) => {
        const name = [u.first_name, u.last_name].filter(Boolean).join(' ');
        return (
          <>
            <div className="sa-name">{name || u.username}</div>
            <div className="sa-schema">{u.username}</div>
          </>
        );
      },
    },
    {
      key: 'boutique',
      label: 'Boutique',
      render: (u) => (
        <>
          <button className="sa-link" onClick={() => route.go(`boutiques/${u.boutique}`)}>
            {u.boutique_name}
          </button>
          <div className="sa-schema">{u.boutique}</div>
        </>
      ),
    },
    { key: 'role', label: 'Role', render: (u) => u.role || <span className="sa-muted">—</span> },
    {
      key: 'token',
      label: 'API token',
      render: (u) => (
        <Pill value="token" tone={u.has_token ? 'ok' : 'muted'}
          label={u.has_token ? 'Live, no expiry' : 'None'} />
      ),
    },
    {
      key: 'state',
      label: 'Account state',
      render: (u) => (
        <Pill value={u.is_active ? 'active' : 'disabled'}
          label={u.is_active ? 'Active' : 'Deactivated'} />
      ),
    },
    {
      key: 'act',
      label: '',
      render: (u) => (
        <button className="sa-btn danger" disabled={!u.has_token}
          title={u.has_token ? undefined : 'This account holds no token, so there is nothing to revoke.'}
          onClick={() => setPending(u)}>
          <KeyRound size={13} /> Revoke
        </button>
      ),
    },
  ];

  return (
    <>
      <SectionHead
        title="Sessions & tokens"
        subtitle="Who currently holds a key to the API."
      >
        <SearchBox value={filters.q} onChange={set('q')} placeholder="Name, username or email…" />
        <Select value={filters.boutique} onChange={set('boutique')} label="Boutique"
          options={boutiques} />
        <Select value={tokenOnly} onChange={setTokenOnly} label="Token" options={[
          { value: 'token', label: 'Has a live token' },
          { value: 'all', label: 'Every account' },
        ]} />
      </SectionHead>

      <div className="sa-note info">
        This product issues DRF tokens and nothing else. They never expire, there is no
        session timeout, and no sign-in is recorded anywhere — so there is no “last active”
        to show and no way to tell a key in use from a key sitting in an old browser.
        Deleting the token is the only sign-out that exists here. It does not lock the
        account: the person can sign in again immediately and get a new key. Deactivate,
        on the Users screen, is what locks an account.
      </div>

      {overview.error && (
        <div className="sa-note info">
          The boutique list did not load, so that filter only offers “All boutiques”.
        </div>
      )}

      <Async
        state={state}
        isEmpty={(d) => d.users.length === 0 && d.unreadable.length === 0}
        empty={<Empty icon={<KeyRound size={22} />} title="No accounts to show."
          detail="Tokens appear here once boutiques have staff who can sign in." />}
      >
        {(data) => {
          const holders = data.users.filter((u) => u.has_token);
          const stranded = holders.filter((u) => !u.is_active).length;
          const rows = tokenOnly === 'token' ? holders : data.users;
          // With one page, the loaded set IS the platform. With more, every
          // figure below counts only what was fetched, and says so.
          const scope = data.pages > 1 ? 'On this page' : 'Platform-wide';

          return (
            <>
              {data.unreadable.length > 0 && (
                <div className="sa-note error">
                  {data.unreadable.length} boutique schema(s) could not be read, so anyone
                  holding a token there is missing from this screen: {data.unreadable.join(', ')}.
                </div>
              )}

              <div className="sa-stats">
                <Stat label="Live tokens" value={count(holders.length)} note={scope} />
                <Stat label="Accounts" value={count(data.users.length)}
                  note={data.pages > 1 ? `Page ${data.page} of ${data.pages}` : 'Every account'} />
                <Stat label="Held by deactivated accounts" value={count(stranded)}
                  tone={stranded > 0 ? 'warn' : undefined}
                  note="Refused while deactivated, live again the moment they are reactivated" />
              </div>

              {tokenOnly === 'token' && data.pages > 1 && (
                <div className="sa-note info">
                  The API has no token filter, so “has a live token” narrows the {PAGE_SIZE}
                  {' '}accounts on this page — not the {count(data.count)} on the platform.
                  Step through the pages, or pick one boutique, to see all of them.
                </div>
              )}

              <Table
                columns={columns}
                rows={rows}
                keyFor={(u) => `${u.boutique}/${u.username}`}
                empty={<Empty title="Nobody here holds a live token."
                  detail="Either nobody has signed in, or every key has already been revoked." />}
              />

              <Pager page={data.page} pages={data.pages} onPage={setPage} total={data.count} />
            </>
          );
        }}
      </Async>

      <Confirm
        open={Boolean(pending)}
        danger
        requireReason
        busy={busy}
        title={pending && `Revoke ${pending.username}'s token?`}
        body={pending && (
          <>
            <p style={{ marginBottom: 8 }}>
              <strong>{pending.username}</strong> at {pending.boutique_name}
              {pending.role && ` · ${pending.role}`}
            </p>
            Their key stops working on the next request, on every device it is stored on.
            They can sign in again straight away and be issued a new one — this is a
            sign-out, not a lock. Deactivate them on the Users screen if they should not
            be able to get back in.
          </>
        )}
        confirmLabel="Revoke"
        onCancel={() => setPending(null)}
        onConfirm={revoke}
      />
    </>
  );
}
