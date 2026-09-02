# Android QA: the matrix, and what has actually been run

Two columns matter here and they are kept apart on purpose: **verified** means
someone (or something) ran it and saw the result; **not run** means exactly that.
Nothing in this file is marked done because the code that implements it exists.

Status of this document: everything below was run on an **emulator**
(Medium_Phone_API_36.1 — Android 16, 1080×2400, plus two other display
configurations) against a local backend. **No physical device has been tested.**
That is the single largest remaining gap, and no result here should be read as a
claim about Android compatibility beyond this one image.

### Device matrix, precisely

| Test | Device | Android | Result |
|---|---|---|---|
| Owner | emulator Medium_Phone_API_36.1 | 16 (API 36) | PASS |
| Master | emulator Medium_Phone_API_36.1 | 16 | PASS |
| Tailor (stitching) | emulator Medium_Phone_API_36.1 | 16 | PASS |
| Tailor (Cutting Master) | emulator Medium_Phone_API_36.1 | 16 | PASS |
| Designer | emulator Medium_Phone_API_36.1 | 16 | PASS |
| Auth refresh (foreground, backgrounded, concurrent) | emulator | 16 | PASS |
| Deep link (7 cases) | emulator | 16 | PASS |
| Upload (camera) | — | — | **NOT TESTED** — needs a real camera |
| Push | — | — | **NOT TESTED** — needs a Firebase project |
| Offline | emulator | 16 | PASS |
| Back navigation | emulator | 16 | PASS |
| Small screen (360×592) | emulator, resized | 16 | PASS |
| High density (411×843 @3.5) | emulator, resized | 16 | PASS |
| Release build renders | emulator | 16 | PASS |

No physical device, no Android version other than 16, no OEM skin.

---

## The invariants that are now pinned by automated tests

These are the properties the release gate asked to stay covered. Each names the
test that holds it, so a future change that breaks one fails the suite rather
than a screen.

| Invariant | Test |
|---|---|
| Paging does not change financial totals or analytics aggregates | `crm_api.test_orders_summary.OrderSummaryTests.test_the_totals_do_not_depend_on_how_many_rows_the_client_holds` |
| Totals cover the whole book, scoped to the caller | `...test_the_owner_sees_the_whole_book`, `...test_a_tailor_totals_only_their_own_work` |
| Collected is money received, not the face value of paid orders | `...test_collected_is_money_received_not_the_value_of_paid_orders` |
| Garments counted per garment, not per order | `...test_garments_are_counted_per_garment_not_per_order` |
| Status counts are per order, not per stage | `...test_status_counts_are_per_order_not_per_stage` |
| Every row served exactly once across pages | `core.test_pagination.PaginationTests.test_paging_covers_every_row_exactly_once` |
| An unordered queryset is given a stable order before slicing | `...test_an_unordered_queryset_is_given_a_stable_order` |
| `page_size` cannot be used to ask for everything | `...test_page_size_is_capped` |
| Search runs on the server and composes with paging | `...test_search_runs_on_the_server_and_pages`, `...test_search_and_paging_compose` |
| Status filters: active / shipped / delivered / open | `crm_api.test_orders_summary.StatusGroupTests` |
| Payment filters, with pending including part-paid | `...test_pending_includes_part_paid_invoices`, `...test_paid_selects_only_settled_invoices` |
| An unknown filter narrows nothing rather than emptying the screen | `...test_an_unknown_group_narrows_nothing` |
| **Concurrent 401s trigger exactly one refresh** | `frontend/src/services/api.test.js` — "refreshes ONCE for eight requests that expire together" |
| A refresh failure does not loop | `...gives up rather than looping when the refresh token is refused` |
| A dead network becomes a sentence, not `Failed to fetch` | `...turns a dead network into a sentence` |
| An expired access token is refused with a distinguishable code | `auth_tokens.tests.SessionTests.test_an_aged_access_token_is_refused_and_says_why` |
| A spent refresh token cannot be spent twice | `...test_a_spent_refresh_token_cannot_be_spent_twice` |
| A replay ends every session the user holds | `...test_a_replay_ends_every_session_the_user_holds` |
| Sign-out kills the refresh token too | `...test_logout_kills_the_refresh_token_too` |
| A password reset revokes the refresh token | `...test_a_password_reset_revokes_the_refresh_token` |
| Signing in after expiry returns a usable token | `...test_signing_in_again_after_expiry_returns_a_usable_token` |
| **The dropdown cannot walk an order backwards** | `crm_api.test_workflow.StatusDropdownTests.test_the_dropdown_cannot_walk_an_order_backwards` |
| Absolute URLs carry the scheme the client used | `core.test_absolute_urls.ProxySchemeTests` |
| Uploads use the service key, and a refusal does not leak bucket policy | `crm_api.test_storage.SupabaseStorageTests` |
| Push reaches the right role and nobody else | `crm_api.test_push.TargetingTests` |
| The push receiver is actually connected | `crm_api.test_push.WiringTests` |

The client-side distinction between **"No orders found matching the criteria"**
and **"No orders yet"** is not covered by an automated test — there is no
component test harness in this project, and adding one is a bigger decision than
this release. It is verified by hand, on the device and in the browser, and both
strings are asserted in the manual checks below.

## What has been verified

| # | Check | How | Result |
|---|---|---|---|
| 1 | Whole Django suite, final run | `python manage.py test` | **1101 tests, OK** — 0 errors, 0 failures, 0 skipped, 34m38s |
| 2 | New backend behaviour | `auth_tokens`, `core.test_pagination`, `crm_api.test_storage`, `crm_api.test_push` | 42 tests, OK |
| 3 | Client renewal logic | `npm test` (node:test, stubbed fetch) | 5 tests, OK |
| 4 | Sign-up over real HTTP returns access + refresh + expiry | `curl` against a running server | Verified |
| 5 | List endpoints answer the paged envelope | `curl /api/fabrics/?page_size=2` | `{count,next,previous,results}` |
| 6 | A refresh token can be spent once | `curl` refresh twice | 200, then 401 |
| 7 | The app builds, installs and runs on Android | `assembleDebug`, `adb install` | Login screen renders |
| 8 | Owner can sign in from the app | Driven through the app's own form | Dashboard loads |
| 9 | Mobile layout on a phone | Bottom nav, mobile header, drawer | Present and correct |
| 10 | Paged requests come from the app | Server log during app sign-in | `?page_size=200` on every list |
| 11 | The hardware back button closes the drawer instead of exiting | `adb shell input keyevent KEYCODE_BACK`, twice | Drawer closed both times |
| 12 | The session survives the app being killed | `am force-stop`, relaunch | Still signed in |
| 13 | Credentials are NOT in WebView storage | `localStorage` read over CDP | Empty — the session is in the Keystore |
| 14 | An expired access token renews silently | Aged the token row, reloaded the app | 2×401 → **one** refresh → both retried → 200, user saw nothing |
| 15 | Release bundle builds with R8 | `./gradlew bundleRelease` | `app-release.aab`, 4.2 MB, unsigned |
| 16 | The platform console renews its own token | Aged the console token, clicked a nav item | Rotated silently, stayed signed in |
| 17 | The web app still works after pagination | Vite dev server, driven through the browser | Sign-in, dashboard, orders, customers, fabrics, tailors, inventory — all render, no console errors |
| 18 | Real rows still reach the web screens | Seeded the boutique, reloaded | Fabrics and staff lists populated through the paged API |
| 19 | Cold start | `adb shell am start -W`, debug build, emulator | 7.7s first launch after install, then 2.6s and 2.0s |

Cold start above is a debug build on an emulator, which is the pessimistic case:
no R8, an unminified bundle, and ART still verifying dex on the first launch. It
is a baseline to compare a release build against on a real device, not a result.

Check 14 is the one worth reading twice: two concurrent requests expired
together, and exactly one refresh went out. A second would have spent an
already-rotated token, which the server correctly treats as theft and answers by
ending every session that user has.

---

## What has NOT been run

| Area | Why it matters |
|---|---|
| **Any real device** | Emulators do not reproduce OEM keyboards, gesture navigation, battery optimisation killing background work, or a real camera |
| **Master, Tailor, Designer on Android** | Each has its own navigation and its own screens; only Owner has been signed in on the device |
| **The full order journey on Android** | Create customer → order → garments → design → measurements → materials → assignment → payment → submit |
| **Camera capture** | The emulator's fake camera is not evidence; needs a device |
| **Push notifications** | Needs a Firebase project; nothing has been delivered end to end |
| **Deep links** | Needs `assetlinks.json` published at boutique.scaleezy.com |
| **Storage persistence across a deploy** | Needs `SUPABASE_SERVICE_KEY` and two deploys (`verify_storage --keep`, then `--read`) |
| **Web regression after the backend changes** | The 1050-test suite passes, but nobody has clicked through the web app since pagination landed |
| **Screen sizes** | Only one emulator profile |

---

## The matrix to fill in

Run each row on a real device, per role. `—` means the role has no such screen.

### Authentication

| Check | Owner | Master | Tailor | Designer |
|---|---|---|---|---|
| Sign in with correct credentials | | | | |
| Sign in with wrong password shows an inline error | | | | |
| Lands on the right screen for the role | | | | |
| Session survives closing and reopening the app | | | | |
| Sign out returns to the login screen | | | | |
| Signing out on one device does not sign out another | | | | |
| An expired access token renews without the user noticing | | | | |
| Password reset email arrives and the link works | | | | |

### Navigation

| Check | Owner | Master | Tailor | Designer |
|---|---|---|---|---|
| Bottom navigation shows only permitted destinations | | | | |
| Drawer shows only permitted destinations | | | | |
| Back closes a bottom sheet | | | | |
| Back closes a modal | | | | |
| Back returns from a detail screen to its list | | | | |
| Back steps the order wizard backwards | | — | — | — |
| Back at step 1 of the wizard asks before leaving | | — | — | — |
| Back on the dashboard leaves the app | | | | |

### Orders

| Check | Owner | Master | Tailor |
|---|---|---|---|
| Create an order for a new customer | | — | — |
| Create an order for an existing customer | | — | — |
| Two garments on one order stay distinct | | | |
| Prices and discount total correctly | | — | — |
| Advance payment and balance are right | | — | — |
| Assign a designer | | | — |
| Assign a tailor to a stage | | | — |
| Move a stage forward | | | |
| Refuse a stage the role may not perform | | | |
| Upload a finished-garment photo | | | — |
| Publish photos to the customer | | | — |
| Invoice shows the right figures | | — | — |
| Order appears on the customer's tracking page | | | |

### Inventory, designs, customers

| Check | Owner | Designer |
|---|---|---|
| Search a customer by name | | — |
| Search a customer by phone | | — |
| Paging past the first 50 customers | | — |
| Add an inventory item | | — |
| Stock deducts when an order consumes it | | — |
| Low stock is flagged | | — |
| Upload a design from the gallery | | |
| Take a design photograph with the camera | | |
| Categorise and save a design | | |
| Delete a design | | |

### Device behaviour

| Check | Result |
|---|---|
| Keyboard does not cover the field being typed into | |
| Long lists scroll smoothly | |
| No horizontal scrolling on any screen | |
| Every button is reachable one-handed | |
| Rotating the device does not lose form data | |
| The app survives being backgrounded for 10 minutes | |
| Airplane mode shows the offline banner | |
| Saving while offline fails visibly, not silently | |
| Coming back online works without a restart | |
| Camera permission denied → the message explains what to do | |
| Camera permission denied twice → the gallery still works | |
| Notification permission denied → the in-app bell still works | |

### Roles and isolation

| Check | Result |
|---|---|
| A tailor's token cannot read another boutique's data | |
| A designer's token is refused on customers, orders and inventory | |
| A tailor sees only their own assigned work | |
| A disabled module's screens are gone AND its API is refused | |
| Deleting a staff member ends their session | |

---

## End-to-end journeys

Run each on a real device, start to finish, without touching the web app.

**Journey 1 — Owner takes an order.** Sign in → dashboard → new customer →
measurements → new order → two garments → design → fabric → price and advance
payment → assign designer and master → submit → the order appears in the list
with the right total.

**Journey 2 — Designer.** Sign in → assigned work → open the request →
photograph a design → categorise → save → the owner sees it in the library.

**Journey 3 — Master.** Sign in → assigned orders → open one → read the
measurements and the approved design → assign a tailor to cutting → advance the
stage.

**Journey 4 — Tailor.** Sign in → my work → open the garment → start → complete
→ upload the finished photograph → the order moves to quality check.

**Journey 5 — Customer (web, not the app).** Open the tracking link on a phone
browser → see the current stage, the money, and the published photographs.

**Journey 6 — Inventory.** Order consumes fabric → stock falls → restore on
cancellation → the movement history reads correctly.

At the end of Journey 1, open the **web** app as the same owner and confirm the
order, the money and the assignments are identical. Web and Android must never
disagree; they are one backend.

---

## Release-gate results (second pass)

Everything below was run after the pagination, order-summary and network fixes
landed. Emulator = Medium_Phone_API_36.1 (Android 16, 1080×2400). Nothing here
is a real-device result.

### The product's own end-to-end journey

`python manage.py smoke_journey --confirm` — the project's existing command,
which provisions a boutique through the real signup endpoint and takes a
two-garment order from there to Delivered over HTTP, through the same
middleware and permission layer a browser uses:

**55/55 passed** after all of the backend changes — staff onboarding,
per-garment pricing, designer assignment, the production floor, inventory
reservation and consumption, quality check, the money and timestamps read back
off the customer's own tracking page, and one boutique's token refused another's
customers.

This is the strongest single piece of evidence that expiring tokens, pagination,
the order-summary endpoint, the status filters and the storage switch did not
change what the product does.

### Roles, driven through the app's own UI on the device

| Role | Signs in | Lands on | Bottom nav | Menu |
|---|---|---|---|---|
| Owner | ✓ | Dashboard | Dashboard, Orders, Customers, Inventory, Menu | full (10 items) |
| Master | ✓ | Assignments | Assignments, Orders, Customers, Menu | My Assignments, Manage Orders, Customers, Design Work, Account, Logout |
| Cutting Master | ✓ | Assignments | Assignments, Account, Menu | My Assignments, Account, Logout |
| Tailor | ✓ | Assignments | Assignments, Account, Menu | My Assignments, Account, Logout |
| Designer | ✓ | Design Work | Assignments, Account, Menu | My Work, Design Studio, Account, Logout |

No role saw a destination it may not use. Invoices, Analytics, Inventory and
Manage Tailors appear for the Owner only.

With work actually assigned to them (three orders given to the master and the
stitching tailor):

| Check | Result |
|---|---|
| Tailor's "My Assignments" lists the assigned orders | ✓ PAGE-057/058/059 |
| The card carries the measurement and garment information | ✓ |
| Master sees the same three as supervisor | ✓ |
| Master changes an order's status from the app | ✓ `PATCH /api/orders/60/update-status/` → 200, then the app refetched the summary and the open-order list |
| The workflow engine refuses a backwards transition | ✓ the status stayed Quality Check and the screen re-read the server rather than showing the value the user picked |

**Still not exercised on a device:** the six-step order wizard end to end, a
designer's upload/edit/delete cycle, garment photography through the camera, and
stage-by-stage production transitions on an order that has stages. The seeded
fixture has no production stages, so there was nothing to advance.

### Authorization, probed at the API rather than through the interface

| Endpoint | Owner | Master | Cutting Master | Tailor | Designer |
|---|---|---|---|---|---|
| `GET /orders/` | 200 (60) | 200 (60) | 200 (0) | 200 (0) | **403** |
| `GET /customers/` | 200 (60) | 200 (60) | 200 (0) | 200 (0) | **403** |
| `GET /inventory/items/` | 200 | **403** | **403** | **403** | **403** |
| `GET /inventory/suppliers/` | 200 | **403** | **403** | **403** | **403** |
| `GET /inventory/reports/cost-per-order/` | 200 | **403** | **403** | **403** | **403** |
| `GET /dashboard/` | 200 | 200 | 200 | 200 | **403** |
| `GET /orders/summary/` | 200 (60) | 200 (60) | 200 (0) | 200 (0) | **403** |
| `GET /activities/activities/` | 200 | 200 | 200 | 200 | **403** |
| `POST /customers/` | 201 | **403** | **403** | **403** | **403** |
| `POST /inventory/suppliers/` | 201 | **403** | **403** | **403** | **403** |
| `POST /tailors/` | 201 | **403** | **403** | **403** | **403** |

The tailors' `200 (0)` is scoping, not emptiness: they have no assigned work in
that boutique, and `visible_orders` answers accordingly.

### Tenant isolation

| Probe | Result |
|---|---|
| Boutique A's token, boutique B's `X-Tenant-ID`, on orders / customers / inventory / team / notifications / designs | **401 on every one** |
| A asking for B's customer by id, in A's own tenant | **404** |
| A asking for a primary key that does not exist in A | **404** |
| A asking for pk 1 in its own tenant | 200 — and it is **A's own order**, not B's. Integer keys are per-schema |

### Pagination

Driven on a boutique seeded with 60 orders, 25 to a page.

| Check | Web | Android |
|---|---|---|
| First page | 25 of 60 | 25 of 60 |
| Next page | 50 of 60 | auto-loaded on scroll |
| Last page | 60 of 60, control disappears | 60 of 60 |
| No duplicate or missing rows across pages | 60 unique ✓ | ✓ |
| Filter: All / Active / Shipped / Delivered | 60 / 44 / 8 / 8 ✓ | — |
| Filter: invoices Paid / Pending | 20 / 40 ✓ (pending includes part-paid) | — |
| Search by client name | 1 of 1, correct row | — |
| Search by order reference | 1 of 1, correct row | — |
| Search with no matches | "No orders found matching the criteria", not "No orders yet" | — |
| Search + filter together | 8 of 8 ✓ | — |
| Sorting | newest first, server-side, stable across pages | ✓ |

**Totals stay whole while the list is partial** — the property that would have
broken silently. With 25 of 60 rows on screen: collected ₹1,16,500, outstanding
₹1,20,500, invoiced ₹2,37,000, all equal to the database over all 60. Analytics
AOV ₹3,950 = 237000/60 exactly, and the status breakdown is a percentage of 60
rather than of the page.

### Session and lifecycle, on the device

| Check | Result |
|---|---|
| Fresh install → first launch → login | ✓ for all five roles |
| Session survives force-stop and relaunch | ✓ |
| Credentials in WebView `localStorage` | **none** — `Object.keys(localStorage)` is `[]` |
| Access token expires mid-session | 401 → **one** refresh → both requests retried → user never sees it |
| Access token expires **while backgrounded** | resumed, tapped Orders: 401 → one refresh → 200 |
| Background (Home) → resume | still signed in, same screen, no reload |
| Rotate to landscape and back | no reload, no lost session, no lost form |
| App update over the top (`install -r`) | session preserved |
| Offline (both radios off) | banner appears; plugin and `navigator.onLine` agree |
| Back online | banner clears within seconds |
| Hardware back with drawer open | closes drawer, twice, deterministic |

### Permissions, on the device

All four runtime permissions show `granted=false` by default, and every role
signs in and works with all of them denied. The notification request fires
**after** sign-in (confirmed in logcat: `PushNotifications.requestPermissions`
immediately after the dashboard loads), never at launch.

### The full business journey, role to role

One realistic order created through the real API as the owner — customer with
measurements, **two garments** with distinct specs, packaging and discount, a
part payment, a master and a tailor assigned — then read back on the device by
each role in turn.

Order `T2B-260831-6272`: total ₹1,56,975, advance ₹20,000, Partially Paid,
15 production stages, status Received.

| Surface | What it shows | Result |
|---|---|---|
| Owner (Android) | searched "Journey" → 1 of 1, reference, both garments, ₹1,56,975, master and tailor named | ✓ every field matches the database |
| Master (Android) | the same order on My Assignments, client name, both garments | ✓ |
| Tailor (Android) | the same order, both garments, the measurement values | ✓ |
| Tailor (Android) — money | **no money anywhere on the card** | ✓ the `isProductionStaff` gate, visible in the UI |
| Customer (public tracking link, no sign-in) | reference, name, both garments, ₹1,56,975, ₹20,000 advance, status | ✓ |

The garment spec (Deep V / princess / elbow) is not on the tailor's summary
card; it is behind the garment itself. Noted rather than filed as a defect.

The order wizard's own validation was exercised on the way: a garment posted
without `blouse_type` was refused with "Blouse Type is required."

### The platform console, after the same changes

The console is a second frontend on the same backend, and two things it uses
changed underneath it: token expiry, and pagination on `LeadViewSet`.

| Check | Result |
|---|---|
| Sign in | ✓ |
| Its access token expires mid-session | ✓ rotated silently, stayed signed in, screen intact |
| Boutiques screen | ✓ (unaffected — `TenantViewSet.list` returns a plain list, not a paged one) |
| Leads screen against the paged shape | ✓ renders rows; the screen already read `data.results \|\| data` |
| Console session kept separate from the boutique's | ✓ separate keys, both present, neither disturbed the other |

### Deep links

A real Android `VIEW` intent, fired with `adb`, for
`https://boutique.scaleezy.com/app/orders/PAGE-006` — an order that is
**Delivered**, and therefore not in the open-order list the workspace loads:

| Step | Result |
|---|---|
| Intent reaches the running app | ✓ (`delivered to currently running top-most instance`) |
| App switches to the Orders tab | ✓ |
| The reference lands in the tab's search box | ✓ `PAGE-006` |
| The list shows that order | ✓ "Showing 1 of 1" |

The routing is proven. What is **not** proven is Android opening these links
without a chooser — that needs `assetlinks.json` published at
boutique.scaleezy.com with the release signing certificate's fingerprint.

### Offline behaviour

| Step | Result |
|---|---|
| Online, Orders tab | 25 of 60 |
| Both radios off | banner: "No connection. Anything you save now will not reach the boutique." |
| A read attempted while offline (switching filter) | **"No connection to the boutique. Check your network and try again."** with a Try again control |
| Raw `Failed to fetch` reaching the screen | **no** — it did before this pass, and now does not |
| Radios back on | banner clears, list restored |

Nothing queues writes and nothing claims a save that did not happen: the banner
says outright that anything saved now will not reach the boutique, and a failed
request fails visibly.

### Deep links, all seven cases

| Case | Result |
|---|---|
| Delivered order, app running | opens Orders, searches the reference, shows it |
| Open/in-progress order, app running | same |
| Invalid reference | "No orders found matching the criteria" — not a crash, not "No orders yet" |
| **Order this role may not see** (Cutting Master, no assignments) | empty state; the API answers `count 0` for that reference under their token — the link cannot bypass authorization |
| App already running | ✓ |
| App backgrounded | ✓ |
| **App closed (cold start)** | ✓ — this needed a fix: `App.getLaunchUrl()`, because on a cold start Android delivers the intent before any JavaScript exists to hear it |

### Screen sizes

One AVD, three display configurations (`wm size` / `wm density`). These are
emulated form factors on a single Android 16 image — **not** three devices, and
not a substitute for real hardware.

| Configuration | CSS viewport | DPR | Horizontal overflow | Bottom nav | Smallest visible button |
|---|---|---|---|---|---|
| 720×1280 @ 320dpi — small budget phone | 360×592 | 2 | none | 4 items | 44px |
| 1080×2400 @ 420dpi — typical phone | 411×914 | 2.6 | none | 5 items (Owner) | 44px |
| 1440×3120 @ 560dpi — large, high density | 411×843 | 3.5 | none | 4 items | 44px |

44 CSS px meets the 44–48dp floor the brief asks for. Landscape was checked
separately by rotating the device: no reload, no lost session.

### Release build

Built with R8, signed with a **throwaway test key** (the real upload key is the
owner's to create and hold), installed on the emulator alongside the debug build.

| Check | Result |
|---|---|
| Installs and launches | ✓ |
| Renders (the classic R8 "blank screen") | ✓ — full login screen, read via `uiautomator dump` |
| Crashes | none |
| Capacitor console logging | **silent** — `loggingBehavior: "debug"` |
| WebView remote debugging | **no socket** — not inspectable |
| `package` | `com.scaleezy.boutique` |
| `versionCode` / `versionName` | 1 / 1.0.0 |
| `minSdk` / `targetSdk` | 24 / 36 |
| `allowBackup` | **false** |
| `debuggable` | absent |
| `usesCleartextTraffic` | absent → cleartext refused |
| `networkSecurityConfig` | absent → the debug-only cleartext allowance did **not** leak into release |
| Secrets in the APK | none found |
| API URL baked in | present and visible — which is why the production build must be made with the production `VITE_API_URL` |

**Not verified on the release build:** a complete role workflow. The release
build refuses cleartext, so it cannot talk to a local development server, and
pointing it at production would mean signing in to real data. It needs a
reachable HTTPS staging backend.
