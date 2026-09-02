# Play Store release: content, declarations and the checklist

Everything Google Play asks for, drafted. What is **not** here is anything only
the account holder can do — creating the app in the console, holding the upload
key, and pressing publish.

---

## Release ordering: the backend goes first

Checked against the live production API today:

```
GET  https://crm-b-sitt.onrender.com/api/auth/me/       -> 401   (up, HTTPS)
POST https://crm-b-sitt.onrender.com/api/auth/refresh/  -> 404   (NOT DEPLOYED)
```

**Production is still running the old code.** The AAB in this repository is
built against that address, and the refresh endpoint it needs does not exist
there yet.

The app degrades rather than breaks — an old backend's login response carries no
`refresh` and no `expires_in`, so the client stores just the token and behaves
exactly as it did before, and the old token never expires anyway. But none of
the work in this release is actually live until the backend is deployed.

**Deploy the backend first, then publish the app.** Not the other way round.

Also worth knowing: the first request after an idle period took **49 seconds**
(Render's free tier sleeping). A phone opening the app to a 49-second wait reads
as broken. That is a hosting-plan decision, not a code one.

## Where this stands

The AAB is built and unsigned. The **upload key does not exist yet**, and it
should not be created by anyone but the account holder — see Signing in
[android.md](android.md). A release APK signed with a deliberately throwaway
test key was installed and exercised to prove the R8 build renders; that key has
nothing to do with the real one and must never be used for a real upload.

## Two decisions that cannot be undone

| Decision | Current value | Why it is permanent |
|---|---|---|
| Application ID | `com.scaleezy.boutique` | Play identifies the app by this string forever. Changing it later means a new listing with zero installs and zero reviews. |
| Upload key | not yet generated | See "Signing" in [android.md](android.md). Enable **Play App Signing** when the app is created — it is the only arrangement in which losing the key is survivable. |

Confirm both before the first upload. Everything else on this page can be edited
afterwards.

---

## Store listing

**App name** (30 char limit)

```
Boutique CRM by Scaleezy
```

**Short description** (80 char limit)

```
Run your boutique: orders, measurements, tailors, designs and stock, in one app.
```

**Full description** (4000 char limit)

```
Boutique CRM is the workspace that runs a custom-tailoring boutique — from the
first measurement to the finished garment in the customer's hands.

Built for boutiques that make clothes to order, it replaces the notebook, the
WhatsApp thread and the spreadsheet with one place your whole team works from.

FOR THE BOUTIQUE OWNER
• Every customer, with their measurements, style preferences and full order
  history
• Custom orders with per-garment pricing, fabric, design and delivery details
• Advance payments and balances, with invoices your customer can see
• Fabric and trim stock that reserves itself against an order and deducts as it
  is used
• Your design library — uploads, boutique catalogue, saved references
• Your team: master tailors, specialists and designers, and who is working on
  what
• A dashboard of revenue, orders in progress, and what needs attention today

FOR MASTERS AND TAILORS
• The work assigned to you, on your phone, on the shop floor
• Measurements and the approved design for the garment in your hands
• One tap to move a garment through cutting, stitching, finishing and QC
• Photograph the finished garment and hand it on

FOR DESIGNERS
• The designs asked of you, and what has been approved
• Upload from the camera or the gallery, categorise by garment type and occasion
• Collections, boards and the boutique's own catalogue

FOR YOUR CUSTOMERS
• A tracking link that shows them where their order has reached, with no app to
  install and no account to create
• Order updates sent from your own WhatsApp, with the details already filled in

Boutique CRM keeps every boutique's data in its own separate database schema.
Your customers, your orders and your prices are visible to your boutique and to
nobody else.

A Scaleezy account is required. Sign up at boutique.scaleezy.com.
```

**Category:** Business
**Tags:** Business management, Inventory, CRM
**Contact:** support email + `https://www.scaleezy.com` (both required)
**Privacy policy URL:** required before publishing — see below.

---

## Screenshots

Play requires **at least 2** phone screenshots; 4–8 is the practical minimum for
a listing that reads as finished. 16:9 or 9:16, minimum 320px on the short edge,
maximum 3840px on the long edge.

Take them from a release build signed in as an owner, on a boutique with real-
looking data (the seeded demo boutique is fine — do **not** use a real
customer's name, number or photograph):

1. Owner dashboard — revenue, orders in progress
2. Order detail — garments, pricing, production stages
3. Customer with measurements
4. The design library
5. Inventory with stock levels
6. A tailor's assignment list

The emulator's own screenshot tool returns black frames on some GPU
configurations; capture from the WebView instead, or use a real device.

A **feature graphic** (1024×500 PNG or JPEG, no alpha) is required for the
listing to be publishable.

---

## Data safety declaration

This must match what the app actually does. What follows is drawn from the code,
not from intent.

| Data type | Collected | Shared | Purpose | Optional? |
|---|---|---|---|---|
| Name (staff) | Yes | No | Account management, app functionality | Required |
| Email address (staff) | Yes | No | Account management, sign-in, password reset | Required |
| Name, phone, address (customers of the boutique) | Yes | No | App functionality — the boutique's own records | Required |
| Photos (garments, designs, customer profile) | Yes | No | App functionality | Optional — only what a user uploads |
| Purchase history (orders, payments recorded by the boutique) | Yes | No | App functionality | Required |
| Device identifier (FCM registration token) | Yes, **once push is enabled** | No | App functionality — delivering notifications to this installation | Optional; only after the notification permission is granted |
| App interactions / crash logs | **No** | No | — | — |
| Location, contacts, calendar, files, messages, health | **No** | No | — | — |

Answers to the console's other questions:

* **Is all data encrypted in transit?** Yes — the API is HTTPS, and cleartext is
  refused in release builds.
* **Can users request data deletion?** Yes. Staff accounts are deleted by the
  boutique owner from the team screen; a boutique's own deletion request goes to
  the support address, which removes its entire database schema. **Play also
  requires a web-accessible deletion request URL** — that page needs to exist
  before submission.
* **Is any data shared with third parties?** No. Data reaches Supabase (database
  and file storage) and the application host as processors, not as recipients —
  Play's declaration is about disclosure to other companies for their own use,
  which does not happen here.

**No analytics and no crash reporting are integrated.** The declaration above
says so. If Firebase Analytics or Crashlytics is added later, this table changes
and the listing must be updated in the same release — a Data safety form that
does not match the app is a policy violation, not a paperwork error.

---

## Content rating

Complete the IARC questionnaire in the console. For this app the answers are all
"no" — no violence, no sexual content, no gambling, no user-generated content
shared publicly (uploads are visible only within the boutique that made them),
no unrestricted internet browsing. Expected outcome: **Everyone / PEGI 3**.

**Target audience:** 18+. This is a business tool used by staff; it is not
directed at children, which keeps it out of the Families policy programme.

---

## App access

The whole app is behind a sign-in, so Play's reviewer cannot see anything
without credentials. Provide them under **App access → All functionality is
restricted**:

* A demo boutique account (owner role) on the production backend, seeded with
  demonstration data and no real customers.
* Any instructions the reviewer needs: sign in with the email and password
  given; no OTP, no second factor.

A reviewer who cannot get in rejects the submission. This is the single most
common avoidable rejection for a B2B app.

---

## Permissions declaration

Eight permissions in the merged manifest — four declared by the app, four added
by plugins — and **none of them is in Play's sensitive list** (no location, no
SMS, no call log, no `QUERY_ALL_PACKAGES`, no `MANAGE_EXTERNAL_STORAGE`), so no
declaration form is required. If asked in review:

* `CAMERA` — photographing finished garments and design references.
* `READ_MEDIA_IMAGES` / `READ_MEDIA_VISUAL_USER_SELECTED` — choosing an existing
  photograph to attach to an order or a design.
* `POST_NOTIFICATIONS` — order and assignment notifications to the staff member.
* `INTERNET` / `ACCESS_NETWORK_STATE` — the app is a client of the boutique's own
  server, and tells the user when it cannot reach it.
* `WAKE_LOCK` / `com.google.android.c2dm.permission.RECEIVE` — Firebase
  Messaging, for the push notifications above.

The full list, read off a running device, is in
[android-security.md](android-security.md).

---

## Release checklist

Build and verification:

- [x] `VITE_API_URL` is the production API, and the built bundle contains it —
      verified: 2 occurrences of `crm-b-sitt.onrender.com/api`, 0 of any
      development address
- [x] The AAB builds with R8 and is **unsigned**, which is what a handover build
      should be: `app/build/outputs/bundle/release/app-release.aab`, 4.2 MB
- [x] A release APK signed with a throwaway key installs, launches and renders
      on Android — the R8 keep rules hold
- [x] The release manifest carries `allowBackup=false`, no `debuggable`, no
      `usesCleartextTraffic`, and none of the debug-only network config
- [ ] `ANDROID_VERSION_CODE` is higher than any previously uploaded
- [ ] `capacitor.config.json` has `allowMixedContent: false`
- [ ] `./gradlew bundleRelease` succeeds and the bundle is **signed**
- [ ] The release build installs on a real device and signs in
- [ ] Owner, Master, Tailor and Designer each sign in and reach their own screen
- [ ] An order can be created end to end
- [ ] A photograph can be taken and uploaded, and appears afterwards
- [ ] The back button closes sheets and screens without leaving the app
- [ ] Killing and reopening the app keeps the user signed in
- [ ] Sign-out leaves nothing behind (sign in again is required)

Backend, before the app points at it:

- [ ] `SUPABASE_SERVICE_KEY` is set, and `python manage.py verify_storage` passes
- [ ] The persistence test has been run across two deploys (`--keep`, then
      `--read`)
- [ ] `DJANGO_SECRET_KEY`, `DB_*` and `DB_SSLMODE=require` are set
- [ ] `python manage.py smoke_journey --confirm` passes against staging

Push, if it is being enabled in this release:

- [ ] `google-services.json` is in place for the build
- [ ] `PUSH_BACKEND`, `FCM_PROJECT_ID` and `GOOGLE_APPLICATION_CREDENTIALS` are
      set on the server, and `google-auth` is installed
- [ ] `FCM_CHANNEL_ID` matches `default_notification_channel_id`
- [ ] A test notification arrives with the app open, backgrounded, and closed

Console:

- [ ] Play App Signing enabled
- [ ] Listing text, icon, feature graphic and screenshots uploaded
- [ ] Privacy policy URL live
- [ ] Data safety form matches the table above
- [ ] Content rating questionnaire completed
- [ ] App access credentials provided for the reviewer
- [ ] Uploaded to **internal testing** first, and installed from Play by someone
      who did not build it
- [ ] Closed testing if the boutique's own staff are to try it before release
- [ ] Staged rollout, then watch crashes and ANRs in the console

---

## What is deliberately not in this release

* **Customer accounts and a customer app.** Customers use the public tracking
  link, which needs no app.
* **Try-on.** It does not exist in the product on any platform.
* **iOS.** The Capacitor project can add it, but nothing here has been built or
  tested for it.

---

## Media storage and push: the exact configuration to supply

Everything else in this release is done. These two need something only the
account holder can provide, and the code is waiting for it.

### Production media storage — BLOCKED

**What is missing:** the Supabase **service-role** key.

**Proven, so you know exactly where the boundary is:** an upload to the real
bucket with the publishable key returns
`new row violates row-level security policy`. The driver itself was run end to
end over real HTTP against a stand-in of the same API — write, authenticated
read, anonymous public read, delete, and the two-deploy persistence flow — all
pass. Only the credential is absent.

**What to do:**

1. Supabase dashboard → Project settings → API → copy the **service_role** key.
   It is not the `sb_publishable_...` one already in `.env`.
2. Set it on the server only — Render → Environment:

   ```
   SUPABASE_SERVICE_KEY=<service role key>
   ```

   Never in a `VITE_` variable, never in the Android project, never in a
   response body. `settings.py` switches to object storage the moment it is
   present, and stays on the local disk while it is not.
3. Deploy, then run the real persistence test:

   ```bash
   python manage.py verify_storage --keep --name release-check.txt   # deploy N
   python manage.py verify_storage --read release-check.txt          # deploy N+1
   ```

   The second command must be run **after a later deploy**. That is the whole
   point: on the day of the deploy, a disk and object storage behave identically.

Until step 3 passes on the real bucket, the honest status is:

```
Production media storage: BLOCKED
```

### Push notifications — WIRED, NOT PRODUCTION VERIFIED

**What is missing:** a Firebase project.

**What exists:** device registration, token storage, per-role targeting,
deep-link payloads, invalid-token cleanup, and the FCM HTTP v1 transport. The
permission request fires after sign-in — confirmed in logcat on a device. What
has never happened is a notification arriving on a phone.

**What to do:**

1. Firebase console → create a project → add an **Android** app with package
   name `com.scaleezy.boutique` (exactly; it must match the manifest, and it
   cannot be changed after publishing).
2. Download `google-services.json` → `frontend/android/app/google-services.json`
   (gitignored; the Gradle plugin applies itself only when it is present).
3. Project settings → Service accounts → generate a private key. On the server:

   ```
   PUSH_BACKEND=crm_api.push_fcm.send
   FCM_PROJECT_ID=<firebase project id>
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
   ```

   and `pip install google-auth`.
4. Confirm `FCM_CHANNEL_ID` matches `default_notification_channel_id` in
   `strings.xml` — both are `boutique_orders` today. If they diverge, Android
   drops every notification without showing anything.
5. Then verify, on a physical device: sign in (a `DeviceToken` row appears),
   trigger a real business event, confirm the notification arrives, tap it and
   confirm it opens that order, and repeat with the app foregrounded,
   backgrounded and force-stopped.

Until step 5 passes:

```
FCM code:         IMPLEMENTED
Firebase:         NOT CONFIGURED
Physical delivery: NOT VERIFIED
```
