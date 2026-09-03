import sys
import pathlib
from playwright.sync_api import sync_playwright

APP = "http://localhost:5173/app.html"
SHOTS = pathlib.Path(__file__).parent / "screenshots"

DEMO = {
    "first": "Kavya",
    "last": "Reddy",
    "email": "kavya@demoboutique.test",
    "mobile": "9840012345",
    "password": "DemoBoutique#2026",
    "boutique": "Kanchi Threads",
}


def shot(page, folder, name):
    path = SHOTS / folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(path), full_page=True)
    print(f"  saved {path.relative_to(SHOTS.parent)}")


def dump(page, label):
    print(f"\n----- {label} -----")
    print(page.inner_text("body")[:2500])


def signup(page):
    page.goto(APP)
    page.wait_for_timeout(800)
    shot(page, "common", "02-login.png")

    page.click("text=Signup")
    page.wait_for_timeout(400)
    shot(page, "common", "03-signup-step1-account.png")

    page.fill("input[placeholder='Enter first name']", DEMO["first"])
    page.fill("input[placeholder='Enter last name']", DEMO["last"])
    page.fill("input[placeholder='Enter your email address']", DEMO["email"])
    page.fill("input[placeholder='Enter mobile number']", DEMO["mobile"])
    page.fill("input[placeholder^='Create a password']", DEMO["password"])
    page.check("input[type='checkbox']")
    shot(page, "common", "03b-signup-step1-filled.png")
    page.click("text=Create Account")
    page.wait_for_timeout(1200)
    shot(page, "common", "04-signup-step2-boutique.png")

    page.fill("input[placeholder=\"e.g. Aditi's Atelier\"]", DEMO["boutique"])
    page.fill("input[placeholder='Street, area, city, PIN']", "12 Kutchery Road, Mylapore, Chennai 600004")
    page.click("text=Create my boutique")
    page.wait_for_timeout(45000)
    dump(page, "after Create my boutique")
    shot(page, "common", "05-signup-step3-complete.png")


def login(page, email=None, password=None):

    page.goto(APP)
    page.wait_for_timeout(800)
    page.fill("input[placeholder='Enter your email']", email or DEMO["email"])
    page.fill("input[placeholder='Enter your password']", password or DEMO["password"])
    page.click("text=Login to Workspace")
    page.wait_for_timeout(5000)


def owner_dashboard(page):
    login(page)
    dump(page, "owner dashboard")
    shot(page, "owner", "10-owner-dashboard.png")




OWNER_TABS = [
    ("Dashboard", "10-owner-dashboard"),
    ("Manage Orders", "11-owner-orders"),
    ("Customers", "12-owner-customers"),
    ("Invoices", "13-owner-invoices"),
    ("Analytics", "14-owner-analytics"),
    ("Manage Fabrics", "15-owner-fabrics"),
    ("Inventory", "16-owner-inventory"),
    ("Manage Tailors", "17-owner-tailors"),
    ("Manage Designs", "18-owner-designs"),
    ("Design Work", "19-owner-design-work"),
    ("My Account", "20-owner-account"),
]


def owner_tour(page):
    login(page)
    for label, name in OWNER_TABS:
        page.click(f".portal-menu-item:has-text('{label}')")
        page.wait_for_timeout(1500)
        dump(page, label)
        shot(page, "owner", f"{name}-empty.png")




def owner_forms(page):

    login(page)
    for label, cta, name in [
        ("Manage Tailors", "Add New Tailor", "17b-owner-add-tailor"),
        ("Manage Designs", "Add New Design", "18b-owner-add-design"),
        ("Inventory", "New Item", "16b-owner-add-inventory"),
        ("Customers", "Add", "12b-owner-add-customer"),
    ]:
        page.click(f".portal-menu-item:has-text('{label}')")
        page.wait_for_timeout(1200)
        try:
            page.click(f"button:has-text('{cta}')", timeout=4000)
        except Exception as exc:
            print(f"  !! {label}: could not click {cta!r}: {str(exc)[:120]}")
            continue
        page.wait_for_timeout(1200)
        dump(page, f"{label} -> {cta}")
        shot(page, "owner", f"{name}.png")
        page.keyboard.press("Escape")
        page.wait_for_timeout(400)

def close_modal(page):
    for sel in ["button:has-text('Cancel')", "button:has-text('Close')", ".modal-close"]:
        try:
            page.click(sel, timeout=1500)
            page.wait_for_timeout(400)
            return
        except Exception:
            continue
    page.keyboard.press("Escape")


def owner_ctas(page):

    login(page)
    for label, _ in OWNER_TABS:
        page.click(f".portal-menu-item:has-text('{label}')")
        page.wait_for_timeout(1500)
        names = page.eval_on_selector_all(
            "button, .btn-primary, .btn-secondary, [role=button]",
            "els => [...new Set(els.map(e => e.innerText.trim()).filter(t => t && t.length < 40))]",
        )
        print(f"\n### {label}\n" + "\n".join(f"  - {n}" for n in names))

STAFF = [
    ("Lakshmi Iyer", "lakshmi@demoboutique.test", "Bridal lehenga, aari work", "Master Tailor (generalist)"),
    ("Ravi Kumar", "ravi@demoboutique.test", "Blouse stitching, fall & pico", "Stitching Tailor"),
    ("Sunita Rao", "sunita@demoboutique.test", "Final inspection", "QC Master"),
]


def seed_staff(page):

    login(page)
    page.click(".portal-menu-item:has-text('Manage Tailors')")
    page.wait_for_timeout(1200)
    for i, (name, email, specialty, role) in enumerate(STAFF):
        page.click("button:has-text('Add New Tailor')")
        page.wait_for_timeout(800)
        page.fill("input[placeholder='e.g. Master Shabbir']", name)
        page.fill("input[placeholder='e.g. shabbir@boutique.com']", email)
        page.fill("input[placeholder='e.g. Lehenga Specialist, Gowns']", specialty)
        page.select_option("select:below(:text('Staff Role'))", label=role)
        if i == 0:
            shot(page, "owner", "17b-owner-add-tailor-filled.png")
        page.click("button:has-text('Save Tailor')")
        page.wait_for_timeout(2500)
        body = page.inner_text("body")
        print(f"\n=== after saving {name} ===")
        print(body[body.find("Manage Tailoring Staff"):][:1800])
        if i == 0:
            shot(page, "owner", "17c-owner-tailor-credentials.png")
        close_modal(page)
        page.wait_for_timeout(600)
    shot(page, "owner", "17-owner-tailors.png")

def seed_designer(page):

    login(page)
    page.click(".portal-menu-item:has-text('Manage Designs')")
    page.wait_for_timeout(1500)
    page.fill("input[placeholder='Designer name']", "Meera Nair")
    shot(page, "owner", "18c-owner-add-designer.png")
    page.click("button:has-text('Add designer')")
    page.wait_for_timeout(2000)
    page.fill("input[placeholder='designer@boutique.com']", "meera@demoboutique.test")
    page.click("button:has-text('Grant login')")
    page.wait_for_timeout(2500)
    body = page.inner_text("body")
    print(body[body.find("Designers"):][:1200])
    shot(page, "owner", "18d-owner-designer-login.png")

def field(page, label):

    return page.locator(
        f"xpath=//label[starts-with(normalize-space(.), {label!r})]"
        "/following-sibling::input[1] | "
        f"//label[starts-with(normalize-space(.), {label!r})]"
        "/following-sibling::select[1]"
    ).first


FABRICS = [
    ("Kanchipuram Silk", "Pure mulberry silk", "Temple Red", "4200"),
    ("Chanderi Silk Cotton", "Silk blend", "Ivory Gold", "1250"),
    ("Raw Silk Dupion", "Raw silk", "Emerald", "1850"),
]

DESIGNS = [
    ("Temple Border Bridal Lehenga", "Lehenga", "Sweetheart Neck", "Cap Sleeve", "48000"),
    ("Aari Work Bridal Blouse", "Blouse", "Deep V Neck", "Elbow Sleeve", "9500"),
    ("Kanchi Silk Half Saree", "Saree", "Boat Neck", "Three Quarter", "26000"),
]

ITEMS = [
    ("FAB-KS-001", "Kanchipuram Silk — Temple Red", "FABRIC", "Temple Red", "A1", "4200", "5600", "5", "3"),
    ("TRM-ZR-002", "Zari Border 3 inch", "BORDER_TRIM", "Antique Gold", "B2", "480", "650", "10", "5"),
    ("EMB-BD-003", "Aari Beads — Ruby", "EMBELLISHMENT", "Ruby", "C1", "220", "320", "20", "10"),
]


def seed_fabrics(page):
    login(page)
    page.click(".portal-menu-item:has-text('Manage Fabrics')")
    page.wait_for_timeout(1200)
    for i, (name, material, colour, price) in enumerate(FABRICS):
        page.click("button:has-text('Add New Fabric')")
        page.wait_for_timeout(700)
        page.fill("input[placeholder='e.g. Chanderi Silk']", name)
        page.fill("input[placeholder='e.g. Silk Blend']", material)
        page.fill("input[placeholder='e.g. Aqua Blue']", colour)
        page.fill("input[placeholder='e.g. 1250']", price)
        if i == 0:
            shot(page, "owner", "15b-owner-add-fabric.png")
        page.click("button:has-text('Save Fabric')")
        page.wait_for_timeout(1800)
    shot(page, "owner", "15-owner-fabrics.png")
    dump(page, "fabrics after seeding")


def seed_designs(page):
    login(page)
    page.click(".portal-menu-item:has-text('Manage Designs')")
    page.wait_for_timeout(1500)
    page.click("button:has-text('Boutique Designs')")
    page.wait_for_timeout(1200)
    for i, (name, cat, neck, sleeve, price) in enumerate(DESIGNS):
        page.click("button:has-text('Add New Design')")
        page.wait_for_timeout(700)
        page.fill("input[placeholder='e.g. Royal Maroon Velvet Lehenga']", name)
        try:
            field(page, "Garment Category").select_option(cat)
        except Exception as exc:
            print("  !! category", cat, str(exc)[:100])
        page.fill("input[placeholder='e.g. Sweetheart Neck']", neck)
        page.fill("input[placeholder='e.g. Cap Sleeve']", sleeve)
        page.fill("input[placeholder='e.g. 45000']", price)
        if i == 0:
            shot(page, "owner", "18b-owner-add-design.png")
        page.click("button:has-text('Save Design')")
        page.wait_for_timeout(1800)
    shot(page, "owner", "18-owner-designs.png")
    dump(page, "designs after seeding")


def seed_inventory(page):
    login(page)
    page.click(".portal-menu-item:has-text('Inventory')")
    page.wait_for_timeout(1500)
    for i, (code, name, cat, colour, rack, buy, sell, reorder, minimum) in enumerate(ITEMS):
        page.click("button:has-text('New Item')")
        page.wait_for_timeout(900)
        field(page, "Item code").fill(code)
        field(page, "Name").fill(name)
        try:
            field(page, "Category").select_option(cat)
        except Exception as exc:
            print("  !! category", cat, str(exc)[:120])
        field(page, "Colour").fill(colour)
        field(page, "Rack location").fill(rack)
        field(page, "Purchase price").fill(buy)
        field(page, "Selling price").fill(sell)
        field(page, "Reorder level").fill(reorder)
        field(page, "Minimum stock").fill(minimum)
        if i == 0:
            shot(page, "owner", "16b-owner-add-inventory.png")
        page.click("button:has-text('Save')")
        page.wait_for_timeout(1800)
    shot(page, "owner", "16-owner-inventory.png")
    dump(page, "inventory after seeding")

def seed_stock(page):

    login(page)
    page.click(".portal-menu-item:has-text('Inventory')")
    page.wait_for_timeout(1800)
    for i, qty_in in enumerate(["18", "40", "500"]):
        row = page.locator("tbody tr").nth(i)
        row.locator("button:has-text('Move')").click()
        page.wait_for_timeout(900)
        field(page, "Quantity").fill(qty_in)
        field(page, "Remarks").fill("Opening stock received from supplier")
        if i == 0:
            shot(page, "owner", "16c-owner-stock-movement.png")
        page.click("button:has-text('Record movement')")
        page.wait_for_timeout(1800)
    shot(page, "owner", "16-owner-inventory.png")
    dump(page, "inventory with stock")

def probe_order_wizard(page):
    login(page)
    page.click("button:has-text('New Custom Order')")
    page.wait_for_timeout(1800)
    dump(page, "order wizard step 1")
    print("\n--- inputs ---")
    for tag in ("input", "select", "textarea", "button"):
        vals = page.eval_on_selector_all(
            tag,
            "els => els.map(e => (e.placeholder || e.getAttribute('aria-label') || e.innerText || e.name || e.type || '').trim()).filter(Boolean)",
        )
        print(f"{tag}: {vals}")
    shot(page, "owner", "30-order-step1-customer.png")

def controls(page, label=""):
    print(f"\n--- controls {label} ---")
    for tag in ("input", "select", "textarea"):
        vals = page.eval_on_selector_all(
            tag,
            "els => els.map(e => (e.placeholder || e.getAttribute('aria-label') || e.name || e.type || '') + '|' + (e.tagName))",
        )
        print(f"{tag}: {vals}")
    print("buttons:", page.eval_on_selector_all(
        "button", "els => els.map(e => e.innerText.trim()).filter(Boolean)"))


def probe_new_customer(page):
    login(page)
    page.click("button:has-text('New Custom Order')")
    page.wait_for_timeout(1500)
    page.click("button:has-text('Create New Customer')")
    page.wait_for_timeout(1500)
    body = page.inner_text("body"); print(body[body.find("Back to Home"):][:2200] if "Back to Home" in body else body[:2600])
    controls(page, "new customer")
    shot(page, "owner", "31-order-step2-new-customer.png")

CUSTOMER = {
    "first": "Ananya",
    "last": "Krishnan",
    "mobile": "9845012345",
    "email": "ananya.krishnan@example.com",
    "address": "7 Alwarpet Second Street, Chennai, Tamil Nadu",
    "city": "Chennai",
}


def create_order(page):

    login(page)
    page.click("button:has-text('New Custom Order')")
    page.wait_for_timeout(1500)
    shot(page, "owner", "30-order-step0-choose-customer.png")
    page.click("button:has-text('Create New Customer')")
    page.wait_for_timeout(1500)

    page.fill("input[placeholder='e.g. Amara']", CUSTOMER["first"])
    page.fill("input[placeholder='e.g. Singh']", CUSTOMER["last"])
    page.fill("input[placeholder='98765 43210']", CUSTOMER["mobile"])
    page.fill("input[placeholder='e.g. amara.s@example.com']", CUSTOMER["email"])
    page.fill("input[placeholder='Street name, Apartment, City, State, PIN code']", CUSTOMER["address"])
    page.fill("input[placeholder='e.g. New Delhi']", CUSTOMER["city"])
    page.click("button:has-text('Blouse'):not(:has-text('Lehenga'))")
    page.wait_for_timeout(300)
    page.click("button:text-is('Lehenga')")
    page.wait_for_timeout(600)
    shot(page, "owner", "31-order-step1-customer-details.png")
    body = page.inner_text("body")
    print(body[body.find("Dresses in this Order"):][:1200])

    page.click("button:text-is('Next')")
    page.wait_for_timeout(2500)
    shot(page, "owner", "32-order-step2-garment-details.png")

    def garment(i):
        return page.locator(".content-card").nth(i)

    def gsel(i, label, value):
        garment(i).locator(f".form-group:has(label:has-text('{label}')) select").first.select_option(label=value)

    def gput(i, label, value):
        garment(i).locator(f".form-group:has(label:has-text('{label}')) input").first.fill(value)

    gsel(0, "Blouse Type", "Princess")
    gsel(0, "Occasion", "Wedding")
    gsel(0, "Material Source", "Store Inventory Fabric")
    gsel(0, "Design Reference", "Boutique Catalog")
    gsel(0, "Trial Required", "Yes")
    gput(0, "Trial Date", "2026-09-10")
    gput(0, "Delivery Date", "2026-09-20")
    gsel(0, "Urgency", "Express")
    gsel(0, "Priority", "High")
    for label, value in [("Blouse Length", "15"), ("Shoulder", "14"), ("Upper Chest", "34"),
                         ("Chest", "36"), ("Waist", "30"), ("Armhole", "16")]:
        gput(0, label, value)
    gsel(0, "Sleeve Length", "Elbow")
    gsel(0, "Padding", "Padded")
    gsel(0, "Main Fabric", "Kanchipuram Silk — Temple Red — 40.000 Meter available")
    garment(0).locator("input[aria-label^='Quantity']").first.fill("1.2")
    shot(page, "owner", "33-order-blouse-details.png")

    gsel(1, "Lehenga Type", "A-Line")
    gsel(1, "Occasion", "Wedding")
    gsel(1, "Material Source", "Store Inventory Fabric")
    gsel(1, "Design Reference", "Boutique Catalog")
    gsel(1, "Trial Required", "Yes")
    gput(1, "Trial Date", "2026-09-10")
    gput(1, "Delivery Date", "2026-09-20")
    gsel(1, "Urgency", "Express")
    gsel(1, "Priority", "High")
    gput(1, "Waist", "30")
    gput(1, "Floor Length", "41")
    gsel(1, "Waist Finish", "Dori")
    gsel(1, "Main Fabric", "Kanchipuram Silk — Temple Red — 40.000 Meter available")
    garment(1).locator("input[aria-label^='Quantity']").first.fill("4.5")
    shot(page, "owner", "34-order-lehenga-details.png")

    page.click("button:text-is('Next')")
    page.wait_for_timeout(2500)
    body = page.inner_text("body")
    pathlib.Path("/tmp/step3.txt").write_text(body)
    shot(page, "owner", "35-order-step3-design-studio.png")

    boards = page.locator(".content-card:has(button:has-text('Add to board'))")
    for i in range(boards.count()):
        boards.nth(i).locator("button:has-text('Add to board')").first.click()
        page.wait_for_timeout(900)
    shot(page, "owner", "36-order-design-selected.png")
    page.click("button:text-is('Next')")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/step4.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "37-order-step4-fabric.png")

    page.click("text=Kanchipuram Silk - Temple Red")
    page.wait_for_timeout(800)
    shot(page, "owner", "38-order-fabric-selected.png")
    page.click("button:text-is('Next')")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/step5.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "39-order-step5-tailor.png")

    page.click("text=Lakshmi Iyer")
    page.wait_for_timeout(400)
    page.click("text=Ravi Kumar")
    page.wait_for_timeout(400)
    page.click("text=Direct Boutique Pickup")
    page.wait_for_timeout(600)
    shot(page, "owner", "40-order-staff-assigned.png")
    page.click("button:has-text('Confirm Order')")
    page.wait_for_timeout(4000)
    pathlib.Path("/tmp/step6.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "41-order-step6-review.png")
    page.click("button:has-text('Create Order & Pay')")
    page.wait_for_timeout(6000)
    pathlib.Path("/tmp/step7.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "42-order-payment-options.png")
    page.click("text=Pay Partially Now")
    page.wait_for_timeout(600)
    page.fill("input[placeholder='e.g. 24938']", "20000")
    page.check("input[type=checkbox]")
    page.wait_for_timeout(400)
    shot(page, "owner", "43-order-advance-payment.png")
    page.click("button:has-text('Confirm Order & Continue')")
    page.wait_for_timeout(8000)
    pathlib.Path("/tmp/step8.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "44-order-created.png")





def owner_data_tour(page):

    login(page)
    for label, name in OWNER_TABS:
        page.click(f".portal-menu-item:has-text('{label}')")
        page.wait_for_timeout(2000)
        shot(page, "owner", f"{name}.png")
        pathlib.Path(f"/tmp/tab-{name}.txt").write_text(page.inner_text("body"))
        print(f"  {label}: captured")


def customer_tracking(page):

    login(page)
    page.click(".portal-menu-item:has-text('Manage Orders')")
    page.wait_for_timeout(2500)
    body = page.inner_text("body")
    start = body.find("http://localhost:8000/track/")
    url = body[start:].split()[0].rstrip()
    print("tracking url:", url)
    pathlib.Path("/tmp/tracking-url.txt").write_text(url)
    page.goto(url)
    page.wait_for_timeout(3000)
    pathlib.Path("/tmp/tracking.txt").write_text(page.inner_text("body"))
    shot(page, "customer", "60-customer-order-tracking.png")


ROLES = {
    "master": ("lakshmi@demoboutique.test", "5T8zXlyrNkbS", "master", "50",
               ["My Assignments", "Manage Orders", "Customers", "Design Work", "My Account"]),
    "tailor": ("ravi@demoboutique.test", "5lsQV4xxfXIZ", "tailor", "70",
               ["My Assignments", "My Account"]),
    "designer": ("meera@demoboutique.test", "noBJXxBGKXuT", "designer", "80",
                 ["My Work", "Design Studio", "My Account"]),
    "qc": ("sunita@demoboutique.test", "DHBCanRHX42T", "master", "55",
           ["My Assignments", "My Account"]),
}


def role_tour(page, which=None):
    which = which or sys.argv[2]
    email, password, folder, base, tabs = ROLES[which]
    login(page, email, password)
    pathlib.Path(f"/tmp/{which}-landing.txt").write_text(page.inner_text("body"))
    for i, tab in enumerate(tabs):
        page.click(f".portal-menu-item:has-text('{tab}')")
        page.wait_for_timeout(2000)
        slug = tab.lower().replace(" ", "-")
        shot(page, folder, f"{int(base) + i}-{which}-{slug}.png")
        pathlib.Path(f"/tmp/{which}-{slug}.txt").write_text(page.inner_text("body"))
        print(f"  {which}/{tab}")


def assign_design_work(page):

    login(page)
    page.click(".portal-menu-item:has-text('Design Work')")
    page.wait_for_timeout(2000)
    selects = page.locator("select")
    selects.nth(0).select_option(index=1)
    page.wait_for_timeout(400)
    selects.nth(1).select_option(index=1)
    page.locator("input[type=date]").first.fill("2026-09-05")
    page.locator("textarea").first.fill(
        "Bridal blouse: temple border motif on sleeves, aari work across the yoke.")
    shot(page, "owner", "19b-owner-assign-design-work.png")
    page.click("button:has-text('Assign')")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/design-work.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "19-owner-design-work.png")


def designer_upload(page):

    email, password, folder, base, _ = ROLES["designer"]
    login(page, email, password)
    page.click(".portal-menu-item:has-text('Design Studio')")
    page.wait_for_timeout(2000)
    page.click("button:has-text('Boutique Designs')")
    page.wait_for_timeout(2000)
    shot(page, "designer", "83-designer-library.png")
    page.click("button:has-text('Upload design')")
    page.wait_for_timeout(1500)
    pathlib.Path("/tmp/designer-upload.txt").write_text(page.inner_text("body"))
    page.set_input_files("input[type=file]", str(pathlib.Path.cwd() / "media" / "design_cat_01.jpg"))
    page.wait_for_timeout(800)
    page.fill("input[placeholder='e.g. Hand-embroidered bridal lehenga']",
              "Temple Motif Aari Blouse — Ananya")
    sels = page.locator("select")
    sels.nth(0).select_option(label="Blouse")
    sels.nth(1).select_option(label="Meera Nair")
    page.fill("input[placeholder='0']", "9500")
    sels.nth(3).select_option(label="Complex")
    page.fill("input[placeholder='e.g. 18']", "22")
    shot(page, "designer", "84-designer-upload-form.png")
    page.click("button:has-text('Add to library')")
    page.wait_for_timeout(4000)
    shot(page, "designer", "85-designer-design-added.png")

    page.click(".portal-menu-item:has-text('My Work')")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/designer-work-after.txt").write_text(page.inner_text("body"))
    page.locator("select").last.select_option(index=1)
    page.fill("input[placeholder='Anything the owner should know']",
              "Yoke aari in antique gold, sleeve border matched to the lehenga.")
    shot(page, "designer", "86-designer-submit-work.png")
    page.click("button:has-text('Submit design')")
    page.wait_for_timeout(3000)
    pathlib.Path("/tmp/designer-submitted.txt").write_text(page.inner_text("body"))
    shot(page, "designer", "87-designer-work-submitted.png")


def owner_review_design(page):
    login(page)
    page.click(".portal-menu-item:has-text('Design Work')")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/owner-review.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "19c-owner-review-design-work.png")
    page.click("button:has-text('Approve')")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/owner-approved.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "19d-owner-design-approved.png")


def probe_stage(page):
    email, password, *_ = ROLES["master"]
    login(page, email, password)
    page.wait_for_timeout(1500)
    page.click("text=Fabric Confirmed")
    page.wait_for_timeout(1500)
    pathlib.Path("/tmp/stage-modal.txt").write_text(page.inner_text("body"))
    shot(page, "master", "57-master-stage-update.png")
    page.click("button:has-text('Start In-Progress')")
    page.wait_for_timeout(2500)
    controls(page, "stage in progress")
    pathlib.Path("/tmp/stage-inprogress.txt").write_text(page.inner_text("body"))
    shot(page, "master", "58-master-stage-in-progress.png")


STAGE_FLOW = [
    "Fabric Confirmed", "Pattern Cutting", "Maggam Work", "Assigned to Tailor",
    "Stitching In Progress", "Stitching Completed", "Hemming & Finishing",
    "Pressing", "Master Quality Check",
]


def stage_buttons(page, stage):
    page.click(f"text={stage}")
    page.wait_for_timeout(1200)
    labels = page.eval_on_selector_all("button", "els => els.map(e => e.innerText.trim())")
    print(f"{stage}: {[l for l in labels if l and 'Inbox' not in l]}")
    page.click("button:has-text('Close')")
    page.wait_for_timeout(500)


def probe_stage2(page):
    email, password, *_ = ROLES["master"]
    login(page, email, password)
    page.wait_for_timeout(1500)
    stage_buttons(page, "Fabric Confirmed")
    stage_buttons(page, "Pattern Cutting")


def run_production(page):

    email, password, *_ = ROLES["master"]
    login(page, email, password)
    page.wait_for_timeout(1500)
    for stage in STAGE_FLOW:
        for action in ("Start In-Progress", "Complete Stage"):
            if page.locator("button:has-text('Close')").count():
                try:
                    page.click("button:has-text('Close')", timeout=2000)
                    page.wait_for_timeout(500)
                except Exception:
                    pass
            page.click(f"text={stage}")
            page.wait_for_timeout(1200)
            try:
                page.click(f"button:has-text('{action}')", timeout=4000)
                page.wait_for_timeout(2000)
            except Exception as exc:
                print(f"  !! {stage} / {action}: {str(exc)[:80]}")
        print(f"  {stage} done")
    shot(page, "master", "59-master-stages-complete.png")
    pathlib.Path("/tmp/master-after-stages.txt").write_text(page.inner_text("body"))


TAILOR_STAGES = ["Stitching In Progress", "Stitching Completed"]
MASTER_STAGES_LATE = ["Hemming & Finishing", "Pressing", "Master Quality Check",
                      "Trial Scheduled", "Trial Completed", "Ready for Delivery"]


def advance(page, role, stages, folder, shots=()):
    email, password, *_ = ROLES[role]
    login(page, email, password)
    page.wait_for_timeout(1500)
    for stage in stages:
        for action in ("Start In-Progress", "Complete Stage"):
            if page.locator("button:has-text('Close')").count():
                try:
                    page.click("button:has-text('Close')", timeout=2000)
                    page.wait_for_timeout(500)
                except Exception:
                    pass
            page.click(f"text={stage}")
            page.wait_for_timeout(1200)
            if stage in shots and action == "Start In-Progress":
                shot(page, folder, f"{shots[stage]}.png")
            try:
                page.click(f"button:has-text('{action}')", timeout=4000)
                page.wait_for_timeout(2000)
            except Exception:
                pass
        print(f"  {role}: {stage}")


def tailor_production(page):
    advance(page, "tailor", TAILOR_STAGES, "tailor",
            {"Stitching In Progress": "72-tailor-stage-stitching"})
    shot(page, "tailor", "73-tailor-stitching-done.png")


def master_production_late(page):
    advance(page, "master", MASTER_STAGES_LATE, "master",
            {"Master Quality Check": "58-master-quality-check"})
    shot(page, "master", "59-master-ready-for-delivery.png")


def probe_invoice(page):
    login(page)
    page.click(".portal-menu-item:has-text('Invoices')")
    page.wait_for_timeout(2500)
    controls(page, "invoices")
    page.click("button:has-text('View Invoice')")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/invoice.txt").write_text(page.inner_text("body"))
    controls(page, "invoice view")
    shot(page, "owner", "13b-owner-invoice.png")


def settle_payment(page):

    login(page)
    page.click(".portal-menu-item:has-text('Invoices')")
    page.wait_for_timeout(2500)
    shot(page, "owner", "13-owner-invoices.png")
    amount = page.locator("input[aria-label^='Amount paid']")
    amount.fill("49875")
    amount.press("Enter")
    page.wait_for_timeout(2000)
    page.locator("select").last.select_option(label="Paid")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/invoice-paid.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "13c-owner-invoice-paid.png")


def owner_order_wrapup(page):

    login(page)
    page.click(".portal-menu-item:has-text('Manage Orders')")
    page.wait_for_timeout(2500)
    shot(page, "owner", "11-owner-orders.png")
    photo = str(pathlib.Path.cwd() / "media" / "completed_garments" / "g.png")
    for view in ("Front view", "Back view"):
        page.locator("select").last.select_option(label=view)
        page.set_input_files("input[type=file]", photo)
        page.wait_for_timeout(1200)
        page.click("button:has-text('Add photo')")
        page.wait_for_timeout(2500)
    shot(page, "owner", "11b-owner-finished-photos.png")
    page.click("button:has-text('Share with customer')")
    page.wait_for_timeout(2500)
    shot(page, "owner", "11c-owner-photos-shared.png")

    for _ in range(page.locator("button:has-text('Mark sent')").count()):
        page.locator("button:has-text('Mark sent')").first.click()
        page.wait_for_timeout(1500)
    shot(page, "owner", "11d-owner-customer-updates.png")
    pathlib.Path("/tmp/orders-tab.txt").write_text(page.inner_text("body"))


def deliver_order(page):

    login(page)
    page.click(".portal-menu-item:has-text('Manage Orders')")
    page.wait_for_timeout(2500)
    for action in ("Start In-Progress", "Complete Stage"):
        if page.locator("button:has-text('Close')").count():
            try:
                page.click("button:has-text('Close')", timeout=2000)
                page.wait_for_timeout(500)
            except Exception:
                pass
        page.click("text=Delivered >> nth=-1")
        page.wait_for_timeout(1200)
        try:
            page.click(f"button:has-text('{action}')", timeout=4000)
            page.wait_for_timeout(2000)
        except Exception as exc:
            print("  !!", action, str(exc)[:80])
    page.locator("select").first.select_option(label="Delivered")
    page.wait_for_timeout(2500)
    shot(page, "owner", "11e-owner-order-delivered.png")
    pathlib.Path("/tmp/delivered.txt").write_text(page.inner_text("body"))


def owner_customer_detail(page):
    login(page)
    page.click(".portal-menu-item:has-text('Customers')")
    page.wait_for_timeout(2500)
    shot(page, "owner", "12-owner-customers.png")
    page.click("text=Ananya Krishnan")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/customer-detail.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "12b-owner-customer-profile.png")


def owner_notifications(page):
    login(page)
    page.click("button:has-text('Inbox Alerts')")
    page.wait_for_timeout(2000)
    pathlib.Path("/tmp/notifications.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "21-owner-notifications.png")
def superadmin_login(page):
    page.goto("http://localhost:5173/superadmin.html")
    page.wait_for_timeout(2500)
    pathlib.Path("/tmp/superadmin.txt").write_text(page.inner_text("body"))
    shot(page, "super-admin", "90-superadmin-login.png")


def login_errors(page):

    page.goto(APP)
    page.wait_for_timeout(1000)
    page.fill("input[placeholder='Enter your email']", DEMO["email"])
    page.fill("input[placeholder='Enter your password']", "not-the-real-one")
    page.click("text=Login to Workspace")
    page.wait_for_timeout(3000)
    print(page.inner_text("body")[:600])
    shot(page, "common", "06-login-invalid.png")
    page.goto(APP)
    page.wait_for_timeout(1000)
    page.click("text=Forgot password?")
    page.wait_for_timeout(1500)
    pathlib.Path("/tmp/forgot.txt").write_text(page.inner_text("body"))
    shot(page, "common", "07-forgot-password.png")


def tryon_visualizer(page):

    login(page)
    page.click("button:has-text('New Custom Order')")
    page.wait_for_timeout(1500)
    shot(page, "owner", "46-order-drafts.png")
    page.locator("button:has-text('Resume')").first.click()
    page.wait_for_timeout(3000)
    for _ in range(5):
        if page.locator("text=Boutique Fabrics").count():
            break
        for label in ("button:text-is('Next')", "button:has-text('Back')"):
            try:
                page.click(label, timeout=4000)
                page.wait_for_timeout(2500)
                break
            except Exception:
                continue
    pathlib.Path("/tmp/tryon-step.txt").write_text(page.inner_text("body"))
    page.click("text=Kanchipuram Silk - Temple Red")
    page.wait_for_timeout(1200)
    shot(page, "owner", "47-order-fabric-visualizer.png")
    page.click("button:has-text('Try On / Drape Fabric')")
    page.wait_for_timeout(1500)
    shot(page, "owner", "48-tryon-modal.png")
    page.click("button:has-text('Start Try On')")
    page.wait_for_timeout(4000)
    pathlib.Path("/tmp/tryon-result.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "49-tryon-result.png")


def discard_drafts(page):

    login(page)
    page.click("button:has-text('New Custom Order')")
    page.wait_for_timeout(2000)
    page.on("dialog", lambda d: d.accept())
    while page.locator("button:has-text('Discard')").count():
        page.locator("button:has-text('Discard')").first.click()
        page.wait_for_timeout(1500)
    print("drafts left:", page.locator("button:has-text('Resume')").count())
    shot(page, "owner", "46-order-drafts.png")


def inventory_tabs(page):

    login(page)
    page.click(".portal-menu-item:has-text('Inventory')")
    page.wait_for_timeout(2000)
    for i, tab in enumerate(["Items", "Catalogue", "Locations", "Recipes",
                             "Purchase Orders", "Suppliers", "Reports"]):
        page.click(f"button:text-is('{tab}')")
        page.wait_for_timeout(2500)
        slug = tab.lower().replace(" ", "-")
        shot(page, "owner", f"16-{i}-inventory-{slug}.png")
        pathlib.Path(f"/tmp/inv-{slug}.txt").write_text(page.inner_text("body"))
        print(f"  inventory/{tab}")


def owner_appointments(page):
    login(page)
    page.click("text=Book Appointment")
    page.wait_for_timeout(2000)
    pathlib.Path("/tmp/appointments.txt").write_text(page.inner_text("body"))
    shot(page, "owner", "22-owner-book-appointment.png")
    field(page, "Client").select_option(label="Ananya Krishnan")
    field(page, "Type").select_option(label="Design Consultation")
    page.locator("input[type='datetime-local']").fill("2026-09-02T11:00")
    field(page, "With").select_option(label="Lakshmi Iyer")
    page.locator("textarea").last.fill("Reception lehenga — discuss colour and border.")
    shot(page, "owner", "22b-owner-appointment-filled.png")
    page.click("button:has-text('Book appointment')")
    page.wait_for_timeout(2500)
    shot(page, "owner", "10-owner-dashboard.png")
    pathlib.Path("/tmp/appointment-booked.txt").write_text(page.inner_text("body"))


def delete_duplicate_design(page):

    login(page)
    page.on("dialog", lambda d: d.accept())
    page.click(".portal-menu-item:has-text('Manage Designs')")
    page.wait_for_timeout(2000)
    page.click("button:has-text('Boutique Designs')")
    page.wait_for_timeout(2000)
    page.click("button:has-text('Blouse')")
    page.wait_for_timeout(2000)
    tiles = page.locator("text=Temple Motif Aari Blouse")
    print("tiles before:", tiles.count())
    tiles.first.click()
    page.wait_for_timeout(1500)
    page.click("button:has-text('Delete')")
    page.wait_for_timeout(2500)
    print("tiles after:", page.locator("text=Temple Motif Aari Blouse").count())
    shot(page, "owner", "18-owner-designs.png")


def verify_gaps(page):

    login(page)

    page.click(".portal-menu-item:has-text('Manage Tailors')")
    page.wait_for_timeout(2000)
    body = page.inner_text("body")
    print("staff roster mentions Sunita Rao (QC Master):", "Sunita Rao" in body)

    page.click(".portal-menu-item:has-text('Manage Designs')")
    page.wait_for_timeout(2000)
    page.click("button:has-text('Boutique Designs')")
    page.wait_for_timeout(2000)
    lib = page.inner_text("body")
    start = lib.find("Uncategorised")
    print("library tiles near Uncategorised:", repr(lib[start:start + 20]))
    print("Blouse tile count:", lib.count("Blouse"))

    page.click(".portal-menu-item:has-text('Dashboard')")
    page.wait_for_timeout(1500)
    page.click("button:has-text('New Custom Order')")
    page.wait_for_timeout(1500)
    page.click("button:has-text('Create New Customer')")
    page.wait_for_timeout(1500)
    page.click("button:has-text('Blouse'):not(:has-text('Lehenga'))")
    page.click("button:text-is('Lehenga')")
    page.wait_for_timeout(800)
    page.fill("input[placeholder='e.g. Amara']", "Gap")
    page.fill("input[placeholder='e.g. Singh']", "Check")
    page.fill("input[placeholder='98765 43210']", "9000000000")
    page.fill("input[placeholder='e.g. amara.s@example.com']", "gap@check.test")
    page.fill("input[placeholder='Street name, Apartment, City, State, PIN code']", "Chennai")
    page.click("button:text-is('Next')")
    page.wait_for_timeout(2500)
    dupes = page.evaluate()
    print("duplicate element ids on the garment step:", dupes[:12], "total", len(dupes))


SITE = "http://localhost:4173"

SITE_PAGES = [
    ("/", "01-landing-page"),
    ("/what-it-is/", "01b-site-what-it-is"),
    ("/modules/", "01c-site-modules"),
    ("/lifecycle/", "01d-site-lifecycle"),
    ("/for-customers/", "01e-site-for-customers"),
    ("/demo/", "01f-site-demo-request"),
    ("/faq/", "01g-site-faq"),
]


def landing_site(page):

    for path, name in SITE_PAGES:
        page.goto(SITE + path)
        page.wait_for_timeout(1500)
        shot(page, "common", f"{name}.png")
        pathlib.Path(f"/tmp/site-{name}.txt").write_text(page.inner_text("body")[:3000])


MOBILE = {"width": 390, "height": 844}


def mobile_tour(page):

    page.goto(APP)
    page.wait_for_timeout(1200)
    shot(page, "mobile", "m01-login.png")

    login(page)
    shot(page, "mobile", "m02-owner-dashboard.png")
    page.click("button:has-text('Menu')")
    page.wait_for_timeout(1200)
    shot(page, "mobile", "m03-owner-menu.png")
    for label, name in [("Manage Orders", "m04-owner-orders"),
                        ("Customers", "m05-owner-customers"),
                        ("Inventory", "m06-owner-inventory"),
                        ("Invoices", "m07-owner-invoices")]:
        if not page.locator("aside.portal-sidebar.mobile-open").count():
            page.click("button:has-text('Menu')")
            page.wait_for_timeout(1000)
        page.click(f"aside.portal-sidebar .portal-menu-item:has-text('{label}')")
        page.wait_for_timeout(2000)
        shot(page, "mobile", f"{name}.png")

    for role, name in [("tailor", "m08-tailor-assignments"),
                       ("designer", "m09-designer-work")]:
        page.evaluate("localStorage.clear(); sessionStorage.clear()")
        email, password, *_ = ROLES[role]
        login(page, email, password)
        shot(page, "mobile", f"{name}.png")

    page.goto(pathlib.Path("/tmp/tracking-url.txt").read_text().strip())
    page.wait_for_timeout(2500)
    shot(page, "mobile", "m10-customer-tracking.png")


if __name__ == "__main__":
    step = sys.argv[1] if len(sys.argv) > 1 else "signup"
    viewport = MOBILE if step.startswith("mobile") else {"width": 1440, "height": 900}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport=viewport)
        globals()[step](page)
        browser.close()
