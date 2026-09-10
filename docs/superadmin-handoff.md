
**Purpose of this document.** It describes a platform-administration console built
into an existing multi-tenant Django + React SaaS, so that a reviewer who has never
seen the codebase can critique it and find the gaps. It is written to be
falsifiable: every claim names the file that backs it, and the "not built" section
is as detailed as the "built" section on purpose.

**What I want from the reviewer.** Attack the design decisions in §4 and §8. Find
the gaps in §7 I have not listed. Tell me which of the accepted limitations in §6
are actually unacceptable. Do not simply agree.

---


A CRM for boutique fashion studios ("Scaleezy" / TryOn2Buy). Django 6 + Django REST
Framework + `django-tenants` + React 19/Vite. Postgres on Supabase, deployed on
Render (API) and Vercel (frontend).

**Multi-tenancy is schema-per-tenant.** Each boutique is one Postgres schema.
There is a `public` schema holding the tenant registry, and one schema per boutique
holding that boutique's customers, orders, inventory, designs and *its own users*.

Two consequences dominate every design decision here:

1. **There is no cross-tenant query.** Postgres will not join across schemas. Any
   platform-wide number is N queries in N schemas, merged in Python.
2. **`django.contrib.auth` is in both `SHARED_APPS` and `TENANT_APPS`.** So
   `auth_user` exists in `public` *and* in every boutique schema. A boutique can
   have its own `is_superuser` row. This is the single most important fact for
   evaluating the security model below.

Scale today: ~4 boutiques, tens of users, hundreds of orders. Design target stated
throughout: honest at tens, documented ceilings past hundreds.

---



| File | Lines | Responsibility |
|---|---|---|
| `api_views.py` | 679 | 16 endpoint classes: users, onboarding, modules, flags, config, health, errors, audit, orders monitor, search, support |
| `views.py` | 289 | Original console: login/me/logout, overview, boutique suspend/reactivate, leads, data browser |
| `onboarding.py` | 398 | Per-boutique onboarding progress from real signals |
| `users.py` | 383 | Cross-schema user listing + deactivate/activate/revoke/reset |
| `metrics.py` | 312 | Per-tenant usage aggregates + platform rollup + operational metrics |
| `health.py` | 273 | 11 health probes |
| `search.py` | 262 | Global search across 6 entity types |
| `models.py` | 239 | `AuditLog`, `ErrorEvent`, `FeatureFlag`, `PlatformSetting` |
| `datasets.py` | 238 | Generic read-only browser over every model in a tenant schema |
| `schemas.py` | 145 | **Safe tenant-schema entry** (see §4.1) |
| `admin.py` | 136 | Django-admin back door for the four models |
| `audit.py` | 132 | `record()` / `recent()` |
| `urls.py` | 109 | Route table |
| `serializers.py` | 68 | Tenant + lead serialization |
| `permissions.py` | 37 | `IsPlatformAdmin` |

Supporting files outside the app:

- `core/modules.py` (258 lines) — the module registry and URL-prefix matcher.
- `core/exceptions.py` (308 lines) — error capture via `got_request_exception`.
- 2 `superadmin` migrations, 2 `tenants` migrations. **All public-schema; zero
  tenant migrations.**


Separate Vite entry (`superadmin.html`), served at `/superadmin`, own bundle
(~120 kB / 31 kB gzipped). 18 screens + shell + a 64-line hash router + a 388-line
shared primitives module + 661 lines of CSS.

Deliberately **not** merged into the boutique workspace (`src/App.jsx`, ~9,000
lines): that app is signed in as a boutique and scoped to one tenant, this one is
signed in as the platform and scoped to all of them. One bundle for both would
make a boutique-role bug into a cross-tenant one.

No component library, no router library, no chart library. Project dependencies
are exactly `react`, `react-dom`, `lucide-react`.


```
POST   /auth/login/                         POST   /auth/logout/       GET /auth/me/
GET    /overview/
GET    /boutiques/                          GET    /boutiques/<schema>/
POST   /boutiques/<schema>/suspend/         POST   /boutiques/<schema>/reactivate/
PATCH  /boutiques/<schema>/modules/
GET    /boutiques/<schema>/data/            GET    /boutiques/<schema>/data/<app.model>/
GET    /users/                              POST   /users/<schema>/<username>/<action>/
GET    /onboarding/                         GET    /onboarding/<schema>/
GET    /modules/
GET    /flags/       POST /flags/           PATCH/DELETE /flags/<key>/
GET    /config/      PUT  /config/
GET    /health/
GET    /errors/      GET  /errors/summary/  PATCH /errors/<id>/
GET    /audit/
GET    /orders/                             GET    /orders/<schema>/
GET    /search/
GET    /support/<schema>/
GET/PATCH /leads/    GET/PATCH /leads/<id>/
```

---


**`AuditLog`** — append-only record of console actions. 15 action types. Fields:
`actor`, `action`, `target`, `boutique`, `before` (JSON), `after` (JSON), `reason`,
`ip`, `user_agent`, `created_at`. Three composite indexes.
*No ForeignKeys, deliberately:* targets are heterogeneous (a schema name, a
username inside another schema, a flag key), two of which are unreachable by FK
from `public`, and an audit row must outlive whatever it describes.

**`ErrorEvent`** — one row per *kind* of unhandled exception, not per crash.
Grouped by `fingerprint` = sha1(exception class + normalised path + last in-project
frame). `count` incremented with `F()`. Carries `boutique` (most recent occurrence
only) **and** `boutiques` (JSON list, capped at 20). Stores in-project traceback
frames only. Never stores request body, headers or tokens.

**`FeatureFlag`** — `enabled`, `enabled_for` (list of schema names),
`rollout_percent` (stable sha1 bucket of `key:schema`, so a boutique in a rollout
stays in it).

**`PlatformSetting`** — key/JSON-value rows. Holds `maintenance_mode`.

Plus two fields on the existing `BoutiqueTenant`: `is_active` (suspension) and
`enabled_modules` (JSON `{module_key: bool}`).

---



`django-tenants` selects a tenant with `SET search_path = '<schema>', public` and
**does not check the schema exists**. Postgres accepts a search_path naming a
missing schema — it silently skips it. Because `auth` and `authtoken` are
`SHARED_APPS`, `auth_user` and `authtoken_token` *do* exist in `public`.

So a `BoutiqueTenant` row whose schema is absent (restored dump, interrupted
signup, `delete(force_drop=False)`) causes every query "inside" that boutique to
resolve against `public`. Confirmed against a live database:

- Searching a ghost boutique for users returned the **platform console's own
  superuser**, labelled as that boutique's staff.
- `set_user_active(ghost, 'admin', False)` would have **deactivated the console
  administrator's own account**.
- Nothing raised. `try/except` ran its happy path.

`tenant_scope(tenant)` checks `information_schema.schemata` (cached, positive
results only) and raises `MissingSchema` rather than entering.
`for_each_tenant(tenants, read)` wraps each boutique in its own **savepoint** —
without one, a failed query inside an enclosing `atomic()` aborts the transaction
and every later statement fails with "current transaction is aborted", turning one
unreadable boutique into a wholly failed request.

*Reviewer: is the positive-only presence cache safe? A schema dropped mid-process
stays cached as present until restart.*


`core/modules.py` maps 11 module keys to the URL prefixes that constitute them.
`TenantHeaderMiddleware.process_request` denies a request whose module is disabled
for that tenant.

Not a DRF permission class, because **21 views declare their own
`permission_classes`** and bypass `RolePermission` entirely — the whole Design
Studio and every `OwnerOnly` inventory endpoint would have stayed open.

Two matching rules, both learned from live bypasses:

- **Canonicalise the path.** DRF's `DefaultRouter` republishes every list route as
  `<name>.<format>`, so `/api/fabrics.json` served a switched-off module.
  `module_for_path` now matches raw *and* canonical form, fail-closed.
- **Longest prefix first**, so disabling `inventory` does not also disable
  `inventory_catalog`.

`ALWAYS_ON` covers `/api/auth/`, `/api/boutique-settings/`, `/api/dashboard/`,
`/api/superadmin/`, `/admin/`, `/media/`, `/demo-request/`. `crm_api` is mounted at
bare `/api/` *alongside login*, so a rule keyed there would permanently lock every
boutique out of its own account.

Registry:
- **Gateable (11):** `design_studio`, `inventory`, `inventory_catalog`,
  `garment_catalog`, `scheduling`, `production_api`, `activities`, `fabrics`,
  `tailors`, `notifications`, `order_tracking`
- **Structural, cannot be gated (2):** `orders` (one prefix carries order CRUD,
  payments, customer messaging, the production workflow and garment images),
  `customers` (carries measurements, design preferences, fabric selection)
- **Client-only, no server surface (3):** `invoices`, `reports`, `try_on`

Absent key means **enabled** — otherwise adding a module to the registry would
switch it off for every existing boutique at deploy time.

*Reviewer: is a URL-prefix registry the right abstraction, or should modules be
declared on the viewsets themselves and collected at startup?*


Checking `is_superuser` alone is insufficient — see §1, point 2. A boutique's own
superuser (and `seed_data.py` creates one) would otherwise read every other
boutique.

`superadmin/test_api_security.py` **walks the URLconf** rather than checking a
hand-written list of endpoints, so a route added later is covered automatically.
On its first run it found a real hole: `DefaultRouter`'s auto-generated
`APIRootView` inherits `DEFAULT_PERMISSION_CLASSES` (= `RolePermission`), and
`resolve_user_role` answers `OWNER` for any authenticated public-schema account —
so the console's own root was readable by any signed-in user. Fixed by switching to
`SimpleRouter`, which removes the view rather than guarding it.


The specification asked for monitoring of systems this product does not have. The
same specification forbade mock data. Where they collide, the screen states what is
missing and what building it would cost.

Verified absent by grep: no Celery/RQ/Huey/django-q/Dramatiq, no cron, no scheduled
management command; no request-timing middleware; no payment gateway (only
`payment_status` / `amount_paid` columns on `Order`); no WhatsApp Business API
(`CUSTOMER_MESSAGE_BACKEND` is unset **by design** — messages are `wa.me` links
composed server-side and sent by hand); no billing or subscription model; no email
verification; no 2FA; no `CACHES`.

`django.contrib.auth.login()` is **never called anywhere** in this product, so
`User.last_login` is NULL for every account. The console renders that as
"not tracked", never as "never signed in".

---


Found by an adversarial review pass over each component, then confirmed against a
live database.

| Severity | Defect | Fix |
|---|---|---|
| **Critical** | Ghost-schema fallthrough to `public` on reads *and writes* (§4.1) | `superadmin/schemas.py` |
| **High** | `/api/fabrics.json` bypassed the module gate | path canonicalisation |
| **High** | `APIRootView` open to any signed-in user | `SimpleRouter` |
| **High** | Onboarding penalised boutiques for steps whose module an admin had disabled | steps carry a module key; disabled ones excluded from the percentage |
| Medium | `except Exception` around a tenant loop with no savepoint → aborted transaction | per-tenant savepoints |
| Medium | Error capture was DRF-only; plain Django views and middleware crashes were invisible | moved to `got_request_exception`, proven exactly-once |
| Medium | `ErrorEvent.boutique` overwritten per occurrence, so a bug hitting 40 boutiques reported only the 40th | added `boutiques` list, capped |
| Medium | `real_designs` onboarding signal counted boutique-created designs as seed data (the serializer stamps `source='catalogue'` on live creates) | step demoted to untracked — no clean signal exists |
| Medium | `?page=abc` → 500 + a spurious `ErrorEvent` | defensive parsing |
| Low | `DJANGO_LOG_LEVEL=info` (lowercase) killed every worker at boot | validated against `logging.getLevelNamesMapping()` |
| Low | Non-dict `enabled_modules` → `AttributeError` in middleware → 500 on every governed endpoint | treated as "no opinion" |

**Pre-existing bugs corrected in passing:**
- `superadmin/metrics.py` had `CLOSED_ORDER_STATUSES = ('Delivered', 'Cancelled')`.
  `'Cancelled'` is **not a value `Order.order_status` can hold** (the vocabulary is
  8 values in `OrderViewSet.CLIENT_STATUSES`), and `'Shipped'` was missing — so the
  console counted every shipped garment as open work forever while the boutique's
  own screens had settled it. Now imported from `domains/orders/services.py`.
- Revenue was ambiguous. Now reported as **booked** (`Sum(total_amount)`) and
  **collected** (`Sum(amount_paid)`, which `_reconcile_payment` makes
  authoritative) as separate figures.
- `create_superuser.py` fell back to a password **committed in the repository**
  for the account that administers every boutique. It now refuses to run without
  `DJANGO_SUPERUSER_PASSWORD`.

---


1. **O(tenants) schema switches** on the overview, users list, onboarding list,
   health, orders monitor and search. One round trip per boutique per page. Fine at
   tens; the documented upgrade is a public-schema rollup table refreshed on a
   schedule.
2. **Per-worker caches.** Tenant and platform-setting caches are module globals
   with a 300 s TTL; `clear_*_cache()` clears only the calling worker, and gunicorn
   runs 2. Suspension and module changes are late by up to 5 minutes on other
   workers. **Turning maintenance mode *off* is the bad direction** — roughly half
   of traffic keeps getting 503 after the admin has been told it worked.
3. **`AuditLog` append-only is enforced by API and convention, not by the
   database.** The API exposes no write route; Postgres would still permit an
   `UPDATE` from a psql session. The README carries the `REVOKE` to enforce it.
4. **Unindexed `ILIKE`** for search and the data browser — a sequential scan per
   text column. Upgrade is pg_trgm GIN indexes, not a search service.
5. **Search per-type caps fill in tenant order**, so a match in the 40th boutique
   can be crowded out by earlier ones.
6. **`estimated_delivery` is nullable and unindexed** and defaults to
   `order_date + 15 days`, so the "overdue" count largely measures dates the system
   invented. The API returns a caveat string next to the number and the UI is
   required to render it.
7. **Schema-presence cache is positive-only** (§4.1).
8. **No frontend error collection.** The Error Center captures server exceptions
   only; a React render crash hits an ErrorBoundary and `console.error`.

---


**Genuinely absent data sources** (building the screen requires building the system
first): background jobs / queues; API request rate, latency, uptime; Try-On;
payments as a gateable module (it shares `/api/orders/` with editing a delivery
date, so it needs field-level gating inside `_reconcile_payment`, not a URL rule).

**Built thin, and I am not confident they are right:**

- **Feature flags have no reader.** `FeatureFlag.applies_to(schema)` exists and is
  tested, but *no product code calls it*. The flags are a control panel wired to
  nothing until someone uses one.
- **Plans / subscriptions: not built at all.** There is no billing in the product,
  so "trial boutiques", "expired subscriptions" and "failed payments" have no
  source. `is_active` is the entire commercial lever.
- **No login-activity or failed-login record.** `authenticate()` is called
  directly and fires no `user_logged_in` signal. The console can revoke a token
  but cannot say when anyone last signed in.
- **No token expiry.** DRF tokens never expire; revoking the row is the only
  sign-out that exists.
- **No 2FA**, and no scaffolding for it.
- **Data-export controls are absent.** The spec asked for export logging; there is
  no export feature, so there is nothing to log — but the *data browser* lets an
  administrator read every row of every table in every boutique, and only
  `SupportView` writes a `data.view` audit entry. **Browsing a boutique's customer
  table via `/boutiques/<schema>/data/crm_api.customer/` is not audited.** I regard
  this as the most serious remaining gap.
- **Retention/archival is undefined.** `AuditLog` and `ErrorEvent` grow without
  bound. No cleanup command exists.
- **Onboarding has 7 untracked steps of ~19** (`email_verified`, `phone_verified`,
  `whatsapp_connected`, `payment_configured`, `integrations_configured`,
  `real_designs`, `design_approval_configured`). They are excluded from the
  percentage and shown as "not tracked". Is that the right call, or should the
  product grow the signals?
- **No rate limiting on the console login** beyond what a parallel change added to
  the boutique login. The console's `PlatformLoginView` is a plausible brute-force
  target.
- **Sensitive-data masking is a denylist**, not an allowlist: `datasets.py` redacts
  fields whose name contains `password`, `secret`, `api_key`, `auth_token`, etc.,
  and excludes `authtoken.Token` wholesale. A new model with a credential in a
  differently-named field would leak. **An allowlist would be safer and I did not
  build one.**

---


**725 tests pass** across the whole project (was 625 before this work; 100 added).

| File | Tests | Covers |
|---|---|---|
| `tenants/tests.py` | 42 | Isolation, suspension, module gate, maintenance mode, lockout |
| `superadmin/tests.py` | 26 | Console access, overview, suspension, data browser, leads, metrics |
| `superadmin/test_users_search.py` | 25 | Cross-tenant users, ghost schemas, search |
| `core/test_exceptions.py` | 20 | Error capture, dedup, exactly-once, log level |
| `superadmin/test_audit.py` | 13 | Audit writes, XFF handling, failure tolerance |
| `superadmin/test_onboarding.py` | 9 | Seed-data inflation, module gating, untracked steps |
| `superadmin/test_api_security.py` | 6 | URLconf-walking perimeter (§4.3) |

**The tests I consider load-bearing:**
- Every console route declares `IsPlatformAdmin` (walks the URLconf, cannot go stale).
- Anonymous / plain public user / *a boutique's own superuser* are refused everywhere.
- No response contains `pbkdf2`, `argon2`, a plaintext password or a live token key.
- A ghost boutique does not mutate the public schema.
- With **every** module disabled, `/api/auth/` and `/api/dashboard/` still answer.
- A freshly created tenant reports a LOW onboarding percentage (proves the ~800
  seeded rows do not inflate it).

**Verified live in a browser** against a real database: module toggle → 403 on both
`/api/fabrics/` and `/api/fabrics.json`, audit row written with the typed reason;
owner deactivation refused; ghost boutique 404s; malformed paging clamped to 200.

**Not verified:** the console has never run against the production database
(deployment is blocked on an unrelated Supabase connection-pooler issue). Behaviour
under 2 gunicorn workers with `CONN_MAX_AGE=60` is reasoned about but not observed.
No load testing at any scale. No accessibility audit.

---


1. Is middleware the right enforcement point for modules, or is a URL-prefix
   registry too brittle as the API grows?
2. Should the generic data browser exist at all? It is the most powerful and least
   audited surface in the console (§7).
3. Is a denylist acceptable for field redaction, or must it be an allowlist?
4. Is per-worker caching with a 5-minute lag defensible for a *security* control
   (suspension), as opposed to a feature switch?
5. What have I missed that a reviewer with no context would notice immediately?
