# Scaleezy — Garment Product Template Specification

Complete product configuration for the 15 garments the boutique stitches. Written so
frontend and backend implement against **one shared definition**: the backend stores the
template, the frontend renders it, and both validate with the same metadata.

Nothing here is hardcoded per garment. Adding a 13th garment, a regional variation or a
boutique-specific option is a data change, not a code change.

A template describes **one dress**, and an order holds many dresses. This is the
`ProductionJob` shape from [v2-requirements-gap-analysis.md](v2-requirements-gap-analysis.md) §A,
implemented here as `GarmentJob` in `apps/catalog` — the order keeps money, delivery
and the customer; each dress keeps its own spec, measurements and materials.

**Status: implemented.** Models and the rule engine are in `apps/catalog` and
`core/templates.py`, all twelve templates are seeded by a data migration, and the
order wizard's garment picker and detail step render from them.

---

## 1. The five sections

Every garment renders the same five sections in the same order, regardless of type. A
garment that has nothing to put in a section simply has fewer fields there; the section
header never disappears, so the staff experience is uniform.

| # | Section key | Title | What belongs here |
|---|---|---|---|
| 1 | `basic` | Basic Information | Type/sub-type, occasion, dates, priority, fabric source |
| 2 | `measurements` | Measurements | Numeric body and garment dimensions, in inches unless stated |
| 3 | `style` | Style & Design Options | Cut, neck, sleeve, borders, finishes — everything the customer chooses |
| 4 | `materials` | Materials & Accessories | Inventory-mapped consumables |
| 5 | `production` | Production Notes | Free text, internal instructions, attachments |

Sections 1, 4 and 5 additionally carry the **common fields** in §5, which are appended to
every template rather than repeated in each garment definition below.

---

## 2. Data model

### 2.1 Template side (configuration — `apps/catalog`)

```
GarmentTemplate            one per garment type, versioned
  ├─ key                   'saree', 'lehenga_blouse', …  (stable, never renamed)
  ├─ name                  'Saree'
  ├─ version               int, bumped on any breaking field change
  ├─ is_active             retired templates stay readable for old jobs
  ├─ tenant                null = global default, set = boutique override
  └─ sections[]  TemplateSection
        ├─ key             one of the five in §1
        ├─ title, sequence
        └─ fields[]  TemplateField
              ├─ key             snake_case, unique within template
              ├─ label
              ├─ field_type      see §2.3
              ├─ unit            'in', 'm', null
              ├─ is_required
              ├─ default
              ├─ help_text
              ├─ sequence
              ├─ visible_when    JSON rule, see §2.4
              ├─ validation      JSON: min, max, step, max_length, regex
              ├─ inventory_category   FABRIC / BORDER / … for inventory_ref fields
              └─ options[]  TemplateFieldOption  (value, label, sequence, is_active)
```

`TemplateFieldOption` is a table, not a Python enum — the boutique owner must be able to
add "Paithani" to saree types from the admin without a deploy.

### 2.2 Instance side (what an order captures)

```
GarmentJob                          one dress
  ├─ order                          FK
  ├─ template                       FK GarmentTemplate
  ├─ template_version               int, frozen at creation
  ├─ spec                           JSONField {field_key: value}
  ├─ measurements                   JSONField {field_key: decimal}   (snapshot)
  └─ material_lines[]  JobMaterial
        ├─ field_key                which template field it satisfies
        ├─ inventory_item           FK apps.inventory.InventoryItem (nullable)
        ├─ free_text                when the item is customer-supplied / not stocked
        ├─ quantity, unit
        └─ source                   STORE / CUSTOMER
```

`spec` and `measurements` are separate JSON columns on purpose: measurements are numeric,
versioned, printed on the cutting sheet and compared across orders; spec values are
categorical. Keeping them apart avoids a schema migration every time a style option
changes, while still letting measurement history work the way it does today.

**`template_version` is frozen at creation.** A job opened in March renders and validates
against the template as it was in March, even after the owner edits it in April.

### 2.3 Field types

| `field_type` | Renders as | Stored as |
|---|---|---|
| `text` | single-line input | string |
| `textarea` | multi-line | string |
| `number` | numeric input with `unit` suffix and `step` | decimal (string in JSON) |
| `select` | dropdown | option `value` |
| `multiselect` | checkbox group | list of option values |
| `boolean` | Yes/No toggle | true/false |
| `date` | date picker | ISO date |
| `file` | upload | media path |
| `inventory_ref` | searchable picker filtered by `inventory_category` | `JobMaterial` row |

Every `select` carries an `Other` option where the list is open-ended; choosing it reveals
a paired `*_other` text field via `visible_when`.

### 2.4 Conditional visibility

One rule shape, evaluated identically in JS and Python:

```json
{ "field": "petticoat_required", "op": "eq", "value": true }
{ "field": "blouse_style", "op": "in", "value": ["peplum", "corset"] }
{ "all": [ {...}, {...} ] }
{ "any": [ {...}, {...} ] }
```

Operators: `eq`, `neq`, `in`, `not_in`, `is_set`. Rules nest via `all` / `any`.

**A hidden field is never required and never stored.** The backend evaluates visibility
before validating, drops values for fields whose rule is false, and rejects a required
field only when it is genuinely visible. This is the single most common source of "form
saved but data is wrong" bugs, so it belongs in shared, tested code — `core/templates.py`
holding `is_visible(field, spec)` and `validate_spec(template, spec)`, mirrored in
`frontend/src/services/templates.js`.

### 2.5 API

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/api/catalog/templates/` | List active templates (key, name, version) |
| `GET` | `/api/catalog/templates/{key}/` | Full nested definition for rendering |
| `POST` | `/api/catalog/templates/{key}/validate/` | Dry-run validation of a spec payload |
| `GET/POST/PATCH/DELETE` | `/api/catalog/jobs/` | Job CRUD (`?order=<order_id>` to filter), spec validated on write |
| `POST` | `/api/catalog/jobs/{id}/materials/` | Attach a material line |

The template endpoint is cacheable per `(key, version)`.

---

## 3. Garment definitions

Notation: `key` — Label · `type` · options. `→` marks a conditional rule. All measurements
are inches unless a `unit` is given.

---

### 3.1 Saree — `saree`

**Basic Information**

| Key | Label | Type | Options / notes |
|---|---|---|---|
| `saree_type` | Saree Type | select | Silk, Cotton, Georgette, Chiffon, Linen, Organza, Tissue, Banarasi, Kanchipuram, Other |
| `saree_type_other` | Specify Type | text | → `saree_type` eq `other` |
| `fabric_source` | Fabric Source | select | Customer Fabric, Store Fabric *(common field, see §5)* |
| `fabric_length` | Fabric Length | number · `m` | step 0.25, min 0 |

**Measurements** — none of their own. When `petticoat_required` is true the petticoat
measurements below apply; blouse measurements belong to a separate Blouse job.

| Key | Label | Type | Notes |
|---|---|---|---|
| `petticoat_length` | Petticoat Length | number · in | → `petticoat_required` eq true |
| `petticoat_waist` | Petticoat Waist | number · in | → `petticoat_required` eq true |

**Style & Design Options**

| Key | Label | Type | Options |
|---|---|---|---|
| `services` | Services Required | multiselect | Stitching, Fall, Pico, Fall + Pico, Tassel Work, Saree Finishing, Polishing / Steam |
| `border` | Border | select | With Border, Without Border |
| `backing` | Backing | select | With Backing, Without Backing |
| `fall_type` | Fall | select | Big Fall, Small Fall → `services` in [fall, fall_pico] |
| `pico_type` | Pico | select | Standard, Premium → `services` in [pico, fall_pico] |
| `tassels` | Tassels | select | No Tassels, Hand Made, Readymade, Knot Style |
| `petticoat_required` | Petticoat Required | boolean | |
| `petticoat_waist_finish` | Petticoat Waist Finish | multiselect | Belt, Elastic, Button, Dori → `petticoat_required` eq true |

**Materials & Accessories** — all `inventory_ref`

`fabric_used` (FABRIC), `border_used` (BORDER → `border` eq `with_border`),
`lining` (LINING), `fall_cloth` (LINING), `tassels_material` (EMBELLISHMENT →
`tassels` neq `no_tassels`), `thread_colour` (STITCHING)

**Production Notes** — `notes` textarea + common fields.

---

### 3.2 Blouse — `blouse`

**Basic Information** — common fields only, plus:

| Key | Label | Type | Options |
|---|---|---|---|
| `blouse_type` | Blouse Type | select | Plain, Princess, One-Tuck, Three Point, Katori, Portable Katori |

**Measurements** — all `number` · in, step 0.25

`blouse_length`, `shoulder`, `upper_chest`, `chest`, `waist`, `armhole`

**Style & Design Options**

| Key | Label | Type | Options |
|---|---|---|---|
| `sleeve_length` | Sleeve Length | select | Sleeveless, Cap, Short, Elbow, 3/4, Full |
| `hand_rounding` | Hand Rounding | select | HR1, HR2, HR3, HR4 → `sleeve_length` neq `sleeveless` |
| `front_neck` | Front Neck | text | depth/shape as recorded by the master |
| `back_neck` | Back Neck | text | |
| `collar` | Collar | text | |
| `dot_point` | Dot Point | text | |
| `padding` | Padding | select | Padded, Non-Padded |
| `dori_required` | Dori | boolean | |
| `dori_colour` | Dori Colour | text | → `dori_required` eq true |
| `dori_tassel_type` | Dori Tassel Type | select | Hand Made, Readymade, Knot → `dori_required` eq true |

**Materials** — `main_fabric` (FABRIC), `lining` (LINING), `cups` (EMBELLISHMENT →
`padding` eq `padded`), `hooks` (STITCHING), `zip` (STITCHING), `thread` (STITCHING)

**Production Notes** — free text + common.

---

### 3.3 Lehenga — `lehenga`

| Section | Fields |
|---|---|
| **Basic** | `lehenga_type` select: A-Line, Circular, Mermaid, Straight Cut, Panelled (Khalis) |
| **Measurements** | `waist` number·in, `floor_length` number·in |
| **Style** | `waist_finish` select: Dori, Belt, Elastic · `border` boolean · `backing` boolean · `lining_type` select: Cotton, Crepe, Catman |
| **Materials** | `main_fabric` (FABRIC), `lining` (LINING), `can_can` (LINING), `canvas` (LINING), `border_material` (BORDER → `border` eq true), `zip` (STITCHING), `hooks` (STITCHING) |
| **Production** | `notes` textarea |

---

### 3.4 Lehenga Blouse — `lehenga_blouse`

Shares the blouse measurement and neck/sleeve block; differs in the style-specific fields.

**Basic** — `blouse_style` select: Standard, Peplum, Ruffled, Jacket Style, Cape Style,
Long Waist, Corset

**Measurements** — `blouse_length`, `shoulder`, `upper_chest`, `chest`, `waist`, `armhole`
(identical keys to §3.2 so the cutting sheet and measurement history stay comparable)

**Style & Design Options** — sleeve, neck and padding blocks identical to §3.2, then:

| Key | Label | Type | Options | Visible when |
|---|---|---|---|---|
| `flare_length` | Flare Length | number · in | | `blouse_style` eq `peplum` |
| `flare_type` | Flare Type | select | A-Line, Pleats, Box Pleats | `blouse_style` eq `peplum` |
| `layer_count` | Number of Layers | number | min 1, max 10 | `blouse_style` eq `ruffled` |
| `collar_style` | Collar Style | text | | `blouse_style` eq `jacket` |
| `cape_length` | Cape Length | number · in | | `blouse_style` eq `cape` |
| `cape_neck_shape` | Cape Neck Shape | text | | `blouse_style` eq `cape` |
| `cape_fastening` | Buttons / Hooks | select | Buttons, Hooks, None | `blouse_style` eq `cape` |
| `corset_cups` | Corset Cups | select | Soft, Moulded, None | `blouse_style` eq `corset` |
| `boning_required` | Boning Required | boolean | | `blouse_style` eq `corset` |

**Materials** — `main_fabric`, `lining`, `cups`, `boning` (EMBELLISHMENT →
`boning_required` eq true), `hooks`, `zip`

---

### 3.5 Dupatta — `dupatta`

| Section | Fields |
|---|---|
| **Measurements** | `length` number·in, `width` number·in |
| **Style** | `border` boolean · `backing` boolean · `embroidery_finish` select: None, Machine, Hand, Maggam |
| **Materials** | `fabric` (FABRIC), `border_material` (BORDER → `border` eq true), `lace` (BORDER), `thread` (STITCHING) |

---

### 3.6 Kurti — `kurti`

| Section | Fields |
|---|---|
| **Basic** | `kurti_type` select: Plain, A-Line, 3 Piece, Khalis |
| **Measurements** | `full_length`, `bodice_length`, `shoulder`, `upper_chest`, `chest`, `waist`, `hip` — all number·in |
| **Style** | `front_neck` text · `back_neck` text · `collar` text · `slit` select: Left, Right, Both, None · `zip_position` select: Side, Front, Back, None · `pocket` boolean · `padding` boolean |
| **Materials** | `fabric` (FABRIC), `lining` (LINING), `zip` (STITCHING → `zip_position` neq `none`), `buttons` (STITCHING) |

---

### 3.7 Anarkali — `anarkali`

| Section | Fields |
|---|---|
| **Basic** | `anarkali_type` select: A-Line, Khalis · `bodice` select: With Bodice, Without Bodice |
| **Measurements** | `top_length`, `bodice_length` (→ `bodice` eq `with_bodice`), `shoulder`, `upper_chest`, `chest`, `waist`, `hip` |
| **Style** | `front_neck` · `back_neck` · `collar` · `padding` boolean · `zip` boolean · `pocket` boolean · `border` boolean · `backing` boolean |
| **Materials** | `fabric` (FABRIC), `lining` (LINING), `can_can` (LINING), `border_material` (BORDER → `border` eq true) |

---

### 3.8 Petticoat — `petticoat`

| Section | Fields |
|---|---|
| **Measurements** | `length`, `waist` |
| **Style** | `waist_finish` multiselect: Belt, Elastic, Button, Dori |
| **Materials** | `fabric` (FABRIC), `elastic` (STITCHING → `waist_finish` in [elastic]), `dori` (STITCHING → `waist_finish` in [dori]) |

---

### 3.9 Salwar — `salwar`

| Section | Fields |
|---|---|
| **Measurements** | `full_length`, `waist` |
| **Style** | `bottom_finish` select: Round, Flared, Ankle · `waist_finish` select: Belt, Elastic, Dori |
| **Materials** | `fabric`, `elastic` (→ `waist_finish` eq `elastic`), `dori` (→ `waist_finish` eq `dori`) |

---

### 3.10 Churidar — `churidar`

| Section | Fields |
|---|---|
| **Measurements** | `full_length`, `waist`, `thigh`, `upper_thigh`, `knee`, `calf`, `crotch` |
| **Style** | `waist_finish` select: Belt, Elastic, Dori |
| **Materials** | `fabric`, `elastic`, `dori` |

---

### 3.11 Palazzo — `palazzo`

| Section | Fields |
|---|---|
| **Measurements** | `length`, `waist` |
| **Style** | `bottom_width` select: 11", 15", 17", 20" |
| **Materials** | `fabric`, `elastic` (STITCHING), `zip` (STITCHING) |

---

### 3.12 Sharara — `sharara`

| Section | Fields |
|---|---|
| **Measurements** | `length`, `waist`, `thigh` |
| **Style** | `bottom_width` select: 17", 20", 24" |
| **Materials** | `fabric`, `can_can` (LINING), `elastic` (STITCHING), `zip` (STITCHING) |

---

## 4. Measurement key registry

Keys are shared across garments deliberately — `waist` means the same thing on a lehenga
and a churidar, so measurement history, the cutting sheet and "reuse last measurements"
all work without per-garment mapping tables.

| Key | Label | Garments |
|---|---|---|
| `shoulder` | Shoulder | blouse, lehenga_blouse, kurti, anarkali |
| `upper_chest` | Upper Chest | blouse, lehenga_blouse, kurti, anarkali |
| `chest` | Chest | blouse, lehenga_blouse, kurti, anarkali |
| `waist` | Waist | almost all |
| `hip` | Hip | kurti, anarkali |
| `armhole` | Armhole | blouse, lehenga_blouse |
| `blouse_length` | Blouse Length | blouse, lehenga_blouse |
| `bodice_length` | Bodice Length | kurti, anarkali |
| `top_length` | Top Length | anarkali |
| `full_length` | Full Length | kurti, salwar, churidar |
| `floor_length` | Floor Length | lehenga |
| `length` | Length | dupatta, petticoat, palazzo, sharara |
| `width` | Width | dupatta |
| `thigh` / `upper_thigh` | Thigh / Upper Thigh | churidar, sharara |
| `knee`, `calf`, `crotch` | Knee, Calf, Crotch | churidar |

**Migration note.** The current `Measurement` model has seven columns
(`bust, waist, hips, shoulder, arm_length, neck, length`) plus an
`additional_measurements` JSON blob, and hangs `OneToOne` off `Customer`. Under this spec
the per-dress snapshot lives in `GarmentJob.measurements`; `Measurement` is retained as
the customer's **latest known body measurements**, pre-filling a new job. Map
`bust → chest`, `hips → hip`, `arm_length → sleeve_length` (measurement, not the style
select) on migration, and keep `neck` as a body measurement outside the template registry.

---

## 5. Common fields (appended to every template)

Defined once in code and merged into every template's sections, so a change reaches all 12
garments at once. Their keys are reserved and cannot be redefined by a garment.

### Section 1 — Basic Information

| Key | Label | Type | Options |
|---|---|---|---|
| `occasion` | Occasion | select | Wedding, Reception, Festive, Party, Daily, Other |
| `design_reference_source` | Design Reference | select | Boutique Catalog, Pinterest, Google Images, Customer Sketch, Designer Sketch, Previous Design *(reuses `DesignPreference.SOURCE_CHOICES`)* |
| `design_reference_links` | Reference Links | text (repeatable) | |
| `trial_required` | Trial Required | boolean | |
| `trial_date` | Trial Date | date | → `trial_required` eq true |
| `delivery_date` | Delivery Date | date | required |
| `urgency` | Urgency | select | Normal, Express |
| `priority` | Priority | select | Low, Medium, High *(mirrors `ProductionTask.PRIORITY_CHOICES`)* |
| `material_source` | Material Source | select | Customer Provided Fabric, Store Inventory Fabric, Mixed |

### Section 4 — Materials & Accessories

Every garment's material fields are `inventory_ref` fields resolving to
`apps.inventory.InventoryItem`. The mapping from the requested accessory list to the
existing `Category` choices:

| Accessory | `inventory_category` |
|---|---|
| Fabric, Lining, Fall Cloth, Can Can, Canvas | `FABRIC` / `LINING` |
| Border, Lace | `BORDER` |
| Tassels, Cups, Boning, Embroidery Material | `EMBELLISHMENT` |
| Elastic, Dori, Buttons, Hooks, Zip, Thread | `STITCHING` |
| Maggam / hand-embroidery supplies | `MAGGAM` |
| Anything else | `OTHER` |

No new inventory categories are needed. Each selected item creates a `JobMaterial` line;
issuing it writes a `StockMovement`, which is what makes auto-deduction and material
costing work. Customer-supplied material is recorded as `source = CUSTOMER` and never
touches stock.

An `other_accessories` repeatable `inventory_ref` field is appended to every template for
anything not anticipated.

### Section 5 — Production Notes

| Key | Label | Type |
|---|---|---|
| `special_instructions` | Special Instructions | textarea |
| `internal_notes` | Internal Notes | textarea *(staff-only, hidden from customer-facing print)* |
| `customer_notes` | Customer Notes | textarea |
| `reference_images` | Reference Images | file (multiple) |
| `measurement_sheet` | Measurement Sheet | file |
| `audio_note` | Audio Note | file *(transcribed to `special_instructions`)* |
| `final_approved_design` | Final Approved Design | file |

### Production tracking — **not** template fields

Master Assigned, Cutter Assigned, Trial Status, Alteration Count, QC Status and Ready for
Delivery are workflow state, not customer configuration. They stay on the existing
`OrderStage.assigned_to` / `ProductionTask` / `QCRecord` models and are edited from the
production board, not the order form. Putting them in the template would make them
editable at intake and duplicate the stage machinery.

---

## 6. Validation rules

1. **Required** applies only to visible fields (§2.4).
2. **Numeric** — measurements: min 0, max 120 in, step 0.25. Lengths in metres: step 0.25.
   Reject values outside range rather than silently clamping.
3. **Unknown keys** in `spec` are rejected, not ignored — a typo'd key that silently
   vanishes is worse than a 400.
4. **Option values** must exist and be active on the field, except on jobs frozen to an
   older `template_version`, which validate against that version's option set.
5. **Inventory refs** must resolve to an active `InventoryItem` whose `category` matches
   the field's `inventory_category`.
6. **Cross-field** — `trial_date` must fall before `delivery_date`; `delivery_date` cannot
   be in the past on creation.

---

## 7. Frontend rendering contract

The wizard's Steps 1 and 2 in [src/App.jsx](../src/App.jsx) — the hardcoded garment
dropdown at [App.jsx:6276](../src/App.jsx:6276), the stitch-parts map at
[App.jsx:6322](../src/App.jsx:6322) and `getVisibleMeasurementFields()` at
[App.jsx:97](../src/App.jsx:97) — are replaced by a single renderer:

```
<TemplateForm template={template} value={spec} onChange={setSpec} section="measurements" />
```

- Fetch `/api/catalog/templates/{key}/` once per garment, cache by `(key, version)`.
- Render sections in `sequence`; render fields in `sequence` within a section.
- Re-evaluate `visible_when` on every change; clear values of fields that become hidden.
- Validate client-side with the shared rules, and let the server be the authority — a
  client that skips validation must not be able to write an invalid spec.
- The "Parts to Stitch" checkbox grid becomes **"add a dress to this order"**: picking
  Lehenga + Blouse + Dupatta creates three `GarmentJob` rows, each with its own form.

---

## 8. Multi-tenancy

Boutiques are already separated by schema (django-tenants), so each one gets its own
copy of the twelve templates and cannot see another's. `GarmentTemplate.tenant` is the
second level, inside a schema: null rows are the shipped defaults, and a branch or label
that needs its own version of a garment gets a copy with `tenant` set, requested with the
`X-Template-Variant` header. Resolution is "variant if present, else default", so a
boutique inherits improvements to the defaults until the moment it overrides one.

---

## 9. Implementation sequence

1. `apps/catalog` models + migrations; `core/templates.py` with `is_visible` /
   `validate_spec`, unit-tested against a fixture template.
2. Seed data for all 12 templates (a versioned data migration, so a boutique's edits are
   never overwritten by a redeploy).
3. Template + validate API endpoints.
4. `GarmentJob` / `JobMaterial` — multi-dress orders. **Done**, additive: the existing
   `Order` is untouched and jobs hang off it.
5. `TemplateForm` renderer; migrate wizard Steps 1–2 onto it. **Done.**
6. `JobMaterial` → `StockMovement` wiring for auto-deduction and material costing.
   **Not done** — material lines record what a dress needs, but issuing them does not
   yet move stock.

Still outstanding after this: the order registry, dashboard and stage tracker read
`Customer.garment_type` and show one garment per order. Until they move onto the job
list, the wizard keeps `garment_type` pointing at the first dress so those views and
the pricing rules keep working.
