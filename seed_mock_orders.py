import os
import django

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django.contrib.auth.models import User
from tenants.models import BoutiqueTenant
from django_tenants.utils import schema_context
from crm_api.models import Customer, Measurement, Tailor, Order, OrderStageHistory, Notification
import datetime

def seed_tenant_orders(schema_name):
    print(f"Seeding mock customers, team users, and orders for schema: {schema_name}")
    with schema_context(schema_name):
        # 1. Clear existing orders/customers/tailors to start clean
        OrderStageHistory.objects.all().delete()
        Order.objects.all().delete()
        Customer.objects.all().delete()
        Notification.objects.all().delete()
        
        # Deleting tailors first
        Tailor.objects.all().delete()
        
        # Clean up existing users in this schema except owners (owner@tryon2buy.com, sanjay.garlapenta@domsglobal.co)
        for u in list(User.objects.all()):
            if "owner" not in u.email and "sanjay" not in u.email and u.username != "admin":
                print(f"Deleting user: {u.username}")
                u.delete()

        # 2. Seed Mock Tailors & Masters with Django User Login Accounts
        tailors_config = [
            {"name": "Rohit Mehra", "specialty": "Ethnic & Bridal Cutting", "rating": 4.90, "status": "Available", "role": "Master", "email": "rohit.master@tryon2buy.com"},
            {"name": "Anya Sharma", "specialty": "Blouse & Lehenga Specialist", "rating": 4.80, "status": "Available", "role": "Tailor", "email": "anya.tailor@tryon2buy.com"},
            {"name": "Rahul Verma", "specialty": "Suit & Gown Specialist", "rating": 4.70, "status": "Available", "role": "Tailor", "email": "rahul.tailor@tryon2buy.com"},
            {"name": "Preeti Singh", "specialty": "Embroidery Specialist", "rating": 4.95, "status": "Available", "role": "Tailor", "email": "preeti.tailor@tryon2buy.com"},
        ]

        seeded_tailors = []
        for t in tailors_config:
            username = t["email"].split('@')[0]
            # Ensure unique username
            orig_username = username
            c = 1
            while User.objects.filter(username=username).exists():
                username = f"{orig_username}{c}"
                c += 1
            
            user = User.objects.create_user(
                username=username,
                email=t["email"],
                password="TailorSecure2026!",
                first_name=t["name"].split(' ')[0],
                last_name=t["name"].split(' ')[1] if len(t["name"].split(' ')) > 1 else ''
            )
            
            # Re-fetch from DB to guarantee it exists and sequences are stable
            user = User.objects.get(id=user.id)
            
            tailor_obj = Tailor.objects.create(
                name=t["name"],
                specialty=t["specialty"],
                rating=t["rating"],
                status=t["status"],
                role=t["role"],
                email=t["email"],
                user=user
            )
            seeded_tailors.append(tailor_obj)

        master = next(t for t in seeded_tailors if t.role == 'Master')
        tailor = next(t for t in seeded_tailors if t.role == 'Tailor')

        # 3. Create mock customers
        customers = [
            {
                "first_name": "Priya", "last_name": "Sharma", "email_address": "priya.sharma@gmail.com", "mobile_number": "9876543210",
                "customer_type": "Women", "garment_type": "Lehenga", "occasion": "Wedding Reception"
            },
            {
                "first_name": "Ananya", "last_name": "Patel", "email_address": "ananya.patel@gmail.com", "mobile_number": "9812345678",
                "customer_type": "Women", "garment_type": "Saree", "occasion": "Diwali Gala"
            },
            {
                "first_name": "Meera", "last_name": "Nair", "email_address": "meera.nair@gmail.com", "mobile_number": "9765432109",
                "customer_type": "Women", "garment_type": "Kurta", "occasion": "Housewarming"
            },
            {
                "first_name": "Kabita", "last_name": "Sen", "email_address": "kabita.sen@gmail.com", "mobile_number": "9555667788",
                "customer_type": "Women", "garment_type": "Gown", "occasion": "Corporate Award Night"
            }
        ]

        created_customers = []
        for c in customers:
            cust = Customer.objects.create(
                first_name=c["first_name"],
                last_name=c["last_name"],
                email_address=c["email_address"],
                mobile_number=c["mobile_number"],
                customer_type=c["customer_type"],
                garment_type=c["garment_type"],
                occasion=c["occasion"]
            )
            # Create measurements
            Measurement.objects.create(
                customer=cust,
                bust=36.5, waist=30.0, hips=39.0, shoulder=15.0,
                arm_length=18.0, length=44.0, neck=14.0
            )
            created_customers.append(cust)

        # 4. Create mock orders with different stages
        # Order 1: Received (Partial Payment)
        o1 = Order.objects.create(
            order_id="ORD-2026-0001",
            customer=created_customers[0],
            tailor=tailor,
            master=master,
            payment_status="Partially Paid",
            order_status="Received",
            base_price=25000.00,
            fabric_price=5000.00,
            tailoring_charges=3000.00,
            taxes=1650.00,
            total_amount=34650.00,
            advance_paid=15000.00,
            amount_paid=15000.00,
            delivery_method="Courier",
            courier_service="Blue Dart",
            tracking_number="BD123456789IN",
            delivery_address="Flat 402, Oakwood Apartments, Bandra West, Mumbai, MH - 400050"
        )
        OrderStageHistory.objects.create(
            order=o1, stage="Received", comments="Bridal Lehenga order logged with raw silk choices and custom zardozi specifications.", completed_by_name=master.name if master else "System"
        )

        # Order 2: Design & Creation (Partial Payment)
        o2 = Order.objects.create(
            order_id="ORD-2026-0002",
            customer=created_customers[1],
            tailor=tailor,
            master=master,
            payment_status="Partially Paid",
            order_status="Design & Creation",
            base_price=12000.00,
            fabric_price=3000.00,
            tailoring_charges=2000.00,
            taxes=850.00,
            total_amount=17850.00,
            advance_paid=10000.00,
            amount_paid=10000.00,
            delivery_method="Direct Pickup"
        )
        OrderStageHistory.objects.create(
            order=o2, stage="Received", comments="Festive saree blouse stitching logged.", completed_by_name="System"
        )
        OrderStageHistory.objects.create(
            order=o2, stage="Confirmed", comments="Blouse neck lining style approved by stylist.", completed_by_name=master.name if master else "Stylist"
        )
        OrderStageHistory.objects.create(
            order=o2, stage="Stylist Review", comments="Lining verified, ready for tailors.", completed_by_name="Stylist"
        )

        # Order 3: Ready for Dispatch (Fully Paid)
        o3 = Order.objects.create(
            order_id="ORD-2026-0003",
            customer=created_customers[2],
            tailor=tailor,
            master=master,
            payment_status="Paid",
            order_status="Ready for Dispatch",
            base_price=5000.00,
            fabric_price=2000.00,
            tailoring_charges=1000.00,
            taxes=400.00,
            total_amount=8400.00,
            advance_paid=8400.00,
            amount_paid=8400.00,
            delivery_method="Direct Pickup",
            tailor_comments="Premium olive green cotton slub kurta is completely stitched and ironed. Fabric has excellent structure.",
        )
        OrderStageHistory.objects.create(
            order=o3, stage="Received", comments="Order details verified.", completed_by_name="System"
        )
        OrderStageHistory.objects.create(
            order=o3, stage="Confirmed", comments="Custom neck cut measurements approved.", completed_by_name=master.name if master else "Master"
        )
        OrderStageHistory.objects.create(
            order=o3, stage="Design & Creation", comments="Stitching completed by Tailor Anya Sharma.", completed_by_name=tailor.name if tailor else "Tailor"
        )
        OrderStageHistory.objects.create(
            order=o3, stage="Quality Check", comments="Passed visual seam inspections. Perfect fit.", completed_by_name="Quality Team"
        )

        # Order 4: Delivered (Fully Paid)
        o4 = Order.objects.create(
            order_id="ORD-2026-0004",
            customer=created_customers[3],
            tailor=tailor,
            master=master,
            payment_status="Paid",
            order_status="Delivered",
            base_price=18000.00,
            fabric_price=4000.00,
            tailoring_charges=3000.00,
            taxes=1250.00,
            total_amount=26250.00,
            advance_paid=13000.00,
            amount_paid=26250.00,
            delivery_method="Courier",
            courier_service="DHL Express",
            tracking_number="DHL987654321",
            delivery_address="House 89, Golf Links, New Delhi, DL - 110003"
        )
        OrderStageHistory.objects.create(
            order=o4, stage="Received", comments="Gown request received.", completed_by_name="System"
        )
        OrderStageHistory.objects.create(
            order=o4, stage="Confirmed", comments="Measurements mapped.", completed_by_name="System"
        )
        OrderStageHistory.objects.create(
            order=o4, stage="Design & Creation", comments="Finished stitching work.", completed_by_name=tailor.name if tailor else "Tailor"
        )
        OrderStageHistory.objects.create(
            order=o4, stage="Ready for Dispatch", comments="Packed and labeled for courier pickup.", completed_by_name="Shipping"
        )
        OrderStageHistory.objects.create(
            order=o4, stage="Shipped", comments="Dispatched via DHL courier cargo plane.", completed_by_name="DHL Carrier"
        )
        OrderStageHistory.objects.create(
            order=o4, stage="Delivered", comments="Garment delivered directly to client and signed for.", completed_by_name="DHL Courier Delivery agent"
        )

        # 5. Create some notifications
        Notification.objects.create(
            title="New Order Logged: ORD-2026-0001",
            message="Priya Sharma has placed an order for a custom Lehenga. Amount: ₹34,650.",
            recipient_role="Owner"
        )
        Notification.objects.create(
            title="Stitching Task Ready",
            message="Order ORD-2026-0002 has transitioned to Design & Creation and is ready for tailoring.",
            recipient_role="Tailor",
            recipient_email=tailor.email if tailor else None
        )
        print("Mocks and login credentials seeded successfully!")

def seed_all():
    for tenant in BoutiqueTenant.objects.exclude(schema_name='public'):
        try:
            seed_tenant_orders(tenant.schema_name)
        except Exception as e:
            print(f"Error seeding tenant {tenant.schema_name}: {e}")

if __name__ == '__main__':
    seed_all()
