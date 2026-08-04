# Scaleezy v2 — Requirements Gap Analysis

Maps the 21 workflow areas onto the system as it exists today (`main`, July 2026).
Written to answer one question before any building starts: **what is already there, what
is a small addition, and what requires restructuring?**

Legend — **Exists**: works today. **Partial**: primitive is present, requirement is not
met. **New**: nothing exists. **Blocked**: cannot be built sensibly until the Production
Job restructure lands (§A).

---

## A. The load-bearing decision: Production Job per dress

The closing recommendation in the notes is the right one, and it is not a nice-to-have —
**most of the other 20 areas depend on it.** It should be decided first, because building
anything else on the current shape means building it twice.

### What the model assumes today

| Today | The requirement |
|---|---|
| One order = one garment | One order = many dresses |
| `Customer.garment_type` — garment type is an attribute of the *person* | Garment type belongs to the dress |
| `Measurement` is `OneToOne` on Customer — one live measurement set per person | Measurements are per dress |
| `DesignPreference.customer` — designs attach to the **customer**, not the order | Design belongs to the dress, and the order records the version used |
| `FabricSelection.customer` — same | Fabric belongs to the dress |
| `Order.tailor` + `Order.master` — two assignees for the whole order | Nine specialists, assigned per stage |
| 12 `OrderStage` rows hang off the Order | Each dress runs its own workflow |

There is a real, present-day defect hiding in row 4: because design and fabric selections
key on the customer rather than the order, a repeat client's second order cannot be told
apart from their first. The requirements expose it; they did not create it.

### The shape it wants to be

```
Order                     commercial envelope
  ├─ customer             who is buying
  ├─ payment, delivery    money and logistics
  └─ ProductionJob[]      one per dress
        ├─ garment_type   lehenga / blouse / gown
        ├─ measurements   snapshot taken for THIS dress
        ├─ design         source, references, approved image
        ├─ materials[]    fabric, border, lining, accessories
        ├─ stages[]       its own workflow, incl. optional maggam branch
        ├─ assignments[]  a specialist per stage
        ├─ checklist      production-readiness gate
        └─ costing        material + labour roll-up
```

Everything that currently hangs off `Order` — stages, tasks, QC records — moves down one
level to `ProductionJob`. `Order` keeps money, delivery and the customer relationship.

### Migration cost

Mechanically modest, because the production data is young: every existing order becomes
one order plus exactly one job, and the existing stage and task rows re-point at that job.
The expensive part is not the data, it is the **frontend** — the order views, the stage
tracker and the dashboard all assume one garment per order.

---

## B. Area-by-area

### Customer & design

| # | Area | Status | Notes |
|---|---|---|---|
| 1 | Customer type (new/existing) | **Partial** | Directory and search exist; there is no explicit new-vs-existing branch at intake. |
| 1 | Customer profile | **Exists** | Personal info, measurement history with versioning, previous orders, style preferences all present. |
| 1 | Preferred tailor/master | **New** | No preference field on the customer; assignment is per order. |
| 2 | Catalog & design version on order | **Blocked** | Designs attach to the customer, not the order — see §A. |
| 2 | Design sources (Pinterest, sketch, etc.) | **Partial** | `DesignPreference` stores notes, reference images and links, but has no `source` field to distinguish them. |
| 2 | Final approved design | **New** | No approval flag or approved-image field. |
| 8 | Inspiration board | **Partial** | Reference images exist; no board concept, no external image search. |
| 8 | AI design suggestion | **New** | Today's "AI suggestions" endpoint filters the catalogue by garment type. There is no model involved. |

### Orders & measurements

| # | Area | Status | Notes |
|---|---|---|---|
| 3 | Multiple dresses per order | **Blocked** | The core restructure — see §A. |
| 4 | Per-dress measurements | **Blocked** | Currently one live set per customer. |
| 4 | Version history | **Exists** | Already automatic — a new version is written on every change. |
| 4 | Re-measurement tracking | **Partial** | Versions are captured; there is no "re-measure requested" state. |
| 4 | Measurement templates | **New** | `additional_measurements` is a free JSON field; no reusable templates. |
| 4 | Owner approval step | **New** | No approval gate between measurement and production. |

### Inventory — the largest new area

| # | Area | Status | Notes |
|---|---|---|---|
| 5 | Customer-supplied fabric | **Partial** | `FabricSelection` records name, price and photographs. No received/balance quantity, no condition. |
| 5 | In-store fabric stock | **New** | `BoutiqueFabric` is a **catalogue**, not inventory: name, material, colour, price per metre, availability flag. No quantities at all. |
| 5 | Available / reserved / used metres | **New** | No stock ledger, no reservation concept. |
| 6 | Materials (lining, buttons, zips…) | **New** | No material entity of any kind. |
| 6 | Required / purchased / issued / remaining | **New** | Requires a stock-movement ledger, not just quantity columns. |
| 15 | Auto-deduct on issue | **New** | Depends on the ledger above. |
| 9 | Border management | **New** | No border entity, length tracking or source. |
| 21 | Material consumption & costing | **New** | Order pricing today is six manually-entered figures plus 5% tax. Nothing is derived from consumption. |

**This is the biggest single body of work in the document.** It is effectively an
inventory module: stock items, batches, units of measure, reservations, issues, returns
and a movement history. Nothing in the current schema can be extended into it — fabric is
modelled as a price list.

### Production workflow

| # | Area | Status | Notes |
|---|---|---|---|
| 7 | Pre-production checklist | **Partial** | Four guard rails already block invalid transitions (no delivery before QC, no stitching without a tailor, no tailor without measurements, no trial before stitching). The requirement adds fabric received, materials available, design approved, pattern ready, delivery date — none of which have data to check yet. |
| 10 | Maggam work | **New** | No embroidery entity, no branch in the workflow, no thread/stone/bead tracking. The workflow is currently strictly linear; this needs a parallel branch. |
| 11 | Pattern making | **Partial** | A `pattern_cutting` stage exists. No pattern images, no approval step. |
| 12 | Fabric cutting | **Partial** | Folded into the same stage. No cut date, fabric used, remaining or wastage. |
| 13 | Tailor workflow | **Exists** | Assigned → in progress → QC → completed is close to today's stage flow. |
| 14 | Hemming & finishing | **Partial** | Exists as a production task, not a tracked stage with its own completion record. |
| 16 | Pressing | **New** | No stage. |
| 17 | Three-level approval | **Partial** | `QCRecord` supports pass/fail/rework with checklist and photographs, but has no interface and models one level, not three. |
| 18 | Customer preview & alteration request | **New** | Customers do not log in. This needs a customer-facing surface — the single largest product addition after inventory. |

### Staffing, costing, alerts

| # | Area | Status | Notes |
|---|---|---|---|
| 20 | Nine specialist roles | **Partial** | `Tailor.role` is a free-text field and the workflow permits `Owner`, `Master`, `Tailor`. The workflow config already stores permitted roles per stage **as data**, so extending to nine roles is mostly configuration — the cheapest win in this document. |
| 20 | Per-stage assignment | **Partial** | `OrderStage.performed_by` records who *did* a stage. There is no forward assignment of who *should*. |
| 19 | Inventory alerts | **Blocked** | Needs stock levels to alert on. |
| 19 | Production delay alerts | **Partial** | Every stage carries an SLA in hours. Nothing evaluates it — there is no scheduled job. |
| 19 | Customer alerts | **Partial** | Notification records generate correctly today, with per-stage copy. **Nothing is ever sent** — no email or SMS integration exists. |
| 21 | Labour charges per stage | **New** | No labour rates, no per-stage cost capture. |

---

## C. What this adds up to

Roughly grouped by cost:

**Cheap, high value — do first**
- Nine roles via the existing workflow config (§20)
- Design `source` field and approval flag (§2)
- Forward assignment on stages (§20)
- Connecting a delivery provider so existing notifications actually send (§19)

**Structural — decide before building around it**
- Production Job per dress (§A) — unblocks §2, §3, §4 and makes §21 coherent

**A module of its own**
- Inventory and materials (§5, §6, §9, §15, §21) — stock items, ledger, reservations
- Costing engine, which depends on it

**A new surface**
- Customer preview and alteration requests (§18) — requires customer authentication,
  which is worth noting against the current state: the API has no authentication at all
  right now, so this cannot start until that is fixed

**Genuinely new capability**
- Maggam work as a parallel workflow branch (§10)
- AI design suggestion (§8) — no model exists today despite the naming

---

## D. Suggested sequence

1. **Close the open API.** Every endpoint is currently unauthenticated. Nothing
   customer-facing (§18) can be built before this, and it is a live exposure regardless.
2. **Expand roles to the nine specialists.** Config-only, immediate value.
3. **Land the Production Job restructure.** Backend, migration, then frontend.
4. **Build the inventory module** — items, ledger, reservations, issues.
5. **Wire the pre-production checklist** to the data inventory now provides.
6. **Add the missing stages** — maggam branch, pressing, finishing.
7. **Costing engine** on top of consumption data.
8. **Customer preview surface.**
9. **Alerting** — an SLA evaluator plus a real delivery provider.

Steps 1 and 2 are days. Step 3 is the pivot. Steps 4–7 are the bulk of the build.
