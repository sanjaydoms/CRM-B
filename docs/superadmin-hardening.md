
Companion to `docs/superadmin-handoff.md`, which described the build. This
describes what was found wrong with it, what was changed, and what is still
outstanding. Every finding below was **measured**, not inferred; where something
could not be verified it says so.

Baseline before this work: **994 tests passing** (the handoff document's "725"
was already stale). After: **1018**, same suite, no test removed or weakened.

---


| # | Severity | Finding | Status |
|---|---|---|---|
| 1 | **P0** | Suspension and module gating were served from a per-worker cache, so a boutique the database said was switched off kept being answered `200` for up to 300s | Fixed |
| 2 | **P0** | The ghost-schema fallthrough closed for the console was still open on the product's own request path — a tenant row with no Postgres schema could be bound to the connection | Fixed |
| 3 | **P0** | The generic data browser read every row of every table in every boutique and wrote **no** audit entry | Fixed |
| 4 | **P0** | Field masking was a denylist of credential-shaped names, so it protected only against names somebody had already thought of | Fixed |
| 5 | **P1** | `console.login` / `console.login_failed` were in the audit vocabulary and were never written by any code | Fixed |
| 6 | **P1** | A successful sign-in recorded an **empty actor** (found while fixing #5 — `request.user` is anonymous during login) | Fixed |
| 7 | **P1** | Feature flags were an operational-looking control wired to nothing | Withdrawn from the UI |
| 8 | **P2** | On a phone the console's navigation occupied ~1200px above every screen's content | Fixed |
| — | — | Console login rate limiting | **Verified working**, not a defect |
| — | — | Cross-schema rewrite of a password-reset payload | **Verified refused**, not a defect |


**Root cause.** `tenants/middleware.py` cached the whole `BoutiqueTenant`
object for 300s per worker, and the suspension check read `is_active` off that
cached copy. `clear_tenant_cache()` clears only the process that calls it, and
gunicorn runs two workers.

**Evidence.** Warm one worker's cache, commit `is_active=False` from another
connection, repeat the identical request:

```
[PROBE] authenticated request before suspension: 200
[PROBE] is_active in the database now: False
[PROBE] same request AFTER suspension is committed: 200   <-- defect
[PROBE] disabled module on a stale worker: 200 (403 = enforced)
```

**Fix.** `is_active` and `enabled_modules` are now read from the database on
every tenant request (`_control_state`). Identity stays cached; authority does
not. A deleted registry row now fails closed rather than being served from cache.

**Measured cost.** Warm steady state is **2 queries per tenant request** — the
`SET search_path` that was always there, plus one indexed two-column
`SELECT`. The schema-existence check is cached after first use per schema per
process.

**Verified after the fix**, against a live server on the real dev database:

```
GET /api/dashboard/ (X-Tenant-ID)   -> 401   (tenant resolves, auth required)
POST .../suspend/                   -> 200
GET /api/dashboard/                 -> 403 "This boutique's access has been suspended."
POST .../reactivate/                -> 200
GET /api/dashboard/                 -> 401   (allowed through again)
```

No cache was cleared between those calls, and reactivation is symmetric.


**Root cause.** `SET search_path = 'ghost', public` does not fail — Postgres
skips the missing entry. `auth` and `authtoken` are in `SHARED_APPS`, so
`auth_user` and `authtoken_token` exist in `public`, and every query "inside" a
missing tenant silently resolves there. `superadmin/schemas.py` closed this for
the console. The middleware — the single place a boutique becomes the
connection's schema — did not.

**Evidence.** With one ghost tenant row present:

```
GET /api/auth/me/  with the PLATFORM CONSOLE's own token and no X-Tenant-ID
  -> 200, tenant_id = "probe_ghost2"
```

The platform administrator was admitted as a boutique user of a boutique that
does not exist. The middleware's token scan had walked into the ghost, where
`authtoken_token` resolves to `public`, so the *first ghost in the registry
matches any token on the platform*. A boutique login with the platform
account's credentials likewise authenticated against the public `auth_user` and
only failed afterwards, by luck, on a tenant-only table.

**Fix.** The middleware skips schemas that do not exist during the token scan,
and refuses (`503`) rather than binding a tenant whose schema is absent. Because
this is the one chokepoint, the guard covers reads and writes across orders,
inventory, design, production, scheduling and customers at once.


**Root cause.** `SupportView` recorded a `data.view` entry; `BoutiqueDataView`
recorded nothing, while returning strictly more.

**Evidence.** Two requests returning a customer's name and phone number, `0`
audit rows before and `0` after.

**Fix.** Every access writes an entry — the table index, a page of rows, and a
refused request are recorded as distinct access types, with actor, boutique,
model, page, row counts, IP and user-agent. A search term is recorded (bounded
to 120 characters) because *what was being looked for* is the substance of the
access; nothing else from the query string is stored.

**Verified in the browser** against the real dev database: browsing
`owner_tryon2buy_com` produced audit rows `datasets` and
`activities.universalactivity`, actor `verify@harden.test`, IP `127.0.0.1`.


**Evidence.** The denylist caught `password`, `api_key`, `auth_token`. It let
through, untouched:

```
gateway_credential  webhook_signing  otp_seed  recovery_code  session_key  pat
```

**Fix.** `ALLOWED_FIELDS` in `superadmin/datasets.py` — an allowlist of models
*and* of the fields of each, seeded from the 52 models present today. A model
not named is not browsable; a field not named is **masked, not hidden**, so the
console still tells an administrator that a column exists. The denylist is kept
underneath as a second layer. Masked columns are also excluded from search, so
`?q=` cannot become an oracle for a value the console refuses to print.

**The maintenance contract is deliberate:** a column added tomorrow is masked
until someone reviews it. Nothing breaks in the meantime — no test fails, no
request errors, the boutique's own product is untouched.

**Consequence, stated plainly:** a developer who adds a model or field and wants
it visible in the console must add it to `ALLOWED_FIELDS`. That is the cost of
the property being bought, and it is the reverse of the old default, which
published first and reviewed later if anyone noticed.

---


| File | Change |
|---|---|
| `tenants/middleware.py` | Authoritative `is_active`/`enabled_modules`; ghost-schema guard on bind and on the token scan; `TenantGone` fails closed |
| `superadmin/datasets.py` | `ALLOWED_FIELDS` allowlist; model- and field-level fail-closed; masked columns unsearchable |
| `superadmin/views.py` | Data-browser auditing; `console.login` / `console.login_failed` / `console.logout` |
| `superadmin/audit.py` | Optional verified `actor` override, for the sign-in case only |
| `superadmin/models.py` | `console.logout` action; `FeatureFlag` marked unused infrastructure |
| `superadmin/migrations/0003_alter_auditlog_action.py` | Choices-only `AlterField`. **Public schema only** — `superadmin` is `SHARED_APPS`, so no tenant migration |
| `superadmin/test_hardening.py` | **New.** 24 regression tests |
| `frontend/src/superadmin/nav.js`, `SuperAdmin.jsx` | Feature Flags withdrawn from navigation and routing |
| `frontend/src/superadmin/superadmin.css` | Mobile navigation becomes a horizontal strip |

Nothing outside the Super Admin and tenant-boundary surface was touched. No
existing API contract, URL, tenant migration or boutique workflow was changed.

---


**No deletion has been implemented, and none should be until the questions below
have owners' answers.** A silent destructive cleanup on an audit trail is worse
than an unbounded one.

**Measured growth.** `AuditLog` gains one row per console mutation, per data
browser access, and per sign-in attempt. On this deployment — four boutiques,
one or two administrators — that is realistically **tens of rows per day**,
dominated by data-browser reads now that they are recorded. At 100 rows/day a
row is roughly 400 bytes, so **~15 MB/year**. `ErrorEvent` is bounded by the
number of *distinct bugs*, not crashes (it upserts on fingerprint), so it grows
in the hundreds of rows, not millions.

**Conclusion: neither table is a capacity problem at this scale, and the
retention question is legal/organisational rather than technical.** What must be
decided before any cleanup exists:

1. How long must administrative access to customer data be reviewable? This is a
   data-protection question about somebody else's customers, not a disk question.
2. Must deletion itself be audited, and by whom?
3. Is archival (export then delete) required, or is retention indefinite
   acceptable given the size above?

**Recommendation.** Keep both tables indefinitely for now — 15 MB/year is far
cheaper than an unrecoverable gap in an access trail. Revisit if the console
gains many more administrators. If a cleanup is ever built it must: run as an
explicit management command, never on import; refuse to delete anything younger
than the agreed retention period; and write its own `AuditLog` entry recording
what it removed.

**Still true and unenforced by the database:** `AuditLog` is append-only by API
and convention. Postgres would permit an `UPDATE` from a psql session. The
`REVOKE` is in the README and is a deployment step, not a migration.

---


No frontend monitoring was invented. The correct extension point, documented so
the next person does not have to find it:

- The React `ErrorBoundary` in `frontend/src/superadmin/SuperAdmin.jsx` (and the
  boutique app's own) is where a client crash is already caught and
  `console.error`'d. That is the call site.
- The server side needs **a new authenticated endpoint** that accepts a
  fingerprintable payload (message, component stack, route) and funnels it into
  `core/exceptions._record`'s upsert. It must not reuse
  `got_request_exception`, which is for server exceptions only.
- Two things must be settled before it is built: the endpoint is
  unauthenticated-adjacent and needs its own rate limit, and a browser stack
  trace can carry user-entered text, so the payload needs the same "never the
  request body" rule `ErrorEvent` already follows.

This is a separate, controlled task. It was not started.

---


Deployment is gunicorn, `WEB_CONCURRENCY=2`, `GUNICORN_THREADS=4`,
`CONN_MAX_AGE=60`, no shared cache configured (`LocMemCache`).

| State | Cached? | Stale for | Security? | Availability? | Acceptable |
|---|---|---|---|---|---|
| Tenant **suspension** | **No — authoritative** | — | Was: yes | — | **Fixed** |
| Tenant **module switches** | **No — authoritative** | — | Was: yes | — | **Fixed** |
| Tenant identity (name, timezone) | Yes, 300s/worker | ≤300s | No | Cosmetic | Yes |
| Schema existence | Positive-only, per process | Until restart | See below | — | Yes, with caveat |
| **Maintenance mode** | Yes, 300s/worker | ≤300s | **No** | **Yes** | Yes, documented |
| Login throttle counters | `LocMemCache`, per worker | — | Partly | — | Documented |
| Audit writes | Not cached | — | — | — | Yes |

**Maintenance mode is deliberately still cached.** It is a platform-wide
availability switch read on every request including those that resolve no
tenant; paying a query per request for a row that is false essentially always
buys nothing security-relevant. The residual defect is unchanged and is
availability-only: **turning maintenance OFF is the bad direction** — roughly
half of traffic keeps receiving `503` for up to 300s after an administrator has
been told it worked. Remedy if it ever matters: a shared cache, or read the row
per request.

**Schema-presence cache is positive-only.** A schema dropped behind a running
worker's back stays cached as present until restart. This is the correct
direction — a *newly created* boutique is never invisible — and the failure it
would allow (entering a schema dropped mid-process) requires someone to drop a
live tenant schema, which is a deliberate operator action. `superadmin.schemas.
forget()` exists for that path and is called by the test helpers; **it is not
called anywhere in production code**, because nothing in production drops a
schema.

**Login throttle is per worker**, so the real ceiling is `WEB_CONCURRENCY ×
20/hour` = 40/hour per address. That is a speed bump against online guessing,
not a lockout. Making it exact needs a shared cache.

---


Warm timings against the real dev database, 8 boutiques, local Postgres:

| Path | Time | Shape |
|---|---|---|
| `/audit/` | 15 ms | Indexed, bounded — **not** O(tenants) |
| `/errors/` | 30 ms | Indexed, bounded |
| `/users/` | 50 ms | **O(tenants)** |
| `/overview/` | 56 ms | **O(tenants)** |
| `/orders/` | 70 ms | **O(tenants)** |
| `/health/` | 84 ms | **O(tenants)** |
| `/search/?q=` | 96 ms | **O(tenants)**, capped and short-circuits |
| `/boutiques/<s>/data/` | 115 ms | ~50 `COUNT`s in one schema |
| `/onboarding/` | 129 ms | **O(tenants)** |
| `/boutiques/` | 143 ms | **O(tenants)** |

**No rollup table was introduced.** At 8 boutiques the slowest console page is
143 ms, which does not justify a denormalised public-schema cache and the
staleness that comes with it. The documented upgrade path — a rollup refreshed
on a schedule — remains correct and remains unbuilt. Revisit at ~50 boutiques,
where these become 1–2 s.

---


Everything above was verified against a **local Postgres dev database with 8
boutiques**, not production. The handoff document's statement still stands: the
console has never run against the production database, and the Supabase
connection-pooler issue that blocked it is outside this work.

Before production use, in this order:

1. Apply `superadmin.0003_alter_auditlog_action` — **public schema only**
   (`migrate_schemas --shared`). Confirmed locally to touch no tenant schema.
2. Confirm `/health/` reports migrations up to date and *N of N* boutique
   schemas readable. (Locally: 8 of 8.)
3. Read-only checks first: `/overview/`, `/users/`, `/onboarding/`, `/audit/`.
4. Then the one reversible control action: suspend a boutique **you own for
   testing**, confirm `403` within one request from *both* workers, reactivate,
   confirm restored. Do not test suspension on a real customer.
5. Confirm a data-browser read produces an audit row with the right actor and IP
   behind the real proxy — `X-Forwarded-For` handling takes the **last** entry,
   which is correct for Render and must be re-confirmed on any other proxy.
6. Confirm no boutique workflow changed: sign in as an owner, a tailor and a
   designer and walk an order through.

**Do not claim production readiness until 1–6 have been done and recorded.**

---


**Blockers.**

- Production verification (§7) has not been performed. This is the only item
  that blocks calling the console production-ready.

**Limitations, unchanged and accepted.**

- Maintenance mode remains eventually consistent (availability only, ≤300s).
- Login throttling is per worker (40/hour effective across two workers).
- `AuditLog` append-only is not enforced by the database.
- `ILIKE` search is unindexed; `pg_trgm` is the upgrade, not a search service.
- Search per-type caps fill in tenant order.
- `estimated_delivery` largely measures dates the system invented; the API
  returns a caveat string and the UI renders it.
- No frontend error telemetry (§4 above documents the extension point).
- No 2FA. Adding it needs an authentication redesign and is a separate phase.
- No token expiry — revoking the row is still the only sign-out.
- Seven onboarding signals remain untracked, deliberately. They are shown as
  "not tracked" rather than counted as incomplete.
- Feature flags remain unused infrastructure with the UI withdrawn.

**Recommended future work, in priority order.**

1. Production verification (§7).
2. A shared cache (the deployment already needs one for the throttle to be
   exact); it also fixes maintenance mode's bad direction.
3. Frontend error telemetry as a controlled task (§4).
4. 2FA for the platform console, as its own phase.
5. Revisit rollups only when the tenant count reaches ~50 (§6).
