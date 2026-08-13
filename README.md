# TryOn2Buy CRM Boutique MVP

A premium, multi-tenant Customer Relationship Management (CRM) platform for boutique fashion studios, enabling owners to track custom order lifecycles, manage staff/tailors, explore fabric libraries, and view auto-generated customer intelligence (Style DNA).

---

## Architecture Overview

The project is structured as a monorepo consisting of a **Django Backend** and a **Vite React Frontend**:

```
├── boutique_crm/         # Django project configuration & settings
├── crm_api/              # Django app containing main business logic & endpoints
├── tenants/              # Tenant management (multi-tenancy routing schema)
├── superadmin/           # Platform console: cross-boutique monitoring & control
├── frontend/             # React + Vite frontend source code
│   ├── app.html          #   the boutique workspace (one tenant)
│   └── superadmin.html   #   the platform console (all tenants)
├── create_superuser.py   # Automatic superuser creator script for Render deploys
├── start.sh              # Local startup script for development servers
└── requirements.txt      # Python dependencies list
```

---

## Backend Core Configurations

### 1. Multi-Tenancy (`django-tenants`)
The backend uses **schema-based multi-tenancy**. Each boutique has its own isolated database schema (e.g. `sanjay_boutique`, `aditi_boutique`) under a single shared PostgreSQL database.

* **Schema Middleware (`tenants/middleware.py`):**
  Matches incoming requests via the `X-Tenant-ID` header (provided by frontend) or falls back to hostname domain resolution to switch database schemas dynamically.
* **Public Schema:** Contains tenant registration metadata (`BoutiqueTenant` & `Domain` models).
* **Tenant Schemas:** Contain customers, measurements, order histories, fabric libraries, and staff directories.

### 2. Database Integration (Supabase PostgreSQL)
* **Configuration Location:** `boutique_crm/settings.py`
* **Default Connection:** Connected to Supabase's transaction pooler on port `6543`.
* **Local Fallback:** By setting `USE_LOCAL_DB=True` in your environment, Django will automatically fall back to your local PostgreSQL instance on port `5432`.

### 3. File Storage Integration (Supabase Storage)
Instead of local media folders, the application uploads files (such as customer profiles, fabric snaps, and design uploads) directly to Supabase Storage:
* **Custom Storage Driver:** `crm_api/storage.py` implements a custom Django storage wrapper (`SupabaseStorage`) communicating with Supabase API.
* **Bucket name:** `boutique-crm`.

---

## API Reference & Endpoint Map

All backend APIs are prefixed with `/api/` and require token-based authentication (except login/signup):

### Authentication
* `POST /api/auth/signup/` — Registers a new boutique, auto-generates their tenant schema, seeds default staff/fabrics, and returns authentication tokens.
* `POST /api/auth/login/` — Authenticats the user and matches them to their tenant.
* `GET /api/auth/me/` — Checks active user context.

### Business Modules
* `GET/POST /api/customers/` — Directory CRUD (includes measurements inline).
* `POST /api/customers/<id>/fabric-selections/` — Uploads fabric files & configurations.
* `POST /api/customers/<id>/design-preferences/` — Stores design specifications and template links.
* `POST /api/customers/<id>/create-order/` — Creates custom order with breakdown.
* `PATCH /api/orders/<id>/update-status/` — Advances order status through staging channels.
* `GET /api/dashboard/` — Provides aggregated boutique statistics (revenue splits, order status, recent activity).

### Platform console
Public schema only, superuser only, and never tenant-scoped — see *Platform
console (superadmin)* under deployment for the rules that enforce that.
* `POST /api/superadmin/auth/login/` — Signs in a platform administrator. Rejects any account that is not a superuser in the public schema.
* `GET /api/superadmin/overview/` — Platform totals, every boutique's live figures, and lead counts in one payload.
* `GET /api/superadmin/boutiques/` — The same boutique rows on their own.
* `POST /api/superadmin/boutiques/<schema>/suspend/` — Blocks the boutique from login and the API. Data untouched.
* `POST /api/superadmin/boutiques/<schema>/reactivate/` — Restores it.
* `GET/PATCH /api/superadmin/leads/` — Demo requests; `status` and `notes` writable, nothing else.

---

## Local Development Setup

### Prerequisite
Ensure you have `npm`, `python3`, and a virtual environment tool installed.

1. **Clone & Install Dependencies:**
   ```bash
   # Create and activate virtual environment
   python3 -m venv .venv
   source .venv/bin/activate
   
   # Install backend packages
   pip install -r requirements.txt
   
   # Install frontend packages
   cd frontend
   npm install
   cd ..
   ```

2. **Start Dev Servers:**
   Run the root startup script to spin up both servers concurrently:
   ```bash
   ./start.sh
   ```
   * **React Frontend:** [http://localhost:5173](http://localhost:5173)
   * **Django Backend / Admin:** [http://localhost:8000](http://localhost:8000)

3. **Backend Testing:**
   Run Django unit tests using:
   ```bash
   python manage.py test
   ```

---

## Production Deployment Guide

### Django Backend (Render)
* **Build Command:**
  ```bash
  pip install -r requirements.txt && python manage.py migrate_schemas --noinput && python create_superuser.py
  ```
* **Start Command:**
  ```bash
  gunicorn -c gunicorn.conf.py boutique_crm.wsgi:application
  ```
  The `-c gunicorn.conf.py` is not optional. Without it gunicorn runs its
  default of a single sync worker with a single thread, so the API serves one
  request at a time -- and the dashboard opens by firing eight at once, which
  then queue behind each other. Measured on eight concurrent requests each
  waiting 300ms on the database: **2.47s with the defaults, 0.35s with the
  config file.**
* **Region:** put the service in the same region as the Supabase database
  (`ap-southeast-1`). Every request makes several database round trips, so a
  cross-region service pays that latency several times over per request. This is
  the single biggest lever left and it is pure configuration.
* **Environment Variables:**
  * `DJANGO_SECRET_KEY` is **required**. The service refuses to start without it
    outside `DEBUG`, and that is deliberate: it used to fall back to a literal
    committed to this repository, and this list never mentioned it, so a deploy
    that followed this README exactly ran on a published key. That key signs the
    customer tracking links (`domains/orders/tracking.py`), and `/track/<token>/`
    accepts them with no authentication — so knowing it means minting a link to
    any order in any boutique. Generate one with:
    ```bash
    python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
    ```
    Rotating it invalidates tracking links already sent to customers. That is
    intended, and it is the point of rotating it.
  * Configure your `DB_PASSWORD`, `SUPABASE_KEY`, and `SUPABASE_URL` under settings.
  * `EMAIL_HOST` (plus `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, optionally
    `EMAIL_PORT` / `EMAIL_USE_TLS`) and `PASSWORD_RESET_BASE_URL`. Without a
    host, the mail backend falls back to the console — a password reset link is
    then written to the service log and never reaches the person locked out.
    `PASSWORD_RESET_BASE_URL` is the **frontend** origin including the entry
    file, e.g. `https://boutique.scaleezy.com/app`; it is not `TRACKING_BASE_URL`,
    which must point at Django because `/track/<token>/` is a Django route.
  * `LOGIN_RATE` and `PASSWORD_RESET_RATE` (defaults `20/hour` and `5/hour`,
    counted per IP) cap password guessing on the two login doors and the reset
    form. Both count in the local-memory cache, so the effective ceiling is the
    rate times `WEB_CONCURRENCY`.
  * `DJANGO_SUPERUSER_PASSWORD` is **required** -- it is the platform
    superadmin's password (see *Platform superadmin* below). `create_superuser.py`
    exits with an error and creates nothing when it is unset, which fails the
    build. It used to fall back to a password written in this repository.
    `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_EMAIL` are optional and
    default to `admin` / `admin@boutiquecrm.com`.

    **This variable is now applied on every deploy, not only the first.**
    `create_superuser.py` used to skip when the account already existed and exit
    zero, so the build printed "already exists", passed green, and left whatever
    password was there — which, for any database seeded by `seed_data.py`, was
    the literal `admin123`, on the console that lists and suspends every
    boutique. Setting a new value and redeploying *is* the rotation procedure.
  * `WEB_CONCURRENCY` / `GUNICORN_THREADS` tune the worker pool. Their product is
    also the cap on database connections held, which is what keeps
    `CONN_MAX_AGE` safe against Supabase's pooler.
  * `TRACKING_BASE_URL` needs nothing here: unset, it falls back to
    `RENDER_EXTERNAL_URL`, which Render injects into every web service and which
    is already this service's own origin. Set it only for a custom domain --
    `RENDER_EXTERNAL_URL` stays the `onrender.com` address even behind one, and
    a customer should be given the boutique's domain. If you do set it, set it
    to **this service**, not the Vercel frontend: `/track/<token>/` is a Django
    route and the frontend domain has no such path, so pointing it there gives
    every customer a link that 404s.
  * `CORS_ALLOWED_ORIGINS` is unset today, which leaves `CORS_ALLOW_ALL_ORIGINS`
    on. If you ever lock it down it **must** include `https://boutique.scaleezy.com`,
    or the demo form on the marketing site stops working. The failure is quiet:
    the browser blocks reading the response and reports it only in its console.
    The form posts `application/x-www-form-urlencoded`, which is a CORS *simple*
    request, so the lead is still recorded even then -- the visitor just sees an
    error and submits again. One entry covers the React app too; it is served
    from the same origin via the `/app` rewrite in `frontend/vercel.json`.
* **Instance tier:** free instances sleep after ~15 minutes idle and take tens of
  seconds to wake, which reads to a user as the whole app hanging on first load.
  No amount of application tuning covers that -- it needs a paid instance.

### React Frontend (Vercel)
* **Root Directory:** `frontend`
* **Build Command:** `npm run build` (runs `vite build`, then `build-site.mjs`
  to assemble the static marketing pages)
* **Output Directory:** `dist`
* **Entries:** three surfaces come out of one deploy -- the static marketing site
  at `/`, the boutique workspace at `/app`, and the platform console at
  `/superadmin`. The last two are Vite entries (`app.html`, `superadmin.html`)
  with a rewrite each in `vercel.json`; both are `noindex` and both are listed in
  `public/robots.txt`.
* **Environment Variables:**
  * `VITE_API_URL` -- the Render origin including the `/api` suffix, e.g.
    `https://crm-b-sitt.onrender.com/api`. Read by the React app
    ([frontend/src/services/api.js](file:///Users/sanjaykumar/gemini/antigravity/scratch/django_screens/frontend/src/services/api.js#L1)),
    by the platform console (`frontend/src/superadmin/api.js`, which appends
    `/superadmin`) *and* by `build-site.mjs`, which strips the suffix to derive
    the demo form's endpoint. One variable, so they cannot drift apart. A local
    build falls back to `http://localhost:8000/api`; a Vercel build with it unset
    fails rather than shipping a form that posts nowhere.

### Platform console (superadmin)
The product-wide administrator's surface: **`/superadmin`** on the frontend
origin, backed by **`/api/superadmin/`** on the API. It is the one place in the
system that is meant to read across every boutique.

**Sign in** with a superuser that lives in the **public** schema. Create or rotate
one with `python create_superuser.py` and `DJANGO_SUPERUSER_PASSWORD` set (already
in the Render build command); locally, `python manage.py createsuperuser` does the
same interactively.

**What it shows**

* **Boutiques** -- every tenant, with its staff, customer, order and open-order
  counts, total order value and the date of its most recent order, read live from
  inside each boutique's own schema. *Last order* is the column to scan for a
  boutique going quiet. A row that could not be read is flagged `Unreadable`
  rather than shown as zeros, and is excluded from the totals with a warning.
* **Suspend / Reactivate** -- flips `is_active` on the tenant. A suspended
  boutique is refused at login and on every API call; nothing is deleted, so
  reactivating restores it exactly. It takes effect in other gunicorn workers
  within the tenant cache TTL (5 minutes), not instantly.
* **Leads** -- demo requests from the marketing form. Status and notes are
  writable; everything the prospect typed is read-only, and leads cannot be
  created or deleted here.

**Why it is a separate app.** `superadmin` is in `SHARED_APPS` only -- it reads
the tenant registry and reaches into every schema on purpose, which is exactly
what must never be installed *inside* a boutique. Two guards make that hold:

* `TenantHeaderMiddleware` pins `/api/superadmin/` to the public schema before
  any view runs, so a stale `X-Tenant-ID` cannot move the console off it.
* `IsPlatformAdmin` requires `is_superuser` **and** the public schema.
  `django.contrib.auth` is in both `SHARED_APPS` and `TENANT_APPS`, so
  `is_superuser` exists as a column inside every boutique too (`seed_data.py`
  creates one); the flag alone would have let a single boutique read all of them.

The console's React bundle is its own Vite entry (`superadmin.html`) with its own
token in `localStorage` under `superadmin_token`, so opening it in a browser that
is signed in to a boutique does not disturb that session, and vice versa.

**Django admin** at `/admin/` remains as the back door to the same tables -- it
needs no frontend build, no `VITE_API_URL` and no CORS, which is what you want
when the console itself is what is broken. Both read the same figures from
`superadmin/metrics.py`.

**Cost.** Building the list issues one query set per boutique, because there is
no cross-schema join to be had. Fine at the tens; past a hundred or so, roll the
counts into a public-schema table on a schedule and read that instead.

### Demo requests
The marketing site's demo form posts to `/demo-request/` -- a plain Django view
(`tenants/views.py`), public and outside `/api/` for the same reason
`/track/<token>/` is. Leads land in `tenants.DemoRequest`, which lives in the
public schema, and are read in Django admin at `/admin/tenants/demorequest/`
until the superadmin portal reads the same table. Status and notes are editable
there; everything a stranger typed is read-only.

Nothing notifies anyone. That is deliberate for now -- the page also keeps a
`mailto:` link to `support@scaleezy.com`, so a monitored inbox is still reachable.
Intake is rate-limited to 5 submissions per IP per hour, counted in Postgres
rather than a cache, because no `CACHES` is configured and LocMemCache would be
per-gunicorn-worker.
