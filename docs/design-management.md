
A design repository the boutique can actually run at scale: thousands of designs,
several designers, and three audiences who need different views of the same rows.

Written to be implemented in slices, each of which works end to end. Nothing here
invents a taxonomy the product already has — §2 is the load-bearing decision.

---


Roughly two thirds of this module is built. The gap is narrower than it looks.

| Exists | Where | Covers |
|---|---|---|
| `DesignAsset` | `apps/design_studio` | The boutique's own library: uploads, favourites, Pinterest/Google imports |
| `DesignBoard` / `DesignBoardItem` | `apps/design_studio` | Per-customer shortlist, approval, link to the order |
| `BoutiqueDesign` | `crm_api` | The seeded catalogue, admin-managed |
| `DesignPreference` | `crm_api` | Per-customer references and the approved image |
| `/api/design-studio/` | `assets/`, `boards/`, `context/`, `discover/` | CRUD, discovery, board approval |

`DesignAsset` already carries most of the proposed `Design` table:

```
source, external_id, title, image_url, source_url, designer(CharField),
garment_type, occasion, attributes(JSON), tags(JSON), colour_palette,
estimated_price, popularity, is_favourite, created_by, created_at, updated_at
```

**The customer selection flow is done.** `DesignBoard` is the shortlist, it has
`status` (DRAFT → SHORTLISTED → APPROVED), `approved_by`, `approved_at`, and a
`OneToOne` to the order. The wizard already builds one in step 3 and attaches it
on submit.

What is genuinely missing: **Designer as an entity** (today a free-text string),
**Collections**, an **upload approval queue**, **portfolios**, and the
**dashboard analytics**.

---


**Designs are tagged with garment-template vocabulary. The module does not mint
its own.**

The proposed categories — Sarees, Lehengas, Blouses, Gowns, Anarkali — are
`GarmentTemplate` rows, which already exist with stable keys, per-tenant
overrides and versioning (see [garment-product-templates.md](garment-product-templates.md)).
The proposed filters already exist too, as `TemplateFieldOption` values:

| Proposed filter | Existing source of truth |
|---|---|
| Category | `GarmentTemplate.key` — the 15 garments |
| Occasion | `occasion` options: Wedding, Reception, Festive, Party, Daily, Other |
| Sleeve | `sleeve_length`: Sleeveless, Cap, Short, Elbow, 3/4, Full |
| Neck | `front_neck` / `back_neck` / `collar` |
| Fabric | `apps.inventory` items in category FABRIC, with real stock |
| Colour | `DesignAsset.colour_palette`, already present |

Why this is load-bearing: if designs carry a parallel vocabulary, a design tagged
**"Half"** sleeve never matches an order spec that says **"Elbow"**. The
design→order handoff then fails silently, which is the worst way for it to fail.
Tagging with template values makes "designs matching this order" a query rather
than a fuzzy string comparison, and it means adding "Paithani" to saree types in
the admin updates the design filters at the same time.


The proposed Categories list mixes three different things:

```
Sarees, Lehengas, Blouses        → garment type      (GarmentTemplate)
Bridal, Reception, Party, Office → occasion / segment (template option, a tag)
Designer Collection, Premium     → collection         (new, user-defined)
Archived                         → status             (a field)
```

Flattened into one list, a "Bridal Lehenga" has to live in two categories at
once and the counts stop adding up. Kept separate, it is one design with a
garment type, an occasion tag, an optional collection and a status.

---



```
Designer                          a person who contributes designs
  ├─ id
  ├─ user            OneToOne auth.User, nullable   (null = credited but no login)
  ├─ staff           FK crm_api.Tailor, nullable    (when they are also floor staff)
  ├─ name, employee_id, profile_image
  ├─ specialisation, experience_years
  ├─ is_active, joined_at, last_active_at
  └─ bio

Collection                        a curated set, owned by a designer
  ├─ id
  ├─ designer        FK Designer
  ├─ name, description, cover_image
  ├─ season          'Bridal 2026', 'Summer'
  ├─ is_active, sequence
  └─ created_at

DesignApproval                    one row per review decision, immutable
  ├─ design          FK DesignAsset
  ├─ reviewer        FK auth.User
  ├─ decision        APPROVED | CHANGES_REQUESTED | REJECTED
  ├─ note
  └─ created_at
```

`DesignApproval` is a log rather than a status column so "why was this rejected
in March" survives the next resubmission.


```
designer_ref       FK Designer, nullable      replaces the free-text `designer`
collection         FK Collection, nullable
template           FK GarmentTemplate, nullable   the category (§2)
spec_tags          JSONField {field_key: value}   template-vocabulary tags
status             DRAFT | PENDING | ACTIVE | ARCHIVED
visibility         BOUTIQUE | DESIGNER_ONLY
approved_by        FK auth.User, nullable
approved_at        datetime, nullable
video_url          for the optional upload video
difficulty         SIMPLE | MODERATE | COMPLEX
stitch_hours       decimal, the estimated stitch time
view_count         int, denormalised
order_count        int, denormalised
```

`designer` (the CharField) stays through one release and is backfilled into
`designer_ref`, so imported Pinterest credits are not lost.

`spec_tags` uses the same shape as `GarmentJob.spec`: `{"sleeve_length": "elbow",
"occasion": "wedding"}`. That is what makes design→order matching a real query,
and it is validated by the existing `core/templates.py` engine rather than a
second validator.


`view_count` and `order_count` are denormalised because the dashboard sorts by
them. They are updated by the view that serves a design detail and by order
creation respectively — never computed with a `COUNT(*)` across the library on
page load, which is what makes a gallery of thousands slow.


`apps/design_studio/models.py` says catalogue entries are "projected into search
results by their providers instead of being copied — duplicating them would leave
two records to keep in sync." That reasoning holds, and it argues for **one**
table, not two.

The module needs approval status, designer, collection, analytics and archival on
every design in the library. Adding all of that to `BoutiqueDesign` as well would
duplicate the schema; leaving it out means half the library cannot be filtered,
approved or attributed.

**Plan:** migrate `BoutiqueDesign` rows into `DesignAsset` with
`source='catalogue'`, repoint the AI-suggestion provider and
`crm_api/utils.py:154` at `DesignAsset`, and keep `BoutiqueDesign` as a
deprecated read-only shim for one release before deleting it. This is a move, not
a copy, so it does not reintroduce the sync problem the comment warns about.

---



✅ Done. `core/roles.py` used to read:

```python
return profile.role if profile else OWNER
```

**Any signed-in user with no Tailor profile was treated as the Owner.** That
was safe only as long as a Tailor profile was the only kind of non-owner
profile that could exist. A Designer account breaks that: with no Tailor row,
it fell through to the same branch as the boutique owner's own account and was
handed full Owner access.

The fallback now checks a Designer profile before giving up and reporting
OWNER, so OWNER is a real "nothing else matched" rather than a guess.
`core/tests.py` pins this directly, including the specific regression it
replaces. See step 7 below for where this gets exercised by a real account.


| Capability | Owner | Designer |
|---|---|---|
| View all boutique designs | ✅ | ✅ (approved only) |
| Upload designs | ✅ | ✅ |
| Edit any design | ✅ | ❌ own uploads only |
| Delete boutique designs | ✅ | ❌ |
| Approve / reject uploads | ✅ | ❌ |
| Create collections | ✅ | ✅ own |
| Archive designs | ✅ | ❌ |
| Assign designs to designers | ✅ | ❌ |
| View designer portfolios | ✅ all | ✅ own |
| View design analytics | ✅ full | ✅ own: views, orders |
| View revenue / margin | ✅ | ❌ |
| View customer information | ✅ | ❌ |
| Everything outside this module | ✅ | ❌ |

**A `Designer` is not a `Tailor` role.** `crm_api` asserts that every role in
`Tailor.ROLE_CHOICES` has a production stage it can be assigned to -- "a role
nobody can be assigned to is a role that does not exist". Design work has no
stage, so adding Designer there would either break that invariant or require a
fake stage. `Designer` is its own model, with an optional `staff` FK for the
designer who also works the floor.

The module's permission class denies by default rather than allowing by default.

**What is actually enforced, and what is not.** ✅ Enforced server-side, in
`DesignLibraryPermission`: a Designer may upload, and may edit or delete only a
design their own profile is credited on -- checked once at the view level
(can this request be attempted) and again at the object level (is this
specifically their design), because the object is not loaded at the point the
first check runs.

❌ **Not enforced anywhere in the codebase today: "Designer cannot view customer
information / financial data."** `crm_api` has no role-based permission class at
all -- every viewset (customers, orders, everything) is `IsAuthenticated` only,
and that was already true for Tailor and Master accounts before this module
existed. A Designer account can currently call those endpoints exactly as
successfully as any other signed-in user. The frontend hides the customer/order
navigation for a Designer session and stops calling those endpoints on login
(see `App.jsx`'s `checkAuthSession`/`handleLoginSubmit`), which keeps a
well-behaved client from ever requesting the data -- but that is a UI courtesy,
not an API boundary, and does not stop a direct API call. Locking that down
properly means adding permission classes across `crm_api`'s viewsets, which is
a systemic change well beyond this module and was out of scope for step 7. The
design-detail fields the original matrix called out as owner-only (revenue,
margin, customer feedback, materials required) do not exist as fields on
`DesignAsset` at all yet, so there is nothing to redact there today either.

---


```
Design Management
├── Dashboard              counters and leaderboards, no image grid
├── Boutique Designs       the library, grouped by garment type
├── Designer Portfolios    per-designer view
├── Collections
├── Pending Approval       owner queue
├── Archived
└── Settings               approval on/off, categories, visibility defaults
```

**Dashboard** opens on numbers, not images: total designs, designers,
collections, recent uploads, pending approval, most viewed, most ordered,
recently used in orders.

**Library** lists garment-type sections with counts (`Sarees 245`,
`Lehengas 184`), each opening a filtered grid. Card shows image, name, designer,
uploaded date, fabric, colour, occasion, views, orders, status.

**Design detail** shows the full record; the owner additionally sees orders using
it, revenue, margin, and materials required.

**Designer dashboard** is the designer's landing page: today's uploads, pending,
approved, rejected, collections, most viewed, most ordered, upload button.

**Settings** carries `approval_required` — small teams turn the queue off and
uploads go straight to ACTIVE.

---


**Upload:** category → collection → images → video → name → fabric → colour →
occasion → style tags → difficulty → stitch time → references → save →
`PENDING` (or `ACTIVE` when approval is off).

**Approval:** designer uploads → pending queue → owner approves, requests changes
or rejects → a `DesignApproval` row is written either way → approved designs
become visible in the library.

**Customer selection:** already built. Choose garment → category opens → filter →
browse → shortlist onto a `DesignBoard` → approve → the board travels to the
order. The only change is that filtering now runs on `spec_tags`.

---


| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/design-studio/assets/` | Library, filtered (see §8) |
| `GET` | `/api/design-studio/assets/{id}/` | Detail; owner fields omitted for designers |
| `POST` | `/api/design-studio/assets/` | Upload → PENDING |
| `POST` | `/api/design-studio/assets/{id}/approve/` | Owner: approve / changes / reject |
| `POST` | `/api/design-studio/assets/{id}/archive/` | Owner |
| `GET` | `/api/design-studio/designers/` | List with design counts |
| `GET` | `/api/design-studio/designers/{id}/portfolio/` | Uploads, collections, performance |
| `GET/POST` | `/api/design-studio/collections/` | Designer's own |
| `GET` | `/api/design-studio/dashboard/` | Counters and leaderboards, one call |
| `GET` | `/api/design-studio/categories/` | Garment types with live counts |

`dashboard/` is deliberately one endpoint. The existing dashboard already fires
eight parallel calls on load; this module should not add nine more.

---


Query parameters map to columns and to `spec_tags`:

```
?template=lehenga &designer=<id> &collection=<id>
&occasion=wedding &sleeve_length=elbow &colour=red
&fabric=<inventory_item_id>
&price_min=3000 &price_max=6000
&uploaded=today|week|month  &status=active|pending|archived
```

Anything not a real column is looked up inside `spec_tags` with a JSON
containment query, which Postgres can index with GIN. **The index is not
optional** — a library of thousands filtered on JSON without one is exactly the
kind of slow page this module is meant to avoid.

Sorting: newest, most viewed, most ordered, name.

---


Each step ships working and is independently reversible.

1. **Designer.** ✅ Done. `Designer` model, `DesignAsset.designer_ref`, the
   backfill, and `/designers/` + `/designers/{id}/portfolio/`. Attribution only:
   `user` stays null, so no login and no new security surface. The
   `core/roles.py` fallback fix moves to step 7, where it is actually load-
   bearing -- changing it now would alter owner access for no benefit.
2. **Consolidation.** ✅ Done, in two commits. First the fields -- `template`,
   `spec_tags`, `status`, `visibility`, counters, GIN index, and the backfill
   from `garment_type`. Then the move: `BoutiqueDesign` rows became `DesignAsset`
   rows with `source='catalogue'`/`'suggestion'`, and every reader switched over
   in the same commit so there was never a period with two live copies.
   `/api/boutique-designs/` keeps its URL and its exact wire format, so Manage
   Designs and the wizard gallery did not have to change.
3. **Library UI.** ✅ Done. Garment sections with live counts, per-category grid,
   filters on the template vocabulary, and a design detail. An *Uncategorised*
   section carries designs with no template link, so the section counts always
   add up to the library and nothing becomes unreachable.
4. **Collections + upload flow.** ✅ Done. `Collection` per designer, filter by
   it in the library, and an upload that takes the photographs themselves rather
   than a pasted URL. The style tags render from the chosen garment's own
   template, so a design can only be tagged with values an order for that garment
   can hold. Uploads land ACTIVE, not PENDING -- see step 5.
5. **Approval queue + settings toggle.** ✅ Done. `DesignApproval` is a log, not a
   status column, so a rejection's reason survives the next resubmission.
   `design_approval_required` is off by default -- a small team is usually the
   owner and one or two designers, and a queue with nobody to clear it is
   friction with no one on the other end of it. The owner's own uploads always
   skip the queue even when it is on, since nobody reviews the reviewer.
   Any signed-in staff member may upload (not just the Owner): gating the
   upload itself on Owner would leave the queue permanently empty until
   designer accounts exist in step 7.
6. **Portfolios and dashboard analytics.** ✅ Done. `DesignAsset.order_count`
   existed since step 2 but nothing had ever written to it; it is now credited
   at the one place a board becomes a real order, resolved by parsing the
   board item's `source_ref` as a UUID rather than trusting its `source` label
   (a re-imported Pinterest pin and a live external result both carry
   `source == 'pinterest'`, and only one of them is a real library design).
   `/api/design-studio/dashboard/` is one call for the module's landing
   counters and leaderboards; a designer's own portfolio reports the same
   shape of numbers scoped to their own designs.
7. **Designer login.** ✅ Done, last as planned -- it needed 1, 2 and the
   `core/roles.py` fallback fix (§4.1) all in place first.
   `DesignerViewSet.create_login` is how an Owner switches a credited designer
   on, idempotent by email the same way `TailorViewSet._ensure_user_account`
   already is. `DesignLibraryPermission` enforces "edit only own uploads" at
   both the view and object level. See §4.2's enforcement note: the module's
   own permission boundary is real and tested; a Designer's isolation from the
   rest of the CRM (customers, orders, financials) is a frontend containment
   only, because `crm_api` has no role-based permission class for any staff
   role to date.

   **Not built:** a UI for a designer to edit their own upload after the fact.
   `DesignAssetViewSet` supports the PATCH, and the permission check is tested
   directly against the API, but the existing "Edit" button in the library only
   ever targets the older catalogue-CRUD endpoint (`/api/boutique-designs/`),
   which rejects anything that is not a catalogue/suggestion row. Wiring a
   second edit path for a plain upload is a small, separate follow-up.

Steps 1–2 are backend-only and change no screens. Step 7 is the one with a
security surface, and the one honest gap above is what is left of it.

---


Steps 1–7 built the library: who *drew* a design, uploads, approval, logins.
None of it could say who had been *asked* to draw one, for which garment, or
whether the work ever came back — a designer signing in saw their own upload
folder and no work at all. `DesignAssignment` closes that loop.

**Keyed on `GarmentJob`, not `Order`.** A `DesignBoard` is per-order (OneToOne),
which was fine when an order meant one dress. A two-garment order needs the
lehenga's design and the blouse's design to be structurally distinct rows —
there is no field in which one garment's design could be recorded against the
other. OneToOne per job: a garment has one design owner at a time; reassignment
replaces the designer on the row (refused with 409 once approved) and the
activity log carries the history.

**The loop:** Owner or Master `POST /assignments/` (garment_job + designer +
brief + due date) → the Designer's queue (`GET /assignments/?open=1`, scoped to
their own rows by `visible_assignments`) → `POST /assignments/{id}/submit/`
with one of their own designs (owner-or-credit checked; an uncredited upload is
credited to them on submit) → `POST /assignments/{id}/review/` with
`approve`/`changes`. `changes` reopens the work with the review note attached;
`open` means everything short of APPROVED, because a SUBMITTED design is open
on the *reviewer's* desk.

**Two serializers, one boundary.** The Owner/Master shape carries the customer
name; `DesignerAssignmentSerializer` carries the garment spec, measurements and
brief — everything needed to do the work — and no customer identity or pricing.
This is the first order-shaped payload a Designer can fetch at all, so §4.2's
"no customer information" line is drawn in the payload, not just the nav.
Roles: Owner/Master assign and review; Designer lists/retrieves/submits own
rows only; every other role (Tailor, QC Master, the rest of the split floor)
is refused outright — the design brief still reaches the floor through the
approved board, not through the assignment queue.

Every transition writes a `UniversalActivity` row (`DESIGN_ASSIGNED`,
`DESIGN_REASSIGNED`, `DESIGN_SUBMITTED`, `DESIGN_APPROVED`,
`DESIGN_CHANGES_REQUESTED`), which is what the owner scrolls back through to
answer "when did this go to her, and when did it come back".

Frontend: one `DesignWork` component for both ends of the loop (supervisors get
the assign form and review buttons, designers get the submit panel), mounted as
the `designWork` tab. A Designer now lands on their work queue at login, not
their upload folder.

Tests: `apps/design_studio/test_assignments.py` (38: assignment, attribution
across two garments/two designers, queue scoping, submission ownership, review
cycle, role boundaries, activity, refresh/resume) plus two cross-tenant
isolation tests in `tenants/tests.py` — TransactionTestCase flushes clash with
TenantTestCase siblings under `--parallel`, which is why they live there.
Fixing that flush exposed a real bug: the middleware's per-process tenant cache
was never invalidated on tenant creation, so every `TenantTestCase` (all
sharing schema `'test'`) could serve a *previous* class's tenant — including
its `owner_email` — to the next class's requests. `tenants/apps.py` now clears
the cache on `BoutiqueTenant` post_save/post_delete, replacing the four
call-sites that each had to remember to do it by hand.

---


- **Do designers need accounts now, or is attribution enough?** A `Designer` row
  with `user = null` credits work without any login surface. Steps 1–6 all work
  that way; only step 7 needs real accounts.
- **Is approval on by default?** Recommended off for a single-designer boutique,
  on for teams. It is a setting either way.
- **Should a design be reusable across garment types?** One template FK assumes
  not. A blouse design that also suits a lehenga blouse would need a
  many-to-many.
- **Who owns a Pinterest import?** Currently `designer` is free text from the
  source. Suggest attributing to the importing user with the original credit kept
  in `source_url`.
