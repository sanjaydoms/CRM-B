# TryOn2Buy CRM Boutique MVP

A premium, multi-tenant Customer Relationship Management (CRM) platform for boutique fashion studios, enabling owners to track custom order lifecycles, manage staff/tailors, explore fabric libraries, and view auto-generated customer intelligence (Style DNA).

---

## 🏗️ Architecture Overview

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

## ⚙️ Backend Core Configurations

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

## 🚦 API Reference & Endpoint Map

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

## 💻 Local Development Setup

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

## 🚀 Production Deployment Guide

### Django Backend (Render)
* **Build Command:**
  ```bash
  pip install -r requirements.txt && python manage.py migrate_schemas --noinput && python create_superuser.py
  ```
* **Start Command:**
  ```bash
  gunicorn boutique_crm.wsgi:application
  ```
* **Environment Variables:**
  * Configure your `DB_PASSWORD`, `SUPABASE_KEY`, and `SUPABASE_URL` under settings.
  * Optionally set `DJANGO_SUPERUSER_USERNAME`, `DJANGO_SUPERUSER_EMAIL`, and `DJANGO_SUPERUSER_PASSWORD` to create a custom administrator account automatically.

### React Frontend (Vercel)
* **Root Directory:** `frontend`
* **Build Command:** `npm run build`
* **Output Directory:** `dist`
* **Endpoint Configuration:** Update `BASE_URL` in [frontend/src/services/api.js](file:///Users/sanjaykumar/gemini/antigravity/scratch/django_screens/frontend/src/services/api.js#L1) to match your Render backend domain.
