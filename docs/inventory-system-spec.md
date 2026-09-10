
This document is the implementation specification to hand to an AI coding agent. It references `01-maggam-embroidery-materials.md` and `02-apparel-ecosystem-checklist.md` as the canonical source inventory catalogs.

The Inventory module is the backbone of the Boutique CRM and must support the complete lifecycle of every inventory item from procurement to customer delivery.


The uploaded inventory documents (`01-maggam-embroidery-materials.md` and `02-apparel-ecosystem-checklist.md`) are the **single source of truth**.

**The implementation AI MUST NOT:**

- Omit any inventory category.
- Omit any material.
- Merge different materials into generic categories.
- Ignore any accessory or consumable.
- Ignore embroidery materials.
- Ignore packaging materials.
- Ignore branding materials.
- Ignore tools and machines.
- Ignore customer-supplied materials.
- Ignore warehouse movement.
- Ignore inventory transactions.
- Ignore waste tracking.
- Ignore reserved inventory.
- Ignore Bills of Materials (BOM).
- Ignore dress-specific material requirements.

Every item listed in the uploaded inventory documents must exist in the database under its appropriate category.

This includes (but is not limited to):

- Product Planning & Design Assets
- All Fabric Types
- Interlining & Support Materials
- Sewing Threads
- Buttons
- Zippers
- Elastics
- Labels & Branding
- Decorative Materials
- Complete Maggam / Aari / Zardosi Materials
- Printing Materials
- Garment Accessories
- Pattern Making Materials
- Cutting Room Materials
- Sewing Machines
- Finishing Equipment
- QC Equipment
- Packaging Materials
- Warehouse Assets
- Retail Assets
- E-commerce Assets
- Logistics Materials
- Women's Clothing Categories
- Men's Clothing Categories
- Boys' Clothing Categories
- Girls' Clothing Categories
- Customer Delivery Materials

Additionally, every individual item inside these categories (every fabric type, thread type, bead type, stone type, lace type, glue, measuring tool, embroidery material, etc.) must be preserved exactly as provided in the source documents, without omission or replacement.

The complete Maggam/Aari/Zardosi material list — including every listed fabric, embroidery thread, needle, frame, bead type, stone type, sequin, mirror, traditional Zardosi material, lace, appliqué material, cord, backing material, adhesive, marking tool, cutting tool, measuring tool, finishing material, decorative embellishment, luxury embellishment, specialty material, and tool/accessory — must also be preserved exactly as provided.

---


Every inventory item must support the following lifecycle:

```
Supplier
    ↓
Purchase Order
    ↓
Goods Received
    ↓
Inventory Added
    ↓
Warehouse Assignment
    ↓
Available for Orders
    ↓
Reserved for Order
    ↓
Transferred to Production
    ↓
Consumed
    ↓
Waste / Damage Tracking
    ↓
Finished Product
    ↓
Packaging
    ↓
Customer Delivery
```

No inventory deduction should occur directly. Inventory must always move through transactions.


- Purchase
- Goods Receipt
- Reservation
- Reservation Release
- Consumption
- Return to Stock
- Transfer
- Adjustment
- Damage
- Waste
- Customer Return
- Supplier Return

Every transaction must remain in history permanently.

---


When an order is created:

1. Generate a Bill of Materials (BOM).
2. Check inventory availability.
3. Reserve required materials.
4. Prevent double allocation.
5. Deduct inventory only when production confirms consumption.
6. Record actual quantities used.
7. Record waste.
8. Return unused reserved materials to stock.
9. Deduct packaging materials at dispatch.
10. Complete inventory reconciliation before closing the order.

---


Every dress/design must support a configurable BOM.

The BOM must support:

- Multiple fabrics
- Multiple linings
- Interlinings
- Embroidery materials
- Threads
- Accessories
- Labels
- Packaging
- Customer-supplied materials
- Optional materials
- Quantity formulas
- Unit conversions
- Waste allowance

The BOM becomes the source for automatic inventory reservation.

---


Customer-owned materials must **never** be added to boutique inventory. Track separately:

- Customer fabric
- Customer borders
- Customer lace
- Customer accessories
- Customer embroidery materials

Each item should have:

- Received Quantity
- Used Quantity
- Remaining Quantity
- Returned Quantity
- Damaged Quantity

These items are linked only to that customer's order.

---


Inventory must support movement between:

- Main Store
- Warehouse
- Workshop
- Cutting Unit
- Embroidery Unit
- Tailor/Master
- Finishing Unit
- Showroom

Every transfer must maintain complete traceability.

---


The system must calculate:

- Current Stock
- Reserved Stock
- Available Stock
- Low Stock
- Reorder Level
- Material Consumption
- Fabric Consumption
- Embroidery Material Consumption
- Packaging Consumption
- Waste %
- Damage %
- Cost per Order
- Inventory Value
- Supplier Performance
- Material Movement History
- Order-wise Material Usage

---


**The implementation AI must parse and preserve every inventory category and every individual inventory item from the referenced documents exactly as provided. No category, subcategory, material, accessory, consumable, tool, asset, embellishment, packaging component, or workflow step may be omitted, merged, renamed, or simplified unless explicitly instructed.**

This instruction ensures the implementation remains exhaustive and production-ready, with `01-maggam-embroidery-materials.md` and `02-apparel-ecosystem-checklist.md` serving as the canonical inventory catalog.
