import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'boutique_crm.settings')
django.setup()

from tenants.models import BoutiqueTenant
from crm_api.models import Measurement, MeasurementHistory
from django_tenants.utils import schema_context

def backfill():
    for tenant in BoutiqueTenant.objects.all():
        schema_name = tenant.schema_name
        if schema_name == 'public':
            continue
        print(f"Backfilling for tenant: {schema_name}")
        with schema_context(schema_name):
            count = 0
            for m in Measurement.objects.all():
                # check if there's any history
                if not MeasurementHistory.objects.filter(customer=m.customer).exists():
                    MeasurementHistory.objects.create(
                        customer=m.customer,
                        bust=m.bust,
                        waist=m.waist,
                        hips=m.hips,
                        shoulder=m.shoulder,
                        arm_length=m.arm_length,
                        neck=m.neck,
                        length=m.length,
                        additional_measurements=m.additional_measurements
                    )
                    count += 1
            print(f"Created {count} history entries for {schema_name}")

if __name__ == '__main__':
    backfill()
