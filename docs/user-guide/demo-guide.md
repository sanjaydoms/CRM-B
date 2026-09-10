
Open this ten minutes before the meeting. Everything below is a click path that
has been walked in the running build.

Full detail: **[Complete User Guide](README.md)** · coverage: **[Product Coverage Matrix](coverage-matrix.md)**

---



```bash
cd antigravity/scratch/django_screens && ./start.sh
```

Backend on `http://localhost:8000`, workspace on `http://localhost:5173`.
`start.sh` points at the local Postgres (`USE_LOCAL_DB=True`) — it will not
touch a hosted database.

For the public website (built separately):

```bash
cd antigravity/scratch/django_screens/frontend && npm run build && npm run preview
```

Served on `http://localhost:4173`.


| Tab | URL |
|---|---|
| 1 — public site | `http://localhost:4173/` |
| 2 — workspace | `http://localhost:5173/app.html` |
| 3 — customer tracking | the link from the demo order (below) |
| 4 — phone view | tab 2, browser dev tools at 390×844 |


1. Sign in as the owner. The dashboard shows one order and one appointment.
2. Open **Manage Orders** — order `T2B-260827-2925`, *Delivered*.
3. Open the tracking link in tab 3 — it should show 15 ticked stages and two photos.

If any of that is missing, the demo data has been reset — see §6.

---


**Boutique:** Kanchi Threads · 12 Kutchery Road, Mylapore, Chennai 600004
**Schema:** `kavyademoboutiquetest_bc8ec80a`


> Local demo credentials on a local database. They are not used anywhere else
> and must never be reused on a hosted environment.

| Role | Email | Password |
|---|---|---|
| Owner — Kavya Reddy | `kavya@demoboutique.test` | `DemoBoutique#2026` |
| Master Tailor — Lakshmi Iyer | `lakshmi@demoboutique.test` | `5T8zXlyrNkbS` |
| Stitching Tailor — Ravi Kumar | `ravi@demoboutique.test` | `5lsQV4xxfXIZ` |
| QC Master — Sunita Rao | `sunita@demoboutique.test` | `DHBCanRHX42T` |
| Designer — Meera Nair | `meera@demoboutique.test` | `noBJXxBGKXuT` |

The Super Admin console needs platform-administrator credentials, which are not
part of this boutique's data. Show it only if you have them.


| Thing | Detail |
|---|---|
| Customer | Ananya Krishnan · +91 98450 12345 · Chennai · segment **HVC** |
| Order | `T2B-260827-2925` — Blouse + Lehenga · ₹49,875 · **Paid** · **Delivered** · all 15 stages complete |
| Staff | 1 Master, 1 Stitching Tailor, 1 QC Master, 1 Designer |
| Fabrics | Kanchipuram Silk (Temple Red) ₹4,200/m · Chanderi Silk Cotton ₹1,250/m · Raw Silk Dupion ₹1,850/m |
| Inventory | 3 items with stock; Kanchipuram Silk shows 34.3 m left of 40 m — the 5.7 m this order consumed |
| Designs | 5 records in the library, one of them uploaded by the designer with a real image (the designer's design appears twice) |
| Design work | One blouse brief, submitted by the designer and approved by the owner |
| Appointment | Design Consultation, 2 Sept 11:00, Ananya with Lakshmi |


Owner → **Manage Orders** → the order card → **Customer updates** — the link is
inside the message text. It is a signed URL; copy it from there rather than
typing one.

---


Work down the list. Each block is *what to show → what to say → what to click →
expected result → the point*.


**Show:** `localhost:4173`
**Say:** "This is what a boutique owner finds. The pitch is narrow on purpose —
this is not generic CRM, it is built for businesses that stitch to measurement."
**Click:** Home → Lifecycle → Book a demo.
**Result:** The demo form; leads land in the platform console.
**Point:** *A vertical product, not a horizontal one.*


**Show:** Owner sign-in.
**Say:** "Each boutique gets its own isolated database schema. Two boutiques on
this server cannot see each other's clients or prices."
**Click:** Sign in → land on the dashboard.
**Result:** Order card, live production progress, upcoming appointment.
**Point:** *One screen answers the two questions an owner asks all day: where is
each order, and who is coming in.*


**Click:** Customers → Ananya Krishnan.
**Say:** "Measurements are versioned — you can see what this client measured
last season, not just today. The style profile is derived from their own orders."
**Result:** Measurements, sizing version history, order history, style profile.
**Point:** *The notebook, made searchable and shared with the whole floor.*


**Click:** New Custom Order → Create New Customer → fill the basics → pick
**Blouse** and **Lehenga** → Next.

**Say at the garment step:** "Two garments, one order, and each asks only for
what it needs. A blouse asks for armhole and hand rounding. A lehenga asks for
floor length and waist finish. This is not one generic form with fields greyed
out."

**Click:** set Blouse Type, Occasion, Trial Required = Yes (**then set the trial
date — the wizard will not advance without it**), the measurements, and under
*Materials & Accessories* pick the Kanchipuram Silk **from live stock** with a
quantity.

**Say:** "That fabric line is your actual stock. It will be reserved and then
consumed as production moves."

**Click:** Next → the AI Design Studio.

**Say:** "Suggestions ranked against this client's measurements, occasion, budget
and past orders — with the reason on each card. It searches your own catalogue,
your uploads and their previous orders."

**Click:** Add to board on one design per garment → Next → pick a fabric → Next
→ assign Lakshmi as Master and Ravi as Tailor, choose pickup → Next.

**Result:** The cost breakdown — per garment, plus packaging, discount, GST.

**Click:** Create Order & Pay → **Pay Partially Now** → advance amount → tick
terms → Confirm Order & Continue.

**Result:** Order confirmed with an id, payment status and the tracking link.

**Point:** *Everything the floor needs is captured once, at the counter, and
never re-keyed.*

> If you are short of time, resume the wizard from a saved draft instead of
> filling it in live.


**Click:** Log out → sign in as **Ravi Kumar** (tailor).
**Say:** "This is the whole application for a stitching tailor. Two menu items.
They see their orders, the measurements as ordered, the spec and the materials —
and no prices, no other customer, no other order."
**Click:** Stitching In Progress → Start In-Progress → comment → Complete Stage.
**Result:** The stage times and credits itself to them.

**Click:** Log out → sign in as **Lakshmi Iyer** (master).
**Say:** "The Master sees the whole floor and owns cutting, finishing and
quality. Notice what they cannot do: they cannot touch a price."
**Click:** the Master Production Verification Checklist.
**Point:** *Each stage belongs to a role. Nobody can advance someone else's
work, and every step is timestamped and attributed.*


**Click:** Sign in as **Meera Nair**.
**Say:** "A designer account is deliberately narrow — the brief and the garment
spec, and no client name or money. That is enforced on the server, not just
hidden in the menu."
**Click:** My Work → the brief → Design Studio → the uploaded design.
**Point:** *Freelance designers can be given access without giving away the
client book.*


**Click:** Owner → Inventory → Items.
**Say:** "The Kanchipuram Silk went in at 40 metres and reads 34.3. Nobody typed
that. It is the 1.2 and 4.5 metres chosen on the two garment cards — reserved
when the fabric was confirmed, consumed when it was stitched."
**Click:** History on that item → the ledger.
**Click:** Reports.
**Point:** *Stock is a consequence of production, not a separate spreadsheet.*


**Click:** Invoices.
**Say:** "Advance at the counter, balance at delivery, and the invoice carries
your own boutique details."
**Click:** View Invoice → Print Invoice (cancel the dialog).
**Point:** *Be straight: payments are recorded here, not collected. There is no
gateway.*

> **Watch the invoice line items.** A garment line reads *Customer supplied
> fabric* unless a fabric cost was typed into the step-6 breakdown — even when
> the fabric came from your own stock. If you are demoing the invoice, fill the
> Fabric field in when you build the order. See §31.10 of the guide.


**Click:** Manage Orders → the order card → Customer updates → copy the tracking
link → paste it in tab 3, ideally on a phone.

**Say:** "This is what your customer sees. No app, no login, no password. Every
stage, timestamped. The photographs, but only after the boutique publishes them.
What they have paid, what is left, and where to collect."

**Point:** *This is the message that stops the daily "any update?" phone call —
and it is the part a boutique owner buys.*

---


```text
Public site (30 s)
   ↓
Owner dashboard (30 s)
   ↓
Customer record — versioned measurements + style profile (1 min)
   ↓
New order: two garments, per-garment forms, stock-linked materials (3 min)
   ↓  (resume a draft if pressed for time)
AI design suggestions with reasons (1 min)
   ↓
Tailor login — the narrow view, advance a stage (1.5 min)
   ↓
Inventory — 40 m → 34.3 m, nobody typed it (1 min)
   ↓
Invoice (30 s)
   ↓
Customer tracking link, on a phone (1 min)
```

---


| Claim | Evidence to show |
|---|---|
| Built for stitch-to-measure, not adapted from retail | Per-garment forms; garment-specific measurements |
| One order, many garments | Blouse + Lehenga on `T2B-260827-2925` |
| Everyone works from the same record | Owner, Master, Tailor and customer views of one order |
| Roles are enforced, not decorative | The tailor's two-item menu; the designer with no client data |
| Stock is real | 40 m → 34.3 m, with a ledger |
| Customers stop chasing you | The tracking link |
| Boutique data is isolated | Each tenant is its own schema |


- Online payment collection — there is no gateway.
- Automatic WhatsApp — the product composes; a human sends.
- Try-On — it is a stock photograph picked by colour keyword.
- Pinterest / Google design search — both read *not connected*.
- That the invoice knows where the fabric came from — it infers it from the
  fabric price (§31.10).

---


| Problem | Fix |
|---|---|
| **Next** does nothing in the wizard | A required field is empty — almost always **Trial Date** after Trial Required = Yes |
| Signup looks frozen | Normal: schema creation takes 20–45 s. Do not reload. |
| You are half way through a wizard and out of time | **Save as Draft**, then Resume later from the New Custom Order screen |
| The demo order got advanced or delivered mid-demo | It is already Delivered; that is the intended resting state. Create a fresh order to demo production. |
| You lost track of which role you are | The header greets you by name; the sidebar length gives it away |
| Everything looks empty | You are signed in as the wrong role, or a filter is still applied |
| Try-On shows a broken image | Expected offline — use it as the honest framing (§20 of the guide) |
| The data is gone | Re-seed by re-running the capture steps in order: `signup`, `seed_staff`, `seed_designer`, `seed_fabrics`, `seed_designs`, `seed_inventory`, `seed_stock`, `create_order`, `assign_design_work`, `designer_upload`, `owner_review_design`, `run_production`, `tailor_production`, `master_production_late`, `settle_payment`, `owner_order_wrapup`, `deliver_order`, `owner_appointments` — each is `python3 docs/user-guide/capture.py <name>` |


Sign up a new boutique with a fresh email and run the seed steps above against
it. Nothing in the demo data is required by the application.
