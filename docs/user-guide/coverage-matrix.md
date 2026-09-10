
What was actually exercised in the running build while writing the
[User Guide](README.md), and what was not.

**Build:** branch `MSK-CL`, commit `ccfed28` · **Captured:** 27 Aug 2026
**Method:** every ✅ under *Tested* means the flow was performed in a real
browser against the running app by [`capture.py`](capture.py), not read from
source.

Legend — ✅ done · ⚠️ partial · ❌ not done · **n/a** not applicable

---


| Role | Module | Flow | Tested | Screenshot | Documented |
|---|---|---|---|---|---|
| — | Public site | Home, What it is, Modules, Lifecycle, For customers, Demo, FAQ | ✅ | ✅ | ✅ §4 |
| — | Auth | Sign up a new boutique (3 steps, schema creation) | ✅ | ✅ | ✅ §2 |
| — | Auth | Sign in | ✅ | ✅ | ✅ §5 |
| — | Auth | Invalid credentials | ✅ | ✅ | ✅ §5 |
| — | Auth | Forgot password — form reached | ⚠️ reset email not delivered (no SMTP) | ✅ | ✅ §5 |
| — | Auth | Logout | ✅ | n/a | ✅ §5 |
| Owner | Dashboard | Empty state | ✅ | ✅ | ✅ §6.1 |
| Owner | Dashboard | Populated: orders, progress, appointments | ✅ | ✅ | ✅ §6.1 |
| Owner | Account | View boutique profile and settings | ✅ | ✅ | ✅ §6.2, §24 |
| Owner | Account | Edit and save boutique profile | ❌ | ✅ (form) | ✅ §6.2 |
| Owner | Team | Roster, empty and populated | ✅ | ✅ | ✅ §6.3 |
| Owner | Team | Add staff (Master, Tailor, QC Master) | ✅ ×3 | ✅ | ✅ §6.3 |
| Owner | Team | One-time credentials modal | ✅ | ✅ | ✅ §6.3 |
| Owner | Team | Edit / disable a staff member | ❌ | ❌ | ⚠️ named only |
| Owner | Customers | Directory, filters | ✅ | ✅ | ✅ §6.4 |
| Owner | Customers | Create (via order wizard) | ✅ | ✅ | ✅ §9 |
| Owner | Customers | Profile: measurements, version history, orders, style profile | ✅ | ✅ | ✅ §6.4 |
| Owner | Customers | Edit / deactivate | ❌ | ❌ | ✅ §31.11 (absent) |
| Owner | Designs | Dashboard counters and panels | ✅ | ✅ | ✅ §7 |
| Owner | Designs | Add catalogue design | ✅ ×3 | ✅ | ✅ §7 |
| Owner | Designs | Add designer + grant login | ✅ | ✅ | ✅ §7 |
| Owner | Designs | Library grouped by garment | ✅ | ✅ | ✅ §7, §31.3 |
| Owner | Designs | Edit / delete a design | ⚠️ delete attempted, control not reached | ❌ | ⚠️ named only |
| Owner | Design Work | Assign a garment to a designer | ✅ | ✅ | ✅ §8.7 |
| Owner | Design Work | Approve submitted work | ✅ | ✅ | ✅ §8.6 |
| Owner | Design Work | Request changes | ❌ | ✅ (control) | ✅ §8.6 |
| Owner | Fabrics | Library, add fabric | ✅ ×3 | ✅ | ✅ §9 step 4 |
| Owner | Fabrics | Edit / delete fabric | ❌ | ✅ (controls) | ⚠️ named only |
| Owner | Inventory | Items list, empty and populated | ✅ | ✅ | ✅ §12 |
| Owner | Inventory | Create item | ✅ ×3 | ✅ | ✅ §12 |
| Owner | Inventory | Stock-in movement | ✅ ×3 | ✅ | ✅ §12 |
| Owner | Inventory | Reserve / consume via an order | ✅ (automatic, verified in the ledger) | ✅ | ✅ §12 |
| Owner | Inventory | Reorder alert | ✅ (raised on the demo data) | ✅ | ✅ §12, §21 |
| Owner | Inventory | Catalogue, Locations, Recipes, Purchase Orders, Suppliers, Reports | ⚠️ opened, not transacted | ✅ ×6 | ✅ §12 |
| Owner | Orders | Wizard step 0 — new vs existing, drafts | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Step 1 — customer + garment picker | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Step 2 — two garment cards in full | ✅ | ✅ ×3 | ✅ §9, §10 |
| Owner | Orders | Step 3 — AI Design Studio, add to board | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Step 4 — fabric selection | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Step 5 — staff + delivery method | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Step 6 — cost breakdown | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Payment: partial advance | ✅ | ✅ | ✅ §9, §16 |
| Owner | Orders | Payment: pay in full | ❌ | ✅ (option) | ✅ §16 |
| Owner | Orders | Order confirmed | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Save as draft, resume, discard | ✅ | ✅ | ✅ §9 |
| Owner | Orders | Registry, search, status filters | ✅ | ✅ | ✅ §9, §22 |
| Owner | Orders | Update order status | ✅ (to Delivered) | ✅ | ✅ §15 |
| Owner | Orders | Finished-garment photos: upload + publish | ✅ ×2 views | ✅ | ✅ §18 |
| Owner | Orders | Customer updates: mark sent | ✅ ×5 | ✅ | ✅ §18 |
| Owner | Orders | Open WhatsApp | ❌ (leaves the product) | ✅ (control) | ✅ §18 |
| Owner | Orders | Courier delivery method | ❌ | ❌ | ⚠️ named only |
| Owner | Invoices | List + KPIs | ✅ | ✅ | ✅ §17 |
| Owner | Invoices | View invoice | ✅ — **defect found**, see §31.10 | ✅ | ✅ §17 |
| Owner | Invoices | Record balance, set Paid | ✅ | ✅ | ✅ §16 |
| Owner | Invoices | Print / save as PDF | ❌ (browser dialog) | ❌ | ✅ §17 |
| Owner | Analytics | All panels with real data | ✅ | ✅ | ✅ §23 |
| Owner | Appointments | Book an appointment | ✅ | ✅ | ✅ §27 |
| Owner | Appointments | Edit / cancel | ❌ | ❌ | ❌ |
| Owner | Notifications | Inbox Alerts with live alerts | ✅ | ✅ | ✅ §21 |
| Owner | Try-On | Visualizer modal + Start Try On | ✅ | ✅ | ✅ §20, §31.1 |
| Master | Assignments | Dashboard, measurements, spec | ✅ | ✅ | ✅ §13 |
| Master | Production | Stage modal, start, complete, skip | ✅ (9 stages) | ✅ | ✅ §13, §15 |
| Master | Production | Verification checklist | ⚠️ shown, not submitted | ✅ | ✅ §13 |
| Master | Production | Assign a stage to someone | ❌ | ✅ (control) | ✅ §13 |
| Master | Other screens | Manage Orders, Customers, Design Work, My Account | ✅ | ✅ ×4 | ✅ §13 |
| Master | Permissions | Blocked from stitching stages | ✅ (observed) | n/a | ✅ §15 |
| Tailor | Assignments | Dashboard, measurements, spec, materials | ✅ | ✅ | ✅ §14 |
| Tailor | Production | Stitching In Progress → Stitching Completed | ✅ | ✅ | ✅ §14 |
| Tailor | Account | My Account | ✅ | ✅ | ✅ §14 |
| Tailor | Permissions | Two-item menu, no prices | ✅ (observed) | ✅ | ✅ §3, §14 |
| Specialist | Assignments | QC Master signs in and sees their queue | ✅ | ✅ | ✅ §13 |
| Specialist | Team | Appears on Manage Tailors | ❌ **defect** | ✅ (absence) | ✅ §31.5 |
| Designer | My Work | Queue with brief and garment spec | ✅ | ✅ | ✅ §8.2 |
| Designer | Design Studio | Library | ✅ | ✅ | ✅ §8.3 |
| Designer | Design Studio | Upload a design with an image | ✅ | ✅ | ✅ §8.4 |
| Designer | My Work | Submit design against the work | ✅ | ✅ | ✅ §8.5 |
| Designer | Account | My Account | ✅ | ✅ | ✅ §8 |
| Designer | Permissions | No customers / orders / money | ✅ (observed + source) | ✅ | ✅ §3 |
| Customer | Tracking | Open the signed link | ✅ | ✅ | ✅ §19 |
| Customer | Tracking | 15 stages timestamped | ✅ | ✅ | ✅ §19 |
| Customer | Tracking | Published photos | ✅ | ✅ | ✅ §19 |
| Customer | Tracking | Payment + collection blocks | ✅ | ✅ | ✅ §19 |
| Customer | Tracking | On a phone | ✅ | ✅ | ✅ §25 |
| Customer | Try-On | Any customer-facing try-on | **does not exist** | n/a | ✅ §20, §31.1 |
| Super Admin | Console | Sign-in screen | ✅ | ✅ | ✅ §26 |
| Super Admin | Console | Every screen behind sign-in | ❌ — no platform credentials | ❌ | ⚠️ §26, from source |

---


| Workflow | Status |
|---|---|
| Boutique signup and schema creation | ✅ end to end |
| Staff creation with logins | ✅ 3 accounts, all verified by signing in |
| Designer creation with login | ✅ verified by signing in |
| Customer creation | ✅ |
| Design library management | ✅ create; ⚠️ edit/delete not completed |
| Design work: assign → upload → submit → approve | ✅ end to end, three roles |
| Order creation, multi-garment | ✅ end to end |
| Measurements: capture, version, reach the floor | ✅ |
| Inventory: create → stock in → reserve → consume | ✅ verified in the ledger |
| Team assignment | ✅ |
| Production: all 15 stages | ✅ across Owner, Master and Tailor accounts |
| Master QC | ✅ stage completed; ⚠️ checklist not submitted |
| Payments: advance then balance | ✅ |
| Invoice | ✅ viewed; ❌ not printed |
| Customer communication | ✅ composed, queued, marked sent; ❌ not actually sent via WhatsApp |
| Finished-garment photos | ✅ uploaded and published |
| Order tracking | ✅ before and after production |
| Try-On | ✅ exercised — and found to be a mock |
| Delivery and completion | ✅ order reached Delivered / Paid |
| Appointments | ✅ booked |
| Notifications | ✅ observed |
| Mobile | ✅ 10 screens at 390×844 |
| Super Admin | ❌ blocked on credentials |

---


```text
docs/user-guide/screenshots/
├── common/       14   public site, sign-in, signup, errors, recovery
├── owner/        61   every owner screen, the full order wizard, try-on
├── master/       10   assignments, stage transitions, QC, specialist view
├── tailor/        4   assignments, stitching stages
├── designer/      8   work queue, library, upload, submit
├── customer/      1   the public tracking page
├── mobile/       10   owner, tailor, designer and customer at 390×844
└── super-admin/   1   console sign-in
                 ───
                 119
```

All captured at 1440×900 (mobile at 390×844), full page, by `capture.py`.

---


| Not covered | Why |
|---|---|
| Super Admin console screens | Needs platform-administrator credentials, which are not part of the boutique demo data and which this documentation pass could not create. **This is the one significant hole in the guide** — §26 is written from the shipped code and the existing handoff document, not from the running console. |
| Courier delivery | The demo order used boutique pickup; courier fields (service, tracking number, shipping address) appear only on that path |
| Edit and delete paths | Fabrics, designs, staff and appointments were created but not edited or removed |
| Print to PDF | Opens the browser's own dialog, outside the application |
| Actually sending WhatsApp | Hands off to WhatsApp, outside the application |
| Password reset email | No SMTP configured on this environment |
| Purchase orders, suppliers, recipes, locations | Panels opened and documented; no transactions performed |
| Tablet breakpoint | Desktop and phone were captured; 768 px was not |
| Multiple concurrent boutiques | Isolation is documented from the architecture, not demonstrated side by side |

---


```bash
./start.sh

python3 docs/user-guide/capture.py signup
python3 docs/user-guide/capture.py seed_staff
python3 docs/user-guide/capture.py seed_designer
python3 docs/user-guide/capture.py seed_fabrics
python3 docs/user-guide/capture.py seed_designs
python3 docs/user-guide/capture.py seed_inventory
python3 docs/user-guide/capture.py seed_stock

python3 docs/user-guide/capture.py create_order
python3 docs/user-guide/capture.py assign_design_work
python3 docs/user-guide/capture.py designer_upload
python3 docs/user-guide/capture.py owner_review_design
python3 docs/user-guide/capture.py run_production
python3 docs/user-guide/capture.py tailor_production
python3 docs/user-guide/capture.py master_production_late
python3 docs/user-guide/capture.py settle_payment
python3 docs/user-guide/capture.py owner_order_wrapup
python3 docs/user-guide/capture.py deliver_order

python3 docs/user-guide/capture.py owner_data_tour
python3 docs/user-guide/capture.py owner_customer_detail
python3 docs/user-guide/capture.py inventory_tabs
python3 docs/user-guide/capture.py owner_appointments
python3 docs/user-guide/capture.py owner_notifications
python3 docs/user-guide/capture.py role_tour master
python3 docs/user-guide/capture.py role_tour tailor
python3 docs/user-guide/capture.py role_tour designer
python3 docs/user-guide/capture.py customer_tracking
python3 docs/user-guide/capture.py tryon_visualizer
python3 docs/user-guide/capture.py mobile_tour
python3 docs/user-guide/capture.py login_errors
python3 docs/user-guide/capture.py superadmin_login
python3 docs/user-guide/capture.py landing_site      # needs `npm run build` + preview on 4173

python3 docs/user-guide/capture.py verify_gaps
```

`verify_gaps` re-tests three of the findings in §31 — the missing specialist
roster, the Uncategorised design grouping, and the duplicate element ids — and
prints what it finds. If it comes back clean, those entries can be struck from
the guide.
