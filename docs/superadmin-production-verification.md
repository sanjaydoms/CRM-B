
**FINAL STATUS: PRODUCTION BLOCKED**

Not because of a defect in the reviewed code. Because the reviewed code **is not
deployed**, and the production service is measurably still running the build that
carries both P0s.

I could not honestly return "production verified" for a build that is not in
production, and I will not record verification evidence that was actually
gathered against a local database.

---


Every branch — `main`, `TEST`, `DEV`, and `origin/MSK-CL` — points at
`337a1fe97f3428e69db792e906c018658bd32539`. All of the hardening work is
**uncommitted in the working tree**. Proven against the commit itself:

```
tenants/schema_guard.py                     NOT IN HEAD (untracked)
superadmin/test_gate.py                     NOT IN HEAD (untracked)
PUBLIC_ONLY_PREFIXES  in HEAD               0 occurrences   (working tree: 3)
EXTRA_SET_TENANT_METHOD_PATH  in HEAD       0 occurrences
```

So the deployed build contains none of it: no `/admin/` pin, no global
schema-switch guard, no data-browser related-object fix, no audit additions, no
mobile or focus fixes.


`https://crm-b-sitt.onrender.com` is up and answering. A single unauthenticated
GET, using a tenant id that does not exist so that nothing real is touched:

```
GET /admin/login/    (X-Tenant-ID: no_such_tenant_probe_2026)   -> 400
body: {"error": "Unknown tenant 'no_such_tenant_probe_2026'."}
```

That 400 is the tell. It can only be produced by the middleware **resolving a
tenant for `/admin/`**. With the pin deployed the request returns the admin login
page and the header is ignored. Therefore:

> **The Django-admin privilege escalation is live in production right now.** A
> boutique's own superuser — an account `seed_data.py` creates — can send their
> own `X-Tenant-ID` to `/admin/login/`, authenticate against their own boutique's
> `auth_user`, and then read the platform registry, read the platform audit log,
> and suspend other boutiques.

I did **not** attempt the escalation itself. Completing it would mean
authenticating against a live system holding another business's data. The
fingerprint above is conclusive and side-effect free.

The second P0 (platform administrator resettable through the boutique password
reset) is in the same undeployed changeset, and `EXTRA_SET_TENANT_METHOD_PATH`
has zero occurrences in `HEAD`, so it is live too. I did not probe it, because
the only non-destructive probe would still send a real password-reset email to a
real address.

**Remediation is deployment, not code.** Commit → promote `MSK-CL → TEST → DEV →
main` → deploy → then re-run this gate.

---


| | |
|---|---|
| Working commit | `337a1fe` (branch `MSK-CL`) |
| Working tree | 15 modified, 7 untracked — the entire hardening changeset, **uncommitted** |
| Deployed API | `https://crm-b-sitt.onrender.com` — up, running `337a1fe` |
| Deployed frontend | `https://boutique.scaleezy.com` — up (`/superadmin` and `/app` both 200) |
| Deployed console bundle | `superadmin-BdjMxjRq.css` / `superadmin-Ct8ZdcWS.js` — **differs from local build** (`superadmin-q5dfccQO.css` / `superadmin-D6DHAsVz.js`), i.e. the old build |
| Production database | **UNREACHABLE from here** — `.env` credentials fail authentication |
| Local verification DB | PostgreSQL `boutique_crm`, 8 boutiques |
| Workers | verified locally at the deployment configuration (gunicorn, 2 × 4 gthread); production worker count not observable from here |


```
.env DB_PORT = 6543   <-- the TRANSACTION pooler, which settings.py documents
                          as unsafe for this application (search_path is session
                          state; the session pooler on 5432 is required)
connect via .env as-is                       -> FATAL: password authentication failed
connect via documented session-pooler config -> FATAL: password authentication failed
```

The credentials in `.env` are stale or rotated. I stopped after two
configuration variants rather than trying further combinations. **Nothing in
§2–§12 that requires database access was performed against production.**

---


| Check | Result |
|---|---|
| Exact commit recorded | `337a1fe97f3428e69db792e906c018658bd32539` |
| Working tree recorded | 15 modified / 7 untracked (listed in §11 of the gate report) |
| No uncommitted debug code | PASS — no `breakpoint()`, `pdb`, TODO-REMOVE markers; zero `print()` in the ten changed production modules |
| Temporary probes removed | PASS — `superadmin/test_gate_probe.py` deleted |
| Temporary verification users removed | PASS — 0 remaining; 1 legitimate public superuser |
| Development-only launch config removed | PASS — temporary `gate-django` / `gate-vite` entries reverted; `.claude/launch.json` is unmodified |
| No test credentials in source | PASS — no verification account or password appears in any tracked file |
| `.env` gitignored | PASS (`.gitignore:21`) |
| No hardcoded production credentials | **FAIL — see below** |
| No temporary logging exposing sensitive data | PASS for this changeset; one **pre-existing** issue below |


`.git/config` carries a personal access token embedded in the `origin` URL
(`https://ghp_…@github.com/sanjaydoms/CRM-B.git`). It is not committed — `.git/config`
is not part of the repository — but it is a working credential sitting in plain
text on disk that grants push access to every branch, including `main`.

**Recommended:** revoke that token, and re-point the remote at a credential
helper or SSH:

```
git remote set-url origin git@github.com:sanjaydoms/CRM-B.git
```

I have not done this, because rotating a credential and changing how the
repository authenticates is your decision, not a verification step.


* `crm_api/auth_views.py:546` logs the **password-reset link** when mail delivery
  fails. On a deployment with no `EMAIL_HOST` the console backend never raises,
  so it does not fire — but with SMTP configured and failing, a working reset
  link is written to the Render log stream. P2.
* `tenants/management/commands/smoke_journey.py:170` hardcodes a password and has
  **no local-database gate** (unlike `seed_data.py` / `seed_mock_orders.py`,
  which call `refuse_unless_local_database()`). Run against production it would
  create a real tenant. P2 — never run it with production credentials.

---


| § | Check | Result |
|---|---|---|
| 2 | Backup / recovery status | **NOT VERIFIED** — no database or Supabase access |
| 2 | Migration state, public and tenant | **NOT VERIFIED** — no database access |
| 2 | Production DB role, schema ownership/visibility | **NOT VERIFIED** — the single most important pre-deploy check, see §5 |
| 2 | Worker count | **NOT VERIFIED** in production; verified locally at the deployment config |
| 3 | Application loads | **PASS** — API and both frontend surfaces return 200 |
| 3 | Super Admin login page loads | **PASS** — `/superadmin` returns 200 |
| 3 | Console endpoints reachable | **PASS** — all answer (401 unauthenticated) |
| 3 | Authenticated dashboard / boutiques / users / onboarding / modules / config / health / errors / audit / orders / search / leads / support / data browser | **NOT VERIFIED** — no production administrator credentials |
| 4 | Anonymous cannot reach Super Admin API | **PASS** — `/auth/me/`, `/overview/`, `/audit/`, `/users/`, `/boutiques/` all 401 |
| 4 | Anonymous cannot reach Django admin content | **PASS** — `/admin/login/` serves a login form only |
| 4 | Ordinary boutique user / boutique owner / boutique superuser boundaries | **NOT VERIFIED** — requires controlled production accounts |
| 5 | Ghost-schema behaviour | **Not verified in production — verified in controlled environment** |
| 6 | `/admin/` cannot perform tenant-context escalation | **FAIL — escalation path confirmed live** (§1) |
| 7 | Password reset cannot target the platform administrator | **NOT VERIFIED in production**; the fix is undeployed, so it is presumed live. Verified in controlled environment |
| 8 | Suspension across workers | **NOT PERFORMED in production.** Verified locally under real gunicorn |
| 9 | Module enforcement | **NOT PERFORMED in production.** Verified locally |
| 10 | Data browser allowlist / audit | **NOT VERIFIED in production.** Verified locally |
| 11 | Audit events | **NOT VERIFIED in production.** Verified locally — evidence in §6 |
| 12 | Multi-worker | **NOT VERIFIED in production.** Verified locally |
| 13 | Mobile at 320/375/414/768/desktop | **NOT VERIFIED against production** — the deployed bundle is the old build, so measuring it would describe code you are replacing. Verified locally on the new build |

I deliberately performed **no production mutation**. §8 and §9 require a
boutique that is safe to suspend; I have no way to know which production
boutique that is, and suspending the wrong one stops a real business from using
its CRM. That choice is yours to name.

---


`superadmin/schemas.py:schema_exists()` now delegates to django-tenants'
`pg_catalog.pg_namespace` lookup, replacing `information_schema.schemata`, which
per Postgres' documentation lists only schemas **owned by a currently enabled
role**.

That change matters because this answer is no longer advisory — it now gates
**every schema switch in the application**. If it were wrong on production's
role, every tenant request would be refused: a total outage.

`pg_namespace` is ownership-independent, so it should be correct on any role.
**It has not been confirmed against the production role**, and it should be, as a
read-only query, before or immediately after deploy:

```sql
SELECT current_user;
SELECT count(*) FROM pg_catalog.pg_namespace  WHERE nspname NOT LIKE 'pg_%';
SELECT count(*) FROM information_schema.schemata;
SELECT nspname, pg_get_userbyid(nspowner) FROM pg_namespace
 WHERE nspname NOT LIKE 'pg_%' AND nspname <> 'information_schema';
```

Expected: the `pg_namespace` count is at least the number of boutiques plus
`public`, and every tenant schema appears. If `information_schema.schemata`
returns fewer rows than `pg_namespace`, that is direct confirmation the old
implementation would have failed on this role — and that the change was
necessary rather than cosmetic.

---


Recorded honestly as **controlled-environment** evidence, not production.

| Action | Expected | Actual | Result |
|---|---|---|---|
| Full suite, local Postgres | 1018 baseline preserved | **1035 passed, 0 failed** | PASS |
| Boutique superuser → `/admin/` + own tenant header, **before** fix | refused | logged in, read registry, read platform audit, **suspended another boutique** | P0 confirmed |
| Same, **after** fix | refused | not authenticated, registry not visible, suspend inert | PASS |
| Platform administrator → `/admin/`, after fix | still works | 302 login, 200 registry | PASS |
| Password reset for platform admin via ghost schema, **before** fix | refused | token minted, **password overwritten** | P0 confirmed |
| Same, **after** fix | refused | 503, **0 emails sent**, password unchanged | PASS |
| Forged reset payload naming a ghost schema | refused | refused, password unchanged | PASS |
| Boutique login via ghost schema | no raw DB error | 503, no SQL in body | PASS |
| Public `/track/<token>/` via ghost schema | refused cleanly | 503 | PASS |
| Data browser into ghost boutique | no platform accounts | 502, none rendered | PASS |
| Writes into ghost boutique, all 8 modules | refused | 503 each; platform admin untouched | PASS |
| Credential-shaped unreviewed fields (`gateway_credential`, `webhook_signing`, `otp_seed`, `recovery_code`, `session_key`, `pat`, …) | masked | masked | PASS |
| Suspension, real gunicorn 2×4, authenticated, 24 concurrent | all refused immediately | 200 → **403** → 200, no cache cleared | PASS |
| Module disable, same conditions | all refused | 24/24 403 | PASS |
| Audit: suspend / reactivate / module change | actor, boutique, before/after, IP | all correct (trail reproduced below) | PASS |
| Console screens × 6 widths (320–1280) | no page overflow | 0 px on all 15 screens | PASS |
| Keyboard focus | visible | 2 px ring, offset, on nav/buttons/inputs | PASS |
| Browser console errors | none | none | PASS |

Audit trail produced by the controlled suspension and module tests — this is the
§11 evidence, showing actor, target boutique, before/after and IP all correct:

```
11:24:19 boutique.suspend     actor=verify@harden.test ip=127.0.0.1 before={'is_active': True}  after={'is_active': False}
11:24:19 boutique.reactivate  actor=verify@harden.test ip=127.0.0.1 before={'is_active': False} after={'is_active': True}
13:13:31 boutique.suspend     actor=verify@gate.test   ip=127.0.0.1 before={'is_active': True}  after={'is_active': False}
13:13:31 boutique.reactivate  actor=verify@gate.test   ip=127.0.0.1 before={'is_active': False} after={'is_active': True}
13:13:31 boutique.modules     before={}                after={'fabrics': False}
13:13:31 boutique.modules     before={'fabrics': False} after={'fabrics': True}
```

No password, token or secret appears in any audit row.

---


| Check | Result |
|---|---|
| Controlled boutique restored | **PASS** — the audit trail recorded `before={}`, so `enabled_modules` was restored to exactly `{}`, not merely to an equivalent `{"fabrics": true}` |
| All boutiques active | **PASS** — 8/8 `is_active=True`, 0 suspended |
| Test accounts removed | **PASS** — 0 remaining; 1 legitimate public superuser |
| Test database triggers removed | **PASS** — 0 (the append-only trigger tested in the previous pass was dropped) |
| Temporary configuration removed | **PASS** — `.claude/launch.json` unmodified |
| Dev servers stopped | **PASS** |
| Production state | **untouched — no production mutation was performed at any point** |
| Rollback | The only schema change is `superadmin.0003_alter_auditlog_action`, a choices-only `AlterField`. Reverse: `migrate superadmin 0002`. No data is written or destroyed by it |

---


**P0**
* **The Django-admin privilege escalation is live in production.** Confirmed by
  direct observation of the deployed service. A boutique superuser can reach the
  platform registry and suspend other boutiques. Fixed in the working tree,
  **undeployed**.
* **The platform administrator is resettable through the boutique password-reset
  flow in production.** Same changeset, same undeployed state. Not probed
  directly (it would email a real person), but `EXTRA_SET_TENANT_METHOD_PATH` is
  absent from `HEAD`, so the guard is definitively not running.

**P1**
* A live GitHub personal access token sits in `.git/config` with push access to
  every branch including `main`. Revoke and switch to SSH or a credential helper.
* No 2FA on the platform console.
* Audit-write failure is visible only in the service log; no health check asserts
  the audit table is writable.

**P2**
* `AuditLog` append-only is not enforced by the database (tested trigger SQL in
  the previous gate report; the real control is a least-privilege app role).
* `smoke_journey.py` has no local-database gate and hardcodes a password.
* Password-reset links are written to the log when SMTP fails.
* `order_tracking`'s module switch is evaluated against the hostname-resolved
  tenant rather than the boutique in the signed token.
* Media files are served unauthenticated from `/media/`; data-browser image cells
  hand over permanent URLs and fetching them is not audited.
* No "last platform administrator" guard (unreachable through the console today).

**Not verified**
* Everything in §4 marked NOT VERIFIED — principally: production database role
  and schema visibility, production migration state, backup/recovery, authenticated
  console behaviour, production boundary tests with controlled accounts,
  production suspension/module/data-browser/audit behaviour, production
  multi-worker behaviour, and production mobile.

**Accepted limitations** (unchanged): maintenance mode eventually consistent
(≤300 s, availability only); login throttle per worker (~40/hour across two);
unindexed `ILIKE` search; search caps fill in tenant order; `estimated_delivery`
is largely inferred and ships with its caveat; no frontend error telemetry; no
token expiry; seven onboarding signals untracked; feature flags remain unused
infrastructure with the UI withdrawn; JSON columns ungovernable field-by-field;
O(tenants) console pages — revisit at 50 boutiques.

---


1. **Revoke the GitHub token** in `.git/config` and re-point the remote.
2. **Commit** the changeset on `MSK-CL`.
3. **Promote** `MSK-CL → TEST → DEV → main` and deploy. Both P0s are live until
   this lands; that is the whole reason this gate is blocked.
4. **Fix the production database credentials** — `.env` is stale and points at
   the transaction pooler (6543) rather than the session pooler (5432), which
   settings.py documents as required for tenant isolation to hold.
5. **Run the read-only query in §5** against the production role before trusting
   the new global schema guard.
6. **Re-run this gate** against the deployed build: repeat the `/admin/`
   fingerprint (it must return the login page, not a 400), then the §4 boundary
   tests with controlled accounts, then one reversible suspension on a boutique
   **you** nominate as safe.

Until step 3 lands, nothing about the hardened control plane is true of
production.
