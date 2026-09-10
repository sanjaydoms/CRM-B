import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from django_tenants.utils import schema_context
from tenants.models import BoutiqueTenant
from crm_api.models import Order, Customer, Tailor
from apps.production.models import ProductionTask, QCRecord
from apps.activities.models import UniversalActivity
from apps.scheduling.models import Appointment
from django.utils import timezone
import datetime

print("🌱 Seeding Phase 2.0 Task Engine, Universal Activity & Scheduling Data...")

def seed_schema(schema_name):
    print(f"--> Processing schema: {schema_name}")
    try:
        with schema_context(schema_name):
            orders = Order.objects.select_related('customer', 'master', 'tailor').all()
            for order in orders:
                master = order.master
                tailor = order.tailor
                
                if not order.production_tasks.exists():
                    print(f"  Creating Production Tasks for Order {order.order_id}...")
                    tasks = [
                        ProductionTask(order=order, title="Verify Measurements & Requirements", stage_key="measurements_completed", assigned_to=master or tailor, sequence=1, status="COMPLETED", priority="HIGH"),
                        ProductionTask(order=order, title="Fabric & Lining Selection Approval", stage_key="fabric_confirmed", assigned_to=master or tailor, sequence=2, status="COMPLETED", priority="MEDIUM"),
                        ProductionTask(order=order, title="Pattern Cutting & Drafting", stage_key="pattern_cutting", assigned_to=master, sequence=3, status="IN_PROGRESS", priority="HIGH"),
                        ProductionTask(order=order, title="Garment Assembly & Stitching", stage_key="stitching_in_progress", assigned_to=tailor, sequence=4, status="PENDING", priority="URGENT"),
                        ProductionTask(order=order, title="Embellishment & Finishing", stage_key="stitching_completed", assigned_to=tailor, sequence=5, status="PENDING", priority="MEDIUM"),
                        ProductionTask(order=order, title="Master Quality Control Inspection", stage_key="master_quality_check", assigned_to=master, sequence=6, status="PENDING", priority="HIGH"),
                        ProductionTask(order=order, title="Customer Fitting Trial", stage_key="trial_scheduled", assigned_to=master, sequence=7, status="PENDING", priority="MEDIUM"),
                        ProductionTask(order=order, title="Final Packaging & Dispatch Preparation", stage_key="ready_for_delivery", assigned_to=master or tailor, sequence=8, status="PENDING", priority="MEDIUM"),
                    ]
                    ProductionTask.objects.bulk_create(tasks)

                if not UniversalActivity.objects.filter(entity_id=order.order_id).exists():
                    UniversalActivity.objects.create(
                        module="orders",
                        entity_type="Order",
                        entity_id=order.order_id,
                        action="ORDER_CREATED",
                        title=f"Order {order.order_id} Received",
                        description=f"Order created for customer {order.customer.first_name} {order.customer.last_name}" if order.customer else f"Order {order.order_id} created",
                        new_value={"order_id": order.order_id, "amount": float(order.total_amount)}
                    )

                if order.customer and not Appointment.objects.filter(order=order).exists():
                    Appointment.objects.create(
                        customer=order.customer,
                        order=order,
                        appointment_type="TRIAL",
                        status="SCHEDULED",
                        scheduled_time=timezone.now() + datetime.timedelta(days=7),
                        assigned_staff=master,
                        notes=f"First fitting trial for {order.customer.garment_type}"
                    )
    except Exception as e:
        print(f"  Skipping {schema_name} due to schema state: {e}")

tenants = BoutiqueTenant.objects.exclude(schema_name='public')
for tenant in tenants:
    seed_schema(tenant.schema_name)

print("✅ Phase 2.0 Task Engine Seeding Complete!")
