# TryOn2Buy CRM Boutique MVP

A premium, multi-tenant Customer Relationship Management (CRM) platform for boutique fashion studios, enabling owners to track custom order lifecycles, manage staff/tailors, explore fabric libraries, and view auto-generated customer intelligence (Style DNA).

---

## Architecture Overview

The project is structured as a monorepo consisting of a **Django Backend** and a **Vite React Frontend**:

```
├── boutique_crm/         # Django project configuration & settings
├── crm_api/              # Django app containing main business logic & endpoints
├── tenants/              # Tenant management (multi-tenancy routing schema)
├── frontend/             # React + Vite frontend source code
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
  * Configure your `DB_PASSWORD`, `SUPABASE_KEY`, and `SUPABASE_URL` under settings.
  * Optionally set `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD` to create a custom administrator account automatically.
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
* **Environment Variables:**
  * `VITE_API_URL` -- the Render origin including the `/api` suffix, e.g.
    `https://crm-b-sitt.onrender.com/api`. Read by the React app
    ([frontend/src/services/api.js](file:///Users/sanjaykumar/gemini/antigravity/scratch/django_screens/frontend/src/services/api.js#L1))
    *and* by `build-site.mjs`, which strips the suffix to derive the demo form's
    endpoint. One variable, so the two cannot drift apart. A local build falls
    back to `http://localhost:8000/api`; a Vercel build with it unset fails
    rather than shipping a form that posts nowhere.

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
