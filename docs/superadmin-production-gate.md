# Super Admin — final security & production-readiness gate

Third pass over the platform control plane. The first built it, the second
hardened it, this one tried to break it before letting it near production.

**Status: READY FOR CONTROLLED PRODUCTION VERIFICATION** — see §9 for what that
means and what is still required.

Two **P0** defects were found and fixed here. Both were measured end to end
before being touched, and both were in surfaces the previous pass had not
examined because it was looking at the console rather than at everything the
console's guarantees depend on.

---

## 1. Environment and baseline

| | |
|---|---|
| Branch | `MSK-CL` |
| Commit at start | `337a1fe97f3428e69db792e906c018658bd32539` |
| Working tree at start | previous hardening pass, uncommitted |
| Database | local PostgreSQL `boutique_crm`, 8 boutiques, 39 staff accounts, 26 orders |
| Deployment config exercised | gunicorn `-c gunicorn.conf.py`, 2 workers × 4 gthread threads, `CONN_MAX_AGE=60` |
| Tests before | **1018 passing** |
| Tests after | **1035 passing, 0 failing** (+17; none removed, none weakened) |

---

## 2. P0 — Django admin was a complete platform escalation

**What was wrong.** The public-schema pin covered `/api/superadmin/` only
(`SUPERADMIN_PREFIX`). `/admin/` appeared only in `ALWAYS_ON`, which is a
maintenance-mode exemption, not a schema pin. So `/admin/` went through full
tenant resolution.

That matters because of how the app lists are arranged:

* `tenants` and `superadmin` are **SHARED_APPS only**, so `tenants_boutiquetenant`
  and `superadmin_auditlog` exist only in `public` — but a tenant search_path is
  `'<tenant>', public`, so they still resolve from inside a boutique.
* `django.contrib.auth` is in **both** lists, so `auth_user` resolves to the
  **boutique's** table.

Send `X-Tenant-ID: <your own boutique>` to `/admin/login/`, authenticate as your
own boutique's superuser — an account `seed_data.py` creates and any boutique can
hold — and Django's admin then administers the *platform*. `IsPlatformAdmin`
never runs, because `/admin/` is not a DRF view.

**Measured, before the fix:**

```
POST /admin/login/            (X-Tenant-ID: gate_adm_a)  -> 302  logged in
GET  /admin/tenants/boutiquetenant/                      -> 200
     sees ANOTHER boutique in the registry:  True
GET  /admin/superadmin/auditlog/                         -> 200  platform audit trail
POST suspend action on a different boutique              -> 302
     another boutique still active:          False   <-- suspended it
```

**Fix.** `PUBLIC_ONLY_PREFIXES = ('/api/superadmin/', '/admin/')` in
`tenants/middleware.py`. The admin now authenticates against `public.auth_user`,
so only a real platform administrator can sign in.

**Measured, after:** boutique superuser cannot authenticate (`200` = login form
re-rendered), registry not visible, suspend action inert, and the legitimate
platform administrator still signs in (`302`) and reads the registry (`200`).

**Accepted consequence, stated plainly.** The ModelAdmins in `crm_api/admin.py`
cover *tenant* models, whose tables do not exist in `public`, so those admin
pages stop working. They were only ever reachable by binding a tenant to
`/admin/` — which is the escalation above — and were already broken for the
platform administrator. Boutique data is edited in the boutique's own workspace,
where its business rules run, and read in the console's data browser.

---

## 3. P0 — the platform administrator's password could be reset through a boutique flow

**What was wrong.** `crm_api.auth_views.find_tenants_for_account` walks every
registry row looking for an account, entering each schema with a bare
`schema_context`. Inside a schema that does not exist, that scan reads `public`,
where the platform administrator lives.

**Measured, before the fix** — with one registry row whose schema was absent:

```
POST /api/auth/password-reset/   {"email": "platform@gate.test"}   -> 200
  emails sent: 1   recipient: ['platform@gate.test']
  reset payload schema segment: gate_ghost_pw
POST /api/auth/password-reset/confirm/  {token: <that payload>}    -> 200
  platform administrator password OVERWRITTEN: True
```

The token validates because the *same* misresolution happens on both halves: the
token is minted for the public administrator and later checked against that same
account. The link is mailed to the administrator's own address, so this is not a
one-step remote takeover — but the platform account, which no boutique-scoped
flow should be able to name, was reachable, resettable, and reachable
**unauthenticated**. With no `EMAIL_HOST` configured the backend is the console
backend, so on such a deployment the link is printed to the service log.

**Fix — at the shared boundary, not the call site.** Three separate paths
resolved their own tenant and never passed the middleware's guard: login,
password reset, and the public order-tracking page. Patching them individually
would have left the fourth one and every one written afterwards.

`connection.set_tenant()` is the single function they all end in — `schema_context`
calls `set_schema` which calls `set_tenant`; `tenant_context` calls `set_tenant`.
django-tenants publishes `EXTRA_SET_TENANT_METHOD_PATH` as the supported hook
into exactly that function. `tenants/schema_guard.py` refuses to point the
connection at a schema that is not there, and `boutique_crm/settings.py` wires it
in. One hook covers every schema switch in the application, including code that
does not exist yet.

`TenantHeaderMiddleware.process_exception` turns the refusal into a clean `503`
rather than a 500 with a traceback.

**Measured, after:**

```
password reset for the platform admin   -> 503,  emails sent: 0
password-reset confirm, forged schema   -> refused, password unchanged
boutique login via a ghost schema       -> 503,  no raw SQL in the body
public /track/<token>/ via a ghost      -> 503
data browser into a ghost boutique      -> 502,  no platform accounts rendered
writes across all 8 modules into a ghost-> 503 each; platform admin untouched
```

**Two details that mattered.** `schema_exists()` previously queried
`information_schema.schemata`, which per Postgres' documentation lists only
schemas *owned by a currently enabled role*. As a console read that was
harmless; as a global gate it would refuse every tenant on a deployment whose
app role does not own the schemas — an outage. It now delegates to
django-tenants' own `pg_catalog.pg_namespace` check. And schema *creation* is
safe because `TenantMixin.create_schema` issues `CREATE SCHEMA` **before**
migrating into it (verified by test: creating a boutique and writing to it still
works).

---

## 4. Other findings fixed

| Severity | Finding | Fix |
|---|---|---|
| P1 | Data browser entered tenants with raw `schema_context`, so a ghost schema rendered **platform administrator accounts as that boutique's staff**, and wrote an audit row naming the wrong boutique | Covered by the global guard (now 502) |
| P1 | Related-object cells rendered `str(related)`, which answers to no allowlist — `Customer.__str__` is `'Ann B (9000000999)'`, so the **Order** table printed a customer's mobile number | `str()` only for models the allowlist has approved; otherwise `verbose_name #pk` |
| P2 | Login and signup returned the raw exception to **unauthenticated** callers (`relation "crm_api_tailor" does not exist`) | Logged, not returned |
| P2 | Boutique suspension via the Django admin wrote **no** audit row and no admin LogEntry — the one action that can suspend every boutique at once was untraceable | `audit.record` per affected boutique |
| P2 | Global search returned cross-boutique customer PII (`?q=<phone>`) with no audit row | Recorded as `data.view` / `search` |
| P2 | Users directory swept every boutique's staff with no audit row | Recorded as `data.view` / `user_directory` |

**Verified NOT defects** (checked, and left alone): cross-tenant tokens are
refused; a platform token cannot read a boutique; boutique superusers are refused
everywhere under `/api/superadmin/`; the console pin holds when a tenant header
is sent; console login throttling works; suspension already held under the
previous pass's fix.

---

## 5. Data browser review (§3)

`ALLOWED_FIELDS` covers **52 models**. Every model is a boutique-data model from
`TENANT_APPS`; no shared/platform model is reachable. Field categories present
and deliberately allowed, because support work needs them: identity, contact PII
(`crm_api.customer` — name, mobile, email, address), body measurements
(`measurement`, `measurementhistory`), order financials (`order` — prices,
discount, `amount_paid`), free-text notes, uploaded-file paths, and boutique
configuration.

Properties verified by reading code and by test:

| Property | State |
|---|---|
| Read-only (no write path in the module) | VERIFIED |
| Model allowlist, fail-closed for unknown models | VERIFIED |
| Field allowlist, fail-closed for unknown fields (masked, not hidden) | VERIFIED |
| Paginated with a hard cap (`MAX_PAGE_SIZE = 500`) | VERIFIED |
| Tenant-scoped, and now schema-guarded | VERIFIED |
| Audited on every access, including refusals | VERIFIED |
| No arbitrary SQL (ORM only, field names never interpolated) | VERIFIED |
| Cannot return credentials (`authtoken.Token` excluded wholesale) | VERIFIED |
| Masked columns are not searchable (no search oracle) | VERIFIED |
| Related-object rendering respects the allowlist | **FIXED THIS PASS** |

Regression test `test_an_unreviewed_credential_shaped_field_is_masked` proves the
names a denylist would have missed are masked without explicit approval:
`gateway_credential`, `webhook_signing`, `otp_seed`, `recovery_code`,
`session_key`, `pat`, `shared_salt`, `device_fingerprint`, `sso_assertion` — plus
the old denylist still underneath for `password`, `api_key`, `auth_token`,
`client_secret`.

**Residual, accepted:** JSON columns (`universalactivity.new_value`,
`order.workflow_config`-shaped fields) cannot be governed field-by-field; and
image columns render `/media/` URLs, which are `ALWAYS_ON` and unauthenticated,
so anyone holding the URL can fetch the file. Both are documented rather than
fixed — the second is a property of how media is served, not of the console.

---

## 6. Audit logging (§4, §5, §6)

**Coverage.** Every state-changing console operation writes a row: suspension,
reactivation, module changes, user activate/deactivate, token revocation,
password reset, lead updates, flag changes, setting changes, error
acknowledge/resolve, console login / logout / failed login, support access,
data-browser access (index, rows, refusals), **and now** search, the user
directory, and Django-admin suspension.

**Failure behaviour — the deliberate decision.** `audit.record()` catches every
exception and returns `None`, so a privileged action succeeds even if its audit
row fails; the failure is logged at ERROR with a traceback.

I considered transactionally coupling the critical set (suspension, reactivation,
privilege changes, password reset, token revocation, configuration) and **decided
against it**, for a reason that survives scrutiny: coupling means an audit-table
outage blocks you from suspending a boutique that is actively being abused. The
control plane's job in an incident is to be able to act. The classification is:

* **Critical security operations** — suspension, reactivation, user
  activate/deactivate, token revocation, password reset, configuration changes.
  These proceed on audit failure, and the failure is logged at ERROR with the
  action, target and boutique. Accepted, with the mitigation below.
* **Operational telemetry** — data-browser reads, search, user directory,
  dashboard reads. These proceed on audit failure. No question.

Mitigation for the critical set, and the honest gap: an audit write failing is
currently visible only in the service log. The right upgrade is a health check
that asserts the audit table is writable, surfaced on the console's own health
page, so "the trail stopped recording" becomes a red row rather than a log line
nobody reads. **Not built this pass.**

**Immutability — measured, not assumed.**

```
app role: sanjaykumar   auditlog owner: sanjaykumar
grants: DELETE, INSERT, REFERENCES, SELECT, TRIGGER, TRUNCATE, UPDATE
can UPDATE audit rows: True   can DELETE audit rows: True
protective triggers present: 0
1. app role can rewrite an audit row today: True
```

Append-only is enforced by the API (no write route) and by the Django admin
(`has_add_permission`/`has_delete_permission` false, every field read-only) — but
**not** by the database. `REVOKE` alone cannot fix this because the app role owns
the table. A `BEFORE UPDATE OR DELETE` trigger can, and I tested it:

```
UPDATE blocked even for the table OWNER -> superadmin_auditlog is append-only
DELETE blocked even for the table OWNER -> superadmin_auditlog is append-only
INSERT still works
```

**Not shipped as a migration, deliberately.** Two reasons: 17 places in the test
suite delete audit rows, so it would break the suite; and the retention policy
below is undecided, so hard-blocking DELETE before anyone has decided whether old
rows are ever removed would paint the deployment into a corner. The real control
is a least-privilege application role (INSERT/SELECT only on this table), which
is an infrastructure decision. The tested SQL is above; run it as a deployment
step if the trigger is wanted in the interim.

**Retention.** Measured growth: `AuditLog` gains a row per console mutation, per
data-browser access, and per sign-in attempt — realistically tens per day at this
scale, dominated by reads now that reads are recorded. At 100 rows/day and ~400
bytes/row that is **~15 MB/year**. `ErrorEvent` upserts on fingerprint, so it
grows with distinct bugs, not crashes — hundreds of rows.

Neither is a capacity problem. **No automatic deletion has been implemented and
none should be until a retention owner exists**, because the question is legal,
not technical: how long must administrative access to another business's customer
data stay reviewable? Recommendation: keep both indefinitely for now; 15 MB/year
is far cheaper than an unrecoverable gap in an access trail. If a cleanup is ever
built it must run as an explicit management command, refuse to delete anything
inside the agreed window, and write its own audit row recording what it removed.

---

## 7. Authentication (§7)

| Control | State | Classification |
|---|---|---|
| Console login rate limiting | Works — refused at the 21st wrong password of a 20/hour budget; shares its scope with the boutique login so alternating doors buys nothing | Launch |
| Failed-login recording | `console.login_failed` written, attempted username in `target`, actor left blank (nobody authenticated) | Launch |
| Login/logout recording | `console.login` / `console.logout` with a verified actor | Launch |
| Token revocation | Deleting the `authtoken` row is real and immediate | Launch |
| **Token expiry** | **None.** DRF tokens never expire | **Controlled risk** |
| **Concurrent sessions** | Not tracked; one token per user, reissued on login | **Controlled risk** |
| Login history | Only what `AuditLog` now records; `User.last_login` is never written by this product and the console says "not tracked" rather than "never" | Controlled risk |
| Password reset | Tenant-bound, and as of this pass cannot resolve the platform account | Launch |
| **2FA** | **Absent, and no scaffolding** | **P1, future phase** |

**Must block production:** nothing in this list.
**Can launch with controlled risk:** no token expiry, no concurrent-session
visibility, no login history beyond the audit trail.
**Future hardening:** 2FA for the platform console. It is a genuine P1 — this is
the account that can read and suspend every boutique — but it needs an
authentication redesign (there is no session framework in use for the API, and
`django.contrib.auth.login()` is never called anywhere), so it must be its own
phase rather than an edit inside this gate.

---

## 8. Everything else verified

**Module control (§9).** Registry unchanged. Verified: normal URL, `.json`
format suffix, missing trailing slash, nested endpoints, `inventory` vs
`inventory_catalog` longest-prefix, ALWAYS_ON routes, `/api/auth/`,
`/api/dashboard/`, `/api/superadmin/`, `/admin/`. With **every** module disabled
a boutique still reaches authentication and its dashboard. Multi-worker: a module
switch reached all workers immediately (24/24 concurrent requests refused).

**Privilege boundary (§10).** The URLconf-walking test is kept and still passes.
Anonymous, ordinary public users, and a boutique's own superuser are refused
everywhere under `/api/superadmin/`; `is_superuser` alone is insufficient, the
account must be in the public schema. Verified live: a boutique superuser got
`401` on overview, users, boutiques and audit.

**User administration (§11).** Boutique owner cannot be deactivated (matched on
both `email` and `username`, so an owner with a blank email is still protected);
the platform administrator cannot be touched through a tenant-scoped operation
(`_tenant()` excludes public, and the schema guard now makes the ghost route
impossible); duplicate usernames across tenants stay isolated; password reset
refuses an address that resolves to two boutiques; token revocation is scoped
inside `tenant_scope`. Every mutation writes an audit row.
**Gap, not fixed:** there is no "last platform administrator" guard — the console
has no route that deactivates a *public* user, so the case is unreachable through
the console today, but nothing structurally prevents a future route from adding
it. Noted as P2.

**Monitoring honesty (§12).** Reviewed every metric. Authoritative: boutique
counts, staff, customers, orders, booked revenue, collected revenue, unreadable
schemas, error counts, audit counts. Derived: open orders, onboarding percentage,
status distributions. Estimated, and labelled: overdue orders (the API returns a
caveat string because `estimated_delivery` defaults to `order_date + 15 days`).
Unavailable and shown as such: uptime, API latency, request volume, background
jobs, payments, WhatsApp/Try-On, billing/subscriptions, `last_login`. The health
page groups six integrations under *"Not configured — by design"* with the line
"Absent from this product on purpose. Grey, not red: there is nothing here to
fix." No fabricated metric was found.

**Performance (§13), measured on the real database, 8 boutiques, warm:**

| Endpoint | Time | Queries | Schema switches |
|---|---|---|---|
| `/audit/` | 5 ms | 6 | 3 |
| `/errors/` | 5 ms | 10 | 5 |
| data browser rows | — | 12 | 5 |
| `/boutiques/` | 38 ms | 84 | 34 |
| `/users/` | 43 ms | 56 | 19 |
| `/orders/` | 48 ms | 116 | 50 |
| `/search/?q=` | 52 ms | 78 | 30 |
| `/overview/` | 57 ms | 88 | 36 |
| `/health/` | 61 ms | 113 | 49 |
| data browser index | 69 ms | 110 | 54 |
| `/onboarding/` | **159 ms** | **196** | **98** |

`audit`, `errors` and data-browser rows are bounded — not O(tenants). The rest
are O(tenants) at roughly **12 schema switches per boutique** on the worst page.
**No rollup table was introduced.** Documented threshold: comfortable to ~25
boutiques (worst page under 500 ms); at 50 boutiques onboarding reaches ~1 s and
~1,200 queries; past that the documented upgrade — a public-schema rollup
refreshed on a schedule — becomes necessary. Revisit at 50.

Cost of the suspension guard: **+1 indexed two-column SELECT per tenant request**
(warm steady state is 2 queries: the `SET search_path` that was always there,
plus the control-state read).

**Multi-worker (§14), real gunicorn, 2 workers × 4 threads, authenticated, 24
concurrent requests per probe:**

```
before suspend      24/24 -> 200
after suspend       24/24 -> 403     (no cache cleared, every worker)
after reactivate    24/24 -> 200
module disabled     24/24 -> 403
```

No security authorization decision relies on stale process-local state.
Still per-worker and documented as such: tenant *identity* (≤300 s, cosmetic),
maintenance mode (≤300 s, availability only — turning it **off** is the bad
direction), login-throttle counters (LocMemCache, so the real ceiling is
`WEB_CONCURRENCY × rate` = 40/hour), and the positive-only schema-presence cache.

**Mobile and accessibility (§15).** Measured page overflow across all 15 console
screens at **320, 375, 390, 414, 768 and 1280 px**. Three real defects found and
fixed:

1. *Sign out was off-screen at 320 px on every screen* — the topbar-right group
   was pinned by `margin-left:auto` and could not wrap within itself.
2. *Nav pills were 300 px each* — they inherit `width:100%` from the 232 px rail,
   which resolved against the new horizontal strip, making 17 items 5,100 px of
   sideways scrolling. Now content-width (113 px), strip halved.
3. *System Health overflowed the page* — `MEDIA_ROOT` is printed as an absolute
   filesystem path with nothing to break at, forcing a card's min-content width
   to 448 px on a 375 px screen, on the very page an administrator opens when
   something is already wrong.

Plus: **the console had no keyboard focus indicator anywhere** — form controls
explicitly set `outline: none` and buttons had nothing, so a keyboard user
tabbing toward Deactivate, Revoke or Suspend could not see what they were about
to press. Added a `:focus-visible` ring with `outline-offset` so it stays legible
on the dark active nav pill.

Final state: **0 px page overflow on all 15 screens at all 6 widths**, tables
scroll inside their own containers, filters and dialogs usable, no console
errors. Desktop layout unchanged.

---

## 9. Production verification (§16, §17) — NOT DONE

**Everything above was verified against a local PostgreSQL database with 8
boutiques and against real gunicorn. None of it has been run against the
production database.** That is the remaining gate, and it cannot be closed from
here: this environment has no production credentials, and the deployment was
previously blocked on an unrelated Supabase connection-pooler issue.

Required before production use, in order:

1. **Backup / rollback.** Take a database snapshot. The only schema change in
   this work is `superadmin.0003_alter_auditlog_action` (a choices-only
   `AlterField`); rollback is `migrate superadmin 0002`.
2. **Migrations.** `migrate_schemas --shared` only. Confirmed locally to touch no
   tenant schema. Then confirm the health page reports migrations up to date and
   *N of N* boutique schemas readable.
3. **Read-only checks first:** overview, boutiques, users, onboarding, health,
   errors, audit, search, orders, configuration, module state, and one
   data-browser page.
4. **Authentication boundary:** confirm a boutique superuser is refused at
   `/api/superadmin/` **and** at `/admin/` with an `X-Tenant-ID` header. This is
   the P0 from §2 and must be re-confirmed against production data.
5. **One reversible mutation, on a boutique you control** — never a real
   customer's: suspend it, confirm `403` from more than one worker, reactivate,
   confirm recovery, and confirm all four audit rows exist with the right actor
   and IP.
6. **Proxy check:** confirm `_client_ip` records the real client behind the
   production proxy. It takes the **last** `X-Forwarded-For` entry, which is
   correct for Render and must be re-verified on any other proxy.
7. **No test account may remain.** The temporary verification administrator used
   in this pass was created on the local database only and has been removed.

---

## 10. Remaining risks

**P0:** none known.

**P1**
* No 2FA on the platform console. Needs its own authentication phase.
* Audit-write failure is visible only in the service log; no health check asserts
  the audit table is writable.

**P2**
* `AuditLog` append-only is not enforced by the database (tested SQL in §6; the
  real fix is a least-privilege app role).
* No "last platform administrator" guard — unreachable through the console today.
* `order_tracking`'s module switch is evaluated against the hostname-resolved
  tenant rather than the boutique named in the signed token, so that particular
  switch does not gate what it names.
* Media files are served unauthenticated from `/media/`; a data-browser image
  cell hands over a permanent URL, and fetching it is not audited.

**Accepted limitations**
* Maintenance mode is eventually consistent (≤300 s, availability only).
* Login throttling is per worker (40/hour effective across two workers).
* Unindexed `ILIKE` search; `pg_trgm` is the upgrade, not a search service.
* Search per-type caps fill in tenant order.
* `estimated_delivery` largely measures dates the system invented; the caveat
  ships with the number.
* No frontend error telemetry; the extension point is documented.
* No token expiry; revoking the row is the only sign-out.
* Seven onboarding signals remain deliberately untracked.
* Feature flags remain unused infrastructure with the UI withdrawn.
* JSON columns in the data browser cannot be governed field-by-field.
* O(tenants) console pages; revisit at 50 boutiques.

---

## 11. Files changed in this pass

| File | Change |
|---|---|
| `tenants/middleware.py` | `/admin/` pinned to public; `MissingSchema` → 503 via `process_exception` |
| `tenants/schema_guard.py` | **New.** The global schema-existence guard |
| `boutique_crm/settings.py` | `EXTRA_SET_TENANT_METHOD_PATH` wired in |
| `superadmin/schemas.py` | `schema_exists` now ownership-independent (`pg_namespace`) |
| `superadmin/datasets.py` | Related-object cells respect the allowlist |
| `superadmin/api_views.py` | Search and user-directory reads audited |
| `tenants/admin.py` | Bulk suspend/reactivate audited |
| `crm_api/auth_views.py` | Signup and login no longer return raw exceptions |
| `frontend/src/superadmin/superadmin.css` | Mobile nav width, topbar wrap, long-value wrapping, focus rings |
| `superadmin/test_gate.py` | **New.** 17 regression tests |
| `core/test_exceptions.py`, `superadmin/test_audit.py` | 5 tests switched from imaginary schemas to real empty ones — **assertions unchanged** |
