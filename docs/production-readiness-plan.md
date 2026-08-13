# Boutique CRM — Consolidated Fix Plan

103 confirmed findings collapse to **68 distinct root causes**. Ordered for one engineer to execute top to bottom. Line numbers in this repo drift (App.jsx is edited concurrently — auditors disagreed by up to 170 lines on the same code); **cite by content, grep the string before editing**. Verified during synthesis: `App.jsx:5734/5746/5760` are the live bootstrap-password sites, `App.jsx:8411` is the crash guard with the deref at 8415, `repositories.py:41-43` holds the three `distinct=True` aggregates.

---

## PHASE 0 — Credentials. Nothing ships until these land.

Every item here is exploitable by someone who has only cloned the repo. Do these before the next deploy, in this order.

### 0.1 Rotate the Supabase database password
*critical · infra, not code · areas: secrets, deployment*
`MSK1122@msk` is in `.env:3` and in git history (`da7341f`, `6d4b55c`, and every commit between `c371cf5`…`55fed97` via `boutique_crm/settings.py`). `DB_USER=postgres.gbdabwahffdgdykbujpx` — the `postgres` superuser role on the single instance hosting every tenant schema. Anyone who ever cloned this has full read/write/DROP on every boutique, bypassing middleware and permissions entirely.
**Do:** rotate in the Supabase dashboard → set new `DB_PASSWORD` in Render env and local `.env`. Delete the false sentence "the database password has been rotated" at `docs/scaleezy-product-architecture.html:1047`. History rewrite is not required and not the point.

### 0.2 SECRET_KEY: fail fast, then rotate
*critical · merged from 2 areas (settings, security)*
`boutique_crm/settings.py:44` falls back to `django-insecure-local-development-only-do-not-use-in-production`. `DJANGO_SECRET_KEY` appears nowhere in `README.md:134-163`, `.env`, or `start.sh` — a README-following deploy runs on the published key. `domains/orders/tracking.py:38-41` signs `{'s': schema, 'o': order_id}` with it and nothing else; `crm_api/tracking_views.py:31-49` accepts any valid signature unauthenticated; order ids are `T2B-YYMMDD-NNNN`, 9000 slots/day. Known key = mint tokens = walk any boutique's whole order book (names, phones, addresses, balances) at `/track/<token>/`.
**Fix:** in `settings.py`, keep the literal only under `DEBUG`; otherwise `raise ImproperlyConfigured` naming the variable (the `create_superuser.py:33-41` pattern). Generate a fresh key, set it on Render, add it to the README env list. Rotation invalidates outstanding tracking links — intended.

### 0.3 Platform superuser is `admin` / `admin123`
*high→critical · areas: seeds, superadmin*
`seed_data.py:33` calls `create_superuser('admin', 'admin@boutique.com', 'admin123')` in the public schema — exactly the account `superadmin/permissions.py:26-37` accepts as platform administrator. The committed dump `boutique_crm.sql:2679-2681` contains that row with a hash verified to be `admin123`. `create_superuser.py:43-47` early-outs on `exists()` and exits 0, so `DJANGO_SUPERUSER_PASSWORD` is silently defeated on every redeploy.
**Fix:** in `create_superuser.py`, replace the `exists()` early-out with an unconditional rotate — `get_or_create(...)` then `set_password(password)`, `is_superuser = is_staff = True`, `save()`. Drop the literals at `seed_data.py:33` and `:64` for `os.environ`. Confirm the hosted DB's admin password after deploying (cannot be verified from the repo).

### 0.4 Shared bootstrap password for all staff and designer accounts
*critical · merged from 5 findings across auth, staff-management, design-studio, frontend*
`crm_api/views.py:272` → `os.environ.get('TAILOR_DEFAULT_PASSWORD', 'TailorSecure2026!')`; `apps/design_studio/views.py:515` → `DesignerSecure2026!`. Usernames are the email local-part. `crm_api/auth_views.py:47-57` (`find_tenant_for_account`) scans **every** non-public schema for a matching email or username, so one unauthenticated POST to `/api/auth/login/` with a guessed first-name-shaped username plus the published password lands inside whichever boutique has such an account. The literals are also shipped in the JS bundle (`App.jsx:5734/5746/5760`, `DesignDashboard.jsx:11`).

Same root cause, opposite symptom: an operator who *follows the code's own advice* and sets the env var breaks staff onboarding, because the modal still prints the hardcoded literal. And `_ensure_user_account` (`crm_api/views.py:264`) reuses a pre-existing `User` untouched — the modal asserts a password that was never set on it.

**One fix covers all of it:** generate `secrets.token_urlsafe(9)` per account in `crm_api/views.py:_ensure_user_account` and `apps/design_studio/views.py:create_login`; return it once as a write-only `bootstrap_password` key on that response. Render *that value* at `App.jsx:5734/5746/5760`, delete `DESIGNER_BOOTSTRAP_PASSWORD` from `DesignDashboard.jsx:11` and use the same field. Also drop the literal at `seed_mock_orders.py:53`.

### 0.5 Rate-limit both login endpoints
*medium, but pairs with 0.3/0.4 · areas: auth, superadmin*
`crm_api/auth_views.py:210` (`LoginView`) and `superadmin/views.py:44` (`PlatformLoginView`) have no `throttle_classes`. The settings comment at `settings.py:376-379` correctly declines a global default — it does not claim these are protected.
**Fix:** copy the in-repo pattern — add `'login': os.environ.get('LOGIN_RATE', '10/hour')` to `DEFAULT_THROTTLE_RATES`, add a two-line `AnonRateThrottle` subclass beside `_PasswordResetThrottle` (`auth_views.py:340`), name it on both views. Do **not** set `DEFAULT_THROTTLE_CLASSES`.

### 0.6 Disarm `seed_mock_orders.py`
*high · merged from 2 areas (seeds, deployment)*
`seed_mock_orders.py:16-24` runs `.objects.all().delete()` on OrderStageHistory, Order, Customer, Notification and Tailor inside `schema_context`, looped over every non-public tenant at `:250-255`. `USE_LOCAL_DB` is exported only by `start.sh:15`, so a hand-run `python seed_mock_orders.py` inherits the Supabase pooler defaults from `.env`. Nothing in the build or start path calls it — it is a loaded gun in the repo root.
**Fix:** one guard at the top of `seed_all()`: `if os.environ.get('USE_LOCAL_DB') != 'True': raise SystemExit('refusing to seed a non-local database')`. Do **not** flip the `USE_LOCAL_DB` default — Render sets no `.env`, so defaulting to local points production at 127.0.0.1. Same guard is cheap insurance at the top of `seed_data.py:seed()` and `seed_v2_tasks.py`.

---

## PHASE 1 — Flows that cannot be completed, or that crash

### 1.1 Owner opening any production stage on a designed order destroys the workspace
*critical · one line · area: design-studio/production*
`apps/design_studio/views.py:585-594` returns `TailorBriefSerializer` only for a caller with a `tailor_profile` who is not the Owner. Every Owner gets `DesignBoardSerializer`, which has no `design` field. `App.jsx:8411` guards on `(stageDesignBrief.design || stageDesignBrief.selected)`, then `:8415` dereferences `stageDesignBrief.design.image_url` → TypeError → the error boundary at `App.jsx:1790` unmounts the entire workspace. That modal is the only place stages are started/paused/completed, so an Owner cannot run production on any designed order at all.
**Fix:** normalise at the fetch site. In `openStageReview`: `setStageDesignBrief(brief ? { ...brief, design: brief.design || brief.selected } : null)`. One edit fixes the guard, all three derefs, and the production-notes deref.

### 1.2 Approved design is silently lost whenever the wizard returns to step 3
*high · area: order-wizard/design-studio*
`DesignStudio.jsx:187-192` fires on mount with `board === null` and calls `onBoardChange({boardId: null, approved: false})`, wired to `setDesignBoard`. The component sits under `{currentStep === 3 && ...}` so it unmounts on every step change and tab toggle. `handleBack` (4→3) and the step-6 summary Edit both remount it. Afterwards `if (designBoard.boardId && designBoard.approved)` is false and `saveDesignBoardToOrder` never runs — the surrounding comment exists specifically to make an attach *failure* loud, and this path bypasses it silently. The studio also forgets the board, so re-shortlisting creates a **second** DesignBoard for the customer.
**Fix:** in `DesignStudio`, fetch the customer's board on mount before the first `onBoardChange` — `api.getDesignBoards({ customer_id })` is already supported (`apps/design_studio/views.py:562-564`) — and seed `board`/`items` from it.

### 1.3 Delivered stage bypasses the QC gate and messages the customer
*high · area: workflow*
`domains/orders/services.py:314` gates on `stage_key == 'delivered' and new_status == 'COMPLETED'`, but `status_map['delivered']` at `:445` is the bare string `'Delivered'`, written for **any** `new_status`. `App.jsx` renders "Start In-Progress" for any NOT_STARTED/PAUSED stage and "Skip Stage" for any non-COMPLETED stage, both posting `transitionStage`. So Skip or Start on Delivered flips an uninspected order to Delivered on the public tracking page and fires the "successfully Delivered! Please complete your remaining balance" message.
**Fix (2 lines, same function):** mirror the `master_quality_check` pattern — `'delivered': 'Delivered' if new_status == 'COMPLETED' else order.order_status` — and drop `and new_status == 'COMPLETED'` from the guard at `:314`.

### 1.4 Master verification checklist loses ticks
*high · area: production*
`App.jsx:2647` and the duplicate at `:3874` spread `order.master_verification` from `ordersList`, which only refreshes on `fetchDashboardAndConfig`. The backend **replaces** rather than merges: `crm_api/views.py:432` writes `{str(k): bool(v) for k, v in checks.items()}`. A stale copy wipes the previous tick. The stored record of what was verified is wrong.
**Fix:** merge server-side at the single choke point both screens post to — `crm_api/views.py:432`: `order.master_verification = {**(order.master_verification or {}), **{str(k): bool(v) for k, v in checks.items()}}`. Unticking still works (the key is sent as False).

### 1.5 Customer Directory CTAs dead-end for a Master
*high · area: roles/frontend*
`App.jsx` `customer-detail-header-actions` renders "Go with Existing Design" and "Create New Design" with no role guard; the Master nav includes the Customers tab. Both routes reach `saveStep1` → `PATCH /customers/<id>/` → `RolePermission` denies `partial_update` for Master → 403 `Your role does not permit this.` Everything typed is lost, and there is no route from that screen to a completed order. The identical button on the Orders registry *is* guarded, with a comment naming this exact failure.
**Fix:** wrap the whole `customer-detail-header-actions` div in the guard the Orders registry already uses: `{(!currentUser?.role || currentUser.role === 'Owner') && ( ... )}`. One gate, both buttons.

### 1.6 Failed garment-job save reports total failure; retrying double-books the customer
*high · merged from 2 findings · area: order-wizard*
`submitOrderAndConfirm` calls `createOrder` then `await saveGarmentJobs(order.id)` in one `try`; `saveGarmentJobs` re-throws and the outer catch alerts the bare `"Failed to submit order."` with the order **already committed**. Nothing resets the wizard, `runOnce` only blocks concurrent clicks, and `create_order_for_customer` has no idempotency check — so pressing Confirm again writes a second Order with the same `total_amount` and `advance_paid`: two invoices, doubled revenue. Separately, `api.createOrder` throws a fixed string without reading the body, discarding the 400 reasons `crm_api/views.py:217-221` deliberately produces ("base_price cannot be negative", the 99,999,999 ceiling).
**Fix (two edits):** (a) in `services/api.js` `createOrder`, read the body and throw `describeApiError(res, data)` — the sibling `updateOrder` already does this and says why. (b) wrap only the `saveGarmentJobs` call in its own try/catch mirroring the design-board branch below it: alert `Order ${order.order_id} was created, but its garment details could not be saved (…) — open the order and add them`, then fall through to `setConfirmedOrder`/`setView('confirmed')` so the button cannot be pressed twice.

### 1.7 Garment file uploads are silently discarded
*high · merged from 2 findings · area: order-wizard/catalog*
`apps/catalog/definitions.py:111-115` puts four `file` fields (Measurement Sheet, Reference Images, Audio Note, Final Approved Design) in `COMMON_PRODUCTION`, rendered in wizard step 2. `TemplateForm.jsx:158-171` stores raw `File` objects (its comment claims "Uploads run through the existing media service on save" — no such call exists anywhere; `services/media.js` has no upload function and `App.jsx` has one unrelated `FormData` use). `api.js` `JSON.stringify`s the payload, so a File becomes `{}`; `core/templates.py:124` treats `{}` as empty and drops the key without error. Arrays become `[{}]` and are stored verbatim, rendering to the tailor as `reference images: [object Object]`. `GarmentSummary.jsx:64-67` still prints "Attached". The scanned measurement sheet — the artefact proving what was measured — is lost at capture with no error.
**Fix (remove the affordance, do not harden the write path):** filter file fields out of what the form renders — `TemplateForm.jsx` field loop: `(f) => f.field_type !== 'file'`. Do **not** raise in `core.templates.validate_spec`: `saveGarmentJobs` runs *after* the order is created, so a hard rejection strands an order with no garment job and a dead wizard. Re-add when a multipart path exists (see Missing Features).

### 1.8 A saree-only order stalls with "Measurements are not completed"
*medium, but it blocks a bread-and-butter flow · area: workflow*
`has_measurements` is duplicated at `domains/orders/services.py:172-174` and `:334-336` as `customer.measurements.bust or .waist or .hips`. Those three columns are written only by `saveStep2`'s `CUSTOMER_KEYS` map from garment-template keys. The saree template's measurements section (`apps/catalog/definitions.py:176-180`) contains only `petticoat_length`/`petticoat_waist` — neither is in `CUSTOMER_KEYS` — so a saree order for a new client leaves all three NULL and `assigned_to_tailor` raises. The message names a step the wizard never asked for.
**Fix:** lift the expression into one module-level helper used by both sites, and widen the **transition** guard (`:334`) to also accept `order.garment_jobs.exclude(measurements={}).exists()` — the per-dress snapshot the wizard genuinely captured.

---

## PHASE 2 — Money and data correctness

### 2.1 Blank advance box books half the order total as received
*medium (money) · area: order-wizard*
`App.jsx:1444`: `advance_paid: paymentOption === 'full' ? getTotalPrice() : (parseFloat(advancePaymentAmount) || getTotalPrice() / 2)`. State starts at `0` and the input clears to `0`, so `||` substitutes half the total. `domains/orders/services.py:167-170` stores it into both `advance_paid` and `amount_paid`. The wizard preview uses the same fallback, so the number is at least visible — but there is no way to express a zero advance.
**Fix all three or the UI starts lying:** send `parseFloat(advancePaymentAmount) || 0`; change the preview to `Math.max(0, getTotalPrice() - (advancePaymentAmount || 0))`; drop the `total_amount * 0.5` default in `create_order_for_customer` (`services.py:168`).

### 2.2 No part payment can be recorded after order creation
*high · merged from 3 findings · area: invoicing*
The only post-creation payment control is the Invoices `<select>` PATCHing `{ payment_status }`. In `_reconcile_payment` (`crm_api/views.py:339-346`), with neither `amount_paid` nor `advance_paid` in `changed` and the label neither 'Paid' nor 'Pending', it falls to `paid = order.amount_paid or 0` and re-derives the label from the unchanged number — "Partially Paid" silently snaps back. `grep amount_paid frontend/src` returns five hits, **all reads**. The backend docstring says outright "the Invoices row only needs to PATCH a number" — the input was never built. Only ₹0 and paid-in-full are expressible, so collected revenue, the tracking-page balance and the delivery message are wrong for every part-paid order.
**Fix:** make the Total Paid cell in the Invoices row an editable number input PATCHing `{ amount_paid: value }` via the existing `api.updateOrder`. `_reconcile_payment` already clamps and derives the label — no backend change. Leaving the "Partially Paid" option in the select without this is the part that must not ship.

### 2.3 Order confirmation screen always says "Paid" for the full total
*medium · merged from 2 findings · area: invoicing*
`App.jsx` ≈7900 renders the literal `Paid • ₹{confirmedOrder.total_amount.toLocaleString('en-IN')}` in success green, referencing neither `payment_status` nor `amount_paid`. `total_amount` also arrives as a string (`COERCE_DECIMAL_TO_STRING` is unset), so `String.prototype.toLocaleString` prints it ungrouped: `₹33075.00`. This is the screen staff turn to the customer, and it contradicts the invoice one click later.
**Fix:** `{confirmedOrder.payment_status} • ₹{parseFloat(confirmedOrder.amount_paid || 0).toLocaleString('en-IN')}`, and drop the hardcoded success colour when the status is not 'Paid'.

### 2.4 Printed invoice demands money already paid
*medium · area: invoicing*
The invoice block guards on `advance_paid > 0` and computes Balance Due as `total_amount - advance_paid`, never `amount_paid`. `_reconcile_payment` only ever *caps* the advance, so a settled order keeps its original `advance_paid` while `amount_paid == total`. Result: "Payment Status: Paid" directly above "Advance Paid ₹10,000 / Balance Due ₹23,075". Reachable for any existing order via Invoices → View Invoice.
**Fix:** switch the guard and both figures to `amount_paid`; Balance Due = `Math.max(0, total_amount - amount_paid)` — the expression the Invoices table and `tracking_views.py:82` already use.

### 2.5 Customer lifetime spend uses `SUM(DISTINCT)`
*high · merged from 3 findings · area: analytics*
Verified live in the file — `domains/customers/repositories.py:42-43`:
```python
orders_total_spend=Sum('orders__total_amount', distinct=True),
orders_avg_price=Avg('orders__total_amount', distinct=True),
```
The comment above explains `distinct=True` was added to counter the `orders__stages` join fan-out — but `SUM(DISTINCT col)` de-duplicates by **value**, not by row, so two ₹40,000 orders total ₹40,000, for every role including Owner (who has no fan-out at all). Feeds the Customer Directory list and dashboard recent-customers via `CustomerSummarySerializer.get_total_spend`/`get_segment` and `build_style_dna`'s budget band, while the *detail* serializer sums rows correctly — so two screens contradict each other about the same person. Segment mis-grades at exactly two identical orders (HVC where the detail banner says VIP). The existing test uses `[1000, 2500, 500]` — three distinct values — which is why it survived.
**Fix (root cause, two edits):**
1. `core/permissions.visible_customers`: replace the multi-valued join filter with `queryset.filter(pk__in=Customer.objects.filter(Q(orders__tailor=profile) | Q(orders__master=profile) | Q(orders__stages__assigned_to=profile)).values('pk'))` — removes the row multiplication and the trailing `.distinct()`.
2. Drop `distinct=True` from the `Sum` and `Avg`. Keep it on `Count('orders', distinct=True)` — correct there. Rewrite the comment so the next reader does not re-add it.

*(A per-customer `Subquery` is the fallback if step 1 turns out to change disclosure semantics under test — but the aggregate already spans all of the customer's orders on the tailor path, so it should not.)*

### 2.6 Purchase-order receipt is not atomic
*high · merged from 2 findings · area: inventory*
`apps/inventory/views.py:318` `receive` carries only `@action`; `ATOMIC_REQUESTS` is set nowhere. Each `InventoryService.purchase()` is individually `@transaction.atomic` and commits on return, so the over-receipt `ValueError` at `:344` or a `decimal.InvalidOperation` from `Decimal(str(quantity))` at `:339` (an `ArithmeticError`, so it escapes the `except ValueError` as a 500) leaves earlier lines already stocked with PURCHASE ledger rows while the owner sees only a failure. `ReceiveModal` pre-fills every line, so multi-line receipts are the default. Resubmitting double-counts, permanently.
**Fix:** `@transaction.atomic` on `PurchaseOrderViewSet.receive` (`transaction` is already imported at line 1), with the `except ValueError` handler outside the block. Covers the 500 path too.

### 2.7 `submit_stage_review` deletes prior history outside a transaction
*medium · merged with the same function's validation gaps · area: production*
`crm_api/views.py:698` does `OrderStageHistory.objects.filter(order=order, stage=stage).delete()` before the `create` at `:700`, with no `@transaction.atomic` (`transaction` is not even imported in that module). If the create fails, the earlier review's comments and evidence photo are gone. Same function: `stage` is free text with no membership check (contrast `assign_stage`, which checks), `completed_by` defaults to the literal `'Boutique Staff'` from the request body, and the upload is assigned straight to the ImageField with no serializer. It is in `STAFF_ORDER_ACTIONS`, so any production account reaches it. *No frontend caller exists today* — `api.submitStageReview` is unreferenced — which is why this ranks here and not higher.
**Fix:** add `from django.db import transaction`, decorate with `@transaction.atomic`, add `if not order.stages.filter(stage_key=stage).exists(): return 404`, and set the performer name from `request.user` rather than the body.

### 2.8 `release_unused()` permanently wedges a material plan
*medium · area: inventory*
`InventoryService.record_movement` clamps the **item's** reserved figure on DAMAGE/SCRAP/SUPPLIER_RETURN/ADJUSTMENT, but never writes back to `OrderMaterialLine`, whose `outstanding_reservation` is computed from its own columns. `apps/inventory/order_materials.py:322` passes that raw figure to `release()` with no clamp → `ValueError: Cannot release N … only M is reserved`. `close()`, `cancel()` and `reconcile()` all route through it, and the `one_live_material_plan_per_order` constraint then blocks re-planning. **API-only today** (no screen), which is why it is medium.
**Fix:** pass the existing flag at the one call site — `InventoryService.release(line.item, outstanding, clamp_reserved=True, ...)`. The service already floors at zero for `reserved_delta < 0`, and the existing over-release test calls `release()` without the flag, so it still refuses a genuine over-release.

### 2.9 Stepping back through wizard step 3 duplicates DesignPreference rows and re-uploads images
*medium · area: order-wizard*
`crm_api/views.py:100` does an unconditional `DesignPreference.objects.create(...)` after saving every file to a fresh UUID path. `saveStep3` fires from both `performNext` and save-as-draft, and `handleBack` from step 4 clears nothing — the same files are re-read and re-saved. The sibling `save_fabric_selection` immediately below carries a comment describing this exact pathology and was fixed to update the latest row; the design path was left on create. Downstream, "Go with Existing Design" prefills from `design_preferences[0]` — the oldest duplicate.
**Fix:** copy the neighbour: take `customer.design_preferences.order_by('-id').first()`, create only when none, guard the `reference_images` write with `if image_urls or created:`, return 200 on update.

### 2.10 Mobile numbers are stored as typed
*medium · area: customers*
`CustomerSerializer.validate_mobile_number` calls `whatsapp_number(value)` purely as a reachability predicate and returns the **raw** string. `whatsapp_number` (`crm_api/models.py:14-56`) already canonicalises `+91 (0) 98765 43211`, `0091…` and `098765…` all to `919876543211`. `Customer.mobile_number` is `unique=True` on the raw column and both search paths are literal JS substring matches. So a return visit typed differently misses search, misses the unique index, and creates a second profile — splitting that client's measurements, history, preferences and orders.
**Fix:** `return whatsapp_number(value) or value`. Ship a data migration running `whatsapp_number` over existing rows in the same change (resolve any collisions it surfaces), or the fix only helps new rows.

### 2.11 Order status walks backwards after delivery
*medium · area: workflow*
`domains/orders/services.py:444-446` assigns `status_map[stage_key]` absolutely with no ordering; the only regression guard covers same-stage re-completion. Optional stages (`maggam_work`, `pattern_cutting`, finishing, pressing, trials) can be NOT_STARTED on a Delivered order, so post-delivery housekeeping reverts the order to an in-production status, re-fires "now in the Design & Creation phase" to the customer, and puts it back in the active-orders table.
**Fix:** same site — keep a module-level ordered tuple of client-facing statuses (matching `OrderViewSet.CLIENT_STATUSES`) and assign only when the new index exceeds the current one.

---

## PHASE 3 — Role boundaries and within-tenant disclosure

No cross-tenant leak was confirmed anywhere in the application layer — django-tenants schema isolation holds. Everything below is a role boundary inside one boutique. (The genuine cross-tenant exposures are 0.1 and 0.2.)

### 3.1 `/api/catalog/jobs/` is unscoped
*high · merged from 3 findings · area: catalog/production/roles*
`apps/catalog/views.py:85` declares no `permission_classes` (its sibling `GarmentTemplateViewSet` three lines up sets one and explains why), so it inherits `RolePermission`, which grants every SAFE_METHOD to any non-Owner, non-Designer role. `get_queryset` at `:88` narrows only by an optional `?order=`. `GarmentJobSerializer` emits `spec` and `measurements` in full — every measurement, `customer_notes`, `special_instructions`, and `internal_notes` whose own help_text reads "Staff only — never shown on the customer copy". A tailor correctly 404'd from `/api/orders/<id>/` reads that same order here.
**Fix:** the sibling apps were fixed for exactly this and say so in their docstrings. In `get_queryset`: `queryset = queryset.filter(order__in=visible_orders(Order.objects.all(), self.request.user))`, importing `visible_orders` from `core.permissions` and `Order` from `crm_api.models`. One line covers list, retrieve and both materials sub-actions.

### 3.2 Stock valuation and purchase prices open to any staff token
*medium · merged from 2 findings · area: inventory*
`InventoryItemViewSet` (`apps/inventory/views.py:54`) sets no `permission_classes` while all three siblings — `SupplierViewSet:43`, `PurchaseOrderViewSet:308`, `InventoryReportViewSet:916` — set `OwnerOnly` with comments naming stock valuation as the boutique's commercial position ("a tailor needs none of it to sew"). `summary` returns `inventory_value = Sum(current_stock * purchase_price)` and the serializer lists `purchase_price`.
**Fix:** `permission_classes = [OwnerOnly]` on `InventoryItemViewSet` (already imported). Verified safe: `/inventory/items/` is called only from the Owner-only Inventory panel and from `TemplateForm.jsx`/`GarmentSummary.jsx`, both inside the Owner-gated order wizard.
*If you need production staff to keep reading quantities:* instead drop `purchase_price` from `InventoryItemSummarySerializer` and gate the `inventory_value` key on `resolve_user_role(request.user) == OWNER`. Pick one — do not do both.

### 3.3 Designer portfolio leaks staff email + live-account flag
*medium · area: design-studio*
`DesignerSerializer.to_representation` pops `email`/`has_login` for non-Owners **only when `request is not None`**. `portfolio` (`apps/design_studio/views.py:538`) constructs the serializer with no `context`, so the guard is skipped; `DesignStudioPermission` allows any signed-in role on SAFE methods. Combined with 0.4 that is an account-takeover shortcut inside the boutique.
**Fix:** `DesignerSerializer(..., context=self.get_serializer_context())` at `:538`. Leave `create_login` at `:524` alone — it is a POST, Owner-only, and the Owner already sees the email.

### 3.4 Masters see every order's Total Value on the registry
*medium · area: roles/frontend*
The Orders registry renders the Total Value block with no role test, and the Master nav routes there. One screen earlier the identical figure is gated: `{!isProductionStaff(currentUser.role) && …}`, and `isProductionStaff` includes 'Master'. The rule is stated in the comment at `App.jsx:44-48` and echoed server-side.
**Fix:** wrap the Total Value block in the same `{!isProductionStaff(currentUser.role) && ( ... )}` guard. Do **not** pop money fields from `OrderSerializer` — it is the read path for the invoice modal, the tracking page and the whole registry.

### 3.5 Any staff member can forge a notification into the Owner's feed
*low–medium · merged from 2 findings · area: notifications*
`OwnNotifications.has_permission` returns True for any role-resolving user on every method; its docstring justifies this by `get_queryset`, which `create` never calls. `NotificationSerializer` is `fields='__all__'` over writable `recipient_role`/`recipient_email`.
**Fix:** one line in `core/permissions.py:102` — `if getattr(view, 'action', None) == 'create': return False` before the existing return. `destroy` already routes through the scoped queryset; `mark_all_read` is a custom action and is unaffected. **Do not set `http_method_names`** — `APIView.dispatch` tests it before the action map, so dropping `'post'` would 405 mark-all-read and take the bell down for every non-Owner (the class comment warns about exactly that outage).

### 3.6 Media is served unauthenticated from one global directory
*medium · area: storage*
`settings.py:350-360` uses plain `FileSystemStorage` with a single `MEDIA_ROOT`; `boutique_crm/urls.py:64` serves it in every environment with no permission check (the comment there justifies serving in non-DEBUG, and says nothing about access control). The five `ImageField` prefixes keep the caller's filename, so an ordinary guess — `logo.png`, `IMG_1234.jpg` — under `/media/customer_profiles/`, `/media/stage_images/` or `/media/finished_garments/` returns the file, bypassing the `garment_images_published` gate on the tracking page. (No directory listing; UUID-prefixed paths from the three `default_storage.save()` call sites are not guessable.)
**Fix:** set `STORAGES['default']['BACKEND']` to `django_tenants.files.storage.TenantFileSystemStorage` (django-tenants 3.10.1 is already pinned). It namespaces path and URL by schema, covering all five prefixes at once, and the existing `serve()` route keeps working. **This is hardening, not authentication** — and existing rows keep paths under `media/<dir>/`, so those files must be moved to `media/<schema>/<dir>/` or their images break. Coordinate with 4.x below.

---

## PHASE 4 — Hit in a normal week

Grouped by area so one file gets opened once.

### 4.1 Delete the fake data every new boutique is born with
*high · area: onboarding*
`seed_tenant_defaults` (`crm_api/utils.py:3`) is called unconditionally from `SignupView` with no demo flag. It creates four invented employees (Rohit Mehra, Master, rating 4.90; Anya Sharma; Rahul Verma; Preeti Singh), five priced fabrics (Silk Dupion ₹1850/m, Banarasi Silk ₹2850/m) and eleven catalogue designs at ₹45,000/₹38,000/₹32,000. Those fabric prices reach money: `App.jsx:1406` sets `fabric_price = selectedFabric.price_per_meter * 3`, which prints on the invoice. So a day-one order can be assigned to a person who does not exist and priced at another business's rate. The adjacent appointments panel comment records the opposite decision being made deliberately: "An empty panel is better than an invented one."
**Fix:** add `demo=True` param to `seed_tenant_defaults` gating the three literal lists; pass `demo=False` from the `SignupView` call. `SeedDataView` and `seed_data.py` keep the demo path. The order wizard already handles an empty roster.

### 4.2 Boutique address: required at signup, no placeholder fallbacks
*high + medium + low, merged from 3 findings · area: onboarding/invoicing*
- Step 3's address input has no validation and `handleProfileSubmit` only advances the step; `SignupView` writes `address` only when non-empty, leaving `BoutiqueSettings.address` at its model default `'123 Atelier Way, Fashion District'`. That renders to the unauthenticated customer on the tracking page ("Address", "Pick up from") and on the invoice.
- The Edit Boutique Profile form uses `defaultValue={boutiqueSettings?.address || "123 Atelier Way, Fashion District"}` — and the same for name / phone / email — with all four `required` and appended to FormData unconditionally. If the settings fetch fails transiently (it records to `loadErrors` and leaves `boutiqueSettings` null, and the profile view has no `loadErrors` branch), saving any change **overwrites the boutique's real identity with vendor demo strings**.

**Fix (three small edits):** guard `handleProfileSubmit` — blank name or address ⇒ alert and return (step 3 is a `<div>`, not a `<form>`, so `required` does nothing there); change the four `defaultValue` fallbacks in the profile form to `|| ''` and move the strings to `placeholder`; drop the hardcoded fallback in the invoice header so a blank address renders blank.

### 4.3 Signup wizard cleanup — one pass
*merged from 6 findings · area: onboarding*
- **OTP step 2 is theatre** (*high*): `handleSignupSubmit` ends `setSignupStep(2) // Mock verification`; the screen asserts "We have sent a 6-digit OTP code to +91 …"; `handleVerifyOTP` advances on any non-empty string with no request. There is no SMS capability anywhere in the repo. No resend, no skip. → **delete step 2**, have `handleSignupSubmit` set step 3, drop `{ step: 2, label: 'Verify' }` from the tracker.
- **Step 4 style tags are inert** (*low*): six plain `<span>`s, no onClick, no state, never submitted. → **delete step 4**, move "Submit Registration" onto step 3.
- **Password says "min 6", server enforces 8** (*low*): the failure lands four steps later and bounces to step 1. → placeholder → "min 8 characters", strength threshold 6→8, and a length check in `handleSignupSubmit`.
- **Three inert social icons** under "OR CONTINUE WITH" (*low*): the login screen's equivalents were already deleted with an explanatory comment. → delete the divider and icon row.
- **Failed signup burns the email permanently** (*medium*): `SignupView` creates BoutiqueTenant → Domain → seed → BoutiqueSettings → *then* `User`, in one try whose except only resets the schema and returns `str(e)`. Nothing deletes the tenant; `owner_email` is unique and the duplicate check tests exactly that field. `gunicorn.conf.py:33` sets a 60s timeout while tenant creation runs the full migration set. The address can then never sign up (duplicate) and never log in (no User) and password reset correctly reports nothing. → in the except, keep the tenant reference, `connection.set_schema_to_public()`, then `tenant.delete(force_drop=True)` in a nested try (`force_drop` is required — only `auto_create_schema` is set), and return a fixed "We could not finish creating your boutique. Please try again." instead of `str(e)`.

### 4.4 Session handling in `services/api.js` — one pass
*merged from 4 findings · area: frontend/auth*
- **No 401/403 handling** (*medium*): nothing in `api.js` inspects status for 401; `superadmin/api.js:47-59` does the opposite and explains why. Signing out on one device leaves the shop desktop failing every call with an alert and showing stale rows forever. → add an `authedFetch` next to `getHeaders` that on 401 clears `token`/`tenant_id` and reloads, and use it throughout.
- **`getMe` clears the token on any non-ok status** (*low*): a 500 from a cold DB or a 502 during worker recycling signs the user out. → `if (res.status === 401 || res.status === 403) localStorage.removeItem('token'); if (!res.ok) return null;`
- **`login`/`signup` parse JSON before checking `ok`** (*low*): an HTML 502 page yields `Unexpected token '<'` at the two moments a clear message matters most. → `await res.json().catch(() => ({}))`, as `requestPasswordReset` already does.
- **Logout leaves all boutique data in state** (*medium*): on a machine shared by two boutiques, A's customers, orders and settings paint for B's owner during the refetch and persist if any request fails. → `handleLogout`: `await api.logout(); window.location.reload();`

### 4.5 Raw JSON and opaque errors reaching staff
*medium · area: frontend*
`api.js` throws `JSON.stringify(body)` at nine sites (208, 260, 701, 753, 929, 961, 991, 1047, 1074) and `App.jsx` concatenates `err.message` into `alert()` in ~34 places, so a DRF field error renders as `{"mobile_number":["…"]}` in a modal. `describeApiError` already exists in that file and unpacks exactly that shape; only nine call sites use it.
**Fix:** replace those nine `JSON.stringify` throws with `describeApiError(res, data)`. Same treatment for `updateBoutiqueDesign`/`deleteBoutiqueDesign`, which throw bare strings and hide their 403. Leave the alert-vs-banner question alone — that is a refactor, not a defect.

### 4.6 Role-gated UI that lies to non-Owners
*merged from 3 findings · area: roles/frontend*
- **My Account tells everyone they are "Boutique Owner"** (*medium*): the panel has no role check — hardcoded `<p>Boutique Owner</p>`, hardcoded "Registered Since / June 2024", and an Edit Boutique Profile form that renders for every role. Submitting POSTs `/boutique-settings/`, and `create` is on neither the SAFE nor the named-action list in `RolePermission`, so Master/Tailor/Designer get a certain 403 rendered as "Failed to update boutique settings" with no reason. → print `{currentUser.role || 'Boutique Owner'}`, wrap the Edit card in `{(!currentUser.role || currentUser.role === 'Owner') && ( ... )}`. Either add tenant `created_on` to the `MeView` payload and render it, or delete the "Registered Since" row.
- **Status dropdown offers eight options production staff can never set** (*medium*): the assignments card hard-codes all eight client statuses for every production role. A Tailor can set exactly one of eight; a Measurement/Pattern/Cutting/Maggam/Finishing/Pressing master, none. `update_status`'s own comment says "Moving an order without doing the work is a supervisor's call." → render the `<select>` only for Owner/supervisors, leave the read-only status badge for everyone else. Production staff keep `StageTimeline` in the same card, which is the control the workflow engine is built around.
- **Designer sees Edit/Delete on catalogue designs that always 403** (*medium*): `DesignLibrary.jsx:223` gates on source alone; both handlers hit `BoutiqueDesignViewSet`, where `RolePermission` returns False outright for DESIGNER. The library is the only screen the app offers a Designer. → `DesignLibrary` already receives `canReview` (true only for Owner); gate the Edit/Delete block on it as well as on `editable`.
  Also: hide the "Add collection" control in `DesignUpload.jsx:217` unless Owner — `CollectionViewSet` refuses a Designer, and widening the permission would let a designer create collections for other designers.

### 4.7 Specialist masters are second-class throughout production
*merged from 3 findings · area: workflow/notifications*
- The Stitching Tailor pickers (order wizard step 5 and the owner's Workflow Assignment select) filter `t.role !== 'Master'`, which passes all seven specialist roles — while `get_default_workflow` restricts both stitching stages to `["Owner", "Tailor"]`. Assigning stitching to the Finishing Master produces an order they can see but can never advance. → change both pickers to `eligibleStaffForStage('stitching_in_progress')`, which already reads the stage's own role list and is used for stage assignment.
- `domains/orders/notifications.py` writes literal `recipient_role="Tailor"` (lines 61, 116) and `"Master"` (54, 132), while `NotificationViewSet._audience` filters on `profile.role`. `assign_stage` does it correctly with `recipient_role=tailor.role`. → replace the four literals with `order.tailor.role` / `order.master.role`.
- `performed_by` is never recorded for a specialist: the fallback at `services.py:385` is gated on `user_role in ['Master','Tailor']`, and the performer dropdown is Owner/Master-only. → test for the profile instead, and do not clear an existing performer: `elif user and user.is_authenticated and getattr(user, 'tailor_profile', None): order_stage.performed_by = user.tailor_profile`.

### 4.8 Reassigning an order leaves everything pointing at the old person
*merged from 2 findings · area: production*
`OrderViewSet.perform_update` does only `serializer.save()`, `_reconcile_payment` and a status-change notification. It never calls `refresh_staff_availability` — whose docstring says deriving the flag at every write site is precisely what stops it drifting — and never writes an assignment notification. So the departing tailor still reads **Busy** with nothing on their table, the new one reads **Available** with a dress to sew (these are the badges the owner picks staff by), `ProductionTask` keeps naming the old tailor, and nobody is told.
**Fix:** capture `serializer.instance.tailor_id`/`master_id` before `save()`; when either changed, call `refresh_staff_availability(old_tailor, old_master, order.tailor, order.master)`, repoint `ProductionTask.objects.filter(order=order, assigned_to=old_tailor).update(assigned_to=order.tailor)`, and write the same Notification row `assign_stage` already writes — with `recipient_role=tailor.role`, not the literal.

### 4.9 Editing a staff email with a capital letter empties their notification feed
*medium · one line · area: staff*
`_ensure_user_account` lowercases in memory **after** `serializer.save()` has persisted the typed casing, then on the existing-account branch updates the `User` and returns at `crm_api/views.py:262` **without `tailor.save()`**. `Tailor.email` keeps `Priya@example.com`; notification rows are written from `user.email` (lowercase); `get_queryset` filters `recipient_email=email` exactly. Login is unaffected, so the failure is silent and permanent.
**Fix:** `tailor.save(update_fields=['email'])` immediately before that `return`.

### 4.10 Measurements: prefill, and show the order's snapshot
*merged from 3 findings · area: production/order-wizard*
- **Returning customers' saved measurements are never prefilled** (*medium*): `addGarment` always pushes `values: {}` and `handleSelectExistingCustomer` clears `garmentJobs`. `customerForm.measurements` is only ever written *from* the garment job, never back. Meanwhile the order-selector card advertises "retrieve their measurements" with a ticked "Use saved measurements". Required fields exist, so the staff member retypes — one chance per digit to mis-transpose. → seed `values` in `addGarment` from `customerForm.measurements` using the inverse of the `CUSTOMER_KEYS` map already in `saveStep2` (bust→chest, hips→hip, …), keeping only keys the fetched template defines. One function; both entry points route through it. If you skip the fix, delete the "Use saved measurements" tick.
- **"Sizing Blueprint" shows the live shared row, not the order's** (*medium*): `OrderSerializer.customer_measurements` sources from `customer.measurements`, a OneToOne on Customer. `saveStep2` rewrites it per order ("the newest dress that carries them wins" — deliberate for the customer record, never reconciled against this order-scoped screen). A client with a lehenga on the table returns for a blouse, is re-measured, and the tailor's blueprint for the first order changes underneath them. → in the assignment card, render `order.garment_jobs[].measurements` generically as key/value pairs (the shape the "What to make" panel already uses) when the order has jobs, falling back to `customer_measurements` when it has none. **Do not index the snapshot by the seven Measurement column names** — the garment job stores template keys (`chest`, `hip`, `floor_length`), so they will all render as "—".
- **Blank "Version 1" in every Sizing Version History** (*low*): `Measurement.save()` sets `changed = True` when `not last_history` and always writes a row; `CustomerSerializer.create` does a bare `Measurement.objects.create(customer=customer)` for every wizard-created customer. → guard the `if changed:` block on at least one of the seven decimals being non-None or `additional_measurements` non-empty. Check `crm_api/test_data_integrity.py:90` (asserts `measurement_history.count() == 1`) before landing.

### 4.11 Tracking page: wrong garment, missing fitting card
*merged from 2 findings · area: tracking*
- `tracking.html:88` renders `{{ customer.garment_type }}` — there is no garment field on Order. The wizard rewrites `Customer.garment_type` on every order, so a repeat customer's **older** tracking link names her newest garment. `notifications.py:46` and three staff screens read the same live field. → snapshot it: add `garment_type` to Order, set it from `customer.garment_type` in `create_order_for_customer`, render `{{ order.garment_type }}`.
- The trial-appointment card never renders: nothing ever sets `Appointment.order`. The booking modal has Client/Type/Date/With/Notes and no order picker; the only client payload spreads `appointmentForm`, which has no `order` key. A comment claims "the tracking page already renders a trial card from them". → add `order: ''` to `appointmentForm` and an order `<select>` to the booking modal restricted to the chosen client's orders. `AppointmentSerializer` is `fields='__all__'`, so the backend already accepts it. **Do not** fall back to `Q(order__isnull=True, customer=order.customer)` — that would show one appointment on every tracking link a repeat customer holds.

### 4.12 Fabric step: empty grids and an impossible filter
*medium · area: order-wizard*
The material tabs are hardcoded `['All','Pure Silk','Zari Silk','Linen','Silk','Cotton']` and compared with `f.material === fabricFilter`, where `material` is a free-text field placeholdered "e.g. Silk Blend". The grids are bare `.filter().filter().map()` with no empty branch, in both step 4 and Manage Fabrics. A boutique typing "Georgette" sees blank areas under every tab but All; a brand-new boutique sees a blank Manage Fabrics page and a blank step 4. (Not unfinishable — the Customer Fabrics tab is a working way past step 4.)
**Fix:** build the tab list from the data — `['All', ...new Set(fabrics.map(f => f.material).filter(Boolean))]` — and add an empty branch to both grids pointing at Add New Fabric.

### 4.13 Double-submit guards on async CTAs
*medium · area: frontend*
`handleSaveFabric`, `handleSaveTailor` and `handleSaveDesign` have no in-flight flag, though the pattern exists twice in the same file (`savingAppointment`, and `runOnce`/`actionInFlight` with a comment describing this exact bug). `DesignStudio.ensureBoard` tests React state, so two quick shortlist clicks create two DesignBoards for one customer — and the board later attached to the order may not be the one the owner built.
**Fix:** `onClick={() => runOnce(handleSaveFabric)}` + `disabled={ctaBusy}` on the three Save buttons; in `ensureBoard`, hold the in-flight create in a `useRef` promise the way `DesignLibrary.jsx:109` already does.

### 4.14 Staff cannot be removed
*medium · area: staff*
`handleDeleteTailor` is declared and referenced nowhere. `api.deleteTailor` exists and `TailorViewSet` is a ModelViewSet. Both staff cards render only Status / Share / Edit.
**Fix:** add a delete button calling `handleDeleteTailor(tailor.id)` next to Edit in both cards. (Note it deletes the Tailor row, not the `User` — pair with 0.4 if account revocation matters.)

### 4.15 Fabricated content on the customer-facing review screens
*merged from 4 findings · area: frontend honesty*
- **Tailor Details card** (*medium*): `getTailorAvatarUrl`/`getTailorTags` switch on first name against rohit/anya/rahul/preeti and otherwise return a fixed stock portrait and `['Custom','Tailoring']`. The card also prints "12+ Years Experience", "98% ON-TIME DELIVERY", "1200+ ORDERS DONE", "5 km FROM BOUTIQUE" — no Tailor field holds any of these. This is the screen staff read back before taking payment. → swap the avatar for the dicebear initials URL already used in `MobileHeader.jsx:65`, delete the two helpers, the tag row, the four fabricated blocks and the two "Rohit Mehra" fallbacks.
- **Delivery date** (*medium*): the review card prints the literal "Standard Delivery" and `Date.now() + 15 days`, while the payload sends the earliest garment `delivery_date` and the real `deliveryMethod` — with a comment saying this is the date the customer must not be told wrong. → hoist `garmentJobs.map(j => j.values?.delivery_date).filter(Boolean).sort()[0]` into a helper and use it; `{deliveryMethod}` for the label.
- **Try-on modal** (*medium*): `getDrapedPreviewImage` is a switch on `fabric.color` returning one of six fixed Unsplash URLs; it reads neither the fabric image nor the design. "Start Try On" is a 2000 ms `setTimeout` captioned "Mapping coordinates onto sketch layers", labelled "✨ 3D Mannequin Draped View", and "Confirm & Save" only calls `setShowDrapingModal(false)`. (A "⚠️ Reference Simulation Only" disclaimer does exist.) → rename the button to "Close", retitle the panel "Colour reference", drop the mapping caption. Persisting a colour-keyed stock photo would be worse than not persisting it.
- **Style DNA** (*low*): both panels print "This is NOT manual entry. AI reads your sales data automatically", while `build_style_dna` derives colour and style by `sha256(str(obj.id))` indexed into six and four canned strings. Budget, size and visit pattern *are* real. → delete the two invented rows and the "AI reads your sales data" line from both panels.

### 4.16 Design Studio pass
*merged from 8 findings · area: design-studio*
Ordered smallest-first, all in `apps/design_studio/` and `frontend/src/features/designStudio/`:
1. **Uploads pinned to the request Host** (*medium*): `views.py:252` persists `request.build_absolute_uri(default_storage.url(saved))` into `image_url`. `resolveMediaUrl` already prefixes `MEDIA_BASE` onto `/media/...`, so storing relative is strictly better and needs no frontend change. → `stored.append(default_storage.url(saved))`. Same edit at `crm_api/views.py:81` and `:184` (see 5.x), which also removes the forged-Host write.
2. **No type or size check on upload** (*medium*): `_store_images` accepts any file, any size, any count — a PDF or a phone `.mov` becomes a cover image that renders permanently broken. Every other upload in the product goes through an `ImageField` (Pillow-validated); this one bypasses it. `accept="image/*"` is client-side only. → reject non-image `content_type` or `size > 10MB` with a 400, and pass `f` to `default_storage.save` instead of `ContentFile(f.read())` so it streams.
3. **Duplicate-email `create_login` returns a 500** (*medium*): guards exist for three cases but not `user.designer_profile`; `Designer.user` is OneToOne, so the assignment raises `IntegrityError` and `core/exceptions.py` is a zero-byte file. The docstring promises "retrying a failed request is always safe". → add a `designer_profile` branch beside the tailor one, returning 400 naming that designer.
4. **"Uncategorised" shows the entire library** (*medium*): the bucket key is `''`, which collapses to `undefined` in `DesignLibrary.jsx:287`, is dropped by `api.js`, and never reaches the filter — and `get_queryset` has no `template__isnull` filter to express it anyway. The endpoint is unpaginated, so it dumps the whole library. → teach `get_queryset` one sentinel (`?template=__none__` → `template__isnull=True`) and send it when `openCategory.key === ''`.
5. **Saved Library ignores search keywords** (*medium*): `LibraryProvider.search` takes `queries` and never references it — only `context.garment_type`, then `[:24]` by `-created_at`. `CatalogueProvider` directly above does the keyword work. Ranking never sees the queries either. → reuse the module-level `_tokens(queries)` and the same `Q(title__icontains) | Q(description__icontains)` with the fall-back-if-empty pattern, before the slice.
6. **Archived designs appear in the grid but not the counts** (*low*): the list endpoint is the only one of three read paths that does not exclude ARCHIVED. → `if not params.get('status'): queryset = queryset.exclude(status=DesignAsset.Status.ARCHIVED)`.
7. **"Trending This Week" is not driven by views** (*low*): the counter uses `.update(view_count=F(...)+1)`, which skips `auto_now` on `updated_at`, while trending filters `updated_at__gte=week_ago`. → include `updated_at=timezone.now()` in the same atomic update (`timezone` is imported).
8. **Gallery photos are stored and never shown** (*low*): the upload modal promises "the rest form the gallery", the backend honours it, and no component reads `design.gallery`. → render it as a thumbnail strip in `DesignDetail` using the `resolveMediaUrl` already on that line.

### 4.17 Performance work — do together, measure after
*merged from 6 findings · area: performance*
1. **`/api/appointments/` nests the full `CustomerSerializer`** (*high*): with no `CUSTOMER_PREFETCH`, and `get_orders`/`get_total_spend`/`get_order_count`/`get_segment`/`get_style_dna` each calling `obj.orders.all()` fresh — each order then through the full `OrderSerializer` with stages, activities, histories, jobs and images. The endpoint runs in `fetchDashboardAndConfig`, i.e. on every login and every mutation refresh, and the frontend reads exactly two names off it. → replace with an inline serializer exposing `id`, `first_name`, `last_name`. One class, no view change; removes the N+1 and the money over-disclosure at once.
2. **`ORDER_PREFETCH` misses two relations its own comment claims to mirror**: `garment_images` and `garment_jobs__materials__inventory_item`. → add both. **Do not** switch the list to `OrderSummarySerializer` — `App.jsx` reads `garment_images` and `garment_jobs` off list rows.
3. **Stock-movement modal downloads every order** on each open, to fill one optional dropdown. → hoist `api.getOrders()` from `MovementModal` up into `InventoryPanel` and pass `orders` down as a prop.
4. **Notifications are unpaginated forever**. → set `pagination_class = PageNumberPagination`, `page_size = 50` on `NotificationViewSet` **only**, and change `fetchNotifications` to `setNotifications(data.results || data)`. `mark_all_read` calls `get_queryset()` directly, so it is unaffected. **Do not** set a global `DEFAULT_PAGINATION_CLASS` — `getOrders`, `getCustomers`, `getTailors`, `getFabrics` and `getAppointments` all consume bare arrays and would break immediately. **Do not** slice `get_queryset()` — Django raises on `filter().update()` against a sliced queryset.
5. **Every save refetches all ten collections** behind `setLoading(true)`, from 26 call sites, flickering the dashboard order panel to "Loading active orders…" on every stage tap. → give `fetchDashboardAndConfig` a `{ background = false }` option that skips `setLoading(true)`, and pass it from the mutation handlers. One flag; skip the 26-site rewrite.
6. **Missing indexes** (*low, per-tenant schemas keep tables small*): `OrderStage.Meta` → `indexes = [models.Index(fields=['stage_key', 'status'])]`; `Notification` has no Meta at all → `indexes = [models.Index(fields=['recipient_role', 'recipient_email', '-created_at'])]`. Skip a `(title, is_read)` index — `_raise_alerts` only fires on a stock-level crossing.
7. **`DesignBoard.selected_item` bypasses the prefetch cache** (`.filter()` on a related manager). → `next((i for i in self.items.all() if i.is_selected), None)`.

### 4.18 Bound the tenant cache
*medium · one line · area: middleware*
`tenants/middleware.py:16` `_tenant_cache = {}` has no bound and no eviction; line 37 assigns unconditionally including the `tenant=None` negative result; the TTL check only declines to *return* a stale value. The key is the raw `X-Tenant-ID` header — unauthenticated, unvalidated beyond `!= 'public'`, up to ~8KB. A loop of random values adds a permanent dict entry per request until the worker is OOM-killed. The comments justify caching and negative caching; neither addresses growth.
**Fix:** before the assignment — `if len(_tenant_cache) > 1000: _tenant_cache.clear()`.

### 4.19 Failed customer messages vanish from the owner's queue
*low today, medium the day a transport is configured · area: messaging*
`customer_messages` filters `status='QUEUED'`; `_deliver` sets FAILED on any transport exception; the recorded `error` is never read. The frontend already dims non-QUEUED rows but gates the action buttons on `status === 'QUEUED'`. Unreachable in the shipped config (`CUSTOMER_MESSAGE_BACKEND` defaults to `''`).
**Fix:** filter `status__in=('QUEUED','FAILED')` and change the frontend gate to `message.status !== 'SENT'`. While there, accept `customer_messaging_enabled` in `BoutiqueSettingsViewSet.create` beside `design_approval_required` and add the matching checkbox — currently it cannot be turned off without a DB shell. Leave `workflow_config` alone; per-tenant workflow editing is a feature.

---

## PHASE 5 — Real but cosmetic. Batch into one cleanup PR.

| # | What | Fix |
|---|---|---|
| 5.1 | Invoice line item is tax-inclusive above a Subtotal+Tax=Total block (₹33,075 / ₹31,500 / ₹1,575 / ₹33,075) | Print `total_amount - taxes` in the Amount cell — same expression as the Subtotal row |
| 5.2 | Orders, Customers and Invoices all say "nothing matching the filters" on day one, with no filters set and no CTA | Branch first on the unfiltered source being empty; render a first-run message with the existing CTA (the dashboard's own orders panel already gets this right) |
| 5.3 | "Style Inspiration" is three hardcoded Unsplash portraits of strangers, no behaviour | Render the first three `allDesigns` with `onClick={() => setDashboardTab('designs')}`, or delete the panel |
| 5.4 | Three inert sidebar items on the order-selector (My Orders / Appointments / Measurements) between two working links; "Need help?" styled clickable with no handler | Delete them |
| 5.5 | "Remember me" checkbox is uncontrolled, unread, `defaultChecked`; the session always persists | Delete the checkbox and label. Wiring it to sessionStorage means touching four api functions for a preference nobody asked for |
| 5.6 | Mobile header search opens a field wired to nothing (`onSearch` has no caller) | Delete the search button and the `searchOpen` branch |
| 5.7 | "Chat Now" in the staff sidebar opens `wa.me/919876543210` — an invented number belonging to nobody | Render only when `boutiqueSettings?.phone` is set, and open that |
| 5.8 | Confirmation-screen WhatsApp link is `wa.me/91${raw_mobile}` → `wa.me/91+91 98765 43211` for any formatted number | Strip non-digits before building the URL; reword the caption to "Message this client on WhatsApp" |
| 5.9 | "Registered Since: June 2024" is a string literal on every boutique's profile | Add tenant `created_on` to `MeView` and render it, or delete the row |
| 5.10 | Recipes tab claims "An order reserves against the recipe" — nothing ever does; the Cost-per-order report panel can never populate (`OrderMaterialLine` is only built by `plan_materials`, which has no caller) | Drop the reservation claim from the copy; remove or relabel the Cost-per-order section |
| 5.11 | Deleting a recipe line has no confirmation (every comparable destructive action does) | `if (!window.confirm(...)) return;` inside `remove()` |
| 5.12 | `preferred_communication` is collected from every customer and read by nothing | Gate only automatic delivery: `if get_backend() is not None and order.customer.preferred_communication == 'WhatsApp':`. **Do not** return early from `send_customer_message` — that deletes the queued row, which is the owner's to-do list |
| 5.13 | No-stage status changes (Shipped, Stylist Review) write no `OrderActivity` — a delivery dispute has no attribution | One `OrderActivity.objects.create(...)` beside the `create_order_notifications` call |
| 5.14 | `CustomerMaterialMovement.Type.CORRECTION` has no writer, so a mis-typed receipt can only be undone by a false RETURNED line | Add CORRECTION to the map in `record_customer_material` with a signed delta bounded at zero |
| 5.15 | Deleting an order cascades away its material plan and the customer's material ledger, stranding reservations | `perform_destroy` on `OrderViewSet` calling `order_materials.cancel()` on any live plan first. Do not touch the CASCADEs |
| 5.16 | `_as_quantity` compares outside its `try`, so `'nan'` raises `InvalidOperation` (an `ArithmeticError`, not `ValueError`) → 500; `'Infinity'` sails through | Move the comparison inside the try, add `if not quantity.is_finite() or quantity <= 0 or quantity >= 10**9: raise ValueError(...)`; same for `adjust`'s `counted` |
| 5.17 | Reports dashboard threads the date window into four panels but not `supplier_performance`, which shows all-time figures with no label | `supplier_performance(since=since, limit=10)`. Leave `cost_per_order` alone (see 5.10) |
| 5.18 | Login binds an email to whichever tenant is found first and never tries another — a freelance tailor at two boutiques can only sign in to one | Make `find_tenant_for_account` yield candidates; have `LoginView.post` try each, returning the credentials error only after all fail. Keep the reset views on the first match |
| 5.19 | Book Appointment dead-ends for a boutique with no customers (required Client select, no options, no CTA) | When `allCustomers.length === 0`, render a line of text plus a button calling `handleStartNewCustomer()` — the inline-add pattern already used for missing tailors |

---

## MISSING FEATURES — not bug fixes. Scope separately.

These cannot be "fixed"; they must be built. Sizes assume one engineer familiar with the codebase after Phases 0–2.

| Feature | Why it is a feature | Size |
|---|---|---|
| **Multipart upload for garment-job files** | 1.7 removes the affordance. Restoring it needs: a media upload endpoint for garment jobs, `FormData` in `saveGarmentJobs`, server-side storage + spec normalisation, and re-adding the four `COMMON_PRODUCTION` fields *plus* a resync migration alongside `apps/catalog/migrations/0003_resync_templates.py` (definitions.py changes do not reach already-seeded tenants). Note the `audio_note` help_text promises transcription — nothing in the repo transcribes anything; either build it or reword. | **1–2 weeks** |
| **Edit / archive / delete for uploaded designs** | `DesignLibraryPermission.OWN_UPLOAD_ACTIONS` with its `created_by` ownership check already exists server-side and is unreachable: `services/api.js` has no PATCH or DELETE against `/design-studio/assets/<id>/`, and `BoutiqueDesignViewSet` filters to catalogue/suggestion so the catalogue endpoints physically cannot reach an upload. Uploads land ACTIVE (approval off by default) and `review` only moves PENDING rows, so they cannot be archived either. A wrong photo or duplicate is permanent and keeps being returned into the discovery gallery. | **2–4 days** (API client + route non-catalogue sources through it) |
| **Order-materials and customer-material screens** | Twelve `api.js` functions (`planMaterials`, `reservePlan`, `consumePlanLine`, `releasePlanUnused`, `deductPlanPackaging`, `reconcilePlan`, `closePlan`, `cancelPlan`, `receiveCustomerMaterial`, …) have **zero callers**. There is no Materials tab. The whole backend lifecycle — including 2.8's wedge and 5.15's cascade — is unreachable from the product. | **3–4 weeks**, and only if the business wants it. Otherwise delete the dead API client functions and the copy that references them |
| **Real SMS/OTP verification** | 4.3 deletes the theatre. Building it means an SMS provider, a verification model, a resend path and rate limiting. The product's only outbound channel today is email. | **1 week** + provider cost |
| **Per-tenant workflow_config editing** | `BoutiqueSettingsViewSet.create` writes six fields; `workflow_config` is written only by tests and migrations. Boutiques cannot adjust stage roles or SLA hours without DB access. | **1–2 weeks** (needs a stage-role editor UI, not just a field) |
| **A real try-on / draping render** | 4.15 relabels the placeholder honestly. A genuine composite needs a render service. | **Unscoped — external dependency** |
| **Object storage for media** | The persistent-disk workaround (D.4) is the deploy-day fix. `crm_api/storage.py`'s `SupabaseStorage` exists but is bypassed because bucket RLS rejects the publishable key. Doing it properly means fixing the bucket policy or moving to S3/R2, plus a migration of existing paths — which must be coordinated with 3.6's schema-namespacing. | **3–5 days**, do both storage changes in one migration or not at all |

---

## DEPLOYMENT / INFRA — no code change, or code plus an ops step

| # | Action | Severity |
|---|---|---|
| D.1 | **Rotate the Supabase `postgres` password** (0.1). Set on Render and in local `.env`. | critical |
| D.2 | **Generate and set `DJANGO_SECRET_KEY` on Render**; add it to `README.md:134`'s env list (0.2). Invalidates outstanding tracking links — intended. | critical |
| D.3 | **Set a real `DJANGO_SUPERUSER_PASSWORD`** and confirm the hosted admin account no longer accepts `admin123` after 0.3 deploys. | critical |
| D.4 | **Attach a Render persistent disk mounted at `MEDIA_ROOT`.** Today uploads live on ephemeral disk — `boutique_crm/urls.py:60-62` says so outright: every fabric swatch, design reference, stage photo and finished-garment image is lost on the next deploy while DB rows keep pointing at 404s. There is no `render.yaml` and the README documents no disk. Until it lands, the deploy guide must say plainly that uploads do not survive a deploy. | **high — silent permanent loss of the boutique's own photography** |
| D.5 | **Fix `README.md:38`** — it documents the transaction pooler on port `6543`, which `settings.py:141-161` explains at length caused queries to run against `public` and intermittent `401 Invalid token` (measured: 12 concurrent requests → 9×200, 2×401, 1×500), and is why `DB_PORT` defaults to `5432`. Also change `DB_PORT` to 5432 in the local `.env`. An operator following the README reintroduces a tenant-isolation bug. | medium |
| D.6 | **Set `DJANGO_ALLOWED_HOSTS`** to the real service hosts and add it to the README env list (currently defaults to `'*'`). | low |
| D.7 | **Add `LOGGING` to settings.** No `LOGGING`, no `ADMINS`. With `DEBUG=False`, Django's default config attaches `console` (filtered to debug-only) and `mail_admins` (no recipients) to the `django` logger — and because handlers *are* attached, `lastResort` never fires, so **every 500 traceback is silently discarded**. `gunicorn` errorlog only carries worker-level errors. No Sentry in requirements. → an unfiltered `StreamHandler` on stderr bound to `django` and root; gunicorn already forwards stderr to Render's log stream. | medium — makes every other bug slower to diagnose |
| D.8 | **Static files for `/admin/`.** No `STATIC_ROOT`, no whitenoise, no `collectstatic` in the build command, and `urls.py` serves only `^media/`. The `/admin/` back door the README designates for "when the console itself is what is broken" renders as unstyled HTML with no JS, so the `raw_id_fields` lookups on the Order admin do not work. → `STATIC_ROOT`, whitenoise after `SecurityMiddleware`, `collectstatic --noinput` appended to the Render build command. | medium |
| D.9 | **Pin `gunicorn` and `requests`** in `requirements.txt` (lines 9-10 are bare while the other eight are exact-pinned; build is a plain `pip install -r`, no lockfile). Installed today: `gunicorn==26.0.0`, `requests==2.34.2`. A redeploy with an empty diff can pull a new gunicorn major and change proxy/scheme handling. | low |
| D.10 | **Secure cookies.** No `SECURE_*`, `SESSION_COOKIE_*` or `CSRF_COOKIE_*` anywhere; `SecurityMiddleware` runs on insecure defaults. Only the `/admin/` session cookie is at risk (the React app uses a token header, `CORS_ALLOW_CREDENTIALS = False`). → gate `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT`, `SECURE_HSTS_SECONDS` on `not DEBUG`. | low |
| D.11 | **`.gitignore` covers only `media/design_library/`** despite stating the intent to exclude all uploads. `git ls-files media` returns 16 files including `customer_profiles/DOMS_LOGO.png` and two customer-scoped fabric shots under `media/fabrics/cust_<uuid>/`. → replace with `media/` plus `!` un-ignores for the seeded catalogue images, and `git rm --cached` the tracked customer files. | low |
| D.12 | **Signup runs the full migration set inside a 60s gunicorn timeout** (`gunicorn.conf.py:33`) — the trigger for 4.3's orphan-tenant case. Measure real tenant-creation time on the production instance tier; if it is anywhere near 60s, raise the timeout or move tenant creation off the request. | unknown — needs measurement |
| D.13 | **Verify a backup and restore actually work.** Nothing in this repo touches backups. Given 0.6's wipe potential and the volume of destructive paths audited, confirm Supabase PITR is enabled and that a restore has been rehearsed. | high |

---

## What could not be verified without a running app and a real database

Be honest about these — several affect how the items above should be prioritised:

- **Whether the hosted database is the one `boutique_crm.sql` came from.** The dump's `admin`/`admin123` hash was recomputed and confirmed, but that proves the *dump*, not production. 0.3 is written to be safe either way.
- **Whether media currently exists on the live disk.** D.4 says every upload is lost on redeploy; whether anything has already been lost, and how much, is unknown. Check the disk before deploying anything else — a redeploy is destructive here.
- **The blast radius of 2.5.** How many customers have repeat orders at identical amounts determines whether the directory has been under-reporting spend for months or is merely theoretically wrong. One query against production answers it.
- **Whether the `visible_customers` rewrite in 2.5 changes disclosure.** Reasoning says no (the aggregate already spans all of the customer's orders on the tailor path), but this needs a test against real multi-role data before it ships.
- **Real query counts for 4.17.** The N+1s are structurally certain from reading the serializers; the actual per-request numbers, and whether the appointment fix alone is enough, need `django-debug-toolbar` or query logging against a populated tenant.
- **Whether tenant migrations fit inside the 60s gunicorn timeout** (D.12) — the single most likely real-world trigger for the orphan-tenant bug.
- **Whether the tenant-cache OOM (4.18) is actually reachable** before some upstream limit (Render request limits, header size caps) kicks in. The fix is one line, so it is not worth measuring first.
- **Migration of existing media paths under `TenantFileSystemStorage`** (3.6). Existing rows point at `media/<dir>/…`; those files must be physically moved to `media/<schema>/<dir>/…` or every existing image breaks. Requires the live filesystem to plan.
- **Whether any tenant currently has staff logins created with the shared password.** 0.4 stops new ones; existing accounts keep the published credential until reset. After deploying 0.4, audit `auth_user` per schema and force resets — that is an ops task, not a code change.