# Security and privacy review — Android v1

Written against the code, not against intent. Where something is a known
weakness it is written down as one rather than left out.

---

## Authentication

**What changed.** The access token was permanent. Anyone holding one held the
boutique until a password reset, and this release puts that token on phones —
devices that get backed up, handed over, sold and lost.

Now:

| | Before | Now |
|---|---|---|
| Access token | never expired | `ACCESS_TOKEN_TTL`, default 1 hour |
| Renewal | — | single-use refresh token, rotated on every exchange |
| Replay of a spent refresh token | — | revokes **every** session that user holds |
| Sign-out | deleted the access token only | revokes both halves |
| Password reset | deleted the access token only | revokes both halves |
| Sign-in after expiry | returned the old, dead token | issues a fresh one |

The scheme is unchanged — same `Authorization: Token <key>` header, same model,
same tenant-scoped table — so nothing else in the product had to be rewritten to
get expiry. A refusal carries `{"code": "token_expired"}`, which is what lets a
client tell "renew and retry" from "sign in again"; an ambiguous 401 can only
safely be read as the latter, which would throw people back to the login screen
several times a day.

**Storage on the device.** The session is held in the Android Keystore via
`capacitor-secure-storage-plugin`, and in memory for the life of the page. The
WebView's `localStorage` was verified **empty** on a running device. Backups are
off (`allowBackup="false"` plus `data_extraction_rules.xml`), so neither the
session nor any cached boutique data can be copied to a Google account or
transferred to another handset.

**Still true, and worth knowing.** DRF's token is keyed on the user, so there is
one access token per person and every issue — a sign-in *or* a refresh —
replaces it. Two devices belonging to the same person evict each other's access
token, though not each other's session: refresh tokens are per-issue, so each
device holds its own and simply renews when it finds its access token gone. The
cost is one extra round trip per device per burst; the client's single-flight
refresh keeps it to one. Verified with a phone and a browser signed in as the
same owner simultaneously.

Extending the existing token instead of replacing it would be quieter and
materially weaker — a stolen access token would live as long as the real user
kept working. The clean fix, when staff need two devices without the extra
round trip, is a per-session access token of our own rather than DRF's.

---

## Authorization and tenant isolation

Unchanged by this work, and deliberately so: the Android app is a client of the
same API, with the same permission classes on the same viewsets. Nothing was
added that decides what a role may do on the device.

* `RolePermission` remains the default for every business endpoint.
* A designer is refused customers, orders, inventory and settings by the API,
  not by a hidden menu item.
* Tenant resolution is unchanged (`X-Tenant-ID`, checked against the registry
  every request, with `is_active` read from the database rather than a cache).
* The refresh endpoint is tenant-scoped by that same header: a refresh token
  from one boutique is simply not present in another boutique's schema, so it
  cannot be spent there.
* The platform console keeps its own separate refresh door, pinned to the public
  schema. `superadmin/test_api_security.py` still walks the URLconf and asserts
  every console route declares `IsPlatformAdmin`; the new refresh route is
  listed as public alongside login, for the same reason login is.

**Two new endpoints, and what they can reach.** `POST/DELETE /api/devices/` is
`IsAuthenticated` rather than `RolePermission`, because a designer must be able
to register the phone they are holding. A device is always bound to
`request.user` — never to a user id in the request body — and deleting someone
else's token is answered 204 without doing anything, so the endpoint cannot be
used to discover whether a guessed token exists.

---

## Uploads and file storage

**Fixed in code, not yet in production:** uploads went to the local filesystem
on a host with an ephemeral disk, so every photograph uploaded since the last
deploy was destroyed by the next one. They now go to Supabase Storage when
`SUPABASE_SERVICE_KEY` is set — and that variable is **not set anywhere yet**,
so a deployment made today still writes to the disk.

**The blocker, confirmed rather than assumed.** An upload attempted against the
real bucket with the publishable key comes back:

```
400 {"statusCode":"403","error":"Unauthorized",
     "message":"new row violates row-level security policy","code":"AccessDenied"}
```

Nothing was written. The credential is the only missing piece.

**What has been proven without it.** The driver was run end to end over real
HTTP against a stand-in that speaks the same storage API: Django selected
`SupabaseStorage`, wrote an object, read it back through the authenticated
endpoint, fetched it anonymously from the public URL, and deleted it. The
two-deploy persistence flow (`verify_storage --keep`, then `--read` from a fresh
process) works. And with only the publishable key, Django correctly does **not**
switch to object storage — it stays on the disk and says so, rather than
switching and failing on the first upload.

**The credential.** `SUPABASE_KEY` is the publishable key and can only read; the
service key is what writes. It is read from the environment on the server, is
never sent to a client, never appears in a `VITE_` variable, and is not in this
repository. The Android bundle contains no Supabase credential of any kind — it
uploads through Django, as the web app does.

**Read access is public, and that is a deliberate, stated exposure.** The
`boutique-crm` bucket is public, so `url()` returns an address any browser can
fetch without signing in. Object paths carry UUIDs, so they cannot be guessed or
enumerated — but a leaked URL is a readable photograph. This is not a regression:
`/media/` has always been served with no authentication at all. Making it private
means bucket policy plus signed URLs here, and signed URLs cost one API round
trip per image per render, which is why they are not the default. **If customer
photographs are considered sensitive, this is the decision to revisit.**

---

## Transport

* Release builds refuse cleartext. `usesCleartextTraffic` is not set, and
  `allowMixedContent` is `false`.
* Cleartext is permitted **only** for `10.0.2.2` and `localhost`, **only** in
  debug builds, through a `src/debug` network security config that is never
  merged into a release.
* The API address is compiled into the bundle. `npm run build:android` refuses to
  build without `VITE_API_URL` and refuses a localhost one unless explicitly
  overridden, so a release cannot silently ship pointing at a laptop.

---

## Deployment checklist findings

`manage.py check --deploy` reported five warnings. Two are now fixed, two are
left to the operator with reasons, and one was the placeholder key used to run
the check:

| Warning | State |
|---|---|
| `SESSION_COOKIE_SECURE` not set | **Fixed** — on outside DEBUG |
| `CSRF_COOKIE_SECURE` not set | **Fixed** — on outside DEBUG |
| `SECURE_SSL_REDIRECT` not set | **Left off.** Redirecting in Django duplicates what the proxy already does and produces a redirect loop when the forwarded-proto header is not what settings assume |
| `SECURE_HSTS_SECONDS` not set | **Left off.** HSTS tells every browser to refuse plain HTTP for the domain and cannot be withdrawn within the max-age. It is a decision about a domain, taken once, knowingly |

Both cookies govern the Django admin only — the API is token-based and sets no
cookie — but the admin session is a platform-administrator credential.

## Secrets

Nothing secret is in the Android app. What it contains: the API base URL, the
app id, and its own code.

Not present, and gitignored so they stay that way: the upload keystore,
`keystore.properties`, `google-services.json`, `local.properties`.

`google-services.json` is worth a sentence because it is often mistaken for a
secret: it identifies the Firebase project and is designed to ship inside apps.
The service-account JSON that authorises *sending* is a real secret and lives on
the server only.

---

## Permissions

Read off the **merged manifest on a running device**
(`adb shell dumpsys package`), not off the source — plugins add permissions of
their own, and the list that matters is the one Play will show.

Four are declared by this app:

| Permission | Used by | Asked | Refusal |
|---|---|---|---|
| `INTERNET` | the whole app | install time | n/a |
| `POST_NOTIFICATIONS` | order and assignment pushes | after sign-in | the in-app bell still works |
| `CAMERA` | photographing garments and designs | at the moment "Take photo" is tapped | a message naming the settings screen; the gallery still works |
| `READ_MEDIA_IMAGES` | choosing an existing photograph | by the system picker | the system picker handles it |

Four more are merged in by the plugins. None prompts the user, and none is in
Play's sensitive list:

| Permission | From | What it is |
|---|---|---|
| `ACCESS_NETWORK_STATE` | @capacitor/network | reading whether there is a connection — the offline banner |
| `WAKE_LOCK` | @capacitor/push-notifications (Firebase) | waking to handle an incoming push |
| `com.google.android.c2dm.permission.RECEIVE` | same | receiving the push itself |
| `READ_MEDIA_VISUAL_USER_SELECTED` | @capacitor/camera | Android 14's "selected photos only" access |

`READ_EXTERNAL_STORAGE` is declared with `maxSdkVersion="32"` and correctly does
**not** appear on a modern device.

Not requested anywhere: location, contacts, calendar, microphone, storage
write, SMS, call log, `QUERY_ALL_PACKAGES`.

**Verified on the device:** with all four runtime permissions showing
`granted=false`, every role signs in and uses the app. Nothing is gated behind a
permission the user has not given.

Notification permission is asked **after sign-in**, never at first launch:
Android 13 gives exactly one chance at that dialog, and a refusal is close to
permanent.

---

## Logging

* The upload driver logs the storage response text at ERROR and raises a
  message that does **not** contain it — bucket policy detail can appear in that
  response, and the raised message reaches an API caller.
* Login already logs exceptions and returns a generic sentence, for the same
  reason.
* Push logs a truncated token prefix, never the whole token.
* No credential, password or key is logged anywhere added here.
* Release builds keep `SourceFile` and `LineNumberTable` for readable crash
  traces; an unreadable crash report is the same as no crash report.

---

## What a privacy policy has to cover

Required by Play before publishing, and it must match the Data safety
declaration in [android-release.md](android-release.md).

**Collected:** staff names and email addresses; the boutique's own customer
records (name, phone, address, measurements, preferences); photographs uploaded
by staff; orders, prices and payments recorded by the boutique; a device
notification token per installation.

**Why:** to provide the product. There is no advertising, no profiling and no
sale of data.

**Where it is stored:** a PostgreSQL database and an object storage bucket, both
hosted by Supabase in `ap-southeast-1`; the application server. Each boutique's
records live in its own database schema.

**Who can access it:** the boutique's own staff, according to their role;
platform administrators through the console, which writes an audit entry for
every action taken.

**Retention and deletion:** records persist until the boutique deletes them. A
boutique's own deletion request removes its entire schema. Play also requires a
web-accessible account deletion request page, and **that page does not exist
yet** — it is a blocker for submission, not a nice-to-have.

**Not collected:** location, contacts, biometrics, health, browsing history. No
analytics or crash reporting is integrated.

---

## Final static scan

Run across the whole tree at the end of the release pass:

| Looked for | Found |
|---|---|
| Service-role keys, private keys, `-----BEGIN` blocks | **none** outside the gitignored `.env` |
| Development API addresses in anything that ships | **none** — the only literals are the `http://localhost:8000/api` *fallback default* in the three API clients, and the Android build refuses to run without an explicit `VITE_API_URL` |
| Development addresses inside the production AAB | **none** — `10.0.2.2` and `localhost:8000` absent; `https://crm-b-sitt.onrender.com/api` present twice |
| Secrets inside the production AAB | **none** |
| Token or password logging | **none** — the only token-adjacent log line counts rejected device tokens (`"deactivated %s device tokens FCM rejected"`) and never prints one |

## Open items before release

1. **Real-device testing.** Everything native here was verified on an emulator.
2. **The account deletion page**, and the privacy policy URL to go with it.
3. **`SUPABASE_SERVICE_KEY` in production**, plus the two-deploy persistence
   test. Until then uploads are still on an ephemeral disk.
4. **Decide on public read access to uploaded photographs** (above).
5. **Per-session access tokens**, if staff need to be signed in on two devices.
