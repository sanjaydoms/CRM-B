# Boutique CRM on Android

The Android app **is** the boutique workspace. There is no second frontend, no
second API and no business rule expressed twice: `frontend/` is built for the
device and Capacitor wraps it, so a change to an order screen ships to the web
and to the phone from the same file.

What is genuinely native lives in `frontend/src/native/` and nowhere else —
about 400 lines covering the back button, deep links, push registration, the
camera and the encrypted session store. Everything else in the app is unaware it
is running on a phone.

---

## What v1 covers

Staff: **Owner, Master, the seven tailor specialists, and Designer.**

Not in v1, and deliberately: customer accounts, a customer app, and try-on.
Customers reach the product the way they already do — the public tracking link
`/track/<token>/`, which is a server-rendered page and needs no app. Try-on does
not exist anywhere in this product; see the note in `core/modules.py`.

---

## Developer setup

Requirements:

| Tool | Version | Why this one |
|---|---|---|
| Node | 20+ | Vite 8 |
| JDK | **21** | Gradle 8.14 cannot run on JDK 25 (`Unsupported class file major version 69`) |
| Android SDK | platform 36, build-tools 35+ | `compileSdk`/`targetSdk` 36 |

```bash
brew install openjdk@21          # if it is not already there
export JAVA_HOME=/opt/homebrew/opt/openjdk@21
export ANDROID_HOME="$HOME/Library/Android/sdk"
```

`frontend/android/local.properties` must point at the SDK. It is gitignored
because it holds an absolute path from whoever built last:

```
sdk.dir=/Users/you/Library/Android/sdk
```

Then:

```bash
cd frontend
npm install
VITE_API_URL=https://crm-b-sitt.onrender.com/api npm run build:android
npx cap sync android
```

`npm run build:android` refuses to run without `VITE_API_URL`, and refuses a
`localhost` one unless `ALLOW_LOCAL_API=true`. That is not fussiness: the API
address is compiled into the bundle, so an app built without one can only ever
talk to the laptop that built it — and you find out after uploading.

To develop against a local backend, use your machine's LAN address, not
localhost — inside the app, localhost is the phone:

```bash
VITE_API_URL=http://192.168.1.20:8000/api ALLOW_LOCAL_API=true npm run build:android
```

...and add that origin to `CORS_ALLOWED_ORIGINS` on the Django side.

Two more things are needed to talk to a plain-HTTP dev server, and only one of
them is already done for you:

* **Cleartext** is permitted for `10.0.2.2` and `localhost` in debug builds only
  — `android/app/src/debug/res/xml/network_security_config.xml`. Release builds
  refuse it. `10.0.2.2` is the emulator's alias for the machine running it.
* **Mixed content** must be allowed while you do this, because the page itself
  is served from `https://localhost` by Capacitor and an `http://` API call from
  it is mixed content. Set `"allowMixedContent": true` in
  `capacitor.config.json`, and **set it back to false before building a
  release**. It is committed as `false` deliberately: production is https-only
  and this switch has no business being on there.

---

## The three environments

Nothing in the Android project names an environment. The environment IS the
`VITE_API_URL` the bundle was built with, plus the version numbers:

```bash
# development — against a machine on the same wifi
VITE_API_URL=http://192.168.1.20:8000/api ALLOW_LOCAL_API=true npm run build:android

# staging
VITE_API_URL=https://staging.example.com/api npm run build:android

# production
VITE_API_URL=https://crm-b-sitt.onrender.com/api npm run build:android
```

A debug build installs as `com.scaleezy.boutique.debug` with a `-debug` version
suffix, so it sits alongside a release build on the same phone and can never be
mistaken for it.

---

## Building

```bash
cd frontend/android
./gradlew assembleDebug     # app/build/outputs/apk/debug/app-debug.apk
./gradlew bundleRelease     # app/build/outputs/bundle/release/app-release.aab
```

`bundleRelease` runs R8. The keep rules in `app/proguard-rules.pro` are
load-bearing: every Capacitor plugin method is reached by reflection from
JavaScript, so without them R8 removes code nothing appears to call and the app
builds, installs, and shows a blank screen.

Version numbers come from the environment, defaulting to the literals in
`app/build.gradle`:

```bash
ANDROID_VERSION_CODE=2 ANDROID_VERSION_NAME=1.0.1 ./gradlew bundleRelease
```

Play refuses an upload whose `versionCode` it has seen before. It only ever goes
up.

---

## Signing

**The upload key is the app's identity on Google Play, permanently.** Lose it
and no update to `com.scaleezy.boutique` can ever be published again — not with
a new key, not with support's help. Commit it and anyone who can read this
repository can publish an update as this app.

Generate it once, and keep it somewhere that is backed up and is not this
repository:

```bash
keytool -genkeypair -v \
  -keystore boutique-upload.jks \
  -keyalg RSA -keysize 2048 -validity 10000 \
  -alias boutique-upload
```

Then either write `frontend/android/keystore.properties` (gitignored):

```
storeFile=/absolute/path/to/boutique-upload.jks
storePassword=...
keyAlias=boutique-upload
keyPassword=...
```

or set `ANDROID_KEYSTORE_FILE`, `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`
and `ANDROID_KEY_PASSWORD` in the environment, which is what CI should do.

With neither, `bundleRelease` still succeeds and produces an **unsigned** bundle
— useful for checking that the build works, and rejected by Play, which is the
right way round.

**What the owner must retain, securely and forever:** the `.jks` file, its store
password, the key alias, and the key password. Also enable Play App Signing when
the app is first created; Google then holds the signing key and this one becomes
the upload key, which is the only arrangement where losing it is recoverable.

---

## Push notifications

The backend writes every staff notification into `Notification` already, and
`crm_api/push.py` listens for those rows and pushes them. Nothing else has to
remember to.

To turn delivery on:

1. Create a Firebase project and add an Android app with package name
   `com.scaleezy.boutique`.
2. Put `google-services.json` at `frontend/android/app/google-services.json`
   (gitignored). The Gradle plugin applies itself only when that file is
   present, so the build works with and without it.
3. Create a service account, download its JSON key, and on the server set:

   ```
   PUSH_BACKEND=crm_api.push_fcm.send
   FCM_PROJECT_ID=<firebase project id>
   GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
   ```

4. `pip install google-auth` on the server. It is imported lazily, so a
   deployment that does not use push does not need it.

`FCM_CHANNEL_ID` (server) and `default_notification_channel_id` (Android
`strings.xml`) must be the same string. If they differ, Android files each
notification under a channel that does not exist and drops it silently.

Until step 3 is done, notifications are written, logged, and delivered nowhere.
The bell inside the app works throughout.

---

## Deep links

`https://boutique.scaleezy.com/app/...` opens the app, when Android has verified
the link. To make that verification succeed, publish at

`https://boutique.scaleezy.com/.well-known/assetlinks.json`:

```json
[{
  "relation": ["delegate_permission/common.handle_all_urls"],
  "target": {
    "namespace": "android_app",
    "package_name": "com.scaleezy.boutique",
    "sha256_cert_fingerprints": ["<SHA-256 of the signing certificate>"]
  }
}]
```

With Play App Signing, that fingerprint comes from the Play Console (App
integrity → App signing), **not** from your upload key.

Until the file is published the links still work — they open in the browser,
which is the correct fallback and the reason the web app must keep serving those
routes.

`/track/` links are deliberately **not** claimed. They are for customers, who do
not have this app.

---

## Permissions

| Permission | Asked when | If refused |
|---|---|---|
| `INTERNET` | never asked; install-time | — |
| `POST_NOTIFICATIONS` | after sign-in | the bell inside the app still works |
| `CAMERA` | when someone taps "Take photo" | the message says how to re-enable it, and the gallery button still works |
| `READ_MEDIA_IMAGES` | when choosing an existing photo | the system picker handles its own permission |

Notification permission is requested **after sign-in**, never at first launch.
Android 13 gives one chance at that dialog, and a refusal is close to permanent
— the only way back is the OS settings screen. Asked after someone has signed in
to their own boutique, the request has a visible reason behind it.

Nothing else is requested. No location, no contacts, no storage write.

---

## What the app stores on the device

| What | Where | Why there |
|---|---|---|
| Access + refresh token | Android Keystore, via `capacitor-secure-storage-plugin` | the refresh token is long-lived; it should not sit in the WebView's own storage |
| Nothing else | — | every screen reads from the API |

`android:allowBackup="false"` and `res/xml/data_extraction_rules.xml` keep all of
it out of cloud backups and device transfers. A restored backup would otherwise
put one boutique's session and cached data onto whatever device signed in next.

---

## The order book, and why it is paged

`GET /api/orders/` answers one page. That is not a detail of the Android build;
it is the shape the product needs, and it took three changes to get there
without breaking anything:

* **The list is paged and filtered by the server.** The Orders tab's four
  buttons are `?status_group=all|active|shipped|delivered`, the Invoices tab's
  three are `?payment=paid|pending`, and both search boxes are `?search=`.
  Filtering in the browser stopped being possible the moment the browser stopped
  holding every order -- a filter applied to page one is not a filter.
* **The totals moved to the server.** `GET /api/orders/summary/` returns
  collected, outstanding, invoiced, average order value, the status breakdown and
  the garment / neckline / sleeve distributions, computed over the whole book and
  scoped to the caller exactly like the list is. The Invoices header and the
  Analytics panel read it. Without this, paging the list would have quietly
  turned a boutique's revenue into the revenue of twenty-five orders.
* **The workspace loads open work, not everything.** Signing in fetches
  `?status_group=open` -- everything except Delivered -- which is what the
  assignment panels and the production floor table are about. A boutique's
  finished orders are the part that grows for as long as it stays in business.

An order row is roughly 7KB with its production stages and garment specs, and
the stages are 60% of that. They are not droppable: the tailor's assignment card
renders the timeline and filters on `stages[].assigned_to`. So the fix had to be
fewer rows, not lighter ones.

The two paged lists load more as they are scrolled (an IntersectionObserver
sentinel 400px before the end) and also carry a **Load more** button, which is
what a keyboard reaches and what works where the observer does not.

**What still fetches a whole collection**, and why that is currently fine:
staff, fabrics, appointments, garment templates, the design library, inventory
items and the customer directory. Measured, a customer row is 1.3KB and an
inventory row 400 bytes, against an order's 7KB — and staff, fabrics and
templates are bounded by what a boutique actually has.

**The customer directory is the next one to page**, and the recipe is now the
one above rather than a design problem: add `/api/customers/summary/` for the
segment counts the dashboard shows, move the directory's search and type filter
onto the server (`?search=` already exists), then give it the same paged state
and sentinel the Orders tab has. The wizard's customer picker becomes a server
search at the same time, which is what it should have been anyway.

## Troubleshooting

**`Unsupported class file major version 69`** — Gradle is running on JDK 25. Set
`JAVA_HOME` to JDK 21.

**`SDK location not found`** — write `frontend/android/local.properties`, or
export `ANDROID_HOME`.

**Blank white screen after a release build** — R8 stripped a bridge class. Check
`app/proguard-rules.pro` still has the Capacitor keep rules, and read
`app/build/outputs/mapping/release/missing_rules.txt`.

**The app talks to the wrong backend** — it was built with a different
`VITE_API_URL`. Rebuild and `npx cap sync android`; the bundle is compiled, not
configured at runtime.

**Web assets look stale** — `npm run build:android` writes `dist-android/`, and
`npx cap sync android` copies it into the Android project. Running one without
the other packages the previous build.

**Push arrives on one device but not another** — each installation registers its
own token (`POST /api/devices/`). Check `DeviceToken` rows for the user, and that
`is_active` is true; FCM's `UNREGISTERED` responses deactivate them.
