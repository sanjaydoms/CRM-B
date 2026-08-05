# Scaleezy — Design Management Module

A design repository the boutique can actually run at scale: thousands of designs,
several designers, and three audiences who need different views of the same rows.

Written to be implemented in slices, each of which works end to end. Nothing here
invents a taxonomy the product already has — §2 is the load-bearing decision.

---

## 1. What already exists

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

## 2. The taxonomy decision

**Designs are tagged with garment-template vocabulary. The module does not mint
its own.**

The proposed categories — Sarees, Lehengas, Blouses, Gowns, Anarkali — are
`GarmentTemplate` rows, which already exist with stable keys, per-tenant
overrides and versioning (see [garment-product-templates.md](garment-product-templates.md)).
The proposed filters already exist too, as `TemplateFieldOption` values:

| Proposed filter | Existing source of truth |
|---|---|
| Category | `GarmentTemplate.key` — the 12 garments |
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

### Three axes, not one list

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

## 3. Data model

### 3.1 New

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

### 3.2 Added to `DesignAsset`

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

### 3.3 Counters

`view_count` and `order_count` are denormalised because the dashboard sorts by
them. They are updated by the view that serves a design detail and by order
creation respectively — never computed with a `COUNT(*)` across the library on
page load, which is what makes a gallery of thousands slow.

### 3.4 `BoutiqueDesign` — merge, do not add a third table

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

## 4. Roles and permissions

### 4.1 Fix the fallback first

[core/roles.py:29](../core/roles.py:29) currently reads:

```python
return profile.role if profile else OWNER
```

**Any signed-in user with no Tailor profile is treated as the Owner.** That is
safe today because staff always get a profile and the only profile-less account
is the boutique owner. It stops being safe the moment designers can log in: a
designer account created without a profile would see customers, orders and
financials — exactly what §4.2 forbids.

This must change before designer login ships. The fallback becomes explicit:
a user is the Owner because the tenant says so, not because a lookup missed.

### 4.2 Matrix

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

A `Designer` role joins `Tailor.ROLE_CHOICES`, and the module's permission class
denies by default rather than allowing by default.

**Owner-only fields on the design detail** — revenue generated, profit margin,
customer feedback, materials required — are excluded at the *serializer* level,
not hidden in the UI. A designer calling the API directly must not receive them.

---

## 5. Screens

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

## 6. Flows

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

## 7. API

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

## 8. Filtering

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

## 9. Build order

Each step ships working and is independently reversible.

1. **Designer + roles.** `Designer` model, `Designer` role, the `core/roles.py`
   fallback fix, module permission class. Backfill `designer` → `designer_ref`.
2. **Consolidation.** Merge `BoutiqueDesign` into `DesignAsset`; add `template`,
   `spec_tags`, `status`, `visibility`, counters; GIN index; backfill
   `garment_type` → `template`.
3. **Library UI.** Category sections with counts, filters, design detail.
4. **Collections + upload flow.**
5. **Approval queue + settings toggle.**
6. **Portfolios and dashboard analytics.**
7. **Designer login** — last deliberately, because it is only safe once 1, 2 and
   the serializer-level field restrictions are all in place.

Steps 1–2 are backend-only and change no screens. Step 7 is the one with a
security surface.

---

## 10. Open questions

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
