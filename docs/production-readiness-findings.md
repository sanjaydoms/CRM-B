# Boutique CRM — confirmed audit findings

145 findings, each verified against the source by a second agent tasked with refuting it.
Line numbers drift (App.jsx is edited concurrently) — grep the quoted code before editing.
The consolidated, de-duplicated execution order is in production-readiness-plan.md.


## CRITICAL

### Live Supabase database password is in git history and is still the password in use
`.env:3`

**Impact.** Anyone who has ever cloned this repository holds a working credential for the Supabase `postgres` role on the single instance that hosts every boutique's schema. That is direct read/write/DROP over every tenant's customers, measurements, phone numbers, orders and revenue, entirely bypassing TenantHeaderMiddleware and core/permissions.py.

**Evidence.** Confirmed by reading, not by assumption. `git log --all -S"MSK1122"` returns two commits (da7341f introduced it, 6d4b55c removed it) and iterating every commit shows `MSK1122` present in boutique_crm/settings.py across a long run of history (c371cf5, 09baf67, c61c995, c1f0d63, 55fed97, ...). The current .env line 3 is DB_PASSWORD with an 11-character value that `grep -n MSK1122 .env` matches — i.e. byte-identical to the literal in history, and 'MSK1122@msk' is exactly 11 characters. .env line 4 is DB_HOST=aws-1-ap-southeast-1.pooler.supabase.com and line 2 is DB_USER=postgres.gbdabwahffdgdykbujpx, which is the same project ref boutique_crm/settings.py:138 still carries as its default. docs/scaleezy-product-architecture.html:1047 does claim "the database password has been rotated" — that claim is false against the file on disk. Current settings.py:139 has an empty default, so the code itself is clean; the credential is live in history and unrotated.

**Fix.** Rotate the password in the Supabase dashboard, set the new DB_PASSWORD in Render and in the local .env, and delete the false 'has been rotated' sentence at docs/scaleezy-product-architecture.html:1047. Rewriting history is not required and not the point — the credential must simply stop working.

### SECRET_KEY falls back to a committed literal, so anyone can forge a tracking token for any order in any boutique
`boutique_crm/settings.py:44`

**Impact.** With the key known, anyone can mint tracking tokens for any (schema, order_id) pair — schema names are public, since tracking.py:35-37 documents the payload as readable base64 — and read every customer's name, phone, address, stage history, total/paid/balance, trial appointment and published garment photos across every boutique. Nothing expires, nothing is logged.

**Evidence.** Opened settings.py:44-46: SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-local-development-only-do-not-use-in-production') with no comment and no fail-fast, sitting two lines above DEBUG which does carry a justifying comment — so this is not one of the deliberate, documented tradeoffs. Contrast create_superuser.py:33-41, which sys.exit()s with an explanatory comment rather than fall back to a literal, proving the codebase knows the pattern. The repo-root .env sets only DB_NAME/DB_USER/DB_PASSWORD/DB_HOST/DB_PORT/SUPABASE_URL/SUPABASE_KEY/DJANGO_DEBUG — no DJANGO_SECRET_KEY — and README.md's Render 'Environment Variables' list (DB_PASSWORD, SUPABASE_KEY/URL, DJANGO_SUPERUSER_PASSWORD, WEB_CONCURRENCY, TRACKING_BASE_URL, CORS_ALLOWED_ORIGINS) never names it, so a deploy that follows the README runs on the published key. domains/orders/tracking.py:38-41 signs {'s': schema, 'o': order_id} with exactly that key, and crm_api/tracking_views.py:31-49 trusts the payload after only checking that the schema row still exists; domains/orders/services.py:15-21 draws order ids from T2B-YYMMDD-NNNN, 9000 values per day, so a forged token plus enumeration walks a whole day's order book. The auditor's cites all check out.

**Fix.** In boutique_crm/settings.py:44, refuse the literal outside DEBUG the way create_superuser.py refuses a missing password: read DJANGO_SECRET_KEY, fall back to the dev literal only when DEBUG, else sys.exit with a message naming the variable. Add it to the README Render env list and rotate once (which invalidates outstanding links, as tracking.py's own ponytail note says).

### SECRET_KEY falls back to a committed literal and is not in the deploy variable list — forged tracking tokens read any boutique's orders
`boutique_crm/settings.py:44`

**Impact.** With the key known, an outsider mints tracking tokens at will. One genuine link leaks the schema name (the payload is plain base64 JSON, as tracking.py's docstring states), and 9000 guesses per date walks that boutique's whole order book — customer names, garment details, money owed — unauthenticated at /track/<token>/.

**Evidence.** Verified end to end. settings.py:44-47 defaults SECRET_KEY to 'django-insecure-local-development-only-do-not-use-in-production'. `grep -rn DJANGO_SECRET_KEY` over .py/.md/.sh/.html finds exactly one hit — settings.py:45 itself; it is absent from README.md's Render environment-variable list (README.md:134-163, which names DB_PASSWORD, SUPABASE_KEY, SUPABASE_URL, DJANGO_SUPERUSER_PASSWORD, WEB_CONCURRENCY/GUNICORN_THREADS, TRACKING_BASE_URL, CORS_ALLOWED_ORIGINS) and from start.sh, so nothing tells a deployer to set it. `git log --all -S"django-insecure-gaq"` confirms the prior real key is recoverable from da7341f/6d4b55c, and docs/scaleezy-product-architecture.html:1047 itself admits "the secret key still needs rotating". The exploit path is real: domains/orders/tracking.py:38-41 mints tokens with signing.dumps({'s': schema, 'o': order_id}, salt='crm.order-tracking') — HMAC over SECRET_KEY and nothing else, no per-order nonce (the module docstring says so) — and crm_api/tracking_views.py:31-104 accepts any validly signed token with no authentication and renders customer name, stages, total, paid and balance. Order ids are enumerable: domains/orders/services.py:17 builds T2B-YYMMDD-NNNN over 9000 slots per day.

**Fix.** In boutique_crm/settings.py, keep the dev literal only under DEBUG and `raise ImproperlyConfigured` when DJANGO_SECRET_KEY is unset and DEBUG is False, so a deploy cannot silently boot on the public key. Then generate a fresh key, set DJANGO_SECRET_KEY on Render, and add it to README.md:134's list. Rotating invalidates outstanding tracking links, which is the intended effect.

### Every staff and designer account is created with one bootstrap password that is published in this repo and in the JS bundle
`crm_api/views.py:272`

**Impact.** Anyone with the repo or the shipped bundle can sign in as staff at any boutique on the platform by guessing a first-name-shaped username, and then read that boutique's customer names, phones, addresses and order book. Departed staff keep working credentials everywhere, not just where they worked.

**Evidence.** Opened crm_api/views.py:264-275: the comment says 'Shared bootstrap password for staff accounts. Override with TAILOR_DEFAULT_PASSWORD; every tailor otherwise shares one credential that is visible in this repository' — it names the risk, it does not resolve it. password=os.environ.get('TAILOR_DEFAULT_PASSWORD','TailorSecure2026!') is real, and apps/design_studio/views.py:513-517 does the same with DESIGNER_DEFAULT_PASSWORD/'DesignerSecure2026!'. The literal is shipped to the browser (frontend/src/App.jsx:5757, 5769, 5783; frontend/src/features/designStudio/DesignDashboard.jsx:11). Usernames are the email local-part (views.py:270 tailor.email.split('@')[0]; design_studio/views.py:504). crm_api/auth_views.py:47-57 (find_tenant_for_account, called by LoginView at line 231) scans every non-public schema for a matching email OR username, so one unauthenticated POST to /api/auth/login/ with a guessed local-part plus the published password finds whichever boutique has such a staff account. boutique_crm/settings.py:376-383 confirms only 'password_reset' is throttled — login is not rate limited at all. CORRECTION to the auditor: the claim 'no one can ever change it' is false — PasswordResetRequestView/PasswordResetConfirmView exist (crm_api/auth_views.py:354-486, urls.py:26-29) and call user.set_password at line 475, and they resolve staff accounts through the same find_tenant_for_account. The severity stands anyway: the bootstrap window is unauthenticated remote access to a live tenant's data, and nothing forces a reset.

**Fix.** In crm_api/views.py:_ensure_user_account and apps/design_studio/views.py:create_login, replace the shared constant with secrets.token_urlsafe(9) per account and return it once in that response (a write-only 'bootstrap_password' key on the serializer output for the create/create_login call) so the owner hands over a unique password. Same change also fixes the next finding.

### Owner opening any production stage on a designed order crashes the whole workspace
`frontend/src/App.jsx:8408`

**Impact.** An Owner clicking any stage on the timeline of an order that went through the Design Studio loses the entire workspace to the runtime-error screen and must reload. That modal is the only place stages are started/paused/completed (App.jsx:8614-8720), so production on designed orders cannot be run from the Owner account at all.

**Evidence.** Confirmed, only the line numbers were off (guard is at 8404, first deref at 8408). Read apps/design_studio/views.py:585-594: get_serializer_class returns TailorBriefSerializer only when the caller has a tailor_profile AND is not Owner; every Owner gets DesignBoardSerializer, whose fields are DesignBoard model fields plus items/selected/customer_name/order_id_display (serializers.py:110-123) — the model (models.py:292-331) has no `design` field, so `design` is undefined for an Owner. TailorBriefSerializer is the only one emitting `design` (serializers.py:130-159). So for an Owner viewing a board with a selected item, `stageDesignBrief.selected` is truthy, the guard passes, and 8408 `stageDesignBrief.design.image_url` throws. App.jsx:1790 confirms an error boundary renders 'Atelier CRM Runtime Error', so the whole workspace unmounts. openStageReview:1707 has the same latent shape (`brief?.design?.production_notes`) but is optional-chained. The comment at 8397-8403 explains why the block exists, not this bug.

**Fix.** Agree with the fetch-site normalisation: in openStageReview (App.jsx:1703-1708) store `setStageDesignBrief(brief ? { ...brief, design: brief.design || brief.selected } : null)`. One edit fixes the guard, all three derefs and the production-notes deref for every role.


## HIGH

### /api/catalog/jobs/ has no order scoping, so any staff account reads every client's body measurements and garment spec
`apps/catalog/views.py:88`

**Impact.** A tailor who is correctly scoped out of another tailor's order by visible_orders can GET /api/catalog/jobs/ and receive every garment on every order in the boutique, including each client's full measurement set and design spec.

**Evidence.** Confirmed exactly as cited. GarmentJobViewSet (apps/catalog/views.py:85-94) declares no permission_classes and its get_queryset applies only the optional `?order=` filter — no visible_orders, no user. It therefore inherits RolePermission, whose non-Owner branch returns True for every SAFE_METHOD (core/permissions.py:74-75). GarmentJobSerializer exposes `spec` and `measurements` plus the order (apps/catalog/serializers.py:81-92), and GarmentJob.measurements is the per-dress numeric snapshot (apps/catalog/models.py:170-176). The sibling apps were fixed for precisely this and say so: apps/production/views.py:12-20 ('RolePermission grants every non-Owner staff member all SAFE_METHODS, which is only safe because each viewset narrows its own queryset') and apps/scheduling/views.py:14-31. The route is live at /api/catalog/jobs/ (apps/catalog/urls.py:8). Not cross-tenant (django-tenants schemas isolate boutiques), so high rather than critical.

**Fix.** Scope GarmentJobViewSet.get_queryset (apps/catalog/views.py:88) the way the siblings do: `from core.permissions import visible_orders` + `from crm_api.models import Order`, then `queryset = queryset.filter(order__in=visible_orders(Order.objects.all(), self.request.user))` before the `?order=` filter.

### Purchase-order receipt is not atomic: a rejected later line leaves earlier lines already stocked in
`apps/inventory/views.py:318`

**Impact.** An owner booking a multi-line delivery who mistypes one quantity gets a 400 saying the receipt failed while the earlier lines are already in stock with PURCHASE ledger rows. Correcting and resubmitting counts those lines twice, so on-hand quantity and inventory value are permanently wrong with only a duplicate ledger pair as evidence.

**Evidence.** Confirmed by reading apps/inventory/views.py:317-360. `receive` carries only `@action(...)` -- no `@transaction.atomic` and no `with transaction.atomic()` in the body (the file's only atomic block is at :588, a different action). The per-line work at :331-355 calls `InventoryService.purchase`, which routes to `record_movement` decorated `@transaction.atomic` at apps/inventory/services.py:59 -- so each line commits independently -- then `line.save(update_fields=...)`. The over-receipt ValueError at :344 and the unknown-line ValueError at :335 are both caught at :356 and returned as 400 after earlier lines have already committed their StockMovement and stock increment. `from django.db import transaction` is already imported at line 1.

**Fix.** Agree. Wrap the body of PurchaseOrderViewSet.receive from the `lines_by_id` build through `purchase_order.save(...)` in `with transaction.atomic():`, leaving the `except ValueError` handler outside the block so the rollback completes before the 400 is returned.

### /api/appointments/ nests the entire CustomerSerializer with zero prefetching
`apps/scheduling/serializers.py:6`

**Impact.** The endpoint is in fetchDashboardAndConfig (App.jsx:1018), so it runs on every login and after every mutation refresh. A calendar of a few dozen appointments costs hundreds to low-thousands of round trips against a pooled remote Postgres, and ships every client's full order history and money to render two names.

**Evidence.** Confirmed. AppointmentSerializer:6 is `customer_detail = CustomerSerializer(source='customer', read_only=True)`, and AppointmentViewSet (apps/scheduling/views.py:10, :30) only ever chains `select_related('customer','order','assigned_staff')` plus a `customer__in` filter -- CUSTOMER_PREFETCH is never applied. I read CustomerSerializer: `measurement_history`, `design_preferences`, `fabric_selections` are nested many=True (crm_api/serializers.py:339-341) and get_orders (:348) builds `visible_orders(obj.orders.all(), user)`, a fresh filtered queryset that cannot use a prefetch cache even if one existed. get_total_spend (:397), get_order_count (:400), get_segment (:403, calling both) and get_style_dna (:415) each call `obj.orders.all()` again -- with no prefetch each is its own round trip. Each order then goes through the full OrderSerializer with its stages, activities, stage_histories, garment_jobs and garment_images. The long docstring at views.py:16-28 is about tenant/role scoping only; it does not address or excuse the query cost. Correcting the auditor's frontend citation: the only consumers are App.jsx:3138-3141 (`appt.customer_detail.first_name`/`last_name` and `assigned_staff_detail.name`), not :3169/:3171.

**Fix.** Agree with the auditor. In apps/scheduling/serializers.py replace the nested CustomerSerializer with an inline two-field serializer (`id`, `first_name`, `last_name`) -- the only fields App.jsx:3138-3139 reads. One class, no view change, and it removes both the N+1 and the over-disclosure of order money at the same time.

### Uploaded media is written to Render's ephemeral disk and is lost on every redeploy
`boutique_crm/settings.py:360`

**Impact.** Every fabric swatch, design reference, stage progress photo and finished-garment image a boutique uploads disappears on the next deploy while the database rows keep pointing at now-404ing URLs. The customer tracking page's gallery (crm_api/tracking_views.py:84-88) and the design library go blank — silent, permanent loss of the boutique's own photography.

**Evidence.** Confirmed, and the surrounding comment does not defend it as a sound tradeoff — it states the defect and defers the fix, so rule 2 does not exempt it. settings.py:348-360 sets STORAGES default to FileSystemStorage with MEDIA_ROOT = BASE_DIR/'media', explicitly bypassing crm_api/storage.py's SupabaseStorage because bucket RLS rejects the publishable key. boutique_crm/urls.py:60-62 says it outright: "Uploads still live on Render's ephemeral disk, so anything a user uploads is lost on the next deploy. Fixing that means real object storage, not a URL route." Write paths verified at crm_api/views.py:79 and :182, domains/orders/services.py:398 and apps/design_studio/views.py:250, plus the ImageField upload_to prefixes in crm_api/models.py. README.md:113-163 documents build command, start command, region, env vars and instance tier with no persistent disk, and there is no render.yaml in the repo.

**Fix.** Attach a Render persistent disk mounted at MEDIA_ROOT and document it in README.md's deployment guide — that is the change that does not require fixing the Supabase bucket policy first. Until it lands, the deploy guide must say plainly that uploads do not survive a deploy.

### Every new boutique is seeded with four invented employees, five priced fabrics and a priced catalogue
`crm_api/utils.py:3`

**Impact.** A day-one owner's first order can be assigned to a person who does not exist and priced at another business's fabric rate, and that price prints on the invoice and reaches the customer.

**Evidence.** Confirmed by reading the whole function. seed_tenant_defaults (crm_api/utils.py:3) is called unconditionally from SignupView at crm_api/auth_views.py:150 with no DEBUG or demo flag and no explanatory comment at either site. It creates Tailor rows for Rohit Mehra (Master, rating 4.90), Anya Sharma, Rahul Verma and Preeti Singh (utils.py:5-16); five BoutiqueFabric rows with real prices, Silk Dupion 1850/m and Banarasi Silk 2850/m among them (utils.py:19-25); and eleven DesignAsset rows including catalogue items at 45000/38000/32000 (utils.py:37-151). Those fabric prices reach money: frontend/src/App.jsx:1406 sets fabric_price = selectedFabric.price_per_meter * 3 on the order, which then prints on the invoice (App.jsx:8138, 8182). The seeded tailors have no email so no User is created (crm_api/views.py:238 guard), and they cannot be removed from the UI (previous finding). The contrast the auditor cites is real: the appointments panel comment at App.jsx:3142-3147 explicitly removed invented content with 'An empty panel is better than an invented one', and that reasoning was never applied here.

**Fix.** Give seed_tenant_defaults a `demo=True` parameter in crm_api/utils.py:3 that gates the three literal lists, and pass demo=False from the SignupView call at crm_api/auth_views.py:150 — SeedDataView (auth_views.py:507) and seed_data.py:73 keep the demo path. The order wizard already handles an empty roster (App.jsx:6894, 6951).

### Customer lifetime spend uses SUM(DISTINCT), so two orders of the same amount count once
`domains/customers/repositories.py:42`

**Impact.** Two ₹40,000 orders show a lifetime spend of ₹40,000 on the Customer Directory list and the dashboard recent-customers panel, and the segment badge reads HVC where the customer detail banner for the same person reads VIP. Repeat orders at a repeated price point are the normal case in a boutique, so the segmentation is wrong for precisely the highest-value clients, and two screens contradict each other about the same person.

**Evidence.** Confirmed by reading the function and its comment. The comment at lines 34-40 explains why distinct=True was added (a tailor's visible_customers join through orders__stages__assigned_to multiplies each order row fifteen times), but distinct on Sum/Avg is SUM(DISTINCT col) — de-duplication by VALUE, not by row — so the stated cure does not treat the stated disease and instead collapses equal order totals for EVERY role, owner included (an owner has no join multiplication at all, yet still gets SUM(DISTINCT)). Count('orders', distinct=True) is the only one of the four where distinct is correct. Cross-checked the two consumers: crm_api/views.py:53 (directory list) and crm_api/views.py:919 (dashboard recent_customers), both of which route through summary_queryset, and CustomerSummarySerializer.get_total_spend (crm_api/serializers.py:510) reads orders_total_spend straight through into the VIP/HVC threshold at line 519. The detail path is genuinely different: CustomerSerializer.get_total_spend (crm_api/serializers.py:398) sums the actual order rows, so the two screens do disagree. I also opened the tests the auditor named: test_spend_totals_every_order (crm_api/test_data_integrity.py:126) uses [1000, 2500, 500] — three distinct values, so SUM(DISTINCT) happens to give the right 4000 — and test_vip_by_order_count (line 113) uses [1000,1000,1000] but asserts only segment, which passes on order_count>=3. Neither test can catch this.

**Fix.** Agreed with the direction but the simpler edit is enough: in CustomerRepository.summary_queryset (domains/customers/repositories.py:42-43), drop distinct=True from the Sum and Avg and replace each with a correlated Subquery over Order (Subquery(Order.objects.filter(customer=OuterRef('pk')).values('customer').annotate(s=Sum('total_amount')).values('s')) and the matching Avg). Merely dropping distinct=True is NOT sufficient — the multiplication the comment describes is real for a tailor, so the subquery is required to make the figure correct for both roles. Leave orders_count=Count(..., distinct=True) alone; it is correct. Update the comment so the next reader does not re-add distinct.

### Customer total spend uses SUM(DISTINCT), so two orders of the same value count once
`domains/customers/repositories.py:42`

**Impact.** Any client with two or more orders at the same price -- the ordinary repeat-order pattern -- has their lifetime spend under-reported by the duplicated amounts. CustomerSummarySerializer.get_total_spend (crm_api/serializers.py:509) and get_segment (:516) then grade them a tier low, and build_style_dna's budget band (via orders_avg_price at :528) is skewed the same way. Applies on the Owner's plain LEFT JOIN too, not just the tailor path.

**Evidence.** Confirmed by rendering the SQL through the project's own venv: `COUNT(DISTINCT "crm_api_order"."id") AS "orders_count", SUM(DISTINCT "crm_api_order"."total_amount") AS "orders_total_spend", AVG(DISTINCT "crm_api_order"."total_amount") AS "orders_avg_price"`. The explanatory comment at :35-40 is present but its reasoning is wrong: distinct=True on Count dedupes rows (it is on the pk), while on Sum/Avg it dedupes the *value*. I also rendered the tailor-scoped variant and found the annotation uses the first unfiltered `LEFT OUTER JOIN crm_api_order` while the visible_customers filter lands on a second alias `T3` joined to crm_api_orderstage -- so the multiplication the comment blames is real, but it comes from the T3/orderstage cartesian, and the aggregate is over all orders either way. The repo's own test at crm_api/test_data_integrity.py:107 builds a customer with [1000, 1000, 1000] and asserts only `segment` (VIP by count), never total_spend, which is why this survived. Downgraded from critical: it corrupts a derived analytics figure on the directory and dashboard, not an invoice or a stored amount.

**Fix.** Two-line root fix, not the auditor's Subquery rewrite. (1) In core/permissions.visible_customers (core/permissions.py:151) replace the multi-valued join filter with `queryset.filter(pk__in=Customer.objects.filter(Q(orders__tailor=profile) | Q(orders__master=profile) | Q(orders__stages__assigned_to=profile)).values('pk'))` -- that removes the row multiplication and the need for the trailing .distinct(). (2) Drop `distinct=True` from the Sum and Avg in CustomerRepository.summary_queryset. Verified this preserves current disclosure semantics: the aggregate already spans all of the customer's orders on the tailor path, so no tailor sees more money than today.

### Skipping or starting the Delivered stage marks the order Delivered and messages the customer, bypassing the QC gate
`domains/orders/services.py:445`

**Impact.** An Owner or Master who clicks 'Skip Stage' or 'Start In-Progress' on the Delivered stage flips an uninspected order to Delivered on the public tracking page and drafts the customer a balance-due message; the one hard invariant of the workflow (asserted for the other route by crm_api/test_workflow.py:521) is unenforced here.

**Evidence.** Confirmed by reading services.py:314-317 (gate is `if stage_key == 'delivered' and new_status == 'COMPLETED'`) and services.py:427-447, where status_map['delivered'] is the bare string 'Delivered' (only master_quality_check at line 438 carries a new_status ternary) and line 445-446 writes it for ANY new_status. No comment anywhere in transition_order_stage excuses this; the comment at 362-369 in fact documents that 'status_map below rewrites order_status unconditionally' and then guards only the re-COMPLETE-the-same-stage case. The frontend reaches it: App.jsx:8635 renders 'Start In-Progress' for any NOT_STARTED/PAUSED stage and App.jsx:8717 renders 'Skip Stage' for any stage not COMPLETED/SKIPPED, both posting api.transitionStage on the selected stage, and 'delivered' is a real stage (crm_api/models.py:475, roles Owner+Master). status_changed at services.py:498-502 is then True, so notifications.py:92-97 sends the 'successfully Delivered! Please complete your remaining balance' message. Deflated from critical to high: no data is lost and no money field is written wrong — the damage is a false customer-facing state plus one wrong WhatsApp draft, and it needs the operator to act on the Delivered stage specifically.

**Fix.** Two one-line edits in OrderService.transition_order_stage (domains/orders/services.py): make the delivered entry mirror the master_quality_check pattern — `'delivered': 'Delivered' if new_status == 'COMPLETED' else order.order_status` — and drop `and new_status == 'COMPLETED'` from the guard at line 314 so the QC precondition also refuses SKIPPED/IN_PROGRESS on that stage. (The auditor's proposed `new_status in ('COMPLETED','IN_PROGRESS')` gate does not help: IN_PROGRESS on 'delivered' would still write 'Delivered'.)

### Signup's OTP step is theatre: it claims an SMS was sent that nothing can send, and accepts any input
`frontend/src/App.jsx:1198`

**Impact.** Every new owner is told to wait for a code that cannot arrive. Some abandon the signup wizard — the product's front door — and those who guess that any digits work have been shown a security assurance the product does not have on a page advertising 'bank level security'.

**Evidence.** Confirmed. handleSignupSubmit ends with setSignupStep(2) // Mock verification (App.jsx:1198). The step-2 block (2178-2205) renders 'We have sent a 6-digit OTP code to +91 {signupForm.mobile_number}' and handleVerifyOTP (1202-1208) advances on any non-empty string with no request made. No SMS capability exists in the repo (settings.py's only outbound channel is email, and its comment at 304-306 says the password reset link is the one thing that sends mail); SignupView never reads an OTP field. The step tracker at App.jsx:2061 still lists { step: 2, label: 'Verify' }.

**Fix.** Delete step 2: make handleSignupSubmit (App.jsx:1191) call setSignupStep(3), drop { step: 2, label: 'Verify' } from the tracker array at line 2061 and remove the signupStep === 2 block (2178-2205).

### Customer Directory CTAs launch the order wizard for a Master, who is 403'd on step 1
`frontend/src/App.jsx:4318`

**Impact.** A Master opens a client from the directory, clicks either CTA, fills in the customer form, and gets `Failed to save customer: detail: Your role does not permit this.` Everything typed is lost and there is no route from that screen to a completed order.

**Evidence.** Confirmed, with corrected line numbers. App.jsx:4318 `<div className="customer-detail-header-actions">` renders both CTAs with no role guard; "Go with Existing Design" (4352) sets setCurrentStep(3)+setView('wizard'), "Create New Design" (4372) calls handleSelectExistingCustomer (defined at 1270) which sets currentStep(1)+view('wizard'). Master's nav contains the Customers tab (App.jsx:2441) and the detail pane renders at 4297. performNext (1504) at step 1 calls saveStep1, which at 1341 does api.updateCustomer(customerId, customerForm) -> PATCH /customers/<id>/ (api.js:225). CustomerViewSet (crm_api/views.py:41) declares no permission_classes and DRF's DEFAULT_PERMISSION_CLASSES is core.permissions.RolePermission (settings.py:373-375); for role 'Master' RolePermission.has_permission (core/permissions.py:63-79) falls through OWNER/DESIGNER, PATCH is not a SAFE_METHOD, and action 'partial_update' is in neither STAFF_ORDER_ACTIONS (44-47) nor SUPERVISOR_ORDER_ACTIONS (52-63) -> 403 {'detail': 'Your role does not permit this.'}, surfaced by api.js:231-235 and saveStep1's catch (1348-1364) as an alert. The 'Go with Existing Design' path also fails: performNext's garmentJobs guard (1512-1516) bounces it back to step 1, into the same saveStep1. The identical button on the Orders registry IS guarded, with a comment naming this exact failure (App.jsx:3673-3684). The customer-detail pair was genuinely missed.

**Fix.** Wrap the `<div className="customer-detail-header-actions">` block at App.jsx:4318 in the guard the Orders registry already uses at App.jsx:3679: `{(!currentUser?.role || currentUser.role === 'Owner') && ( ... )}`. One gate covers both buttons.

### Boutique address is skippable at signup, so the customer tracking page shows the shipped placeholder address
`frontend/src/App.jsx:2233`

**Impact.** A customer opens their tracking link and is told to collect a garment from a fictional address, and the same address prints on the invoice. The owner gets no signal that anything is wrong.

**Evidence.** Confirmed, with a correction to the fix. Signup step 3's boutique-name (App.jsx:2224) and boutique-address (2233) inputs carry no validation, and handleProfileSubmit (App.jsx:1210-1212) does nothing but setSignupStep(4). SignupView writes address only when non-empty: **({'address': business_address} if business_address else {}) at crm_api/auth_views.py:161, so update_or_create leaves BoutiqueSettings.address at its model default '123 Atelier Way, Fashion District' (crm_api/models.py:480). That value renders to the unauthenticated customer at crm_api/templates/crm_api/tracking.html:136 ('Address') and :162 ('Pick up from'), and on the invoice at App.jsx:8111. tracking_views.py:53-58 documents exactly this harm for the get_or_create path but the model default was left alone. The auditor's suggested fix is wrong: step 3 is a <div className="auth-form">, not a <form>, and its button is an onClick — a `required` attribute on the input would do nothing.

**Fix.** Guard handleProfileSubmit (frontend/src/App.jsx:1210): if boutiqueName or boutiqueAddress is blank, alert and return instead of advancing — step 3 is a div, not a form, so HTML `required` has no effect there.

### Garment-form file uploads (Measurement Sheet, Reference Images, Audio Note, Final Approved Design) are never uploaded — single files are silently discarded, repeatable ones store "[object Object]"
`frontend/src/App.jsx:740`

**Impact.** A staff member scans the hand-written measurement sheet, attaches it, the wizard advances with no error and the file is gone — the artefact proving what was actually measured is lost at capture. Reference images persist as [{}] and the tailor's "What to make" panel renders them through String(v) (App.jsx:8405) as "reference images: [object Object]".

**Evidence.** Traced the whole path. TemplateForm.jsx:158-170 renders field_type 'file' as <input type="file"> whose onChange stores raw File objects in job.values — and its comment ("Uploads run through the existing media service on save, so the form only records the intent here") asserts an upload step that does not exist. frontend/src/services/templates.js validateSpec has no 'file' branch, so the values pass the browser check untouched; splitSpec (templates.js:120) just partitions them. saveGarmentJobs (App.jsx:740-754) calls api.createGarmentJob, which at services/api.js:1067-1072 does JSON.stringify(payload) — a File serialises to {} and an array of Files to [{}]. Server side I read core/templates.py:123-124: `if raw in (None, '', [], {}): continue` uses == so {} matches and measurement_sheet/audio_note/final_approved_design are dropped; [{}] matches nothing and falls to the else branch at line 138 (value = raw) and is written verbatim into GarmentJob.spec. grep for FormData in App.jsx returns exactly one unrelated hit (line 5358), and src/services/media.js has no upload function at all. The four fields are in COMMON_PRODUCTION (apps/catalog/definitions.py:111-115) and the 'production' section is rendered in wizard step 2 (App.jsx:6579 iterates ['basic','measurements','style','materials','production'] into TemplateForm). None is is_required, so nothing blocks the wizard — the loss is silent. The audio_note help_text at definitions.py:114 does promise "Transcribed into the special instructions" and nothing in the repo transcribes anything.

**Fix.** Smallest correct fix is to remove the affordance, not to harden the write path: drop the four 'file' entries from COMMON_PRODUCTION (apps/catalog/definitions.py:111-115) and add a resync migration alongside apps/catalog/migrations/0003_resync_templates.py so existing tenants lose the fields too — otherwise definitions.py changes never reach seeded rows. Do NOT take the auditor's alternative of raising in core.templates.validate_spec: saveGarmentJobs runs AFTER the order is created (App.jsx:1454), so a hard rejection there leaves an order saved with no garment job and the wizard dead mid-flow. Re-add the fields when saveGarmentJobs can POST multipart.

### Files attached to a garment (measurement sheet, reference images, audio note) are silently discarded
`frontend/src/App.jsx:754`

**Impact.** Staff photograph the customer's handwritten measurement sheet or record the audio note, the step-6 review says 'Attached', and the workroom receives nothing — the key is not even present on the GarmentJob, with no error anywhere.

**Evidence.** Confirmed end to end. apps/catalog/definitions.py:111-115 puts four `file` fields in COMMON_PRODUCTION; App.jsx:6549 renders the 'production' section for every garment; TemplateForm.jsx:158-171 stores raw File/File[] into values (its comment at 159-160 claims 'Uploads run through the existing media service on save' — no such call exists); splitSpec (services/templates.js:120-132) copies them into `spec`; api.js:1066-1070 JSON.stringify's the payload, so a File becomes {}. Server side core/templates.py:124 treats {} as empty and drops the key entirely without error, so nothing is stored and nothing is reported. GarmentSummary.jsx:64-67 still prints 'Attached'/'N file(s)'. Downgraded from critical: the typed spec and measurements still save correctly, and no upload path was ever built — this is an input the product offers but cannot honour, not corruption of saved data.

**Fix.** Smallest honest fix: drop file fields from what the form renders — in TemplateForm.jsx:199 filter `(f) => f.field_type !== 'file'` — so the product stops offering an input it cannot save. (Also removes the false 'Attached' in GarmentSummary, since those keys will never be set.) Only build the multipart path when the media service is actually wired to garment jobs.

### A failed order submission leaves the order created and a second click bills the customer twice
`frontend/src/App.jsx:1461`

**Impact.** On a partial failure the owner is told only 'Failed to submit order.', not that an order exists, and retrying creates a second order with the same total_amount and advance_paid — two invoices and doubled revenue in Invoices and Analytics. On a money-validation 400 the owner sees the same blank message and can never learn which figure the server refused.

**Evidence.** Confirmed; lines are 1424-1490 (not 1336-1398) and api.js:352-360 (not 326-334). createOrder then saveGarmentJobs run in one try; saveGarmentJobs re-throws (App.jsx:766) and the catch at 1486-1489 alerts 'Failed to submit order.' with the order row already written. domains/orders/services.py:73-75 create_order_for_customer has no idempotency key or duplicate check, and runOnce (1503-1513) only blocks concurrent clicks, not a retry, so pressing Confirm again writes a second Order. api.js:358 `throw new Error('Failed to create order')` does discard the body, while crm_api/views.py:222-226 deliberately returns {'error': str(ve)} for the money validation in services.py — and api.js:363-375 already carries a comment saying reading the body is the right pattern. Downgraded from critical: the duplicate needs a garment-job failure first; the certain, every-time half is that a rejected order (negative or >10^8 price) reports no reason at all.

**Fix.** Two small edits: in api.js createOrder (352-360) read the body and throw `describeApiError(res, data)` like updateOrderStatus already does; in submitOrderAndConfirm keep the created order in a ref and reuse it instead of re-POSTing on retry, and name the created order id in the catch at 1486-1489.

### Master's verification checklist loses ticks — each checkbox posts a stale copy of the whole object
`frontend/src/App.jsx:2647`

**Impact.** A Master ticking six or seven items in sequence sees earlier ticks revert after each dashboard refresh, and the stored record of what was verified is wrong.

**Evidence.** Confirmed at App.jsx:2647-2658 and duplicated at 3874-3885 (not 2509/3729). The payload is spread from `order.master_verification`, and `order` comes from ordersList, which only changes when fetchDashboardAndConfig resolves. Critically, the backend REPLACES rather than merges: crm_api/views.py:432 `order.master_verification = {str(k): bool(v) for k, v in checks.items()}`, so a stale copy that predates the previous tick wipes it. The long docstring at 411-425 explains why the route exists at all (permissions), not the write semantics.

**Fix.** Merge server-side instead of patching two React call sites: in crm_api/views.py:432 write `order.master_verification = {**(order.master_verification or {}), **{str(k): bool(v) for k, v in checks.items()}}`. One edit at the single choke point both screens post to; unticking still works because the key is sent with False.

### 'Partially Paid' in the Invoices table does nothing; no screen can record a part payment
`frontend/src/App.jsx:4945`

**Impact.** A customer paying an installment at the counter cannot be recorded: selecting 'Partially Paid' snaps back to Pending and Balance Due never moves. Only 'nothing paid' and 'paid in full' are expressible, so the invoice ledger and the Analytics paid/pending totals are wrong for every part-paid order.

**Evidence.** Confirmed at App.jsx:4945-4961 (not 4800). The only post-order payment control is the three-option select PATCHing payment_status. crm_api/views.py _reconcile_payment: with neither amount_paid nor advance_paid in `changed` and the status neither 'Paid' nor 'Pending', it takes `paid = order.amount_paid or 0`, and `paid <= 0` forces the label back to 'Pending'. `grep -rn amount_paid frontend/src` returns five hits, all reads (4837, 4838, 4942, 4943, 4987) — nothing writes it. The backend docstring above _reconcile_payment says outright that 'the Invoices row only needs to PATCH a number', i.e. the intended input was never built.

**Fix.** Agree: make the 'Total Paid' cell at App.jsx:4942 an editable number input that PATCHes `{ amount_paid: value }` via the existing api.updateOrder. _reconcile_payment already derives the correct label and clamps the advance, so no backend change is needed.

### An uploaded design can never be edited, archived or deleted — no UI and no API client for it
`frontend/src/features/designStudio/DesignLibrary.jsx:33`

**Impact.** An owner or designer who uploads the wrong photograph, the wrong title, or the same dress twice has no way to correct or remove the row. It stays ACTIVE, counts in DesignCategoryView's tile (views.py:386-403) and keeps being returned into the discovery gallery by LibraryProvider (providers/internal.py:127) that the owner picks a customer's design from. Compounds findings 3 and 4: a design whose cover image is broken is also unfixable.

**Evidence.** Confirmed by reading all four ends of the path. DesignLibrary.jsx:33 EDITABLE_SOURCES = ['catalogue','suggestion'] and the gate at :223 `{editable && !isPending &&` are exactly as reported. crm_api/views.py:295-300 BoutiqueDesignViewSet.queryset is `DesignAsset.objects.filter(source__in=[SOURCE_CATALOGUE, SOURCE_SUGGESTION])`, so the catalogue endpoints the Edit/Delete buttons route to physically cannot reach an upload. apps/design_studio/models.py:145 sets `source ... default=SOURCE_UPLOAD` (the auditor cited views.py:146 — wrong file) and serializers.py:90 has 'source' in read_only_fields, so an upload can never become a catalogue row. I re-grepped frontend/src/services/api.js: the only `design-studio/assets` calls are list (912), review (922), approval-history (933), retrieve (965) and create/upload (1005) — no PATCH, no DELETE, no archive anywhere (the auditor's line numbers were ~25 off but the set is right). apps/design_studio/permissions.py:51-83 implements OWN_UPLOAD_ACTIONS = {'update','partial_update','destroy'} with a created_by ownership check that nothing in the product ever invokes. Uploads are ACTIVE immediately (views.py:227) unless approval is on, and `review` only moves a PENDING design, so nothing can archive an upload either.

**Fix.** Agreed and kept. Add `updateDesignAsset(id, payload)` (PATCH) and `deleteDesignAsset(id)` (DELETE) next to getDesignAsset in frontend/src/services/api.js, and in DesignLibrary.jsx's DesignDetail route non-catalogue sources through them instead of hiding the buttons — DesignLibraryPermission.has_object_permission already enforces exactly the right rule server-side.

### Approved design is lost whenever the wizard returns to step 3
`frontend/src/features/designStudio/DesignStudio.jsx:187`

**Impact.** Owner approves a design in step 3, goes back or edits from the summary, then submits: the order reaches the floor with no design attached, behind the green confirmation screen and with no message.

**Evidence.** Confirmed. DesignStudio holds `board` in local state only and never loads an existing board on mount; its effect (DesignStudio.jsx:187-192) fires on mount with board === null and calls onBoardChange({boardId: null, approved: false}), which App wires straight to setDesignBoard (App.jsx:6609). The component lives under `{currentStep === 3 && ...}` (6573) inside `{designSourceTab === 'studio' && ...}` (6598), so it unmounts and remounts on every step change and on every tab toggle. handleBack (1318-1330) walks 4→3, and the step-6 Order Summary Edit at 7065 sets step 3 directly. After that `if (designBoard.boardId && designBoard.approved)` at 1468 is false and saveDesignBoardToOrder never runs — the surrounding comment at 1466-1482 exists to make an attach FAILURE loud, and is silently bypassed by this path. Worse, the studio also forgets the board, so shortlisting again creates a second DesignBoard for the same customer.

**Fix.** Agree: in DesignStudio, fetch the customer's board on mount before the first onBoardChange — `api.getDesignBoards({ customer_id: customerId })` is already supported server-side (apps/design_studio/views.py:562-564) — and seed board/items from it. That restores boardId+approved on remount and stops ensureBoard creating a duplicate board.

### seed_data.py creates the platform superuser as admin/admin123 and create_superuser.py can never rotate it
`seed_data.py:33`

**Impact.** Every database seeded by seed_data.py keeps admin/admin123 on the console that lists, browses and suspends every boutique on the platform, and every redeploy prints "Superuser 'admin' already exists" and passes green, so the DJANGO_SUPERUSER_PASSWORD work in create_superuser.py is silently defeated by the script next to it.

**Evidence.** seed_data.py:31-34 runs inside schema_context('public') and calls User.objects.create_superuser('admin', 'admin@boutique.com', 'admin123') — the exact account superadmin/permissions.py:26-37 accepts as platform administrator (is_superuser + public schema) and that /admin/ exposes every boutique through. create_superuser.py:43-47 is `if User.objects.filter(username=username).exists(): print(...)` and exits 0, so the README's build command never sets a password on an existing account; its default username is 'admin' (line 26), the same one seed_data.py creates. I confirmed this is not hypothetical: the committed dump boutique_crm.sql:2679-2681 contains public.auth_user id=1, username 'admin', email 'admin@boutique.com', is_superuser=t, and I recomputed its hash — pbkdf2_sha256$1200000$EFYB8hh030yA3keuYCY66d$gBYamkqKCiJaGRDp7qcyS2HsAYsmlqdYoVDPNNLOPIk= is 'admin123'. seed_data.py:64 likewise ships password123 for the tenant owner. I left severity at high rather than critical only because I cannot prove the hosted database is the one this dump came from; the create_superuser.py half of the defect is unconditional.

**Fix.** In create_superuser.py, replace the exists() early-out at line 43 with an unconditional rotate — user, _ = User.objects.get_or_create(username=username, defaults={'email': email}); user.set_password(password); user.is_superuser = user.is_staff = True; user.save() — so every deploy makes the environment value true. Then drop the literals at seed_data.py:33 and :64 in favour of os.environ.

### seed_mock_orders.py deletes every order and customer and defaults to the production database
`seed_mock_orders.py:18`

**Impact.** A developer running the seed script to populate their local database irreversibly wipes every order, customer, tailor and notification in every live boutique's schema.

**Evidence.** Confirmed. seed_mock_orders.py:1-24 does django.setup() with DJANGO_SETTINGS_MODULE=boutique_crm.settings, then inside schema_context() runs OrderStageHistory/Order/Customer/Notification/Tailor .objects.all().delete(), and seed_all() (line 143) loops over every non-public BoutiqueTenant. `grep USE_LOCAL_DB` over the three seed scripts returns nothing; only start.sh:15 exports it. settings.py:196-211 confirms the local switch fires only when USE_LOCAL_DB=='True' or when 'test' is in sys.argv, and settings.py:37 loads the .env whose DB_HOST is the Supabase pooler. So a direct `python seed_mock_orders.py` from the repo root does target production. I downgraded critical to high: it needs a deliberate invocation of a clearly-named seed script, not a normal request path. The other two scripts contain no delete() calls, so this is the only loaded gun.

**Fix.** Do NOT adopt the proposed global flip of USE_LOCAL_DB. Render sets no .env and no USE_LOCAL_DB (README.md:134-163 never mentions it), so defaulting to local would point production at 127.0.0.1 and take the service down. The smallest correct fix is a guard at the top of seed_all() in seed_mock_orders.py: `if os.environ.get('USE_LOCAL_DB') != 'True': raise SystemExit('refusing to seed a non-local database')` — one condition in the one destructive file.


## MEDIUM

### README documents port 6543 — the transaction pooler settings.py proves breaks tenant isolation
`README.md:38`

**Impact.** An operator following README.md:38 sets DB_PORT=6543 on Render and reintroduces exactly the configuration the settings comment documents as having leaked queries into the wrong schema and produced random 401s. Locally, any manage.py command run outside start.sh reaches the live database in that same broken configuration.

**Evidence.** Confirmed, but the durable defect is the README, not the .env, so I moved the anchor. README.md:38 reads "**Default Connection:** Connected to Supabase's transaction pooler on port `6543`", which directly contradicts settings.py:141-161 — a long comment explaining that django-tenants' `SET search_path` is session state pgbouncer does not preserve under transaction pooling, that this produced intermittent `401 Invalid token` and queries running against `public` in production (measured: 12 concurrent requests returned 9x200, 2x401, 1x500), and that DB_PORT therefore defaults to '5432'. The local .env does set DB_PORT=6543 (verified: `grep -c '^DB_PORT=6543$' .env` returns 1) and _load_dotenv at settings.py:34 uses os.environ.setdefault so it beats the 5432 default — but .env is untracked (`git ls-files .env` is empty, and .gitignore:21 ignores it), so that part is one developer's machine, not something shipped.

**Fix.** Fix README.md:38 to say session pooler / port 5432 and cite the reasoning in boutique_crm/settings.py:141-161; change DB_PORT to 5432 in the local .env.

### /api/catalog/jobs/ is unscoped: any tailor reads every order's garment spec and measurement snapshot
`apps/catalog/views.py:88`

**Impact.** A tailor assigned to one garment can GET /api/catalog/jobs/ with their own token and receive the per-dress specification and body-measurement snapshot for every order in the boutique, including clients they were never put on. Within-tenant only -- no cross-tenant leak.

**Evidence.** Confirmed at the cited line. GarmentJobViewSet (apps/catalog/views.py:85) declares no permission_classes -- unlike its sibling GarmentTemplateViewSet three lines up, which sets permission_classes = [permissions.IsAuthenticated] and explains why in a docstring -- so it inherits RolePermission, which returns True for every SAFE_METHOD from any non-Owner, non-Designer role (core/permissions.py:75-76). get_queryset (88-94) narrows only by an optional ?order= param and never calls visible_orders. GarmentJobSerializer (apps/catalog/serializers.py:80-93) emits order, spec and measurements. visible_orders exists and is used for exactly this in apps/production/views.py:12-20, whose docstring says the unscoped version 'handed any signed-in tailor every order id and customer name in the boutique'. No comment anywhere in apps/catalog/views.py justifies the omission.

**Fix.** In GarmentJobViewSet.get_queryset (apps/catalog/views.py:88), add `from core.permissions import visible_orders` / `from crm_api.models import Order` and chain `queryset = queryset.filter(order__in=visible_orders(Order.objects.all(), self.request.user))`, matching apps/production/views.py:20.

### GET /api/catalog/jobs/ returns every order's garment spec and measurements to any signed-in tailor
`apps/catalog/views.py:88`

**Impact.** A tailor who is correctly 404'd from /api/orders/<id>/ for an order they are not on can call /api/catalog/jobs/ and read that order's full garment spec — every measurement, the customer_notes, the internal_notes and the special_instructions for every dress in the boutique. It is the same read the role matrix exists to prevent, reached through a route that was never given the guard.

**Evidence.** Confirmed at the cited line. GarmentJobViewSet (apps/catalog/views.py:85) declares no permission_classes, so it inherits DEFAULT_PERMISSION_CLASSES = core.permissions.RolePermission (boutique_crm/settings.py:373-375), and RolePermission.has_permission returns True for any non-Owner, non-Designer role on a SAFE method (core/permissions.py:75-76). get_queryset (line 88-94) applies only an optional ?order= filter and no user scoping. Note the deliberate contrast in the same file: GarmentTemplateViewSet directly above carries a long comment (lines 30-40) explaining exactly why IT opts out of RolePermission — so the author was thinking about permissions in this file and the job viewset was simply left on the default with no scoping. GarmentJobSerializer (apps/catalog/serializers.py) exposes spec and measurements in full, and spec carries special_instructions, internal_notes (help_text: "Staff only — never shown on the customer copy") and customer_notes from COMMON_PRODUCTION. Every sibling does scope: CustomerViewSet.get_queryset (crm_api/views.py:55) and CustomerSerializer.get_orders (crm_api/serializers.py:349-365, whose docstring says queryset scoping alone was not enough). The route is mounted at boutique_crm/urls.py:46. Writes are not exposed — 'create'/'update' are on neither STAFF_ORDER_ACTIONS nor SUPERVISOR_ORDER_ACTIONS — so this is read-only leakage, and it is within one tenant's schema, not cross-tenant. Medium is honest.

**Fix.** Agreed. In GarmentJobViewSet.get_queryset (apps/catalog/views.py:88), wrap the base queryset with `queryset.filter(order__in=visible_orders(Order.objects.all(), self.request.user))`, importing visible_orders from core.permissions and Order from crm_api.models. One line covering list, retrieve and both materials sub-actions, since all of them reach rows through this queryset.

### The Saved Library source ignores the search keywords entirely
`apps/design_studio/providers/internal.py:119`

**Impact.** The owner types 'peacock motif' during a customer's order and the boutique's own uploaded and saved designs are unaffected — the studio returns the 24 most recently added ACTIVE designs whatever was typed. A matching design uploaded months ago is unreachable through discovery, while the catalogue source beside it does honour the same words.

**Evidence.** Read both providers side by side. LibraryProvider.search (internal.py:119-155) takes `queries` and never references it: the only narrowing is context.garment_type at :128-130, then assets[:limit] with the model's default '-created_at' ordering (models.py Meta ordering) and PER_SOURCE_LIMIT = 24 (services.py:19). CatalogueProvider directly above (:44-51) does the keyword work — `tokens = _tokens(queries)` then Q(title__icontains) | Q(description__icontains) with a fall-back-if-empty pattern. No comment anywhere explains the asymmetry. I also checked the ranking stage in case keywords re-entered there: RulesIntelligence.rank / _score (intelligence/rules.py:78-108) scores against the customer *context* signals only, never the free-text queries, so the keywords truly have no effect on library results at any stage. The keyword box is real: DesignStudio.jsx:141-262 collects keywords and passes them into runSearch.

**Fix.** Agreed and kept: in LibraryProvider.search, reuse the module-level _tokens(queries) helper and the same Q(title__icontains=…) | Q(description__icontains=…) narrowing with CatalogueProvider's fall-back-if-nothing-hits pattern, applied before the [:limit] slice.

### DesignerViewSet.portfolio bypasses the serializer redaction that hides staff email addresses
`apps/design_studio/views.py:538`

**Impact.** Any signed-in tailor or designer can GET /api/design-studio/designers/<id>/portfolio/ and read that designer's login address plus a flag saying a live account exists for it, which combined with the shared default password is an account-takeover shortcut inside the boutique.

**Evidence.** Confirmed. DesignerSerializer.to_representation (apps/design_studio/serializers.py:24-41) pops 'email' and 'has_login' for non-Owners, but only inside `if request is not None`, and the docstring says the unredacted version shipped 'a map of live accounts, next to a bootstrap password written in this repository'. portfolio (views.py:529-542) builds `DesignerSerializer(Designer.objects.annotate(design_count=Count('designs')).get(pk=designer.pk)).data` at line 538 with no context kwarg, so self.context is {} and the guard is skipped. DesignerViewSet.permission_classes = [DesignStudioPermission] (views.py:422), which returns True for every SAFE_METHOD from any signed-in role (permissions.py:29-30), so any tailor or designer can call it. The bootstrap fallback 'DesignerSecure2026!' is at views.py:515. One correction to the finding: the same pattern at line 524-527 (create_login) is NOT a leak -- create_login is a POST, and DesignStudioPermission allows non-safe methods only to the Owner, who already sees the email.

**Fix.** In DesignerViewSet.portfolio (apps/design_studio/views.py:538) pass the context: `DesignerSerializer(..., context=self.get_serializer_context())`. That is the whole fix; leave line 524 alone.

### Design uploads accept any file of any size — no server-side type or size check
`apps/design_studio/views.py:246`

**Impact.** A PDF, a .mov picked from a phone's camera roll or a corrupt file is accepted with a 201 and becomes the design's cover image; the card then renders permanently broken, and per finding 1 the row can never be corrected or deleted. accept="image/*" at DesignUpload.jsx:149 is client-side only and any direct API caller ignores it.

**Evidence.** Read _store_images at views.py:246-253 in full: `for f in request.FILES.getlist('images'): path = f"design_library/{uuid.uuid4()}_{f.name}"; saved = default_storage.save(path, ContentFile(f.read()))`. There is no content-type test, no extension whitelist, no per-file size cap and no cap on file count, and no comment claiming the omission is deliberate. I re-ran the grep across crm_api/, apps/ and core/ for content_type / .size / MAX_UPLOAD — the only hits are in test files, so no shared guard exists elsewhere. settings.py has no DATA_UPLOAD_MAX_MEMORY_SIZE or FILE_UPLOAD_* override either. Note the contrast the auditor missed: every other upload in the product goes through an ImageField (crm_api/models.py:86, 276, 340, 384), which Pillow-validates that the bytes really are an image. This one endpoint bypasses that entirely. I am discounting the OOM half of the claim — a TemporaryUploadedFile over 2.5MB is on disk and f.read() pulls it into RAM, which is wasteful, but 'takes the API down for the whole boutique' is asserted, not shown.

**Fix.** One guard in DesignAssetViewSet._store_images (apps/design_studio/views.py:246): before storing, reject with 400 any file whose f.content_type is not in a small image whitelist or whose f.size exceeds a limit (10MB is ample for a garment photograph). While there, pass `f` to default_storage.save instead of ContentFile(f.read()) so Django streams it in chunks.

### Upload stores an absolute URL built from the request Host, so image_url breaks when the host changes and is attacker-settable
`apps/design_studio/views.py:252`

**Impact.** The API hostname is frozen into every uploaded row, so a move to a custom domain or a new Render URL 404s every uploaded design image while seeded catalogue rows (bare filenames) keep working — and per finding 1 the row cannot be edited to repair it. Uploading against a dev host bakes localhost:8000 into the row permanently. Secondarily, any signed-in role may upload (permissions.py:55-56) and can point a design's cover image at a host they control.

**Evidence.** views.py:252 is verbatim `stored.append(request.build_absolute_uri(default_storage.url(saved)))`, and that full string is persisted as DesignAsset.image_url (views.py:213-215). settings.py:55 is `ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS','*').split(',') if h]` with no comment defending the '*' default, and request.get_host() only rejects a Host that ALLOWED_HOSTS excludes — so with the default it trusts anything. I checked the Host-forgery half against tenants/middleware.py:73-107: tenant resolution reads X-Tenant-ID (or sweeps by token), never the hostname unless both fail, so a forged Host does not break the request. The claim stands. I also confirmed the receiving side: frontend/src/services/media.js:16-23 resolveMediaUrl already prefixes MEDIA_BASE onto '/media/...' and is used at DesignLibrary.jsx:155 and :404, DesignDashboard.jsx:58 and DesignStudio.jsx — so storing a relative path is strictly better and needs no frontend change.

**Fix.** Agreed and kept, it is the smallest fix: in _store_images (apps/design_studio/views.py:252) store the relative path — `stored.append(default_storage.url(saved))`. resolveMediaUrl already resolves it on every screen that renders a design.

### Granting a designer a login on an email already linked to another designer returns a 500
`apps/design_studio/views.py:519`

**Impact.** An owner granting a login to a second designer at a shared studio address, or simply reusing an address they already granted, gets an unreadable 500 from the roster with no indication of what is wrong or which designer holds that address. The action is blocked with no path forward from the screen.

**Evidence.** Read create_login end to end (views.py:452-527). It guards three cases — designer already has a login (:464), the address is the tenant owner's (:489-496), the address belongs to a Tailor (:497-501) — and never checks user.designer_profile. Designer.user is a OneToOneField (models.py:55-59, related_name='designer_profile'), so the assignment at :519-521 violates the unique constraint on user_id and raises IntegrityError. I confirmed core/exceptions.py is a zero-byte file, so no custom handler catches it and DRF returns a 500. describeApiError (api.js:39) turns that into 'The server could not complete that (error 500). Please try again.', surfaced by DesignerRoster's grant() at DesignDashboard.jsx:133. The docstring at :461 does promise 'retrying a failed request is always safe', which this contradicts.

**Fix.** Agreed and kept: in DesignerViewSet.create_login, alongside the tailor_profile check at views.py:497, add — if getattr(user, 'designer_profile', None) is not None, return 400 naming that designer, mirroring the Tailor branch's wording.

### release_unused() releases the line's full outstanding reservation with no clamp, so a write-off that shrank the item's reserved figure permanently wedges the plan
`apps/inventory/order_materials.py:322`

**Impact.** Any plan whose reserved material is later damaged, scrapped, returned to supplier, or counted short can never be closed or cancelled — both 400 with "Cannot release N ... only M is reserved" — and the order can never be given a new plan. Reachable only through the material-plan API, which has no screen.

**Evidence.** Traced every step in code. services.py:111-128 clamps the ITEM: for DAMAGE/SCRAP/SUPPLIER_RETURN/ADJUSTMENT (reserved_delta == 0) it sets `released = new_reserved - new_stock; new_reserved = new_stock`. Nothing writes back to OrderMaterialLine, and models.py:816 computes outstanding_reservation purely from the line's own four columns. release_unused (order_materials.py:319-324) passes that raw figure to InventoryService.release(), which sets reserved_delta=-1 with no clamp_reserved and no reserved_backed, so record_movement takes the `else` branch at services.py:99 and hits `if new_reserved < 0: raise ValueError` at services.py:106. close() (line 432) and cancel() (line 455) both route through it, close(release_outstanding=False) fails at reconcile() (line 434, models.py:816 again), and the `one_live_material_plan_per_order` partial-unique constraint (models.py:759-765) then blocks re-planning. The auditor's claim is correct in every detail. Severity corrected down from high: the entire material-plan lifecycle is API-only — grepping frontend/src for planMaterials/reservePlan/closePlan/cancelPlan returns only their definitions in services/api.js:1160-1169, and InventoryPanel.jsx:186-193 has no materials tab — so no boutique owner reaches this through the product in a normal week. The pure-UI path (MovementModal Reserve then Damage then Release, InventoryPanel.jsx:12-28) does NOT wedge, because the modal reads item.reserved_stock, which the clamp already lowered.

**Fix.** Smaller than the auditor's version: pass the existing clamp to the one call site — `InventoryService.release(line.item, outstanding, clamp_reserved=True, ...)` at apps/inventory/order_materials.py:322. services.py:96-97 already handles reserved_delta < 0 by flooring at zero, and tests.py:125 (test_cannot_release_more_than_reserved) calls release() without the flag, so it still refuses a genuine over-release. close(), cancel() and the release-unused endpoint all route through this one line.

### dashboard() ignores the selected date window for the Suppliers panel (and for Cost-per-order)
`apps/inventory/reports.py:425`

**Impact.** The owner picks a week, four panels narrow, and the supplier on-time percentages keep showing all-time figures with nothing on screen saying so.

**Evidence.** Read the code: dashboard(*, since=None, until=None) at reports.py:415 threads the window into consumption(), loss_rates() and movement_summary() but calls `cost_per_order(limit=10)` (line 425) and `supplier_performance(limit=10)` (line 426) with neither, even though supplier_performance's signature is `(*, since=None, limit=50)` (reports.py:315) and the standalone endpoint does pass it (views.py:1024). ReportsTab.jsx:66-79 renders From/To date inputs whose only consumer is this one dashboard call (line 39), and the Suppliers panel is drawn from its result at ReportsTab.jsx:156. The _window comment at views.py:930-936 does say silently reporting over all time when a period was asked for is the worst option. Severity kept at medium but for half the reason the auditor gave: cost_per_order is structurally always empty (see the next finding), so only the Suppliers panel actually shows an unlabelled all-time figure inside a narrowed dashboard. stock_position() and low_stock() are also unwindowed, correctly — they are point-in-time by nature.

**Fix.** In dashboard() in apps/inventory/reports.py:426, pass the window through: `supplier_performance(since=since, limit=10)`. Leave cost_per_order alone — it has no date column of its own and is empty in practice; if you want it labelled, that belongs in ReportsTab.jsx, not here.

### Stock valuation is Owner-only on the reports endpoint but open to any tailor on /inventory/items/summary/
`apps/inventory/views.py:54`

**Impact.** A tailor's token reads the boutique's total stock valuation and the purchase price of every material -- the exact commercial figure OwnerOnly exists to withhold -- through a URL their nav never shows them.

**Evidence.** Confirmed; line corrected from 92 to 54 (the class), the summary action is at 91-113. InventoryItemViewSet (apps/inventory/views.py:54) sets no permission_classes, so RolePermission's blanket SAFE_METHODS grant (core/permissions.py:75-76) applies to every production role. summary returns 'inventory_value': Sum(current_stock * purchase_price) (95-113) and InventoryItemSummarySerializer includes purchase_price (apps/inventory/serializers.py:40-54). Its three siblings in the same file all carry the guard with a comment giving the reason: SupplierViewSet at 43-49, PurchaseOrderViewSet at 308-311, InventoryReportViewSet at 916-926 ('a tailor needs none of it to sew'). No comment justifies the omission on this one. Verified the fix is safe: /inventory/items/ is called only from features/inventory/InventoryPanel.jsx (Owner-only nav, App.jsx:2432) and from features/catalog/TemplateForm.jsx:28 and GarmentSummary.jsx:27, both of which live in the order wizard, which is Owner-gated.

**Fix.** Add `permission_classes = [OwnerOnly]` to InventoryItemViewSet at apps/inventory/views.py:54, matching SupplierViewSet (43) and PurchaseOrderViewSet (308). OwnerOnly is already imported in this module.

### PurchaseOrderViewSet.receive() is not atomic, so a mid-loop failure half-applies a multi-line goods receipt
`apps/inventory/views.py:318`

**Impact.** When the receipt does error partway, the earlier lines' goods are already in stock and in the ledger while the owner sees only a failure; the retry then contradicts what the modal still displays, and the PO cannot be completed without a page reload.

**Evidence.** Confirmed by reading the code: `def receive` at views.py:318 carries only @action, no @transaction.atomic, and `grep -rn ATOMIC_REQUESTS --include='*.py' .` returns nothing (settings.py:362-383 defines REST_FRAMEWORK only). Each InventoryService.purchase() call carries its own @transaction.atomic (services.py:59), so it commits on return; the guard at views.py:343 and the except at views.py:356 then return 400 with earlier lines already committed. ReceiveModal (frontend/src/features/inventory/InventoryPanel.jsx:841-845) does pre-fill every line with quantity_outstanding and post them together, so multi-line receipts are the default. Severity corrected down from high: the auditor missed `max={line.quantity_outstanding}` on the quantity input at InventoryPanel.jsx:879 — native constraint validation blocks the form before onSubmit fires, so the over-receive error the finding describes cannot originate from the UI. It needs a stale PO (a concurrent receipt from another tab/device) to fire the first time. Also worth noting on the same line: `Decimal(str(quantity))` at views.py:339 raises decimal.InvalidOperation for a non-numeric string, which is an ArithmeticError and escapes the `except ValueError` at 356 as a 500 — same half-applied state, no error message at all.

**Fix.** Add @transaction.atomic to PurchaseOrderViewSet.receive in apps/inventory/views.py:318 — agreed, that is the smallest fix and covers the 500 path too, since the whole request rolls back either way.

### Stock valuation and purchase prices are readable by any non-Owner staff account, defeating the OwnerOnly guard two viewsets over
`apps/inventory/views.py:54`

**Impact.** Any signed-in Master or Tailor can GET /api/inventory/items/summary/ for the boutique's total stock valuation and GET /api/inventory/items/ for what every material cost.

**Evidence.** Confirmed against all four files. SupplierViewSet (views.py:49-54) and InventoryReportViewSet (views.py:915-926) both set `permission_classes = [OwnerOnly]` with comments naming stock valuation and supplier data as the boutique's commercial position and calling out RolePermission's blanket SAFE_METHODS grant by name. InventoryItemViewSet (views.py:54) sets no permission_classes, so it takes DEFAULT_PERMISSION_CLASSES = core.permissions.RolePermission (settings.py:373-375), which returns True for every SAFE_METHOD for any non-Designer role (core/permissions.py:74-76). Its summary action (views.py:91-121) returns `inventory_value` computed as Sum(current_stock * purchase_price), and InventoryItemSummarySerializer lists `purchase_price` at serializers.py:52 — so both the list and the summary hand a Master or Tailor token exactly the data the two neighbouring viewsets were deliberately locked down to protect. No comment anywhere on InventoryItemViewSet explains this as a tradeoff; the only comment there is about serializer choice for list views.

**Fix.** Two lines in apps/inventory: drop 'purchase_price' from InventoryItemSummarySerializer's fields (serializers.py:52), and gate the `inventory_value` key in InventoryItemViewSet.summary (views.py:113) on `resolve_user_role(request.user) == OWNER`. Quantities, reorder levels and locations stay readable so production staff can still work.

### Uploaded customer and garment photos share one global media directory served with no authentication
`boutique_crm/settings.py:350`

**Impact.** Customer profile photos, stage-progress shots and finished-garment photographs of any boutique are fetchable by any unauthenticated client that guesses a plain filename, and the 'not published yet' gate on garment images is bypassable that way.

**Evidence.** Confirmed, with the severity corrected. settings.py:350-360 sets STORAGES['default'] to plain django.core.files.storage.FileSystemStorage with a single MEDIA_ROOT = BASE_DIR/'media', and boutique_crm/urls.py:64 serves that root in every environment via re_path(r'^media/(?P<path>.*)$', serve, {'document_root': MEDIA_ROOT}) with no permission check. The comment above it (urls.py:48-62) explains only why serving in non-DEBUG is deliberate; it says nothing about access control, so the guard is genuinely absent rather than documented-and-accepted. The five tenant-less prefixes are real: crm_api/models.py:86, 276, 340, 384, 483. But the auditor overstated exploitability. The three default_storage.save() call sites it groups in (crm_api/views.py:79-81, :182-184, apps/design_studio/views.py:249-252) all build paths as {uuid4()}_{name}, which are not guessable — only the five ImageField prefixes keep the caller's filename. serve() is called without show_indexes, so there is no directory listing, and Django's storage appends a random suffix on collision, so the DOMS_LOGO.png / DOMS_LOGO_bWyRTlq.png pair the auditor cites is not evidence of a collision between boutiques and no file is overwritten. What remains is real: a stranger or a rival boutique who guesses an ordinary filename (logo.png, IMG_1234.jpg) under /media/customer_profiles/, /media/stage_images/ or /media/finished_garments/ gets the file, including garment images the tracking page withholds until garment_images_published (tracking_views.py:83-85).

**Fix.** In boutique_crm/settings.py:350, set STORAGES['default']['BACKEND'] to 'django_tenants.files.storage.TenantFileSystemStorage' (django-tenants 3.10.1 is already pinned in requirements.txt). It prefixes path and URL with the schema name, so all five upload_to prefixes are namespaced at once and the existing serve() route keeps working. Note this is hardening, not authentication, and existing rows keep paths under media/<dir>/ — those files must be moved under media/<schema>/<dir>/ or their images break.

### No pagination anywhere: /api/orders/ and /api/notifications/ return the whole table forever
`boutique_crm/settings.py:362`

**Impact.** By the second year an Owner's bell fetch returns tens of thousands of notification rows as one JSON array on every login and every refresh, and the orders tab downloads the boutique's entire order book with stages, activities and jobs attached. Degrades exactly the boutiques that grow, with no error to point at.

**Evidence.** The factual claim holds: REST_FRAMEWORK at settings.py:362-383 has no DEFAULT_PAGINATION_CLASS or PAGE_SIZE, and `grep -rn pagination --include=*.py` returns exactly one hit, in superadmin/tests.py -- no viewset sets pagination_class. NotificationViewSet.get_queryset (crm_api/views.py:857-867) does return the role's whole feed ordered by -created_at, with no age or read-state cap, and App.jsx:857-861 does `setNotifications(data)` on the raw array. Severity lowered from high: this is gradual growth, not a defect a user hits today, and the tenant schemas keep each boutique's tables small. Both of the auditor's suggested fixes are wrong and I am replacing them: (a) a global DEFAULT_PAGINATION_CLASS would break the frontend immediately -- I grepped `\.results` across frontend/src and only App.jsx:691, TemplateForm.jsx:29, GarmentSummary.jsx:30, DesignUpload.jsx:38, DesignStudio.jsx:170 and SuperAdmin.jsx:435 handle it; getOrders, getCustomers, getTailors, getFabrics, getAppointments and getNotifications all consume a bare array, and the auditor's claim that 'getOrders/getCustomers already have that pattern' is false. (b) capping get_queryset with `[:200]` would crash mark_all_read at crm_api/views.py:873, which does `self.get_queryset().filter(is_read=False).update(...)` -- Django raises on filter/update against a sliced queryset.

**Fix.** Scope it to the one genuinely unbounded feed and keep the frontend working: set `pagination_class = PageNumberPagination` with `page_size = 50` on NotificationViewSet only (crm_api/views.py), and change fetchNotifications (App.jsx:857) to `setNotifications(data.results || data)`. mark_all_read is unaffected because it calls get_queryset() directly, not the paginated response. Leave the global REST_FRAMEWORK default alone until the list readers in services/api.js are converted.

### No LOGGING configuration — with DEBUG=False every 500 traceback is silently discarded
`boutique_crm/settings.py:53`

**Impact.** Unhandled exceptions surface to the boutique as a generic error and leave no trace an operator can read, so a customer-reported bug has to be reproduced by guesswork.

**Evidence.** Confirmed against Django's own source rather than assumed. `grep -rn 'LOGGING|ADMINS'` across boutique_crm/, crm_api/, core/, tenants/, superadmin/, apps/, domains/ returns nothing. .venv/.../django/utils/log.py:18-63 shows DEFAULT_LOGGING attaching `console` (filter require_debug_true) and `mail_admins` (filter require_debug_false, AdminEmailHandler) to the `django` logger; with DEBUG=False at settings.py:53 the console handler drops the record and AdminEmailHandler has no ADMINS to mail. Because the `django` logger does have handlers attached, logging's callHandlers counts them as found and never falls back to lastResort, so nothing reaches stderr. gunicorn.conf.py:45-46 sets accesslog/errorlog to '-' but that only carries the access line and worker-level errors, and requirements.txt has no Sentry. Severity corrected from high to medium: no boutique user is harmed directly by this — it makes every other bug slower to diagnose.

**Fix.** Add a LOGGING dict to boutique_crm/settings.py with an unfiltered StreamHandler on stderr bound to the `django` and root loggers at ERROR/INFO. gunicorn already forwards stderr to Render's log stream, so no new dependency is needed.

### No STATIC_ROOT and nothing serves /static/ — the Django admin has no CSS or JS in production
`boutique_crm/settings.py:283`

**Impact.** The /admin/ fallback README.md designates for use "when the console itself is what is broken" renders as unstyled raw HTML with no admin JavaScript, so the raw-id lookups on the Order admin do not work and the page is painful to use in exactly the situation it exists for.

**Evidence.** Confirmed, with one piece of the auditor's evidence corrected. settings.py:283 defines STATIC_URL and `grep -rn 'STATIC_ROOT|whitenoise'` over the repo (excluding .venv) returns nothing at all — no STATIC_ROOT, no whitenoise in requirements.txt (which lists only asgiref, Django, django-cors-headers, django-tenants, DRF, pillow, psycopg2-binary, sqlparse, requests, gunicorn). README.md:116-118's build command has no collectstatic. boutique_crm/urls.py:63-65 adds a serve() route for ^media/ only; nothing matches /static/. Under gunicorn with DEBUG=False, staticfiles serves nothing, so every /static/admin/... URL 404s. Correction: the finding's claim about filter_horizontal on the tenant and DemoRequest admins is wrong — grep across crm_api/admin.py and tenants/admin.py finds no filter_horizontal, date_hierarchy or autocomplete_fields; the only JS-dependent widget is raw_id_fields at crm_api/admin.py:83. Severity medium is right: the page still renders and is readable, so the documented back door (README.md:225-240) is degraded, not dead.

**Fix.** Set `STATIC_ROOT = BASE_DIR / 'staticfiles'` in boutique_crm/settings.py, add whitenoise to requirements.txt with WhiteNoiseMiddleware directly after SecurityMiddleware in MIDDLEWARE (settings.py:102), and append `python manage.py collectstatic --noinput` to the Render build command at README.md:118.

### Any signed-in staff member can POST forged notifications into the owner's inbox
`core/permissions.py:101`

**Impact.** A tailor or designer can post a notification that appears in the owner's bell indistinguishable from a system event, making the owner's only trusted event feed forgeable.

**Evidence.** Confirmed. OwnNotifications.has_permission (core/permissions.py:101-102) returns True for any role-resolving user on every method; its docstring (lines 94-96) justifies this by get_queryset, which `create` never calls. NotificationViewSet (crm_api/views.py:824) is a full ModelViewSet registered at r'notifications' (crm_api/urls.py:15) with NotificationSerializer `fields='__all__'` (crm_api/serializers.py:532-535), so recipient_role/recipient_email/title/message are all writable on POST. I checked the other unsafe verbs: update/partial_update/destroy all resolve the object through the scoped get_queryset (views.py:857-867), so only `create` escapes. Severity lowered from high: it forges a feed entry, it does not leak another tenant's data, move money, or grant access — and it needs a staff member deliberately using dev tools.

**Fix.** One guard in OwnNotifications.has_permission (core/permissions.py:102): `if getattr(view, 'action', None) == 'create': return False` before the existing return. Blocking 'destroy' is unnecessary — it already routes through the scoped get_queryset — and mark_all_read is a custom action, so it is unaffected.

### A signup that fails after the tenant row is created burns the email address permanently
`crm_api/auth_views.py:205`

**Impact.** Owner sees a raw exception string or a gateway timeout, retries, and is told the email already exists while login says invalid credentials. That address is permanently unusable for the product.

**Evidence.** Confirmed, at line 205 not 162. crm_api/auth_views.py:124-201 creates BoutiqueTenant (124), Domain (132), clears the tenant cache (142), set_tenant (146), seed_tenant_defaults (150), BoutiqueSettings.update_or_create (158) and only then User.objects.create_user (170) — all in one try whose except (205-207) does connection.set_schema_to_public() and returns str(e) as a 500. Nothing deletes the tenant, and BoutiqueTenant.owner_email is unique (tenants/models.py:5) with the duplicate check at auth_views.py:100 testing exactly that field, so a retry is refused. gunicorn.conf.py:33 sets a 60s timeout while tenant creation runs the full migration set plus seeding. Recovery is genuinely absent: password reset finds the tenant by owner_email but no User exists in that schema, so PasswordResetRequestView returns its generic answer (auth_views.py:400-403). SEVERITY CORRECTED down from high: it requires a server-side failure mid-signup, which is not a normal-week event — but it is unrecoverable for that address when it happens.

**Fix.** In SignupView's except (crm_api/auth_views.py:205), keep the reference from line 124 and call tenant.delete(force_drop=True) if it was created before returning, and return a fixed 'We could not finish creating your boutique. Please try again.' instead of str(e).

### Failed signup after tenant creation leaves an orphan tenant row that blocks re-signup on that email
`crm_api/auth_views.py:205`

**Impact.** When a signup does fail after the schema is created, that email address can never sign up again and can never log in (no User row exists, and password reset correctly reports nothing). The owner also sees the raw exception string, since line 207 returns str(e) and frontend/src/services/api.js:74 throws data.error verbatim into an alert.

**Evidence.** Confirmed the mechanism: BoutiqueTenant.objects.create at auth_views.py:122 (auto_create_schema=True, tenants/models.py:22, no auto_drop_schema), then Domain, seed_tenant_defaults (line 150), BoutiqueSettings (157), and only then User.objects.create_user at 168. The except at 205-208 does only connection.set_schema_to_public() and returns str(e); nothing deletes the tenant. No ATOMIC_REQUESTS is set anywhere, so the tenant row is committed. The duplicate check at line 100 then permanently rejects the same owner_email. BUT the auditor's supporting evidence is substantially wrong and I am downgrading on that basis: password reset DOES exist end to end (PasswordResetRequestView/PasswordResetConfirmView at crm_api/auth_views.py:354 and 425, routed at crm_api/urls.py:26-29, called from frontend/src/App.jsx:869/900 via api.requestPasswordReset), and the login screen has a working 'Forgot password?' button at App.jsx:1893-1899 -- the claimed 'Password help? Ask your admin' text does not exist in the file. The named failure triggers are also thin: email and password are validated before line 122, the schema name carries a uuid4 suffix so a Domain clash is not realistic, and create_user runs on a fresh schema. What remains is a genuine but uncommon failure (migration timeout under gunicorn.conf.py:33 timeout=60, a seed error) with a permanent consequence, not a weekly event. Severity medium, not high.

**Fix.** In SignupView.post's except block (crm_api/auth_views.py:205), keep a reference to the created tenant, call connection.set_schema_to_public() first, then inside a nested try call tenant.delete(force_drop=True) (force_drop is required -- BoutiqueTenant sets only auto_create_schema), and return a generic 'We could not finish creating your boutique. Please try again.' instead of str(e).

### The tailor's "Sizing Blueprint" shows the customer's live measurements, not the order's, so a later order silently rewrites an in-production one
`crm_api/serializers.py:173`

**Impact.** A client with a lehenga on the table returns for a blouse and is re-measured. Step 2 of the second order rewrites the customer's chest/waist. The tailor still working the first order opens their assignment card and the Sizing Blueprint for that order has changed underneath them with no indication that it did — a garment cut to numbers taken for a different dress.

**Evidence.** Confirmed at the cited line: OrderSerializer.customer_measurements = MeasurementSerializer(source='customer.measurements', read_only=True) — Measurement is a OneToOneField on Customer (crm_api/models.py:95), so this is the single current row, not a per-order snapshot. The assignment card at App.jsx:2572-2600 renders exactly order.customer_measurements under the header "📍 Sizing Blueprint Passed From Master" (line 2582). saveStep2 (App.jsx:1367-1386) PATCHes that same row on every new order, and its own comment at 1369-1372 states the intent plainly: "these are the ones that describe the person, so the newest dress that carries them wins" — deliberate for the customer record, but nobody reconciled it against the order-scoped screen that reads it. Measurement.save() (crm_api/models.py:108) only appends a MeasurementHistory row; it versions nothing that an order points at. The per-order snapshot does exist in GarmentJob.measurements and is nested by OrderSerializer.garment_jobs (crm_api/serializers.py:180-186, whose comment says it was added precisely so the tailor can see what the customer asked for).

**Fix.** Replace the auditor's fix — it does not drop in. GarmentJob.measurements is keyed by TEMPLATE keys (chest/hip/floor_length/petticoat_waist), while the assignment card hardcodes the seven Measurement columns (bust/waist/hips/shoulder/arm_length/neck/length), so the keys do not line up. Instead, on the assignment card block (frontend/src/App.jsx:2572-2600), render order.garment_jobs[].measurements generically as key/value pairs — the same shape the "What to make" panel already renders at App.jsx:8398-8412 — when the order has jobs, and fall back to order.customer_measurements only when it has none. That makes the two production screens read the same snapshot.

### Mobile numbers are stored exactly as typed, so the same customer can be created twice and cannot be found by search
`crm_api/serializers.py:382`

**Impact.** Staff type the number differently on a return visit — '+91 98765 43211' where the record says '9876543211'. Both search paths miss, the unique index does not fire because the strings differ, and a second customer record is created. That client's measurements, measurement history, design preferences and order history split across two profiles, and the directory shows one person twice.

**Evidence.** Confirmed; the cited line 378 is the check, line 382 is the `return value` that is the actual defect. validate_mobile_number (crm_api/serializers.py:367-382) calls whatsapp_number(value) purely as a reachability predicate and returns the raw string. Its docstring (368-377) explains why the check was added — a nine-digit slip producing a dead WhatsApp button — and correctly calls whatsapp_number "the single definition of what is reachable"; it just never writes that definition back. whatsapp_number (crm_api/models.py:14-56) does canonicalise, stripping '00', a leading country code on over-length input, and a national trunk zero, so '+91 (0) 98765 43211', '0091 9876543211' and '098765 43211' all return '919876543211'. Customer.mobile_number (crm_api/models.py:62) is unique=True on the raw column. I grepped whatsapp_number across the repo: it is used only here and in crm_api/models.py:446 for outbound messaging — nothing normalises on write. Both search paths are literal JS substring matches on the raw value: App.jsx:1658 and App.jsx:1767. The ponytail comment in whatsapp_number (models.py:33-36) flags only the single-country assumption, not the storage question, so no comment covers this tradeoff.

**Fix.** Agreed. Make CustomerSerializer.validate_mobile_number (crm_api/serializers.py:382) return the canonical form — `return whatsapp_number(value) or value` — so create and update, the wizard and the API all store one shape. One caveat to handle in the same change: existing rows are unnormalised, so ship a data migration that runs whatsapp_number over Customer.mobile_number (resolving any collisions it surfaces) or the fix only helps rows created after it lands.

### Tracking page shows the wrong garment for a repeat customer
`crm_api/templates/crm_api/tracking.html:88`

**Impact.** A returning customer's older tracking link names the garment from her newest order — the one line on the page that tells her what is being made is wrong for every order but the latest.

**Evidence.** Confirmed. tracking.html:88 renders `{{ customer.garment_type }}`; I read Order's full field list (crm_api/models.py:249-296) and there is no garment field on it — garment_type exists only on Customer (models.py:68). The wizard's step 1 saves with `api.updateCustomer(customerId, customerForm)` (App.jsx:1352) and customerForm carries garment_type (App.jsx:107), and App.jsx:725 also rewrites it from the first selected dress. So a second order for the same customer mutates the field behind the first order. domains/orders/notifications.py:46 reads the same live field when composing the confirmation message. The blast radius is wider than the finding says: every staff screen using order.customer_garment_type (App.jsx:2546, 3761, 8100) is retroactively wrong too.

**Fix.** Snapshot it: add `garment_type` to Order, set it from `customer.garment_type` in the Order.objects.create(...) call in OrderService.create_order_for_customer (domains/orders/services.py), and render `{{ order.garment_type }}` in tracking.html:88.

### Tracking page's trial-appointment card never renders: nothing ever sets Appointment.order
`crm_api/tracking_views.py:73`

**Impact.** The customer's tracking page never shows the fitting date, time, boutique address or contact number, even though the boutique booked the appointment in the product.

**Evidence.** Confirmed by reading every link in the chain. tracking_views.py:73-79 builds `trial` from `order.appointments`; Appointment.order is nullable (apps/scheduling/models.py:23) and no writer sets it — AppointmentViewSet.perform_create (apps/scheduling/views.py:33) just saves the serializer, and the only client payload is App.jsx:1078 spreading `appointmentForm`, whose initial state (App.jsx:788-790) is {customer, appointment_type, scheduled_time, assigned_staff, notes}. I read the booking modal's fields (App.jsx:5545-5590): Client / Type / Date & time / With / Notes — no order picker. `grep Appointment.objects.create` outside migrations hits only seed_v2_tasks.py, crm_api/test_workflow.py, apps/tests_modules.py. So order.appointments is always empty and tracking.html:130-140 is dead. The comment at App.jsx:5532-5534 asserts the tracking page 'already renders a trial card from them', which makes this an unfinished wiring, not a documented tradeoff. Severity lowered from high: nothing breaks or errors — one optional card is absent, and the boutique still books the appointment.

**Fix.** Wire the source, not the read: add `order: ''` to appointmentForm (frontend/src/App.jsx:788) and an order <select> to the booking modal (App.jsx:5545-5590) restricted to the chosen client's orders. AppointmentSerializer is `fields='__all__'`, so the backend already accepts it. Do NOT use the proposed `Q(order__isnull=True, customer=order.customer)` fallback — it would show the same appointment on every tracking link a repeat customer holds.

### Stepping back and forward through wizard step 3 creates a duplicate DesignPreference row and re-uploads the same images
`crm_api/views.py:100`

**Impact.** An owner who goes back to change the design notes leaves the client's profile with two or three identical Design Files entries and duplicate copies of every reference image in storage, with no delete in the UI. 'Go with Existing Design' then prefills from the oldest duplicate rather than the current or approved one.

**Evidence.** Confirmed at the cited line. save_design_preferences (crm_api/views.py:65) unconditionally does DesignPreference.objects.create(...) at line 100, after saving every uploaded file to a fresh UUID path at lines 76-81. Frontend: saveStep3 (App.jsx:1388-1398) is called from performNext on step 3 (App.jsx:1530) AND from the save-as-draft path (App.jsx:1571), and handleBack from step 4 returns to step 3 (App.jsx:1315-1317). I checked handleBack and it clears nothing — designFiles survives the round trip, so the same files are re-read and re-saved under new paths. The decisive evidence is the sibling immediately below: save_fabric_selection (crm_api/views.py:186-204) carries a comment describing this exact pathology ("Back/Next through step 4 calls it again, so a customer who changed their mind twice ended up with three FabricSelection rows and no way to delete any of them... a genuinely new selection is what a new order is for") and was fixed to update the latest row, keeping already-attached images when the pass uploaded none. The design path was left on create. So the tradeoff is not defended here — it was explicitly rejected one function away. Confirmed the downstream read too: 'Go with Existing Design' prefills from design_preferences[0] (App.jsx:4331-4332).

**Fix.** Agreed, and it is a direct copy of the neighbour: in save_design_preferences (crm_api/views.py:65-105), take `customer.design_preferences.order_by('-id').first()`, create only when there is none, and guard the reference_images write with `if image_urls or created:` so a pass that uploaded no files keeps the existing ones — exactly the shape of save_fabric_selection at lines 193-204. Return 200 rather than 201 on the update path for the same reason it does.

### Reassigning an order's tailor or master leaves the Available/Busy flags and the production queue on the old person
`crm_api/views.py:308`

**Impact.** After a handover the departing tailor still reads Busy with nothing on their table and the new one reads Available with a dress to sew — the exact badges the owner uses to pick staff — and /api/production/tasks/ keeps naming the old tailor for the stitching task.

**Evidence.** Confirmed. OrderViewSet.perform_update (crm_api/views.py:307-313) does only serializer.save(), _reconcile_payment and a status-change notification — no refresh_staff_availability, whose docstring (domains/orders/services.py:28-42) states the design is that deriving the flag at every write site is what stops it drifting. Every other write site calls it (create_order_for_customer at services.py:277, transition_order_stage at services.py:495-496, and the latter only for the CURRENT order.tailor/master, so the departing person is never recomputed). The reassignment UI exists: App.jsx:3532 and 3545 call handleAssignWorkflow → api.updateOrder → PATCH. ProductionTask rows are stamped at creation (services.py:236-251) and repointed only by assign_stage (crm_api/views.py ~788) or by a stage transition with a performer, so they keep naming the old tailor. The stale badge is visible where it matters — the wizard staff cards (App.jsx:6940) and Manage Tailors both render tailor.status. Only correction: cited frontend lines were 3377/3364, actually 3545/3532.

**Fix.** In OrderViewSet.perform_update (crm_api/views.py:307), capture serializer.instance.tailor_id/master_id before save() and, when either changed, call `refresh_staff_availability(old_tailor, old_master, order.tailor, order.master)` and `ProductionTask.objects.filter(order=order, assigned_to=old_tailor).update(assigned_to=order.tailor)`.

### Editing a staff member's email with any capital letter silently empties their notification feed
`crm_api/views.py:262`

**Impact.** After the owner edits a staff email with any capital letter, that person's notification bell is permanently empty — every order notification is filed under the lowercase address their queryset no longer matches.

**Evidence.** Confirmed by reading the whole function. _ensure_user_account lowercases in memory at crm_api/views.py:245 — after serializer.save() has already persisted the typed casing (perform_update, views.py:233-235) — then on the existing-account branch updates the User and returns at line 262 without any tailor.save(); the only tailor.save() is at line 278 on the create branch. So Tailor.email keeps 'Priya@example.com' while User.email becomes lowercase. _audience returns `profile.email or self.request.user.email` (views.py:853) and get_queryset applies `qs.filter(recipient_email=email)` (views.py:866) — an exact, case-sensitive match — against rows written as order.master.user.email / order.tailor.user.email, i.e. lowercase (notifications.py:55, 62, 117, 133). Login is unaffected (it matches User.email), so the failure is entirely silent.

**Fix.** Persist the normalisation: add `tailor.save(update_fields=['email'])` immediately before the `return` at crm_api/views.py:262. That one line covers both sub-cases of the branch.

### submit_stage_review deletes the previous stage review before writing the new one, outside a transaction
`crm_api/views.py:698`

**Impact.** A staff member re-submitting a stage review with a new photograph loses the earlier review's comments and evidence photo if the write fails, with a 500 as the only feedback. The deleted rows' image files are orphaned on disk regardless, since .delete() removes rows but not files.

**Evidence.** Confirmed at crm_api/views.py:686-708. Line 698 is `OrderStageHistory.objects.filter(order=order, stage=stage).delete()` with the comment '# Delete duplicate history for same stage if any exists', and the replacement `OrderStageHistory.objects.create(...)` is at :700-706 with `image` taken from `request.FILES` at :691. There is no @transaction.atomic on the action, and crm_api/views.py imports only `from django.db.models import Q, Sum, Count` (:18) -- `transaction` is not imported, confirming nothing wraps it. RolePermission.STAFF_ORDER_ACTIONS (core/permissions.py:45) includes submit_stage_review, so ordinary production staff reach it. Kept at medium rather than raised: the create failing needs a storage or write error, which is uncommon, but the loss is silent and permanent when it happens.

**Fix.** Agree. Add `from django.db import transaction` to crm_api/views.py and decorate OrderViewSet.submit_stage_review with `@transaction.atomic` (below the @action decorator), so the delete rolls back if the create fails.

### Customer spend uses SUM(DISTINCT), so repeat orders at the same price are counted once
`domains/customers/repositories.py:42`

**Impact.** A returning client with repeat orders at an identical price shows a lifetime spend equal to one order in the customer list and on the dashboard, can be mis-segmented (HVC instead of VIP at two identical orders), and her Style Profile budget line is skewed.

**Evidence.** Verified, including the comment the auditor was supposed to check. repositories.py:34-44 carries a long comment explaining that distinct=True was added because visible_customers joins orders__stages and multiplies each order by fifteen stage rows — but SUM(DISTINCT col)/AVG(DISTINCT col) de-duplicate equal VALUES, not duplicate join rows, so the stated fix does not do what the comment claims and introduces a new error. Django==6.0.6 (requirements.txt) has Sum.allow_distinct/Avg.allow_distinct True, so this really emits SUM(DISTINCT total_amount). It backs the customer list (crm_api/views.py:53) and dashboard recent_customers (views.py:919), feeding CustomerSummarySerializer.get_total_spend/get_segment (serializers.py:509-522) and build_style_dna's avg_price (serializers.py:528), while the detail CustomerSerializer.get_total_spend sums the rows properly (serializers.py:398) — so the same client shows two different lifetime figures. No test covers duplicate amounts (crm_api/test_data_integrity.py:93-124 only uses distinct values or a single order). One correction to the auditor's impact: three ₹25,000 orders still segment as VIP, because get_segment (serializers.py:517) ORs on order_count >= 3 and Count is correctly distinct; the segment only goes wrong at two identical orders (e.g. 2 × ₹40,000 shows ₹40,000 → HVC instead of VIP). Severity medium, not high: a wrong displayed figure on the list/dashboard, contradicted by the correct detail view, and only when amounts repeat exactly.

**Fix.** In CustomerRepository.summary_queryset (domains/customers/repositories.py:42-43) replace both distinct aggregates with a per-customer subquery, e.g. Subquery(Order.objects.filter(customer=OuterRef('pk')).values('customer').annotate(s=Sum('total_amount')).values('s')) for spend and the same shape with Avg — a subquery is immune to the stages-join fan-out the comment was guarding against. Count('orders', distinct=True) is correct and stays. Update the comment so the next reader does not re-add distinct.

### Specialist staff never see their order notifications: write side hardcodes Master/Tailor, read side filters on the profile role
`domains/orders/notifications.py:61`

**Impact.** A specialist assigned as an order's stitching tailor receives no 'New Stitching Task' and no 'Stitching Ready' notification; the rows are filed under a role nobody holds and their bell stays empty while work waits.

**Evidence.** Confirmed on both sides. create_order_notifications writes literal recipient_role="Master" (notifications.py:54, 132) and "Tailor" (61, 116). NotificationViewSet._audience returns profile.role (crm_api/views.py:853) — one of Tailor.ROLE_CHOICES (crm_api/models.py:226-236, which includes 'Cutting Master', 'QC Master', 'Pressing Staff') — and get_queryset filters recipient_role=role (views.py:864). The stitching-tailor pickers really do offer every specialist: `tailors.filter(t => t.role !== 'Master')` at App.jsx:3400 (order wizard step 5) and App.jsx:6935/3518 (assignment cards). assign_stage does it correctly with recipient_role=tailor.role (crm_api/views.py:770), which confirms the intended contract. One correction: the master side is safe in practice — every master picker filters `t.role === 'Master'` (App.jsx:3333, 3505, 6878) — so only the tailor literals bite through the UI. Severity lowered from high on that basis: it only hits boutiques that assign a specialist (not a plain 'Tailor') as the order's stitching tailor.

**Fix.** In domains/orders/notifications.py, replace the two tailor literals (lines 61 and 116) with `order.tailor.role`, matching crm_api/views.py:770. Change lines 54 and 132 to `order.master.role` in the same pass for the direct-API case.

### OrderSerializer reads garment_images and job materials that ORDER_PREFETCH never fetches
`domains/orders/repositories.py:6`

**Impact.** Every /api/orders/ list and every order detail pays one extra query per order for garment_images plus one per JobMaterial row that points at stock. Since /api/orders/ is unpaginated and getOrders runs on every dashboard refresh and on every stock-movement modal open, that cost repeats all day.

**Evidence.** Confirmed. ORDER_PREFETCH (:6-18) ends at 'garment_jobs__materials' (:17). 'garment_images' is absent, yet OrderSerializer declares `garment_images = GarmentImageSerializer(many=True, read_only=True)` at crm_api/serializers.py:52 of the class body (the related_name exists: crm_api/models.py:382). 'garment_jobs__materials__inventory_item' is absent, yet JobMaterialSerializer reads `source='inventory_item.name'` (apps/catalog/serializers.py:56) and inventory_item is a real FK (apps/catalog/models.py:208). The module comment at :3-4 does claim it 'Mirrors every relation OrderSerializer reads', so the omission is an oversight, not a documented tradeoff. Severity lowered from high: it is two extra queries per order on an endpoint that is already doing the heavy work correctly for everything else, so it is a real but bounded cost, not a new failure mode.

**Fix.** Agree. Add 'garment_images' and 'garment_jobs__materials__inventory_item' to ORDER_PREFETCH. Every list and detail path routes through OrderRepository.base_queryset, so this tuple is the only place to change. (Note: do NOT 'fix' this by switching the list to OrderSummarySerializer -- App.jsx:322 and :8373 read garment_images and garment_jobs off list rows.)

### A saree-only order stalls with "Measurements are not completed" even though a saree needs no body measurement
`domains/orders/services.py:334`

**Impact.** Saree fall/pico/finishing work is bread-and-butter for an Indian boutique, and every such order for a new client refuses to advance past Assigned to Tailor with a message naming a step the wizard never asked for. The reason given is wrong, so the natural response is to hunt for a measurement form that does not apply to a saree.

**Evidence.** Confirmed at both cited lines. has_measurements is defined identically twice — domains/orders/services.py:172-174 in create_order_for_customer and 334-336 inside transition_order_stage — as customer.measurements.bust or .waist or .hips. Those three columns are written only by saveStep2's CUSTOMER_KEYS map (App.jsx:1374-1383), which reads template keys chest/waist/hip/shoulder/neck off the garment job; I grepped App.jsx for every other write to customerForm.measurements and there is none, and there is no editable measurement form anywhere in the frontend (all other hits at 2590-2596, 4119-4125, 4440-4443, 4478-4484 are read-only renders). The saree template's measurements section (apps/catalog/definitions.py:176-180) contains only petticoat_length and petticoat_waist, both themselves conditional on petticoat_required — neither key is in CUSTOMER_KEYS. So a saree-only order for a new client leaves bust/waist/hips NULL, create_order_for_customer sets current_stage_key='created' (line 199) and seeds the measurements_completed stage NOT_STARTED (line 219), and completing assigned_to_tailor raises 'Cannot assign tailor. Measurements are not completed for this customer.' (line 338). No comment anywhere defends this. Medium is right, not higher: nothing blocks completing the measurements_completed stage manually first, so the order is recoverable.

**Fix.** Agreed. Lift the duplicated expression into one module-level helper in domains/orders/services.py used by both line 172 and line 334, and widen it to also return True when the order carries a garment job with a non-empty measurements dict: `order.garment_jobs.exclude(measurements={}).exists()`. That is the per-dress snapshot the wizard genuinely captured. The create-time call site has no order yet, so pass the in-flight garment jobs or keep the customer-only check there and widen only the transition guard at line 334 — the transition is the one that blocks the flow.

### Completing or skipping a lagging stage after delivery walks the order backwards and re-messages the customer
`domains/orders/services.py:446`

**Impact.** A delivered order reverts to an in-production status, the customer's tracking page and WhatsApp say the finished garment is being crafted, and the order reappears in the owner's active-orders table.

**Evidence.** Confirmed at services.py:444-447: `previous_order_status = order.order_status` / `if stage_key in status_map: order.order_status = status_map[stage_key]` — an absolute assignment with no ordering. The only regression guard is services.py:368 (`order_stage.status == 'COMPLETED' and new_status == 'COMPLETED' -> return order`), and its own comment (362-369) states the problem in exactly these terms while covering only the same-stage re-completion. The prerequisite chain is as described: delivery needs QC (314-317), QC needs stitching_completed (356-360), and maggam_work is marked optional (crm_api/models.py:465) — so it, pattern_cutting, finishing, pressing and trial_* can be NOT_STARTED on a Delivered order. Transitioning any of them afterwards rewrites order_status backwards and status_changed (498-502) is True, firing the 'now in the Design & Creation phase' message (notifications.py:73-74). Deflated from high to medium: it requires housekeeping on a stage after the order is already delivered, and the state is recoverable by the Owner.

**Fix.** Same site (domains/orders/services.py:444-446): make the write monotonic — keep a module-level ordered tuple of the client-facing statuses (the same order as OrderViewSet.CLIENT_STATUSES lists) and assign status_map[stage_key] only when its index exceeds the index of order.order_status.

### Setting TAILOR_DEFAULT_PASSWORD makes the "Share credentials" screen hand staff a password that does not work
`frontend/src/App.jsx:5757`

**Impact.** An operator who follows the code's own advice and sets TAILOR_DEFAULT_PASSWORD silently breaks staff onboarding: the owner WhatsApps the printed credentials and the tailor gets 'Invalid login credentials'.

**Evidence.** Read frontend/src/App.jsx:5754-5788: the modal prints the literal 'TailorSecure2026!' under 'Temporary Password' (5757), and the same literal is baked into the Copy text (5769) and the WhatsApp text (5783). The server side is os.environ.get('TAILOR_DEFAULT_PASSWORD', 'TailorSecure2026!') (crm_api/views.py:272) and nothing returns that value to the client — TailorSerializer carries no password field. Same split for designers (apps/design_studio/views.py:515 vs DesignDashboard.jsx:11, whose comment admits 'The server never returns this'). Also wrong in a second case the auditor missed: _ensure_user_account (views.py:264) reuses an already-existing User untouched, so for any staff member who already has an account the modal advertises a password that was never set on it. SEVERITY CORRECTED down from high: it only bites an operator who sets the env var (default matches the literal), and a locked-out staff member can now self-serve through 'Forgot password?' (App.jsx:1893-1900) — though with EMAIL_BACKEND defaulting to console (boutique_crm/settings.py:324-327) that link only reaches the server log.

**Fix.** Have the server return the password it actually set (previous finding) and render that field in the modal, the copy text and the WhatsApp text; delete DESIGNER_BOOTSTRAP_PASSWORD from DesignDashboard.jsx and use the same field.

### Signing out does not clear the loaded boutique data, so it can render into the next session on that machine
`frontend/src/App.jsx:1237`

**Impact.** On a shared machine used by two boutiques, one boutique's customer rows, order rows and boutique settings display to the other's owner until every refetch lands — and stay if one fails.

**Evidence.** The code is as described — handleLogout (App.jsx:1237-1241) is `await api.logout(); setCurrentUser(null); setView('login');` and leaves dashboardData, customersList, ordersList, tailors, appointments and boutiqueSettings in state; handleLoginSubmit (1172-1186) sets the view to dashboard before fetchDashboardAndConfig resolves, the loading gate at 1790 is `loading && !dashboardData && view === 'login'`, and a failed request in fetchDashboardAndConfig only appends to loadErrors (966-970) leaving the old value. BUT THE AUDITOR'S IMPACT IS WRONG: a Master is not shown data 'visible_orders/visible_customers exists to keep from them' — core/permissions.py:120-124 returns the full queryset for Owner and Master, so the order book and customer directory are theirs by design; a Tailor lands on 'assignments' whose list is filtered by isMyAssignment against the NEW user's tailor_id (App.jsx:1671-1677, 2509), and a Designer's login returns before any fetch with a designs-only nav (2443-2449). The residue that genuinely renders is the cross-boutique case: two different tenants signing in on the same browser without a reload, where boutique A's rows and settings paint for boutique B's owner during the refetch window and persist indefinitely if one of those requests fails.

**Fix.** Make handleLogout (App.jsx:1237) drop all in-memory state in one line: `await api.logout(); window.location.reload();`.

### My Account tells every staff member they are the "Boutique Owner" and offers them an editor that always fails
`frontend/src/App.jsx:5327`

**Impact.** A tailor or master opens My Account, is labelled Boutique Owner, edits the name/address/phone that print on customer invoices, and gets 'Failed to update boutique settings' with no reason, every time.

**Evidence.** Confirmed, with corrected lines. The account panel (App.jsx:5292-5500) has no role check: the hardcoded <p>Boutique Owner</p> is at 5327, the hardcoded 'Registered Since' / 'June 2024' at 5344-5346, and the 'Edit Boutique Profile' form at 5352 renders for everyone. 'My Account' sits outside the role branches in the nav, at line 2453. Submitting calls api.updateBoutiqueSettings, a POST to /boutique-settings/ (api.js:403-411) that throws the fixed string 'Failed to update boutique settings' on any failure; server-side, BoutiqueSettingsViewSet (crm_api/views.py:933) names no permission class so it gets RolePermission (settings.py:373-375), whose has_permission (core/permissions.py:66-80) allows a non-Owner only SAFE_METHODS plus the named order actions — 'create' is on neither list, so a 403 is certain for Master, Tailor and Designer.

**Fix.** In App.jsx, print the session role at 5327 (`{currentUser.role || 'Boutique Owner'}`) and wrap the Edit Boutique Profile card at 5351 in `{(!currentUser.role || currentUser.role === 'Owner') && ( ... )}`.

### Orders registry shows each order's Total Value to a Master, which the assignments card deliberately hides
`frontend/src/App.jsx:3859`

**Impact.** Every Master sees the price of every garment in the boutique on the registry they use daily, contradicting the rule the product enforces on their own assignments screen. Within-tenant disclosure to a supervisor role; no data loss.

**Evidence.** Confirmed; line corrected from 3691 to 3859-3860. The Orders registry renders the 'Total Value' block with no role test at App.jsx:3858-3861, and the Master nav routes to that tab (App.jsx:2440); the same registry has a `currentUser.role === 'Master'` branch at 3868, so Masters demonstrably reach it. One screen earlier the identical figure is gated: `{!isProductionStaff(currentUser.role) && <div>Total Value: ...}` (App.jsx:2566), and isProductionStaff (App.jsx:53) includes 'Master' via PRODUCTION_ROLES (App.jsx:49-52). The rule is stated in the comment at App.jsx:44-48 and echoed server-side at crm_api/views.py:603-607. OrderSerializer emits total_amount/advance_paid/amount_paid to every caller who can read the order (crm_api/serializers.py:199-215), so the API does not enforce it either. Genuine inconsistency, not a misread. I did NOT keep the proposed serializer fix: OrderSerializer is the read path for the invoice modal, the tracking page and the whole registry, and popping money fields there is a broad behavioural change with several unaudited consumers -- not the smallest correct fix for the screen actually named.

**Fix.** Wrap the Total Value block at App.jsx:3858-3861 in the same guard already used at App.jsx:2566: `{!isProductionStaff(currentUser.role) && ( ... )}`. One line, consistent with how the product enforces this rule everywhere else.

### The status dropdown offers production staff eight options their role can never set
`frontend/src/App.jsx:2542`

**Impact.** A tailor picking any status but 'Design & Creation' gets an alert and the dropdown snaps back; a Measurement/Pattern/Cutting/Maggam/Finishing/Pressing master gets an alert whatever they pick. Seven or eight of eight controls on the only screen these roles have produce nothing but an error.

**Evidence.** Confirmed; line corrected from 2373 to 2542. The assignments card renders a `<select>` at App.jsx:2542-2558 with all eight client statuses hard-coded, for every production role, posting to api.updateOrderStatus with `.catch(err => alert(...))`. update_status (crm_api/views.py:437) maps via STATUS_TO_STAGE (382-399) and defers to OrderService.transition_order_stage, which raises for any role not in that stage's list (domains/orders/services.py:305-312); the two statuses that map to no stage ('Stylist Review', 'Shipped') are gated to Owner/SUPERVISOR_ROLES at views.py:462-477. Against get_default_workflow (crm_api/models.py:458-476): a Tailor is on stitching_in_progress and stitching_completed only, so of the eight options only 'Design & Creation' succeeds (7 of 8 fail). One correction to the finding: a QC Master IS on master_quality_check, so 'Quality Check' works for them -- it is the Measurement/Pattern/Cutting/Maggam/Finishing/Pressing roles for whom all eight fail. Verified the proposed fix leaves a working control: StageTimeline is rendered in the same card (App.jsx:2627).

**Fix.** Render the `<select>` at App.jsx:2542 only for Owner/supervisors -- `{(!currentUser.role || currentUser.role === 'Owner' || SUPERVISOR_ROLES.includes(currentUser.role)) && ( ... )}` -- leaving the read-only status badge at 2539-2541 for everyone else. Production staff keep StageTimeline (2627), which is the control the workflow engine is built around, and update_status's own comment says 'Moving an order without doing the work is a supervisor's call.'

### Staff credential-share modal hardcodes a bootstrap password the server may have been configured away from
`frontend/src/App.jsx:5757`

**Impact.** On a deployment that follows its own security note and sets TAILOR_DEFAULT_PASSWORD/DESIGNER_DEFAULT_PASSWORD, every staff invitation the new owner sends carries a password that does not work; the owner has no way to see the real one and has to talk the staff member through the reset flow.

**Evidence.** Confirmed on both sides. The modal prints the literal 'TailorSecure2026!' at App.jsx:5757, embeds it in the clipboard string at 5769 and in the WhatsApp message at 5783. The server creates the account with os.environ.get('TAILOR_DEFAULT_PASSWORD', 'TailorSecure2026!') at crm_api/views.py:272, under a comment (266-268) that instructs the operator to override it. Nothing in the API response carries the actual password. Identical split for designers: DESIGNER_BOOTSTRAP_PASSWORD = 'DesignerSecure2026!' at frontend/src/features/designStudio/DesignDashboard.jsx:11, rendered at :216, vs os.environ.get('DESIGNER_DEFAULT_PASSWORD', ...) at apps/design_studio/views.py:515, whose response (523-527) is only the serialized Designer. Downgraded from high on two counts: it only bites on deployments that set the env var, and the auditor's 'no password-reset flow in the product at all' is false -- staff accounts are found by find_tenant_for_account's schema scan (crm_api/auth_views.py:49-57), so a staff member whose Tailor row has an email can recover via Forgot password.

**Fix.** Return the bootstrap password once, at creation time: include it in the response of TailorViewSet.perform_create (crm_api/views.py:229) and DesignerViewSet.create_login (apps/design_studio/views.py:523), and render that value in the modal instead of the literals at App.jsx:5757/5769/5783 and DesignDashboard.jsx:11.

### handleDeleteTailor is dead code — no staff member can be removed from the UI
`frontend/src/App.jsx:1106`

**Impact.** An owner cannot remove the four seeded fictional tailors or a real tailor who has left; they stay in every assignment dropdown and in the stage-assignment picker.

**Evidence.** Confirmed. handleDeleteTailor is declared at App.jsx:1106 and grep across App.jsx finds no other reference. I read both staff cards: the Master block (App.jsx:3363-3409) and the Stitching block render only the status badge, a 'Share' button and an 'Edit' button. api.deleteTailor exists at frontend/src/services/api.js:595 and TailorViewSet is a ModelViewSet so DELETE works. Corrected the auditor's line numbers (cards are at 3356/3414, not 3193/3260). Downgraded from high: Edit lets an owner repurpose or rename a row, staff turnover is not weekly, and the auditor's 'keeps a live login' consequence is wrong anyway -- Tailor.user is an FK to User, so deleting the Tailor would not delete or disable the User account either.

**Fix.** Add a delete button calling handleDeleteTailor(tailor.id) next to the existing Edit button in both staff cards (frontend/src/App.jsx around 3404 and the matching Stitching block) — handler and API method already exist.

### Edit Boutique Profile falls back to placeholder strings that get saved over real data
`frontend/src/App.jsx:5394`

**Impact.** An owner who opens the profile page during a transient settings-load failure and saves any change silently overwrites their boutique's real name, address, phone and email with the vendor demo strings, which then print on every invoice and every customer tracking page.

**Evidence.** Confirmed; line numbers were ~168 low. defaultValue={boutiqueSettings?.address || "123 Atelier Way, Fashion District"} at App.jsx:5394, and the same pattern for name (5383 -> 'Scaleezy Atelier'), phone (5406 -> '+91 9999999999') and email (5416 -> 'contact@scaleezy.com'). All four are `required` and the submit handler (5354-5374) appends every one of them to the FormData unconditionally. fetchDashboardAndConfig's load() helper (App.jsx:972-977) records a failed settings request in loadErrors and leaves boutiqueSettings null rather than blocking the screen, and the profile view has no loadErrors branch (the only one is for customers, at 4056). BoutiqueSettingsViewSet.create (crm_api/views.py:939-961) writes any non-null field, so the placeholders land in the database.

**Fix.** Change the four defaultValue fallbacks (frontend/src/App.jsx:5383, 5394, 5406, 5416) to `|| ''` and move the strings into `placeholder` attributes, so an unloaded form cannot submit fabricated values.

### Signup step 2 asks for an OTP that is never sent and never checked
`frontend/src/App.jsx:1202`

**Impact.** A prospective owner waits for an SMS that will never arrive, on the acquisition funnel's second screen, with no resend to reveal the problem. Anyone who types arbitrary digits gets through, so the step also verifies nothing.

**Evidence.** Confirmed. handleVerifyOTP (App.jsx:1202-1208) checks only `if (!otpCode)` and then setSignupStep(3) — no API call exists, and SignupView never touches the mobile number except to store it as BoutiqueSettings.phone (crm_api/auth_views.py:160). handleSignupSubmit's own trailing comment reads '// Mock verification' (App.jsx:1199). The screen asserts 'We have sent a 6-digit OTP code to +91 {signupForm.mobile_number}' (App.jsx:2181) and offers only 'Verify OTP' and 'Back' (2197, 2200) — no resend, no skip. Lines were ~77 low but the code is exactly as described.

**Fix.** Remove step 2 from the wizard (frontend/src/App.jsx:2179-2204) and have handleSignupSubmit (1199) set step 3 directly, dropping the 'We have sent' claim and the handleVerifyOTP handler.

### A returning customer's saved measurements are never prefilled into the new order form
`frontend/src/App.jsx:689`

**Impact.** Every repeat order forces the staff member to re-measure or hand-copy chest/waist/hip/shoulder/neck from the directory profile into the garment form, because the wizard never shows the saved values on the same screen. The "Existing Customer" card promises a time saving that does not exist, and each retype is a chance to transpose a digit the cutter then cuts to.

**Evidence.** Confirmed but the cited line was wrong — addGarment is at App.jsx:689, not 677, and handleSelectExistingCustomer is at 1269, not 1217. The code is as described: addGarment always pushes { key, template, values: {} } (line 692) and handleSelectExistingCustomer clears garmentJobs (line 1288). I grepped customerForm.measurements across App.jsx: it appears at exactly two places — line 1276 where the fetched customer's measurements are loaded into customerForm, and line 1373 inside saveStep2, which only copies the other way (garment job -> customer, via CUSTOMER_KEYS chest->bust, waist->waist, hip->hips, shoulder->shoulder, neck->neck). TemplateForm has no default-seeding path. The order-selector card does advertise the opposite: "Select a client profile from your database and retrieve their measurements" (App.jsx:6001) with a ticked "Use saved measurements" (App.jsx:6006). Required measurement fields do exist (e.g. lehenga waist and floor_length, apps/catalog/definitions.py:268-269), so the wizard genuinely will not advance until they are retyped. Severity corrected down from high: nothing here writes wrong data or blocks the flow — the staff member can complete the order by retyping, and the saved values are visible in the Customer Directory profile panel. This is advertised-but-absent convenience plus a re-entry risk, which is degraded-but-workable.

**Fix.** Agreed. In addGarment (frontend/src/App.jsx:689), seed values from customerForm.measurements using the inverse of the CUSTOMER_KEYS map already written in saveStep2 (bust->chest, hips->hip, waist->waist, shoulder->shoulder, neck->neck), keeping only keys the just-fetched template actually defines. One function; both the wizard and the 'Go with Existing Design' entry point route through it. If the fix is not taken, delete the "Use saved measurements" tick at App.jsx:6006 so the card stops promising it.

### An order whose garment specs fail to save reports "Failed to submit order" while the order exists, so retrying books a duplicate
`frontend/src/App.jsx:1487`

**Impact.** On a failed garment-job POST the owner sees a message implying nothing was saved; retrying creates a second order with its own production tasks, notifications and revenue, while the first sits on the floor with no garment spec.

**Evidence.** Confirmed, though the cited line was wrong: createOrder is App.jsx:1451, `await saveGarmentJobs(order.id)` is App.jsx:1454, and the outer catch that alerts the bare "Failed to submit order." is App.jsx:1485-1488. saveGarmentJobs re-raises (App.jsx:751) and there is no inner try around it, unlike the design-board block immediately below (1456-1470) whose comment explicitly reasons about not rolling the order back and telling the owner what is missing. Server side GarmentJobSerializer.validate (apps/catalog/serializers.py:94-127) is authoritative and OrderService.create_order_for_customer is atomic over the order only, so the order is already committed when the job POST fails. Nothing resets the wizard, so pressing the CTA again runs createOrder again (runOnce at App.jsx:1497 only blocks double-clicks within one call). Deflated from high to medium: garmentJobs are validated client-side against the same engine at step 2 (performNext, App.jsx:1533-1536), so the realistic trigger is a transient/auth failure rather than a routine validation divergence.

**Fix.** In submitOrderAndConfirm (frontend/src/App.jsx:1454), wrap only the saveGarmentJobs call in its own try/catch mirroring the design-board branch below it: alert `Order ${order.order_id} was created, but its garment details could not be saved (${err.message}) — open the order and add them`, then fall through to setConfirmedOrder/setView('confirmed') so the button cannot be pressed twice.

### The Stitching Tailor picker offers specialist masters who are forbidden from the stitching stages, stalling the order
`frontend/src/App.jsx:6965`

**Impact.** In a split-role studio, assigning stitching to e.g. the Finishing Master produces an order they can see but can never advance: every stitching transition 400s with a raw role message, no assignment notification reaches them, and their screen shows no completion panel.

**Evidence.** Real, but both cited line numbers were wrong: the wizard's step-5 Stitching Tailor list is App.jsx:6959/6965 and the owner's Workflow Assignment select is App.jsx:3548; both filter `t.role !== 'Master'`. Tailor.ROLE_CHOICES (crm_api/models.py:226-236) contains seven non-Master specialist roles that all pass that filter, while get_default_workflow restricts both stitching stages to ["Owner", "Tailor"] (crm_api/models.py:467-468) and transition_order_stage enforces it at services.py:310-312. The mismatch is real and the codebase already knows the right pattern — eligibleStaffForStage (App.jsx:1731-1736) filters by the stage's own role list and is used for stage assignment. Notification side confirmed too: notifications.py:57-63 hardcodes recipient_role="Tailor" while NotificationViewSet._audience keys on profile.role (crm_api/views.py:848-853, whose docstring specifically says specialists must not be cut off), and the completion panel is gated on `currentUser.role === 'Tailor'` (App.jsx:2711).

**Fix.** Change both pickers (frontend/src/App.jsx:3548 and 6959/6965) from `t.role !== 'Master'` to `eligibleStaffForStage('stitching_in_progress')`, which already reads the stage's own role list from boutique settings; and in domains/orders/notifications.py:60 use `recipient_role=order.tailor.role` instead of the literal "Tailor".

### "Partially Paid" in the Invoices table is a silent no-op that reverts to the previous status
`frontend/src/App.jsx:4972`

**Impact.** The owner selects 'Partially Paid' after taking a part payment, sees no error, and the row snaps back to Pending on refresh. There is no control anywhere in the product for recording a part payment against an existing order.

**Evidence.** Confirmed; the line is 4972 (dropdown option at 4982), not 4804. The handler PATCHes only `{ payment_status: e.target.value }`. In _reconcile_payment (crm_api/views.py:334-355) neither 'amount_paid' nor 'advance_paid' is in `changed` and the value is neither 'Paid' nor 'Pending', so it falls to `else: paid = order.amount_paid or Decimal('0')` and the label is re-derived from the unchanged amount — 'Pending' on an unpaid order. The docstring above it (crm_api/views.py:334-335) says the Invoices row 'only needs to PATCH a number', but grepping App.jsx for amount_paid finds only display sites (4860, 4861, 4965, 4966, 5010) — no input anywhere writes it after order creation. So the documented remedy was never built on the client and the no-op the docstring records is still shipping.

**Fix.** In the Invoices row (frontend/src/App.jsx:4966-4985) add a small amount input next to the Balance cell that PATCHes `{ amount_paid: <value> }` via api.updateOrder; _reconcile_payment already clamps it to the total and derives the label, so the payment_status dropdown can stay read-only display.

### Blank advance box books half the order total as money received
`frontend/src/App.jsx:1444`

**Impact.** An owner who picks 'Pay Partially Now' and types nothing books half the total as collected: Invoices 'Total Collected', Analytics collected revenue, the tracking page balance (crm_api/tracking_views.py:82) and the Delivered WhatsApp balance (domains/orders/notifications.py:93) are all short by that amount until someone notices.

**Evidence.** Confirmed by reading the code. App.jsx:1444 is `advance_paid: paymentOption === 'full' ? getTotalPrice() : (parseFloat(advancePaymentAmount) || getTotalPrice() / 2)`; the state is useState(0) (line ~608) and the input is `value={advancePaymentAmount || ''}` with `onChange={... parseFloat(e.target.value) || 0}` (App.jsx:7491-7494), so an untouched or cleared field is 0 and `||` substitutes half the total. domains/orders/services.py:167-170 stores it verbatim (clamped) into both advance_paid and amount_paid, and the clamp comment there only explains the min/max, not the 0.5 default. But the auditor overstated the surprise: the wizard's own preview at App.jsx:7505 uses the identical `advancePaymentAmount || getTotalPrice() / 2` fallback, so the owner is shown 'Remaining Balance Due at Delivery = total/2' at the moment of entry, and the placeholder is the same half figure. It is a half-default that the owner can see, not a silent invention, and it only bites when the intended advance was zero — for which the wizard has no option at all. Wrong money in the ledger, but visible and workable: medium, not high.

**Fix.** Fix both halves of the same expression or the UI starts lying instead: in submitOrderAndConfirm send `parseFloat(advancePaymentAmount) || 0` (App.jsx:1444) AND change the preview at App.jsx:7505 to `Math.max(0, getTotalPrice() - (advancePaymentAmount || 0))`, then drop the `total_amount * 0.5` default in OrderService.create_order_for_customer (domains/orders/services.py:168) so an omitted advance means zero. Sending 0 while leaving the preview on the half-fallback would only move the inconsistency.

### Printed invoice shows a balance still owing on an order that is fully paid
`frontend/src/App.jsx:8184`

**Impact.** An order booked with a ₹10,000 advance on ₹33,075 and later marked Paid prints 'Payment Status: Paid' directly above 'Advance Paid ₹10,000 / Balance Due ₹23,075' — the customer is handed a bill demanding money already paid.

**Evidence.** Verified. The invoice modal prints Payment Status from confirmedOrder.payment_status (App.jsx:8180) and then, guarded by `confirmedOrder.advance_paid > 0` (8182), 'Advance Paid' from advance_paid (8186) and 'Balance Due' as total_amount - advance_paid (8184) — advance_paid, never amount_paid. OrderViewSet._reconcile_payment (crm_api/views.py:361) only ever caps the advance: `order.advance_paid = min(order.advance_paid or Decimal('0'), paid)`, so after an order is settled amount_paid == total while advance_paid stays at the original advance. The modal is reachable for any existing order — Invoices row 'View Invoice' does setConfirmedOrder(order) (App.jsx:4957-4959) — so the contradiction prints for real orders. Auditor's line number (8057) was wrong; the file is being edited concurrently, so cite by content. Severity lowered from high: the same document prints 'Paid' immediately above the phantom balance and the Invoices table beside it shows the correct Balance Due, so it is a self-evident contradiction on paper rather than an undetectable money error.

**Fix.** In the invoice payment block (frontend/src/App.jsx:8182-8189) switch the guard and both figures to amount_paid: render 'Amount Paid' from parseFloat(confirmedOrder.amount_paid) and Balance Due as Math.max(0, total_amount - amount_paid) — the same expression the Invoices table already uses at App.jsx:4936 and tracking_views.py:82.

### "Partially Paid" in the Invoices dropdown is a silent no-op; a part payment cannot be recorded after creation
`frontend/src/App.jsx:4942`

**Impact.** A customer paying ₹10,000 of ₹33,075 at the counter cannot be recorded: choosing 'Partially Paid' shows no error and reverts on the refetch, leaving the owner only ₹0 or the full amount, so collected revenue, the tracking-page balance and the delivery message stay wrong until the order is fully settled.

**Evidence.** Verified. The only post-creation payment control is the Invoices select, which sends exactly `api.updateOrder(order.id, { payment_status: e.target.value })` (App.jsx:4942). grep for amount_paid across frontend/src returns five hits, all reads (App.jsx:4830, 4831, 4935, 4936, 4980) — nothing ever PATCHes it, and the only other updateOrder caller is handleAssignWorkflow (App.jsx:1130) for staff. In _reconcile_payment (crm_api/views.py:339-346) a PATCH carrying only payment_status hits neither the amount branch nor the Paid/Pending branches when the new label is 'Partially Paid', so `paid = order.amount_paid or 0` and the label is re-derived from the unchanged number: a Pending order snaps back to Pending, a settled order back to Paid. The docstring at views.py:318-336 states the intent explicitly — 'the Invoices row only needs to PATCH a number' — so the backend was finished and the control was never wired. Severity lowered from high: the owner can still record the final settlement via 'Paid', so the gap is an unrecordable intermediate instalment plus one dropdown option that silently reverts.

**Fix.** Add a number input beside the status select in the Invoices row (frontend/src/App.jsx:4938-4952) that PATCHes `{ amount_paid: value }` through api.updateOrder — endpoint, clamping and label derivation already exist in _reconcile_payment. Keeping the 'Partially Paid' option in the select without it is the part that must not ship.

### Order confirmation screen always says "Paid" for the full total, even on a part-paid order
`frontend/src/App.jsx:7895`

**Impact.** An order booked with a ₹10,000 advance is presented as 'Payment Status: Paid • ₹33075.00' at handover — the moment the outstanding balance should be discussed.

**Evidence.** Verified verbatim. App.jsx:7893-7896 renders the label 'Payment Status' and then the literal string `Paid • ₹{confirmedOrder.total_amount.toLocaleString('en-IN')}` in success green, with no reference to confirmedOrder.payment_status or amount_paid anywhere in the block. The secondary claim is also right: settings.py's REST_FRAMEWORK block sets no COERCE_DECIMAL_TO_STRING, so total_amount arrives as the string '33075.00' and String.prototype.toLocaleString prints it ungrouped. This is the screen the owner shows the customer and prints the invoice from.

**Fix.** In the confirmed view (frontend/src/App.jsx:7893-7896) render `{confirmedOrder.payment_status} • ₹{parseFloat(confirmedOrder.amount_paid || 0).toLocaleString('en-IN')}` and drop the hardcoded success colour when the status is not 'Paid'.

### Staff credentials copied or WhatsApp-shared always say 'TailorSecure2026!', ignoring TAILOR_DEFAULT_PASSWORD
`frontend/src/App.jsx:5734`

**Impact.** Any deploy that follows its own comment and sets TAILOR_DEFAULT_PASSWORD hands every new staff member a password that does not work, with no way for the owner to see the real one; a deploy that leaves it unset WhatsApps a password published in the repository.

**Evidence.** Confirmed, with corrected lines: the literal is at App.jsx:5734 (displayed), 5746 (clipboard text) and 5760 (WhatsApp body) — not 5757/5769/5783. The backend really does read the environment: `password=os.environ.get('TAILOR_DEFAULT_PASSWORD', 'TailorSecure2026!')` at crm_api/views.py:272, and the comment at 266-268 explicitly tells operators to override it because the fallback 'is visible in this repository'. So the two halves of the product disagree by construction. Second real case the finding misses: when `User.objects.filter(email__iexact=...)` finds a pre-existing account (views.py:264) no password is set at all, and the modal still asserts this one.

**Fix.** Stop asserting a password client-side: drop the password line from all three spots (frontend/src/App.jsx:5734, 5746, 5760) and have the modal tell the owner to share the password out of band. Returning a generated one-time password from _ensure_user_account is the better product answer but is a larger change.

### Staff and designer bootstrap passwords are hardcoded in the frontend and diverge from the deployed ones
`frontend/src/App.jsx:5734`

**Impact.** On a deployment that sets the env var (or where the address already had an account), the owner WhatsApps a password that does not work and the new tailor has to go through password reset to get in.

**Evidence.** The literals are real: App.jsx:5734 displays, 5746 copies and 5760 WhatsApps 'TailorSecure2026!'; DesignDashboard.jsx:11/216 does the same with 'DesignerSecure2026!'. The server reads os.environ.get('TAILOR_DEFAULT_PASSWORD', ...) at crm_api/views.py:272 and DESIGNER_DEFAULT_PASSWORD at apps/design_studio/views.py:515, and both comments tell operators to override, so any hardened deployment sends the wrong password. crm_api/views.py:264-274 also reuses an existing User by email without touching its password. Two corrections that lower the severity: DesignDashboard.jsx:7-10 carries an explanatory comment for the convention, and the auditor's claim that there is no reset flow is wrong — App.jsx:1943-1962 is a working 'Reset your password' view reachable from the login screen, so a wrong password is recoverable.

**Fix.** Return the value the server actually used: add it to the TailorViewSet create/update response and to create_login's response, then render that field at App.jsx:5734/5746/5760 and DesignDashboard.jsx:216 instead of the literals.

### Async CTAs with no pending guard — duplicate fabrics, tailors, designs and design boards
`frontend/src/App.jsx:1044`

**Impact.** A double-tap on Save Fabric / Save Tailor / Save Design writes two rows; two quick shortlist clicks create two design boards for one customer, so the board later attached to the order may not be the one the owner built.

**Evidence.** Confirmed. handleSaveFabric (1044), handleSaveTailor (1103), handleSaveDesign (1144), handleLoginSubmit (1184) and handleCompleteRegistration (1220) have no in-flight flag; the pattern exists elsewhere in the same file (handleSaveAppointment guards with `if (savingAppointment) return` at 1082, and runOnce/actionInFlight at 1500-1513 with a comment explaining exactly this double-click bug). DesignStudio.jsx:194-199 ensureBoard tests React state (`if (board) return board`), so two shortlist clicks before the first POST returns both create a DesignBoard — the useRef fix is already used in DesignLibrary.jsx:104-109 with a comment describing the same failure. Correction: handleCompleteRegistration IS guarded — App.jsx:2249 has `disabled={signupBusy}` — and the four stage-transition buttons (8614, 8644, 8670, 8700) are inside a modal that closes on success, so a repeat transition to the same status is the low-risk case.

**Fix.** Reuse the existing helper: `onClick={() => runOnce(handleSaveFabric)}` plus `disabled={ctaBusy}` on the Save Fabric / Save Tailor / Save Design buttons, and in DesignStudio.ensureBoard hold the in-flight create in a useRef promise the way DesignLibrary.jsx:109 already does.

### 'Try On / Drape Fabric' shows a stock photo of an unrelated garment, and 'Confirm & Save' saves nothing
`frontend/src/App.jsx:8894`

**Impact.** Staff show the customer a photograph of a different garment as a preview of theirs, then press 'Confirm & Save' and nothing is stored — the next screen has no record of it.

**Evidence.** Confirmed with corrected lines. getDrapedPreviewImage (App.jsx:965-983) is a switch on `fabric.color` returning one of six fixed Unsplash URLs — it never reads the fabric image or the selected design. 'Start Try On' (8861-8868) is a 2000 ms setTimeout, the result is labelled '✨ 3D Mannequin Draped View' (8831), and 'Confirm & Save' (8886-8895) only calls setShowDrapingModal(false); drapedImage is never persisted or sent. One mitigation the auditor missed: line 8842 does carry a '⚠️ Reference Simulation Only' disclaimer, so the fake preview is hedged — the unhedged part is a green primary button labelled Save that saves nothing.

**Fix.** Rename the button at App.jsx:8894 from 'Confirm & Save' to 'Close', which is what it does. Removing the whole modal (6817-6830, 8770-8902) and getDrapedPreviewImage (965-983) is the honest larger fix if no render service is coming.

### Order review invents the assigned tailor's photo, tags and performance statistics
`frontend/src/App.jsx:7233`

**Impact.** The screen staff read back to the customer before taking payment shows a stranger's photograph as their tailor plus four fabricated performance numbers.

**Evidence.** Confirmed with corrected lines. getTailorAvatarUrl (166-174) and getTailorTags (176-184) switch on first name against rohit/anya/rahul/preeti and otherwise return a fixed stock portrait and ['Custom','Tailoring']. The step-6 Tailor Details card renders that photo (7233), those tags (7242), a hardcoded '+2' tag (7245), '12+ Years Experience' (7240), '98% ON-TIME DELIVERY' (7249-7250), '1200+ ORDERS DONE' (7254-7255) and '5 km FROM BOUTIQUE' (7259-7260). 'Rohit Mehra' fallbacks are at 7407 and 7827 (not 7262/7682). MobileHeader.jsx:65 confirms dicebear initials is the convention elsewhere. No Tailor model field holds years, on-time rate, order count or distance.

**Fix.** Swap the src at App.jsx:7233 for the dicebear initials URL used at MobileHeader.jsx:65, delete getTailorAvatarUrl/getTailorTags (166-184) and the tag row (7241-7246), and drop the fabricated blocks at 7240 and 7248-7261 and the 'Rohit Mehra' fallbacks at 7407/7827.

### Order confirmation always says 'Paid' and shows the full total, even for a part payment
`frontend/src/App.jsx:7902`

**Impact.** An order taken with a ₹10,000 advance on a ₹45,000 dress confirms on screen as 'Paid • ₹45,000' — the screen staff turn to the customer — and contradicts the invoice one click later.

**Evidence.** Confirmed at App.jsx:7902 (not 7756): the string is literally `Paid • ₹{confirmedOrder.total_amount...}` under a 'Payment Status' label styled success-green, while the payload at 1443-1444 sets payment_status 'Partially Paid' and advance_paid to the advance. The invoice modal for the same order prints confirmedOrder.payment_status correctly.

**Fix.** Render `{confirmedOrder.payment_status} • ₹{confirmedOrder.amount_paid}` at App.jsx:7900-7903, matching the invoice block.

### Review step promises a delivery date that is not the one saved on the order
`frontend/src/App.jsx:7303`

**Impact.** Staff read today+15 days back to the customer while the order carries the real promised date, so the registry, tracking page and invoice all show a different date than the customer was told.

**Evidence.** Confirmed at App.jsx:7300-7304 (not 7155/7157). The Delivery Details card prints the literal 'Standard Delivery' and `new Date(Date.now() + 15*24*60*60*1000)` as 'Estimated delivery by', while the payload built at 1450-1454 sends `estimated_delivery` = the earliest garment delivery_date (with a comment at 1446-1449 explaining that this is the date the customer must not be told wrong) and `delivery_method: deliveryMethod` (Direct Pickup / Courier).

**Fix.** Render the same expression the payload uses — hoist `garmentJobs.map(j => j.values?.delivery_date).filter(Boolean).sort()[0]` into a `promisedDeliveryDate()` helper beside submitOrderAndConfirm and use it at App.jsx:7303, with `{deliveryMethod}` replacing the literal at 7300.

### Fabric grids render nothing when empty, and the material filter can never match a real fabric
`frontend/src/App.jsx:6774`

**Impact.** A boutique whose fabrics are typed as 'Silk Blend' or 'Georgette' sees a blank area under every tab except All, with no message; a brand-new boutique sees a blank Manage Fabrics page and a blank step 4 and is blocked by 'Please select a fabric...' with nothing on screen explaining why.

**Evidence.** Confirmed at App.jsx:6755 (hardcoded tabs ['All','Pure Silk','Zari Silk','Linen','Silk','Cotton']) and 6774-6813 (bare .filter().filter().map() with no empty branch), compared against `f.material === fabricFilter` while material is a free-text input placeholdered 'e.g. Silk Blend' (5478). Manage Fabrics has the same gap at 3216-3217. The comment at 6776-6784 explains the is_available filter, not the missing empty state. One correction to the impact: the wizard is not unfinishable — performNext:1551 only blocks when `fabricTab === 'boutique'`, and the Customer Fabrics tab (upload your own) is a working way past step 4.

**Fix.** Build the tab list from the data — `['All', ...new Set(fabrics.map(f => f.material).filter(Boolean))]` at App.jsx:6755 — and add an empty branch to the step-4 grid (6774) and to Manage Fabrics (3216) pointing at the Add New Fabric button.

### Every save in the app refetches all ten collections, including the full orders and customers lists
`frontend/src/App.jsx:988`

**Impact.** Ticking a production stage re-downloads the entire order book, client directory, design catalogue and notification history, and the dashboard's order panel flickers to a loading line each time. On the floor a tailor advancing several stages pays that cost per tap.

**Evidence.** Structurally confirmed at App.jsx:988-1032 (the auditor's line 970 is off by 18): ten loads -- dashboard, customers, orders, tailors, appointments, fabrics, designs, settings, notifications, plus customer messages for Owner -- all unpaginated, all behind setLoading(true)/setLoading(false). `grep -c 'fetchDashboardAndConfig('` returns 26 call sites including :1595, :1770, :2524, :3789, :8632, :8662, :8688, :8718. But the stated impact is overstated and I am correcting it: `loading` is read in exactly three places (App.jsx:1808, :2819, :4029). :1808 is gated on `view === 'login'`, :4029 on `customersList.length === 0`, so nothing blanks -- the only visible effect is the dashboard's 'My Orders' panel at :2819 swapping to 'Loading active orders...' during the refetch. Downgraded to medium accordingly: slow and flickery, not a broken flow. The comment at :985-987 explains the per-collection paint, not the call-site count.

**Fix.** Smaller than the auditor's 26-call-site rewrite: give fetchDashboardAndConfig a `{ background = false }` option that skips `setLoading(true)` (App.jsx:989), and pass it from the mutation handlers -- one flag kills the flicker. The bandwidth half of the problem belongs to the ORDER_PREFETCH and notification-pagination fixes, not here; only pursue per-handler local updates (transition_stage already returns the full serialized order at crm_api/views.py:683) if profiling still shows it after those land.

### Mobile header search box is wired to nothing
`frontend/src/components/ui/MobileHeader.jsx:20`

**Impact.** On a phone, tapping the magnifier opens a field placeholdered 'Search orders, customers, designs…'; typing and pressing enter does nothing and gives no feedback.

**Evidence.** Confirmed. MobileHeader accepts onSearch (line 14) and calls it on submit (line 20), and `grep -rn onSearch frontend/src` returns only those two lines in that file — neither MobileHeader usage (App.jsx:2291-2303 and 5934-5944) passes it. The search button at line 52 opens the field unconditionally.

**Fix.** Smaller than wiring a search: delete the search button (MobileHeader.jsx:52-54) along with the searchOpen branch, until a caller passes onSearch.

### Opening the 'Uncategorised' category shows the entire library instead of the untagged designs
`frontend/src/features/designStudio/DesignLibrary.jsx:287`

**Impact.** The tile says 'Uncategorised — 3'; clicking it renders every design in the boutique with the header reading the full count. The one screen an owner would use to find and tag the untagged designs instead dumps the entire library on them — the flat grid the module's own docstring (DesignLibrary.jsx:8-19) says it exists to replace.

**Evidence.** Traced every step. DesignCategoryView appends the bucket with an empty key at views.py:405: `categories.append({'key': '', 'name': 'Uncategorised', 'count': untagged})`. DesignLibrary.jsx:287 builds `{ ...filters, template: openCategory.key || undefined }` — '' || undefined is undefined. api.js getDesignLibrary at :912-916 drops it: `if (v !== '' && v !== null && v !== undefined) url.searchParams.append(k, v)`. So no template parameter reaches DesignAssetViewSet.get_queryset, whose DIRECT_FILTERS loop only filters when `params.get('template')` is truthy — no filter is applied at all. I confirmed there is no template__isnull filter anywhere in get_queryset, so even a deliberate value could not express it, and that the endpoint is unpaginated (no DEFAULT_PAGINATION_CLASS in settings.py:360-383), so the response really is the whole library.

**Fix.** Agreed. Teach DesignAssetViewSet.get_queryset one sentinel — treat `?template=__none__` as `template__isnull=True` before the DIRECT_FILTERS loop — and send it from DesignLibrary.jsx:287 when openCategory.key === '' instead of collapsing to undefined.

### Edit and Delete on catalogue designs are shown to Designers and fail with an opaque error
`frontend/src/features/designStudio/DesignLibrary.jsx:223`

**Impact.** A Designer — for whom this library is the only screen the app offers — opens any catalogue design, sees Edit and Delete, fills in the form, saves, and is told 'Failed to save design: Failed to update boutique design.' Delete pops a confirmation, they confirm, and get the same shape of message. Nothing indicates it is a permissions problem rather than a bug or a lost design.

**Evidence.** The mechanism checks out but the blast radius in the finding is wrong. DesignLibrary.jsx:223 gates the Edit/Delete row on source alone with no role check; App.jsx:3633-3651 passes onEditDesign/onDeleteDesign unconditionally while the 'Add New Design' button at :3583 is wrapped in `(!currentUser?.role || currentUser.role === 'Owner')` with a comment explaining exactly why. Both handlers hit the catalogue endpoints (App.jsx:1140 updateBoutiqueDesign, :1156 deleteBoutiqueDesign). crm_api/views.py:295 declares no permission_classes so it inherits core.permissions.RolePermission (settings.py:373-375), which returns False outright for DESIGNER (core/permissions.py:71-74). api.js:629 and :638 throw bare strings ('Failed to update boutique design' / 'Failed to delete boutique design') rather than describeApiError, so the 403 message never reaches the user — App.jsx alerts 'Failed to save design: Failed to update boutique design.' CORRECTION: the auditor's claim that 'Masters and Tailors browsing the library hit the same dead buttons' is false — App.jsx:2434-2452 gives the Manage Designs / Design Studio nav item only to Owner and Designer; a Master's nav is assignments/orders/customers and every other role gets assignments only. This affects Designers only.

**Fix.** Agreed. DesignLibrary already receives canReview (App.jsx:3635, true only for Owner); gate the Edit/Delete block at DesignLibrary.jsx:223 on it as well as on `editable`. Separately, have api.js's updateBoutiqueDesign and deleteBoutiqueDesign use describeApiError(res, data) like uploadDesign does, so any future 403 reads 'You do not have permission to do that.'

### Stock movement modal downloads every order in the boutique to fill a dropdown
`frontend/src/features/inventory/InventoryPanel.jsx:467`

**Impact.** Opening the stock-movement dialog on any item pulls the boutique's whole order history with its nested stage and activity rows before the form is usable, and this dialog is the entry point for every issue, consume, waste and reserve entry.

**Evidence.** Confirmed: `api.getOrders().then((rows) => setOrders(rows || [])).catch(() => setOrders([]))` sits in MovementModal's mount effect at :465-471, keyed on `[item.id]`, so it refires on every modal open. /api/orders/ is unpaginated (verified: no pagination_class anywhere) and returns the full OrderSerializer with stages, activities, stage_histories, garment_jobs and garment_images. The result is used only for the 'Against order (optional)' options. The comment at :463-464 covers the best-effort error handling, not the payload size. The auditor's suggested alternative of reusing OrderSummarySerializer for the list is unsafe -- App.jsx:322 and :8373 read garment_images and garment_jobs off list rows -- so I am dropping that half of the fix.

**Fix.** Hoist the `api.getOrders()` call from MovementModal into InventoryPanel and pass `orders` down as a prop, so it runs once per panel mount instead of once per modal open. No backend change, and combined with adding garment_images to ORDER_PREFETCH it is the whole of the practical win.

### The boutique client never handles 401/403, so a killed session leaves the user stuck on a dead dashboard
`frontend/src/services/api.js:3`

**Impact.** Owner signs out on their phone; the shop desktop still on the dashboard now fails every call with an alert, keeps showing stale rows, and never returns to the login screen without a manual refresh.

**Evidence.** Confirmed. getHeaders (api.js:3-17) attaches the token and X-Tenant-ID, and nothing in api.js inspects res.status for 401 — the only status branches are the message strings in describeApiError (36-39), which do not clear anything. frontend/src/superadmin/api.js:47-59 does the opposite and says why: 'A 401/403 on anything other than the login call means the stored token is no longer good... if (res.status === 401 || res.status === 403) clearToken()'. LogoutView deletes the one DRF token (crm_api/auth_views.py:296-299), so signing out on one device does invalidate the other device's session. App.jsx has no 401 handling either — the only escape is the global error screen's manual localStorage.clear() button at App.jsx:1783.

**Fix.** Add the superadmin rule to frontend/src/services/api.js once, next to getHeaders: wrap fetch in an authedFetch that on res.status === 401 removes 'token' and 'tenant_id' and reloads, and use it throughout the file.

### Order-creation failures show "Failed to submit order." and discard the server's explanation
`frontend/src/services/api.js:358`

**Impact.** An owner who mistypes a price (stray minus, extra zero) is told only 'Failed to submit order.' at the final step of the wizard, with nothing naming the field; the order cannot be placed and the message the backend wrote for this exact case is thrown away.

**Evidence.** Verified. api.createOrder is `if (!res.ok) throw new Error('Failed to create order');` with no body read (services/api.js:352-360), and submitOrderAndConfirm swallows it as `alert("Failed to submit order.")` (App.jsx:1488). The server deliberately produces a printable reason: crm_api/views.py:217-221 catches ValueError with the comment 'Surface its reason as a 400 the wizard can print, not a 500', carrying messages raised in domains/orders/services.py:119 ('base_price cannot be negative.') and services.py:128-131 (the 99,999,999 ceiling message, itself written so 'nobody can act on' the driver error is no longer true). The sibling api.updateOrder at api.js:454-466 already does exactly the right thing and says so in its own comment — so the pattern is established and createOrder is the straggler.

**Fix.** In api.createOrder (frontend/src/services/api.js:352-360) copy the updateOrder body: `const detail = await res.json().catch(() => ({})); throw new Error(detail.error || detail.detail || 'Failed to create order');`, and print err.message in the alert at App.jsx:1488.

### Validation failures reach staff as raw JSON in a browser dialog
`frontend/src/services/api.js:208`

**Impact.** Creating a customer, a design review, a collection or a garment job with any invalid field shows staff a JSON blob they cannot act on.

**Evidence.** Partly confirmed, and narrowed. The raw-JSON half is real: api.js throws JSON.stringify'd bodies at 208 (createCustomer), 260, 701, 753, 929, 961, 991, 1047 and 1074, and App.jsx concatenates err.message into alert() in 34 places (e.g. 1065 'Failed to save fabric: ', 4952 'Failed to update payment status: ', 8634 'Failed to transition: '), so a DRF field error renders as {"mobile_number":["..."]} in a modal. api.js:19-45 already has describeApiError, which unpacks exactly that shape, and only nine call sites use it. The rest of the finding — 53 alerts, successes as alerts, 'replace them all with a banner' — is a UX refactor, not a defect, and I am not confirming it.

**Fix.** Replace the nine `JSON.stringify(...)` throws in api.js (208, 260, 701, 753, 929, 961, 991, 1047, 1074) with `describeApiError(res, data)`, which already exists in that file. Leave the alert-vs-banner question alone.

### seed_mock_orders.py hard-deletes every boutique's customers and orders and defaults to the hosted database
`seed_mock_orders.py:251`

**Impact.** One command run from the project root with the shipped .env destroys the client list and full order history of every boutique on the hosted database, irrecoverably, and leaves staff accounts whose password is published in this repository. seed_v2_tasks.py and seed_data.py share the same production-by-default connection.

**Evidence.** Mechanism confirmed exactly as described. seed_mock_orders.py:250-255 iterates BoutiqueTenant.objects.exclude(schema_name='public') and calls seed_tenant_orders, whose first statements (lines 16-24, inside schema_context) are OrderStageHistory/Order/Customer/Notification/Tailor .objects.all().delete(); line 53 creates staff logins with the literal 'TailorSecure2026!'. No confirmation prompt, no environment guard, and settings.py:194-203 only defaults USE_LOCAL_DB for 'test' in sys.argv, so `python seed_mock_orders.py` inherits the Supabase pooler defaults at settings.py:134-141 with .env supplying DB_HOST/DB_PASSWORD — start.sh:15 exports USE_LOCAL_DB=True but only for its own children, not for a script run by hand. I lowered severity from high to medium: nothing in the build or start path invokes this file (grep across *.sh/*.md/*.py finds no caller), so it is an operator footgun rather than something a boutique hits in a normal week — but the consequence, an unrecoverable wipe of the order book of every tenant, is why it still belongs in the report.

**Fix.** Guard the entrypoint: at the top of seed_all() in seed_mock_orders.py, refuse unless settings.DATABASES['default']['HOST'] starts with '127.' / 'localhost' or SEED_I_MEAN_IT=1 is set, and read the staff password from os.environ instead of line 53. The same three-line guard belongs at the top of seed_data.py:seed() and seed_v2_tasks.py.

### Neither login endpoint is rate limited, including the console that reads and suspends every boutique
`superadmin/views.py:44`

**Impact.** Passwords can be guessed against /api/superadmin/login/ as fast as the network allows, on an account with a known username that can read, page through and suspend every boutique on the platform; the same applies to boutique owner and staff logins at /api/auth/login/.

**Evidence.** Confirmed, with the settings cite corrected: the REST_FRAMEWORK block is at boutique_crm/settings.py:362-383, not 321-335 (that range is the email settings). There IS an explanatory comment at 376-379 — 'Only the password-reset views throttle, and they name the class themselves. Nothing else is rate limited here, so no DEFAULT_THROTTLE_CLASSES entry' — but it only justifies not throttling every business endpoint by default; it does not claim the login endpoints are protected, and they are not. superadmin/views.py:44-78 PlatformLoginView is permission_classes=[AllowAny], authentication_classes=[] with no throttle_classes; crm_api/auth_views.py:210 LoginView is the same. The mechanism is already present and used: DEFAULT_THROTTLE_RATES has a 'password_reset' scope (settings.py:380-382) consumed by _PasswordResetThrottle (auth_views.py:340-352) on two views, and tenants/views.py:34-35,119-127 rate-limits the demo form by counting rows. The default admin username is the literal 'admin' (create_superuser.py:26) and, per the finding above, its password may be admin123.

**Fix.** Do not set DEFAULT_THROTTLE_CLASSES — the comment at settings.py:376 is right about that. Copy the pattern already in the repo: add 'login': os.environ.get('LOGIN_RATE', '10/hour') to DEFAULT_THROTTLE_RATES, add a two-line AnonRateThrottle subclass with scope='login' next to _PasswordResetThrottle in crm_api/auth_views.py, and name it in throttle_classes on crm_api.auth_views.LoginView and superadmin.views.PlatformLoginView. Same LocMemCache-per-worker ceiling the existing ponytail note at auth_views.py:343-348 already documents.

### The in-process tenant cache grows without bound on an unauthenticated, attacker-controlled header
`tenants/middleware.py:37`

**Impact.** An unauthenticated client looping requests with fresh random (and arbitrarily long, up to the ~8KB header limit) X-Tenant-ID values adds a permanent dict entry per request in whichever gunicorn worker it lands on, until the worker is OOM-killed — taking the API down for every boutique. The defence written to stop a query per request becomes memory per request.

**Evidence.** Read tenants/middleware.py:8-44 including the comments. The comment at 8-14 justifies caching tenants (they never change) and the one at 35-36 justifies caching negative results; neither addresses growth, so this is not a documented tradeoff. _tenant_cache = {} at line 16 has no bound and no eviction — clear_tenant_cache() at 41-44 is only called from superadmin/views.py after a tenant edit. Line 37 assigns unconditionally, including the tenant=None branch from line 34, and the TTL check at 29 only declines to return a stale value, it never deletes it. The key is request.headers['X-Tenant-ID'] read at line 74 with no validation beyond `!= 'public'` and no length limit, before any authentication, on every request that is not under /api/superadmin/.

**Fix.** One line in _get_tenant_by_schema, before the assignment at tenants/middleware.py:37: `if len(_tenant_cache) > 1000: _tenant_cache.clear()`. Keeps the hit rate for the handful of real schemas and caps growth.


## LOW

### Customer uploads are committed to the repository; .gitignore covers only one of the upload directories
`.gitignore:25`

**Impact.** A routine `git add -A` sweeps customers' garment photos and profile pictures into version control, where they survive any deletion in the app and are readable by everyone with repo access.

**Evidence.** Confirmed. .gitignore:23-25 states the intent ('anything a user uploads is not [committed], and it must not arrive in the repo via a test run') but the only pattern is `media/design_library/`. `git ls-files media` returns 16 files including media/customer_profiles/DOMS_LOGO.png, media/customer_profiles/DOMS_LOGO_bWyRTlq.png and two customer-scoped uploads under media/fabrics/cust_cc73295a-6563-4e38-bb91-eb8d70bd61de/ — the exact prefix crm_api/views.py:182 writes. `git status --porcelain media` currently shows untracked media/completed_garments/ and media/stage_images/. Severity corrected from medium to low: what is actually committed today is a logo and two fabric shots in a private repo, which is real but small.

**Fix.** Replace the `media/design_library/` line in .gitignore with `media/` plus explicit `!media/fabric_0*.jpg` / `!media/design_*.jpg` un-ignores for the seeded catalogue images, and `git rm --cached` the four already-tracked files under media/customer_profiles/ and media/fabrics/cust_*/.

### DesignBoard.selected_item bypasses the prefetch cache, costing one query per board
`apps/design_studio/models.py:330`

**Impact.** One extra query per board on the boards list and on the tailor brief, on top of a prefetch that has already loaded the same rows. Small, but pure waste on an already-correct path.

**Evidence.** Confirmed. apps/design_studio/models.py:329-331 is `@property def selected_item(self): return self.items.filter(is_selected=True).first()`. `.filter()` on a related manager builds a fresh queryset and cannot use the prefetch cache set up by DesignBoardViewSet.get_queryset, which does `.prefetch_related('items')` at apps/design_studio/views.py:560. Both callers check out: DesignBoardSerializer.get_selected at serializers.py:121 and TailorBriefSerializer.get_design at :144. No comment anywhere explains the .filter() as deliberate.

**Fix.** Agree. Change the property body to `next((i for i in self.items.all() if i.is_selected), None)` -- self.items.all() uses the prefetch cache when present and falls back to a single query when not.

### The library grid returns every status while the category counts only count ACTIVE, so archived designs reappear
`apps/design_studio/views.py:140`

**Impact.** A category tile reads 4 and the grid under it reads '7 shown' (DesignLibrary.jsx:377), including rejected and draft designs. Confusing rather than harmful, and the Status filter does let the owner narrow manually.

**Evidence.** Verified the disagreement between the three read paths. DesignAssetViewSet.get_queryset (views.py:140-169) starts from DesignAsset.objects.select_related(...) and only narrows on status when the caller passes ?status= (DIRECT_FILTERS, :118-124). DesignCategoryView.get (:386-403) counts status=ACTIVE only, and tests.py:828 test_archived_designs_are_not_counted asserts it. LibraryProvider (providers/internal.py:120-127) filters ACTIVE with a long comment explaining that a rejected design must not come back. The list endpoint is genuinely the odd one out. I am cutting the severity: the grid stamps design.status on every card (DesignLibrary.jsx:406-410), so an archived design is visibly badged ARCHIVED, and the discovery gallery the owner actually selects from already excludes it — so 'sits in the gallery looking selectable' is wrong. What is left is a real count-vs-grid mismatch.

**Fix.** Agreed: in DesignAssetViewSet.get_queryset, after the DIRECT_FILTERS loop, `if not params.get('status'): queryset = queryset.exclude(status=DesignAsset.Status.ARCHIVED)` — one line, and it puts the list endpoint in step with the two read paths that already do this.

### 'Trending This Week' is never driven by views, because the view counter bypasses updated_at
`apps/design_studio/views.py:371`

**Impact.** 'Trending This Week' on the design dashboard (DesignDashboard.jsx:276) is really 'designs edited in the last 7 days, ordered by lifetime views' — for most boutiques a near-duplicate of the Recent Uploads strip above it, while a design that got fifty views this week never appears. A soft signal the owner reads as customer interest and that is not one.

**Evidence.** Both ends verified. DesignDashboardView computes trending at views.py:370-372 as `active.filter(updated_at__gte=week_ago).order_by('-view_count')[:5]`, under a comment (:365-369) that explicitly reads the window as 'designs updated (viewed) in the last 7 days' — so the author's intent is that a view refreshes updated_at. The counter at views.py:265 is `DesignAsset.objects.filter(pk=...).update(view_count=F('view_count') + 1)`, and a queryset .update() does not run the auto_now on updated_at (models.py:239); the comment there (:259-263) justifies the atomic UPDATE for a different reason — concurrent increments — and does not notice the side effect. Nothing else touches updated_at when a design is opened; favourite() (:272) and review() (:303, :306) do, which is what actually populates the strip.

**Fix.** Agreed and kept: in DesignAssetViewSet.retrieve (views.py:265) include the timestamp in the same atomic statement — `.update(view_count=F('view_count') + 1, updated_at=timezone.now())`; timezone is already imported at views.py:11, and this matches the intent the dashboard comment already states.

### Deleting an order cascades away its material plan and the customer's material ledger, stranding the reservations on the shelf
`apps/inventory/models.py:744`

**Impact.** If an order carrying a plan is ever deleted (admin, or a direct API call), its reserved quantity stays locked on every material with no plan left to release it, and the customer's material record plus its movement history are destroyed.

**Evidence.** The code reads as described: OrderMaterialPlan.order is FK(Order, CASCADE) at models.py:744, OrderMaterialLine cascades off the plan (models.py:788), CustomerMaterial.order is FK(Order, CASCADE) at models.py:841, and OrderViewSet (crm_api/views.py:301) is a plain ModelViewSet with no destroy/perform_destroy override and no http_method_names, so DELETE is live for an Owner token. Grepping outside apps/inventory for OrderMaterialPlan / order_materials / InventoryService returns nothing, so no order-side hook cancels the plan. CustomerMaterialViewSet's docstring at views.py:797-802 does refuse DELETE for exactly this reason. Severity corrected down from medium to low: the auditor did not check reachability. There is no deleteOrder in frontend/src/services/api.js (the only DELETE helpers are for garment images, locations, recipes and catalog rows), and there is no screen that creates a material plan or a customer material in the first place — so a boutique using the product cannot arrive at an order that has a plan AND then delete it. Order is registered in Django admin (crm_api/admin.py:78), which keeps this a genuine latent bug rather than an invented one.

**Fix.** One hook at the single deletion point: add perform_destroy to OrderViewSet in crm_api/views.py that calls apps.inventory.order_materials.cancel() on any live plan before delete (or refuses while one exists). Agreed — do not touch the CASCADEs.

### CustomerMaterialMovement.Type.CORRECTION has no writer, so a mis-recorded receipt can only be undone by a false RETURNED line
`apps/inventory/order_materials.py:502`

**Impact.** A quantity typed wrong on receipt can only be brought back by recording a RETURNED movement for material that was never returned, putting a false "Returned to customer" line in the ledger that exists to answer where the customer's material went.

**Evidence.** Verified. record_customer_material maps exactly three types at order_materials.py:502-506 and raises MaterialPlanError for anything else at line 508. CORRECTION is defined at models.py:882 and appears nowhere else in the repo except migration 0008 — grep for CORRECTION across all .py files returns only those two hits, so it genuinely has no writer. The lockdowns the finding cites are all real: received_quantity is in CustomerMaterialSerializer.read_only_fields (serializers.py:345), CustomerMaterialViewSet omits 'delete' from http_method_names (views.py:806), perform_update permits descriptive fields only (views.py:855-868), and the class docstring at views.py:801-802 does say material recorded in error is returned or corrected. Severity low is right, and correctly so — the customer-material screens do not exist either (no call sites for receiveCustomerMaterial / recordCustomerMaterial in frontend/src), so this is an API-only gap.

**Fix.** Agreed: add CORRECTION to the map in record_customer_material (apps/inventory/order_materials.py:502) applying a signed delta to received_quantity, bounded so remaining_quantity cannot go negative, logged through the existing _log_customer_movement. The movement type and the helper are already there.

### _as_quantity() compares outside its try, so 'nan' returns a 500 instead of a 400
`apps/inventory/services.py:24`

**Impact.** A hand-crafted or buggy client posting a malformed quantity to any stock endpoint gets an opaque 500 rather than "quantity must be a number".

**Evidence.** Verified by reading and by running it: services.py:20-25 parses inside `try/except Exception` but compares at line 24 outside it; `Decimal('nan') <= 0` raises decimal.InvalidOperation, whose MRO is (InvalidOperation, DecimalException, ArithmeticError, Exception) — not ValueError — and InventoryItemViewSet._apply catches only ValueError (views.py:140). InventoryService.adjust has the identical shape (`counted = Decimal(str(...))` at line 324, `if counted < 0` at line 327). I also confirmed `Decimal('Infinity') <= 0` is False, so it sails through to locked.save() at services.py:144. order_materials._quantity (order_materials.py:67-85) carries a comment describing exactly this bug class and puts the comparison inside the try, and tests.py:1960 covers only that path — so the hardening genuinely was never applied here. Severity corrected down from medium to low: 'nan'/'Infinity' cannot be produced by the UI at all (MovementModal uses `type="number" step="0.001" min="0"`, InventoryPanel.jsx:517-519), and the over-large path needs >= 1e9 to exceed DecimalField(max_digits=12, decimal_places=3), which is not a plausible fat-finger. This is API robustness, not something a boutique owner hits.

**Fix.** Agreed and minimal: in apps/inventory/services.py, move the comparison inside the try in _as_quantity and add `if not quantity.is_finite() or quantity <= 0 or quantity >= 10**9: raise ValueError(...)`; give adjust's `counted` the same treatment (allowing 0). These two are the only entry points for every quantity in the module.

### ALLOWED_HOSTS defaults to '*' and three upload paths bake the Host header into stored boutique data
`boutique_crm/settings.py:55`

**Impact.** A low-privileged staff member can plant image URLs pointing at a host they control into the boutique's own records, which the owner's browser then loads on every gallery view; and every stored reference URL breaks permanently the day the API moves to a custom domain or is reached over a second hostname.

**Evidence.** Verified. settings.py:55 is ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',') if h], with no comment, directly under a DEBUG default that does carry one — and DJANGO_ALLOWED_HOSTS appears nowhere in README.md's env list or in .env. The three persistence sites are exactly where the auditor says: crm_api/views.py:81 and :184 append request.build_absolute_uri(default_storage.url(...)) into DesignPreference.reference_images and FabricSelection, and apps/design_studio/views.py:252 does the same for the design library. Kept at low, and I checked the exploit path is narrower than stated: all three endpoints require an authenticated boutique user, so the forged-Host write needs an insider, not a stranger. What is unconditionally real is the fragility — those absolute URLs are frozen to whatever host was used at upload time. domains/orders/services.py:405 already stores the relative form when it has no request, and frontend/src/services/media.js:16-22 resolves '/media/...' against MEDIA_BASE, so absolute URLs buy nothing.

**Fix.** Smaller and complete: drop request.build_absolute_uri( at crm_api/views.py:81, crm_api/views.py:184 and apps/design_studio/views.py:252 and store default_storage.url(saved_path) directly — that is what domains/orders/services.py:405 already does and what media.js already resolves, and it removes the Host dependency rather than constraining it. Defaulting ALLOWED_HOSTS to RENDER_EXTERNAL_HOSTNAME is worth doing too, but on its own it does not fix the stored-URL fragility.

### No secure-cookie, HSTS or SSL-redirect settings — the superadmin session cookie has no Secure flag
`boutique_crm/settings.py:102`

**Impact.** A typed-in http:// URL or an old bookmark to the Render host sends the platform superadmin's session cookie in the clear before the edge redirect fires, and it can be stripped on a hostile network.

**Evidence.** Confirmed: `grep -rn 'SECURE_|SESSION_COOKIE|CSRF_COOKIE|CSRF_TRUSTED'` over every .py outside .venv returns zero hits, so SecurityMiddleware at settings.py:102 runs entirely on Django's insecure defaults. The auditor's own caveat is correct — gunicorn.conf.py:43's forwarded_allow_ips='*' means request.is_secure() is right behind Render's proxy, so this is only about the flags. I downgraded medium to low: exploitation needs an attacker on the network path AND a plaintext request that Render's edge already redirects, and the React workspace authenticates with a token header rather than cookies (settings.py:288 CORS_ALLOW_CREDENTIALS = False), so the only cookie at risk is the /admin/ session.

**Fix.** In boutique_crm/settings.py, gate four settings on `not DEBUG`: SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE, SECURE_SSL_REDIRECT = True and SECURE_HSTS_SECONDS = 31536000. Four lines, off under DEBUG so local http still works.

### ALLOWED_HOSTS defaults to '*' while request-derived absolute URLs are persisted into stored data
`boutique_crm/settings.py:55`

**Impact.** Stored image URLs are pinned to whatever Host the uploading request carried, so images silently break for everyone once the service moves to a custom domain; the forged-Host write itself requires an authenticated boutique user.

**Evidence.** The facts check out but the impact was overstated, so I cut the severity. settings.py:55 is `ALLOWED_HOSTS = [h for h in os.environ.get('DJANGO_ALLOWED_HOSTS', '*').split(',') if h]` with no defending comment, and DJANGO_ALLOWED_HOSTS appears nowhere in README.md's env list. The four persisted build_absolute_uri sites are real (crm_api/views.py:81 and :184, domains/orders/services.py:403, apps/design_studio/views.py:252 — the full set; grep finds no others outside tests). But every one of them sits behind DRF's DEFAULT_PERMISSION_CLASSES = core.permissions.RolePermission (settings.py:369-378), so the 'attacker' who plants a forged Host must already hold a token for that boutique — they can upload arbitrary images anyway. No unauthenticated write path reaches these lines. The concrete harm that remains is durability: the host at upload time is frozen into DesignPreference.image_urls and OrderStage.attachments, so an upload made from localhost or from the onrender.com origin keeps pointing there after a custom domain lands.

**Fix.** Set DJANGO_ALLOWED_HOSTS on Render to the real service host(s) and add it to README.md's environment-variable list — that closes the forged-Host write at settings.py:55 in one place. The durability half is a separate, larger change (store default_storage.url() relative paths and let the frontend resolve them) and should not be bundled in.

### Login binds an email address to whichever boutique it finds first and never tries another
`crm_api/auth_views.py:47`

**Impact.** A freelance tailor working for two boutiques can only ever sign in to one, chosen by database ordering; if the address is also an owner_email elsewhere, the owner_email match wins and the valid staff password is rejected.

**Evidence.** Real, but the code moved: the resolution now lives in find_tenant_for_account (crm_api/auth_views.py:28-57), which LoginView calls at line 231. It returns the owner_email match first, otherwise the first schema in an unordered queryset containing a matching email or username, and returns immediately — LoginView then authenticates only in that tenant and returns 'Invalid login credentials' (auth_views.py:256-262) without trying the remaining candidates. The docstring covers the O(n) schema scan and its upgrade path, not this ambiguity, so no comment excuses it. Duplicates across tenants are possible: _ensure_user_account (crm_api/views.py:237) matches within the current schema only, and each tenant has its own auth_user table. SEVERITY CORRECTED down from medium: it needs the same address to exist in two boutiques, and the workaround (a second address) is trivial once someone understands the cause.

**Fix.** Change find_tenant_for_account into a generator/list of candidates and have LoginView.post try each in turn, returning the credentials error only after all have failed. Keep the reset views on the first match.

### Every new customer gets an all-blank "Version 1" row in their Sizing Version History
`crm_api/models.py:112`

**Impact.** Opening any client's profile shows a Sizing Version History whose oldest entry is "Version 1" with every measurement an em-dash, and the real first measurement is labelled Version 2. It reads as a lost record rather than an empty one.

**Evidence.** Confirmed at the cited line. Measurement.save() (crm_api/models.py:108-137) sets changed = True when `if not last_history:` (line 112-113) and then always writes a MeasurementHistory row. CustomerSerializer.create (crm_api/serializers.py:423-429) falls through to `Measurement.objects.create(customer=customer)` at line 427 with no field values whenever the payload carries no measurements — which is every customer created through the wizard, since saveStep1 posts the customer before step 2 collects any garment measurements. So a row of seven NULLs and an empty additional_measurements is written at signup. The display side confirms the symptom: the Sizing Version History panel at App.jsx:4455-4487 reverses measurement_history and labels rows "Version {arr.length - idx}", rendering each absent value as an em-dash, so the blank row is Version 1 and the first real measurement is Version 2. No comment anywhere addresses the empty-history case. Low is correct — nothing is lost or wrong, it just reads as a lost record.

**Fix.** Agreed. In Measurement.save() (crm_api/models.py:108), skip the history write when the row carries nothing — guard the `if changed:` block with a check that at least one of the seven decimal fields is not None or additional_measurements is non-empty. One guard in the model covers CustomerSerializer.create's bare create and the get_or_create in CustomerSerializer.update alike. Note crm_api/test_data_integrity.py:90 asserts measurement_history.count() == 1 for a customer; check whether that test creates a Measurement with values before landing this.

### Invoices print a placeholder studio address when signup's optional boutique address is skipped
`crm_api/models.py:480`

**Impact.** A boutique that skips the optional address field hands every customer an invoice showing a fictional street address as its own, with no on-screen warning that it is a default.

**Evidence.** Half-verified; the phone half is refuted and the suggested fix was wrong. Confirmed: BoutiqueSettings.address defaults to '123 Atelier Way, Fashion District' (crm_api/models.py:480), signup only overrides it when non-blank (crm_api/auth_views.py:163-168), and the boutique-address input at App.jsx:2228-2234 has no `required`, so step 2 can be clicked through — the comment at App.jsx:2206-2213 acknowledges the old fallback but the skip path survives. REFUTED for phone: the signup mobile input at App.jsx:2144-2150 carries `required`, and auth_views.py:166 writes it into BoutiqueSettings.phone, so '+91 9999999999' cannot reach a UI-created boutique. Also refuted: the auditor's fix would not work — App.jsx:8081-8083 renders `boutiqueSettings?.address || "123 Atelier Way, Fashion District"`, so an empty-string default is falsy and the placeholder prints anyway.

**Fix.** Two-line change in the frontend, not the model: drop the hardcoded fallbacks in the invoice header (frontend/src/App.jsx:8081) so a blank address renders blank, and add `required` to the boutique-address input at App.jsx:2228-2234 so the value is collected once at signup. (Settings at App.jsx:5364 shows the same placeholder as a defaultValue — harmless there, since it is an editable form field.)

### preferred_communication is collected from every customer and honoured by nothing
`crm_api/models.py:82`

**Impact.** A customer who asks to be called is recorded as such and the preference changes nothing; with a transport configured she would be auto-messaged anyway.

**Evidence.** Confirmed. `grep -rn preferred_communication` across Python and JSX returns only the model default (models.py:82), two serializer field lists (serializers.py:392, 504), the admin fieldset (admin.py:32) and the wizard dropdown (App.jsx:119, 6495-6496). send_customer_message (domains/orders/messaging.py:105-121) and create_order_notifications never read it. Low is the right severity: with the shipped manual backend the owner personally decides whether to open each queued message, so a customer who asked for a phone call is not automatically messaged today.

**Fix.** REPLACING the proposed fix — returning None from send_customer_message would also delete the queued row, and that row is the boutique's to-do list of what the customer is owed (messaging.py docstring, lines 84-90), so the owner would never be reminded to call either. Instead gate only automatic delivery: change messaging.py:119 to `if get_backend() is not None and order.customer.preferred_communication == 'WhatsApp':` so the message is still recorded for the owner to action by hand.

### OrderStage.stage_key has no index, and refresh_staff_availability scans the whole stage table on every transition
`crm_api/models.py:301`

**Impact.** Two unindexed scans of the stage table per stage transition, growing linearly with the boutique's order history. Measurable only at high volume.

**Evidence.** The code facts check out: `stage_key = models.CharField(max_length=100)` at :301 with no db_index, and OrderStage.Meta at :317 sets only `ordering = ['sequence']`, in contrast to Order.current_stage_key at :293 which does carry db_index=True. domains/orders/services.py:59-61 does run `OrderStage.objects.filter(stage_key='stitching_completed', status='COMPLETED').values('order_id')` unbounded, inside refresh_staff_availability, which fires from services.py:276 and :496 on every stitching/delivery transition, once per staff member. Severity cut from medium to low: this is django-tenants with a schema per boutique, so the table holds one boutique's rows -- roughly 45k after 3,000 orders, which Postgres seq-scans in single-digit milliseconds. It is a real missing index but not something an owner experiences. One of the auditor's three cited beneficiaries is also wrong: the QC check at domains/orders/notifications.py:81 is `order.stages.filter(...)`, already narrowed by the order_id FK index to ~15 rows.

**Fix.** Add `indexes = [models.Index(fields=['stage_key', 'status'])]` to OrderStage.Meta in crm_api/models.py and generate the migration. Prefer the composite over a bare db_index=True on stage_key -- the hot query filters on both columns.

### Notification has no index on the two columns every read filters by
`crm_api/models.py:347`

**Impact.** Sequential scan plus sort on every bell open and mark-all-read. Only becomes visible once the notification table has grown for a year or more, which is the same growth the pagination finding covers.

**Evidence.** Confirmed by reading crm_api/models.py:347-356: title, message, recipient_role, recipient_email, created_at and is_read, none with db_index, and no Meta class at all. The readers are as described -- NotificationViewSet.get_queryset (crm_api/views.py:857-867) filters recipient_role then recipient_email and orders by -created_at; mark_all_read (:873) adds is_read=False; InventoryService._raise_alerts (apps/inventory/services.py:355-363) does an exists() on title plus is_read for every crossing movement. Severity cut from medium to low for the same reason as the OrderStage index: per-tenant schema, small tables, and the alert exists() only fires on a stock-level crossing rather than on every movement (the docstring at services.py:356-360 is explicit about that, which the auditor's evidence misstates).

**Fix.** Add a Meta to Notification with `indexes = [models.Index(fields=['recipient_role', 'recipient_email', '-created_at'])]` and migrate. Skip the second (title, is_read) index -- _raise_alerts only runs on a stock-level crossing, not on every movement, so it does not earn one.

### Any signed-in staff member can POST a notification into the Owner's feed
`crm_api/views.py:824`

**Impact.** A tailor or designer can POST /api/notifications/ with recipient_role='Owner' and arbitrary title/message, and it appears in the owner's drawer indistinguishable from a system alert -- a spoofing channel inside the product.

**Evidence.** The mechanism is real but the severity was inflated and the proposed fix is wrong. NotificationViewSet (crm_api/views.py:824) is a ModelViewSet with permission_classes = [OwnNotifications] (831), whose has_permission is only `resolve_user_role(request.user) is not None` (core/permissions.py:101-102). The class comment (827-830) and the OwnNotifications docstring justify the class on the grounds that get_queryset scopes reads and updates -- true, and `create` never consults get_queryset, so the justification does not cover it. NotificationSerializer is fields='__all__' (crm_api/serializers.py:532-535) over recipient_role / recipient_email as plain writable CharFields (crm_api/models.py:350-351), so a POST with recipient_role='Owner' lands in the owner's drawer. But this needs a hostile insider with dev tools, costs no data and no money, and destroy is already confined to the caller's own rows via get_queryset -- low, not medium. IMPORTANT: the proposed `http_method_names = ['get','patch','put','head','options']` is incorrect and would reintroduce the exact outage the comment warns about -- APIView.dispatch tests request.method against http_method_names before it ever reaches the action map, so dropping 'post' would 405 the mark-all-read POST at line 869 and take the bell down again for every non-Owner.

**Fix.** Notifications are only ever written server-side (assign_stage, create_order_notifications). Change the base class at crm_api/views.py:824 from `viewsets.ModelViewSet` to `mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin, viewsets.GenericViewSet` -- that drops create and destroy while leaving the mark-all-read POST route intact. Do NOT set http_method_names.

### customer_messaging_enabled and workflow_config cannot be changed by a boutique
`crm_api/views.py:939`

**Impact.** A boutique cannot silence its own customer-message queue or adjust its workflow/SLA hours without database access; today that means unwanted rows in a to-send list, not unwanted messages.

**Evidence.** Confirmed on the facts, downgraded hard on impact. BoutiqueSettingsViewSet.create (crm_api/views.py:939-963) applies only name, address, phone, email, logo and design_approval_required; workflow_config and customer_messaging_enabled are silently dropped even though BoutiqueSettingsSerializer is fields='__all__' (crm_api/serializers.py:13-16). The settings form (App.jsx:5353-5430) has no control for either, and the only non-migration writes to workflow_config are in tests. But the harm the auditor claims does not exist today: domains/orders/messaging.py:107-119 shows the switch only gates writing a QUEUED CustomerMessage row, and with no CUSTOMER_MESSAGE_BACKEND configured — the shipped default, documented at messaging.py:83-88 — nothing is ever delivered. Leaving the switch on costs a boutique a queue entry, not a message to a customer. Per-tenant workflow editing is an unbuilt feature, not a defect. Low, not medium.

**Fix.** Accept customer_messaging_enabled in BoutiqueSettingsViewSet.create the same way design_approval_required is handled (crm_api/views.py:957-959) and add a matching checkbox to the settings form beside the design-approval one in frontend/src/App.jsx. Leave workflow_config alone — editing it is a feature, not a fix.

### Statuses that map to no stage (Shipped, Stylist Review) change the order and message the customer with no audit row at all
`crm_api/views.py:478`

**Impact.** A shipped-status change carries no record of who made it, so a delivery dispute has nothing in the order's activity log between the last stage transition and the delivery.

**Evidence.** The code is as cited: crm_api/views.py:477-481 writes order_status and calls create_order_notifications with no OrderActivity/UniversalActivity, while the stage path always writes one (domains/orders/services.py:478-490) and assign_stage writes an ASSIGNMENT row. 'Shipped' and 'Stylist Review' are the only CLIENT_STATUSES absent from STATUS_TO_STAGE (crm_api/views.py:382-399), and Shipped is the branch that sends courier + tracking (notifications.py:87-91). But the auditor's framing overstates it: the branch is NOT ungated — lines 464-476 carry a deliberate role check with a long comment explaining that these statuses need their own gate, so only an Owner or Master can reach it, and the Notification row created at notifications.py:64-68 does record the status change (without the actor). Nothing is wrong or lost in the order data; what is missing is attribution. Deflated medium → low.

**Fix.** In the no-stage branch of OrderViewSet.update_status (crm_api/views.py:477-481), add one `OrderActivity.objects.create(order=order, event_type='STATUS_CHANGE', user=request.user, metadata={'old_status': old, 'new_status': new_status})` beside the create_order_notifications call.

### submit-stage-review accepts any stage name, deletes prior history, attributes work to whatever the caller types, and writes no audit row
`crm_api/views.py:698`

**Impact.** An authenticated production account can POST an arbitrary file and an arbitrary performer name onto an order and destroy that stage's prior history row, with nothing in the activity log; no screen currently reaches or reads it.

**Evidence.** Code confirmed at crm_api/views.py:687-709: `stage` is free text with no membership check (contrast assign_stage at 726-729, which does exactly that check on the same model), `OrderStageHistory.objects.filter(order=order, stage=stage).delete()` runs before the create, completed_by defaults to the literal 'Boutique Staff' from the request body, the uploaded file is assigned straight to the ImageField with no serializer, and no OrderActivity is written. It is in RolePermission.STAFF_ORDER_ACTIONS (core/permissions.py:41-46), so any production account can call it. The auditor's own caveat is right and I confirm it: api.submitStageReview (frontend/src/services/api.js:387) has no callers, so nothing in the product writes or reads these rows. Genuine but low.

**Fix.** In OrderViewSet.submit_stage_review (crm_api/views.py:687), add `if not order.stages.filter(stage_key=stage).exists(): return Response(..., status=404)` (the same guard assign_stage already has), set completed_by_name from request.user rather than the body, and pass the upload through OrderStageHistorySerializer instead of assigning it to the field.

### A failed customer message drops out of the owner's queue and can never be retried
`crm_api/views.py:614`

**Impact.** With a transport configured, a message that fails to deliver silently disappears from the owner's to-do list and the recorded `error` is never read; the customer is never told their garment is ready.

**Evidence.** Confirmed. customer_messages filters `status='QUEUED'` (crm_api/views.py:614) and its docstring (lines 608-610) justifies excluding only what 'has already been sent' — it does not consider FAILED, which _deliver sets on any transport exception (domains/orders/messaging.py:70-75). The frontend already half-expects non-QUEUED rows: CustomerMessageQueue dims them and prints the status (App.jsx:249, 254) but gates the action buttons on status === 'QUEUED' (App.jsx:262). Severity lowered from medium to low: FAILED is unreachable in the shipped configuration — CUSTOMER_MESSAGE_BACKEND defaults to '' (boutique_crm/settings.py:415), get_backend() then returns None and messaging.py:119 never schedules _deliver, so every message stays QUEUED. This only bites a deployment that configures a transport.

**Fix.** Change the filter in OrderViewSet.customer_messages (crm_api/views.py:614) to `status__in=('QUEUED', 'FAILED')`, and change the gate in CustomerMessageQueue (frontend/src/App.jsx:262) to `message.status !== 'SENT'` so the owner can send it by hand.

### customer_messaging_enabled cannot be changed from anywhere in the product
`crm_api/views.py:939`

**Impact.** A boutique with a transport connected has no way to stop customer messaging short of a database shell.

**Evidence.** Confirmed on every leg. BoutiqueSettingsViewSet is a plain ViewSet with only list and create (crm_api/views.py:933-963); create assigns name/address/phone/email/logo/design_approval_required and nothing else. The settings form matches — App.jsx:5360-5426 has those same fields and one design_approval_required checkbox. BoutiqueSettings is absent from crm_api/admin.py (registrations at lines 19,66,72,78,104,110,115,120). `grep customer_messaging_enabled` finds only the model (models.py:493), the gate (messaging.py:109), a test and the migration. Severity lowered from medium to low: with the shipped default (no CUSTOMER_MESSAGE_BACKEND, settings.py:415) nothing is actually sent — messages only queue for the owner, who can simply not send them — so the switch is load-bearing only in a deployment that has connected a real transport.

**Fix.** Add one branch to BoutiqueSettingsViewSet.create (crm_api/views.py, beside the design_approval_required branch at 957-959) and one checkbox beside App.jsx:5426.

### Reassigning an order's tailor or master notifies nobody
`crm_api/views.py:308`

**Impact.** A tailor reassigned mid-week is not told; they find the order only by browsing their assignments board, and the previous tailor is never told to stop.

**Evidence.** Confirmed. OrderViewSet.perform_update (crm_api/views.py:308-313) captures only old_status and calls create_order_notifications solely when order_status changed; the 'New Assignment'/'New Stitching Task' rows exist only under `if created:` (notifications.py:50-63). The reassignment UI is real — the master and tailor <select>s at App.jsx:3505-3524 PATCH the order via handleAssignWorkflow. Severity lowered from medium to low: visible_orders (core/permissions.py:135-137) includes `Q(tailor=profile) | Q(master=profile)`, so the order does appear on the new assignee's own board immediately; only the bell is silent, and nothing is lost.

**Fix.** In OrderViewSet.perform_update (crm_api/views.py:308), capture serializer.instance.tailor_id/master_id before save() and, when either changed, write the same Notification row assign_stage already writes (crm_api/views.py:769-775) — including `recipient_role=tailor.role`, not the literal.

### performed_by is never recorded for any specialist master, so their stage work is unattributed
`domains/orders/services.py:385`

**Impact.** In a split-role studio, 'Assigned Performer' stays blank on every stage a Cutting/QC/Finishing Master completes and the production task keeps naming the order's original tailor.

**Evidence.** Confirmed at services.py:385-386: the fallback is gated on `user_role in ['Master', 'Tailor']`, and resolve_user_role returns the Tailor profile's role verbatim including the seven specialist strings (core/roles.py:29-36, crm_api/models.py:226-236) — none of which match. The performer dropdown is indeed unreachable for them: App.jsx:8593 gates it on `currentUser.role === 'Owner' || SUPERVISOR_ROLES.includes(currentUser.role)` and frontend SUPERVISOR_ROLES is ['Master'] only (App.jsx:40), mirroring core/permissions.py:24. The ProductionTask repoint at services.py:469-475 is conditional on `performer is not None`, so it is skipped too. Deflated medium → low: nothing is wrong or lost, one display field is blank, only in studios that have split the roles, and OrderActivity still records the acting user for every transition (services.py:478-490), so attribution is recoverable.

**Fix.** In domains/orders/services.py:385, test for the profile rather than the role string, and do not clear an existing performer: `elif user and user.is_authenticated and getattr(user, 'tailor_profile', None): order_stage.performed_by = user.tailor_profile`. (The auditor's 'drop the allowlist' wording would assign None for an Owner and wipe a previously recorded performer.)

### Signup step 4 asks the user to select style tags that cannot be selected and are never saved
`frontend/src/App.jsx:2250`

**Impact.** A new owner clicks the tags, nothing responds, and whatever they meant to say about their specialisation is discarded.

**Evidence.** Confirmed at App.jsx:2250-2280 (not 2089): the block is titled 'Design Style Preferences' with 'Select style tags that correspond to your boutique specialization', and the six tags are plain <span> elements with inline styling — no onClick, no state, no selected class. handleCompleteRegistration (1211-1234) posts only first_name, last_name, email_address, mobile_number, password, business_name and business_address, and SignupView reads nothing else. The tracker still lists { step: 4, label: 'Preferences' } at line 2063.

**Fix.** Remove step 4: drop { step: 4, label: 'Preferences' } at App.jsx:2063, delete the signupStep === 4 block (2250-2280), and point step 3's button at handleCompleteRegistration.

### The password field promises "min 6 characters" while the server rejects anything under 8 — four steps later
`frontend/src/App.jsx:2136`

**Impact.** An owner types the 6-character password the form asked for, walks through the OTP screen, boutique details and preferences, then gets bounced to step 1 with 'This password is too short' and redoes the wizard.

**Evidence.** Confirmed. The placeholder is 'Create a password (min 6 characters)' (App.jsx:2136) and getPasswordStrength (1646-1651) grades anything from 6 to 9 characters as 'medium'. SignupView runs validate_password (crm_api/auth_views.py:87) against AUTH_PASSWORD_VALIDATORS (settings.py:252-265), which includes MinimumLengthValidator with no override — Django's default is 8 — plus CommonPassword and Numeric validators. handleSignupSubmit (App.jsx:1191-1199) checks only presence, and the API is not called until handleCompleteRegistration (1211), whose catch alerts the server message and does setSignupStep(1).

**Fix.** Change the placeholder at App.jsx:2136 to 'min 8 characters', the `len < 6` threshold at 1649 to 8, and add `if (signupForm.password.length < 8) { alert('Use at least 8 characters.'); return; }` to handleSignupSubmit (1191) so the failure lands on the field.

### The "Remember me" checkbox does nothing; the session is always persisted
`frontend/src/App.jsx:1889`

**Impact.** Staff on the shared boutique computer untick it expecting the session to end at browser close; the next person to open the app is signed in as them.

**Evidence.** Confirmed at App.jsx:1889 (not 1812): `<input type="checkbox" defaultChecked style={{ accentColor: '#b07c40' }} />` is uncontrolled, has no ref and no onChange, and handleLoginSubmit (1166-1189) never reads it. api.login writes the token to localStorage unconditionally (api.js:57-62), which survives a browser restart, and DRF's Token has no expiry. The neighbouring 'Forgot password?' control on the same row (1892-1899) is wired, which makes the dead checkbox next to it more believable to a user, not less.

**Fix.** Delete the checkbox and its label (App.jsx:1887-1890). Wiring it to sessionStorage means touching getHeaders, api.login, api.logout and getMe for a preference nobody asked for.

### Book Appointment quick action dead-ends for a boutique with no customers
`frontend/src/App.jsx:5577`

**Impact.** A new owner exploring the dashboard opens a modal they cannot submit, with no hint about what is missing.

**Evidence.** Confirmed on content, corrected on lines and on the surrounding claim. The quick-action grid is at App.jsx:2801-2831 and the Book Appointment tile at 2827 does open the modal (App.jsx:5566), whose Client select at 5577-5585 is `required` and is populated only from allCustomers — empty on day one, leaving a single 'Select a client' option and no CTA. But the auditor's framing that this is 'the only one of the five that dead-ends' is stale: the comment at App.jsx:2822-2825 records that this tile was the one with NO onClick and that booking was wired up in a previous pass. Downgraded from medium: nothing is broken or wrong, the owner just has to add a customer first, which is one tab away and is the natural first step anyway.

**Fix.** In the appointment modal's Client block (frontend/src/App.jsx:5576-5586), when allCustomers.length === 0 render a line of text plus a button calling handleStartNewCustomer() instead of the empty select — the same inline-add pattern already used for missing tailors at App.jsx:6894.

### Dead social-auth affordance on the signup screen
`frontend/src/App.jsx:2169`

**Impact.** Three clickable-looking icons under an 'OR CONTINUE WITH' heading on the signup screen do nothing when pressed.

**Evidence.** Half refuted. The login-screen 'Continue with Google' / 'Continue with Apple' buttons the auditor cites at App.jsx:1837-1844 DO NOT EXIST — they were already deleted, and App.jsx:1907-1913 carries an explanatory comment saying exactly why ('no OAuth anywhere in this product -- no client id, no callback route, no social account model... Deleted rather than wired up'). That part of the finding is invented from a stale read. What survives is the signup screen: an 'OR CONTINUE WITH' divider at App.jsx:2169 followed by three .social-icon-circle divs (2171-2173) with no onClick, whose CSS at frontend/src/index.css:1754-1769 gives them cursor:pointer and a hover state. Real but much smaller than filed, and low rather than medium.

**Fix.** Delete the divider and the icon row at frontend/src/App.jsx:2169-2174 — the same treatment already applied to the login screen at 1907.

### Signup step 4 presents style tags as selectable, but they are inert and never submitted
`frontend/src/App.jsx:2253`

**Impact.** The one onboarding step that promises to personalise the product collects nothing; the owner either thinks the app is broken or believes they configured something they did not.

**Evidence.** Confirmed. The subtitle at App.jsx:2253 reads 'Select style tags that correspond to your boutique specialization.' and the six tags below (2257-2274) are plain <span> elements with no onClick, no selected state and no backing state — there is no styleTags variable anywhere in App.jsx. handleCompleteRegistration (App.jsx:1214-1233) posts only first_name, last_name, email_address, mobile_number, password, business_name and business_address, and SignupView reads nothing else.

**Fix.** Remove step 4 from the wizard (frontend/src/App.jsx:2247-2281) and move its 'Submit Registration' button onto step 3, so signup ends on the step that actually feeds BoutiqueSettings.

### Profile page reports every boutique as registered in June 2024
`frontend/src/App.jsx:5345`

**Impact.** A boutique that signed up today is told, on its own account page, that it registered in June 2024.

**Evidence.** Confirmed. Under the 'Registered Since' label at App.jsx:5344 the value is the string literal 'June 2024' at 5345, bound to nothing. BoutiqueTenant.created_on exists (tenants/models.py:7) but is not returned by the signup response, the login response, or MeView (crm_api/auth_views.py:320-338). The adjacent 'Tenant Domain' row at 5334 does print the raw schema name.

**Fix.** Add the tenant's created_on to the MeView payload (crm_api/auth_views.py:329-338, alongside tenant_id) and render it at frontend/src/App.jsx:5345 — or delete the row.

### Day-one Orders, Customers and Invoices all report 'nothing matching the filters' with no filters set
`frontend/src/App.jsx:3762`

**Impact.** A new owner opening the three main tabs is told three times that a search returned nothing, implying data hidden behind a filter they never set, instead of being offered the button that would create the first record.

**Evidence.** Confirmed at all three sites, with corrected lines. Manage Orders renders 'No orders found matching the criteria.' whenever the filtered list is empty (App.jsx:3752-3765), which includes an empty ordersList; Customers renders 'No customers found matching current filters' at 4063 (note it does already branch on loading at 4052 and on loadErrors at 4056 with a Retry button, so the panel is not naive — only the empty case is); Invoices renders 'No invoices matching the criteria.' at 4953. None offers an action. The dashboard's own orders panel gets it right on the same data at App.jsx:2848 ('No active custom orders. Click "New Custom Order" to begin!').

**Fix.** In each of the three blocks (frontend/src/App.jsx:3752, 4060, 4950), branch first on the unfiltered source list being empty and render a first-run message with the existing CTA — setView('order-selector') for orders and invoices, handleStartNewCustomer() for customers.

### 'Style Inspiration' dashboard panel is three hardcoded stock portraits with no behaviour
`frontend/src/App.jsx:3184`

**Impact.** Half of a prime dashboard row on a new boutique's home screen is portraits of unrelated strangers under a heading that implies curated style content, and clicking them does nothing.

**Evidence.** Confirmed. The panel at App.jsx:3183-3195 renders exactly three hardcoded Unsplash URLs of photographed people (photo-1534528741775, photo-1507003211169, photo-1494790108377) inside .inspiration-circle-avatar divs with no onClick and no link to the design library. It sits directly beside the appointments panel, whose comment at App.jsx:3142-3147 records removing precisely this kind of shipped-invented content ('shown to every boutique including one created a minute ago... An empty panel is better than an invented one') — so the precedent the auditor cites is real and in the adjacent block.

**Fix.** Replace the three literal images at frontend/src/App.jsx:3185-3194 with the first three entries of allDesigns wrapped in an onClick of setDashboardTab('designs'), or delete the panel.

### The tailor's "Sizing Blueprint" shows the live shared customer measurement, not the order's frozen snapshot
`frontend/src/App.jsx:2582`

**Impact.** Re-measuring a returning client for a second garment silently changes the blueprint on the tailor's card for their first, unfinished order, and it then disagrees with the frozen per-garment numbers shown in the stage-review modal.

**Evidence.** Confirmed, at App.jsx:2582-2600 (not 2422/2404). The card reads order.customer_measurements.bust/waist/hips…, which OrderSerializer sources from the customer, not the order (crm_api/serializers.py:173, `MeasurementSerializer(source='customer.measurements')`), and Measurement is a OneToOneField on Customer (crm_api/models.py:95) — one row shared by all that client's orders. saveStep2 (App.jsx:1377-1396) overwrites it from each new order's garment values, with a comment stating 'the newest dress that carries them wins' — that comment justifies updating the customer record, not reading it on a per-order production card, so it is not a documented tradeoff covering this. The per-order snapshot exists (GarmentJob.measurements, apps/catalog/models.py:170-176) and OrderSerializer already exposes it as garment_jobs (crm_api/serializers.py:195, 220-224).

**Fix.** In the tailor assignment card (frontend/src/App.jsx:2585-2599), prefer the frozen snapshot: read order.garment_jobs?.[0]?.measurements and fall back to order.customer_measurements. Note the key names differ — the garment job stores template keys (chest, hip) while the card renders bust/hips — so reuse the CUSTOMER_KEYS map already defined in saveStep2 (App.jsx:1384-1386) rather than indexing the snapshot directly, or the fields will render as '—'.

### Invoice line item is priced tax-inclusive but sits above a Subtotal + Tax = Total block
`frontend/src/App.jsx:8151`

**Impact.** The printed bill reads line item ₹33,075 / Subtotal ₹31,500 / Taxes ₹1,575 / Total ₹33,075 — the itemised amount does not make up the subtotal it sits above, which is the first thing a customer or accountant queries.

**Evidence.** Verified. The single line item's Amount cell prints the gross figure `₹{parseFloat(confirmedOrder.total_amount || 0).toLocaleString('en-IN')}` (App.jsx:8151), and the summary immediately below computes Subtotal as total_amount - taxes (App.jsx:8167), adds 'Taxes (GST 5%)' (8172) and reprints total_amount as 'Total Amount' (8176). The comment at 8160-8163 explains why the tax line was added but does not address the line-item figure, so it is not a documented tradeoff. Genuine but cosmetic-in-effect: the total charged is right, only the itemisation fails to add up.

**Fix.** In the pricing table cell (frontend/src/App.jsx:8150-8152) print the pre-tax figure using the same expression as the Subtotal row at 8167: `parseFloat(confirmedOrder.total_amount || 0) - parseFloat(confirmedOrder.taxes || 0)`.

### Try-on 'Confirm & Save' saves nothing
`frontend/src/App.jsx:8884`

**Impact.** Staff press a primary button labelled 'Confirm & Save' and nothing is written; the try-on result is attached to no order and the customer never sees it.

**Evidence.** Confirmed, but the cited line was wrong: the green primary button's onClick is at App.jsx:8884 and its label at 8887 (8913 is past the end of the modal). The handler body is exactly `setShowDrapingModal(false);` — identical to Cancel (8769/8844). `grep drapedImage` returns only useState (818), the <img> at 8826 and the setter at 8857; no API call, no field, no persistence. Severity lowered from high to low: the only thing not saved is the value returned by getDrapedPreviewImage, which is a fixed Unsplash URL keyed on a colour word (App.jsx:958-982, see the next finding) — nothing of the customer's is lost. Also refuting one supporting claim: drapingCompleted is not reset on close, so within a session reopening the modal still shows the preview; it resets only on reload.

**Fix.** Relabel the button 'Done' (frontend/src/App.jsx:8887). Persisting a colour-keyed stock photo would be worse than not persisting it — if a real composite is ever produced, persist it then.

### Try-on preview is a stock photograph picked by colour keyword and ignores the selected sketch and fabric
`frontend/src/App.jsx:958`

**Impact.** A customer at the counter is shown a stock photo of an unrelated garment framed as her fabric draped on her chosen silhouette; two customers who both pick a rose-toned fabric see the identical picture.

**Evidence.** Confirmed, line corrected to 958 (the function runs 958-982; 947 is unrelated session-restore code). getDrapedPreviewImage(fabric, designUrl) never references designUrl and never reads fabric.image_url — it returns one of six fixed Unsplash URLs by substring of fabric.color with a catch-all. It is rendered under '✨ 3D Mannequin Draped View' (App.jsx:8824) after a 2-second setTimeout captioned 'Mapping coordinates onto sketch layers' (8818, 8855-8861). Severity lowered from medium to low: the modal carries a visible disclaimer, 'Reference Simulation Only' (App.jsx:8836), the screen is staff-facing rather than part of the customer's tracking page, and nothing downstream consumes the image (see the Confirm & Save finding).

**Fix.** Honest relabel, entirely in App.jsx: retitle 8824 to 'Colour reference' and drop the 'Mapping coordinates onto sketch layers' caption at 8818. Compositing the real fabric over the sketch is the right feature but is not the smallest fix.

### 'Chat on WhatsApp' on the order-confirmation screen builds a malformed wa.me link
`frontend/src/App.jsx:7939`

**Impact.** For any number not typed as bare digits the button opens a dead wa.me link; the surrounding copy also implies it reaches the boutique when it opens the customer's chat.

**Evidence.** Partly confirmed, line corrected to 7939. The link really is `https://wa.me/91${customerForm.mobile_number}` with a literal '91' prefixed to raw free text, and validate_mobile_number (crm_api/serializers.py:366-382) accepts anything whatsapp_number() can normalise — including '+91 98765 43211' — so the URL becomes wa.me/91+91 98765 43211, a dead link. whatsapp_number() (crm_api/models.py:14) is the codebase's own single definition of a reachable number and is unused here. REFUTING the 'wrong party' half: this is the staff wizard's confirmation screen (its sibling buttons are 'Back to Dashboard' and 'View & Print Invoice', App.jsx:7946-7950), so opening the customer's chat is a reasonable action for the staff member looking at it; only the customer-voiced copy at 7937 is misleading. Severity low is right.

**Fix.** Strip non-digits and reuse the normalisation the backend already does: `window.open('https://wa.me/' + (customerForm.mobile_number || '').replace(/\D/g,'').replace(/^0+/, '').replace(/^(?!91)/, '91'))` at frontend/src/App.jsx:7939, and reword the caption at 7937 to 'Message this client on WhatsApp'.

### Staff portal 'Chat Now' opens a hardcoded placeholder phone number
`frontend/src/App.jsx:2441`

**Impact.** Every staff member in every tenant who clicks 'Chat Now' is sent to a WhatsApp chat with a number that belongs to nobody in the boutique.

**Evidence.** Confirmed that the literal exists — `window.open('https://wa.me/919876543210')` at App.jsx:2441 (not 2464), in the tailor/designer sidebar 'Need Help?' card, with no tenant awareness. REFUTING one supporting claim: it is NOT the default value of BoutiqueSettings.phone, which is '+91 9999999999' (crm_api/models.py:481) — 919876543210 is an unrelated invented number, which if anything makes it likelier to belong to a real stranger. Severity low is right.

**Fix.** Use the tenant's own number and hide the card when it is unset: at frontend/src/App.jsx:2441 render the button only when boutiqueSettings?.phone is set and open `'https://wa.me/' + boutiqueSettings.phone.replace(/\D/g,'')`.

### Three inert sidebar nav items on the order-selector screen (the rest of this finding is stale)
`frontend/src/App.jsx:5957`

**Impact.** On the order-selector screen a user clicking My Orders / Appointments / Measurements gets nothing at all, with working links directly above and below.

**Evidence.** Mostly refuted. 'Continue with Google'/'Continue with Apple' are GONE — App.jsx:1925-1931 is a comment explaining they were deleted because no OAuth exists in the product. The six 'Design Style Preferences' pills are GONE, removed with the OTP step and explained at 2077-2090. What survives: App.jsx:5957-5959, three `<a className="portal-menu-item">` items (My Orders, Appointments, Measurements) with no onClick, sitting between Dashboard (5956) and Logout (5960) which both work; the three inert `social-icon-circle` divs under 'OR CONTINUE WITH' at 2201-2203; and 'Need help?' at 6158-6160 styled cursor:pointer with no handler. The 'Style Inspiration' avatars (3163-3171) are plain decorative <img> with no click affordance in the JSX — not a CTA.

**Fix.** Delete App.jsx:5957-5959, 2199-2204 and 6158-6160. Nothing else in this finding still exists.

### Style DNA is presented as AI reading the boutique's sales data, but colour and style come from a hash of the customer id
`frontend/src/App.jsx:4259`

**Impact.** The owner reads 'Emerald Green 80% Pink 15%' as a fact about their client and buys fabric or pitches a design on it; it is a function of the primary key.

**Evidence.** Confirmed. Both panels print 'This is NOT manual entry. AI reads your sales data automatically.' at App.jsx:4259 and 4715. crm_api/serializers.py build_style_dna (227-279) hashes str(obj.id) with sha256 and indexes six canned colour strings (262-270) and four canned style strings (273-279) — nothing to do with any order. The comment at 258-260 explains only why a sha256 digest replaced the salted built-in hash (stability across restarts); it does not defend the fabrication. Budget (234-255) and size (281-295) are genuinely derived.

**Fix.** Drop the two invented rows and the 'AI reads your sales data' line from both panels (App.jsx around 4259 and 4715), leaving budget, size and visit pattern, which are real.

### The designer bootstrap password is hardcoded in the frontend bundle and diverges from the server's
`frontend/src/features/designStudio/DesignDashboard.jsx:11`

**Impact.** On a deployment that sets DESIGNER_DEFAULT_PASSWORD as its own code advises, the roster banner prints the wrong password every time; the owner hands over a credential that does not work and the designer must go through password reset instead.

**Evidence.** Both halves verified: DesignDashboard.jsx:11 `const DESIGNER_BOOTSTRAP_PASSWORD = 'DesignerSecure2026!'` printed at :216 under 'this is the only time the password is shown here', against views.py:515 `password=os.environ.get('DESIGNER_DEFAULT_PASSWORD', 'DesignerSecure2026!')`. They agree only when the variable is unset, and views.py:509-512 tells the deployment to set it. CORRECTIONS that cut this to low: the hardcoding itself is deliberate and explained at DesignDashboard.jsx:7-10 ('The server never returns this... the same convention the Tailor share-credentials panel already uses'), and views.py:509-512 acknowledges the shared-credential tradeoff in as many words — so only the divergence is a defect, not the constant. The auditor's 'no reset flow anywhere in the product' is false: App.jsx:1898 has a 'Forgot password?' link, api.js requestPasswordReset/confirmPasswordReset exist, and settings.py:334-341 configures PASSWORD_RESET_BASE_URL and a one-hour timeout, so a designer handed a wrong password can recover (given SMTP is configured).

**Fix.** Agreed: have DesignerViewSet.create_login include the password it actually used in its 200 response body, and have DesignerRoster (DesignDashboard.jsx:210-220) print that value instead of the local constant — then delete the constant.

### No one can edit or delete a design uploaded to the library, so the Designer's own-upload rights are unreachable
`frontend/src/features/designStudio/DesignLibrary.jsx:32`

**Impact.** A designer who uploads the wrong photograph or a wrong title has no way to correct or remove it, and neither has the Owner; the library only grows. A Designer who clicks Edit or Delete on a catalogue row gets 'Failed to save design: detail: Your role does not permit this.'

**Evidence.** Every factual claim checks out, but this is a never-wired capability rather than a broken control, so medium is inflated. `EDITABLE_SOURCES = ['catalogue', 'suggestion']` is at DesignLibrary.jsx:32 with a comment explaining only that catalogue endpoints suit catalogue rows -- it does not claim uploads should be uneditable. `editable` is computed at line 100 and gates the Edit/Delete pair at line 223. DesignAsset.source defaults to SOURCE_UPLOAD ('upload') (apps/design_studio/models.py:128,146) and perform_create (views.py:255-256) does not override it, so uploads never match. Confirmed services/api.js has no PATCH or DELETE against /design-studio/assets/<id>/ -- only GET (966), list (913), create (1005), review (923) and approval-history (934). DesignLibraryPermission.OWN_UPLOAD_ACTIONS and its has_object_permission (apps/design_studio/permissions.py:52-79) exist to grant exactly this and are unreachable from any client code. The review action (views.py:275) is the only status write and the UI exposes it on PENDING rows only, so with design_approval_required=False (crm_api/models.py:489) an upload lands ACTIVE and cannot be archived either. Worth noting a sharper adjacent defect the finding did not name: for a Designer, the Edit/Delete buttons that DO render (catalogue/suggestion rows) route to api.updateBoutiqueDesign/deleteBoutiqueDesign (App.jsx:1139,1156) -> BoutiqueDesignViewSet (crm_api/views.py:295) on default RolePermission, whose DESIGNER branch returns False -- so those buttons 403 for the one role that sees the library most.

**Fix.** Smallest useful change is the Designer-facing 403 first: hide the Edit/Delete pair at DesignLibrary.jsx:223 when the caller is a Designer (pass the same `canReview`-style flag App.jsx already computes at 3635). Wiring upload edit/delete is a feature, not a bug fix: if it is wanted, add `updateDesignAsset(id, payload)` / `deleteDesignAsset(id)` in services/api.js against PATCH and DELETE on /design-studio/assets/<id>/ and route source==='upload' rows to those instead of the catalogue calls -- the API side already permits exactly the right people.

### Extra photographs are uploaded into `gallery` and never shown anywhere
`frontend/src/features/designStudio/DesignUpload.jsx:148`

**Impact.** A boutique photographs a garment from four angles as the modal invites them to; only the cover is ever visible afterwards. The other files sit on disk unreachable through the product.

**Evidence.** The promise is at DesignUpload.jsx:148 verbatim ('The first becomes the cover; the rest form the gallery.') and the backend honours it at views.py:241 `gallery=uploaded[1:] if len(uploaded) > 1 else []`, asserted by tests.py:942. I re-ran `grep -rn gallery frontend/src`: the only hits are that subtext string, an unrelated comment at App.jsx:311, a docstring in DesignDashboard.jsx:16 and a CSS class in index.css — no component reads design.gallery. DesignDetail (DesignLibrary.jsx:155) renders design.image_url and nothing else. Confirmed. Severity cut to low: nothing is lost or wrong, the extra photographs are stored correctly and are simply not surfaced; the modal's own preview strip (DesignUpload.jsx:153-161) already shows the user which one is the cover, so nobody is misled about what was uploaded.

**Fix.** Agreed: in DesignLibrary.jsx's DesignDetail, render design.gallery as a thumbnail strip under the cover image using the same resolveMediaUrl call already on line 155.

### 'Add collection' in the upload modal always fails for a Designer
`frontend/src/features/designStudio/DesignUpload.jsx:76`

**Impact.** A designer uploading their own work types a collection name, clicks Add collection, and gets a raw JSON permission error. They can still complete the upload without a collection.

**Evidence.** The path is real: DesignUpload.jsx:217-227 renders the control whenever a designer is picked, with no role gate, and :76 calls api.createCollection, which POSTs to /design-studio/collections/. CollectionViewSet uses DesignStudioPermission (views.py:324), whose has_permission (permissions.py:23-32) admits a non-Owner only on SAFE_METHODS plus a Master's production_notes action, so a Designer gets 403 every time. A Designer does reach the modal — App.jsx:2447-2452 gives them the Design Studio nav and DesignLibrary renders 'Upload design' unconditionally (:332, :379). CORRECTION on two points that cut the severity: the failure is not silent or unexplained — createCollection throws JSON.stringify(data) (api.js:993) and DRF returns DesignStudioPermission.message, so the banner reads 'Could not create the collection — {"detail":"Your role does not permit this action in the Design Studio."}' — ugly, but it names the reason. And the collection field is optional, so the upload itself still completes; the flow is not blocked.

**Fix.** Smaller than either option offered: hide the Add-collection control in DesignUpload.jsx:217 unless the signed-in user is an Owner (the same `!role || role === 'Owner'` test App.jsx already uses), rather than widening DesignStudioPermission — opening create on CollectionViewSet to DESIGNER would also let a designer create collections for other designers, since nothing in the serializer scopes `designer` to the caller.

### The order-materials lifecycle has no screen: Cost-per-order is structurally always empty and RecipesTab promises a capability the product does not have
`frontend/src/features/inventory/InventoryPanel.jsx:186`

**Impact.** The Cost-per-order panel on the Reports tab always shows its empty state, and the Recipes tab tells the owner orders reserve against a recipe when nothing in the product ever does.

**Evidence.** Factually verified. Grepping frontend/src for planMaterials, getPlanAvailability, reservePlan, consumePlanLine, releasePlanUnused, deductPlanPackaging, reconcilePlan, closePlan, cancelPlan, receiveCustomerMaterial, getCustomerMaterials and recordCustomerMaterial returns only their own definitions at services/api.js:1160-1175 — zero call sites. The tab list at InventoryPanel.jsx:186-193 is items/catalog/locations/recipes/purchase/suppliers/reports, with no materials or customer-material screen. The consequence chain also checks out: OrderMaterialLine is constructed in exactly one place, order_materials.py:117 inside plan_materials(), so reports.cost_per_order (reports.py:223-233) can never return a row and ReportsTab.jsx:140 permanently renders "No order has consumed material yet." RecipesTab.jsx:61 does say "An order reserves against the recipe." Severity corrected down from medium: a whole unbuilt feature is a gap, not a defect, and the audit brief excludes missing-feature reports. What survives as an actual defect is narrow — one report panel that can never populate and one sentence of UI copy that is untrue — and both are cosmetic-but-real.

**Fix.** Do not build the Materials panel as a bug fix — that is a feature. The defect-sized change is in frontend/src/features/inventory: reword RecipesTab.jsx:61 to drop the reservation claim, and drop the Cost-per-order Section from ReportsTab.jsx:138-158 (or label it "available via the materials API") so the dashboard stops implying data that cannot exist.

### Recipes promise that orders reserve stock, but no screen ever creates a material plan
`frontend/src/features/inventory/RecipesTab.jsx:61`

**Impact.** An owner writes recipes with formulas and waste allowances believing orders will reserve against them; nothing is ever reserved and available stock stays unchanged for every order in flight.

**Evidence.** Confirmed. RecipesTab.jsx:61 reads 'What each garment is made of. An order reserves against the recipe.' `grep -rn` for planMaterials/getMaterialPlans/reservePlan/consumePlanLine/releasePlanUnused/deductPlanPackaging/reconcilePlan/closePlan/cancelPlan across frontend/src returns hits only inside services/api.js:1160-1169 — zero callers. apps/inventory/order_materials.py:plan_materials is reachable only from apps/inventory/views.py:683, which nothing in the frontend calls, and domains/orders/services.py create_order_for_customer never touches it. Downgraded from medium: this is an unshipped module, and rule 4 says an unbuilt feature is not a finding — what is a finding is one sentence of UI copy asserting behaviour that does not happen.

**Fix.** Change the copy at RecipesTab.jsx:61 to drop the reservation claim (e.g. 'What each garment is made of. Used when planning materials.'). Do not build the plan UI as a bug fix.

### Deleting a recipe line has no confirmation
`frontend/src/features/inventory/RecipesTab.jsx:206`

**Impact.** One mis-tap permanently removes a material line with its formula and waste allowance, with no confirmation and no undo.

**Evidence.** Confirmed: RecipesTab.jsx:206 `onClick={() => remove(line)}` on a small Trash2 button in a table row, and remove (128-136) goes straight to api.deleteBomLine with no confirm. Every comparable destructive action does confirm — App.jsx:1070 (fabric), and the same window.confirm pattern for tailor and design deletes.

**Fix.** Guard inside remove (RecipesTab.jsx:129) rather than at the button: `if (!window.confirm(`Remove ${line.material_name} from this recipe?`)) return;`, matching App.jsx:1070.

### A single server hiccup on page load silently signs the user out
`frontend/src/services/api.js:132`

**Impact.** An owner refreshing during a brief backend blip is thrown back to the login screen with no explanation.

**Evidence.** Confirmed, at line 132 not 106: getMe does `if (!res.ok) { localStorage.removeItem('token'); return null; }` for ANY non-ok status, so a 500 from a cold DB, a 502 while a gunicorn worker recycles (gunicorn.conf.py:38 max_requests = 1000) or the middleware's 400 all discard the credential. checkAuthSession (App.jsx:911-940) calls it on every mount and falls through to the login screen. SEVERITY CORRECTED down from medium: the auditor's stated impact rests on 'with no reset flow, anyone unsure of their password is now genuinely locked out', and that premise is false — the reset flow exists (auth_views.py:354-486). The real cost is retyping a password after a blip.

**Fix.** In api.getMe (frontend/src/services/api.js:132), only clear on an auth failure: `if (res.status === 401 || res.status === 403) localStorage.removeItem('token'); if (!res.ok) return null;`.

### Login and signup crash on any non-JSON error response, showing the user a JavaScript parser error
`frontend/src/services/api.js:53`

**Impact.** At the two moments a clear message matters most the user sees `Unexpected token '<' ... is not valid JSON` and cannot tell whether their boutique was created.

**Evidence.** Confirmed at api.js:53-54 (login) and 74-75 (signup): both do `const data = await res.json();` before checking res.ok, so an HTML 502/504 page or an empty proxy body throws a SyntaxError that propagates to alert(err.message || 'Registration failed.') in handleCompleteRegistration (App.jsx:1232) and alert(err.message || 'Invalid credentials.') in handleLoginSubmit (App.jsx:1188). The file already knows better everywhere else — requestPasswordReset (96) and confirmPasswordReset (107) use `await res.json().catch(() => ({}))` with describeApiError, and superadmin/api.js:52 does the same. SEVERITY CORRECTED down from medium: the request still fails either way; what differs is the readability of the message.

**Fix.** In api.js login (line 53) and signup (line 74), use `const data = await res.json().catch(() => ({}));` and keep the existing 'Failed to login' / 'Failed to sign up' fallbacks.

### gunicorn and requests are unpinned while every other dependency is exact-pinned
`requirements.txt:10`

**Impact.** A redeploy with an empty diff can pull a new gunicorn major and either fail to boot or change proxy/scheme handling — an outage with no code change to attribute it to.

**Evidence.** Confirmed by reading the file: lines 1-8 pin asgiref==3.11.1 through sqlparse==0.5.5 exactly, line 9 is a bare `requests` and line 10 a bare `gunicorn`. README.md:118's Render build command is a plain `pip install -r requirements.txt` with no lockfile, so each deploy resolves whatever PyPI serves at that moment. gunicorn is the process manager the whole service runs under and gunicorn.conf.py depends on gthread, forwarded_allow_ips and max_requests_jitter behaving as they do today. Installed today: gunicorn 26.0.0, requests 2.34.2.

**Fix.** Pin both in requirements.txt to what is installed: `gunicorn==26.0.0` and `requests==2.34.2`, matching the style of the other eight lines.
