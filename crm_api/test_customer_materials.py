from decimal import Decimal

from apps.catalog.models import JobMaterial
from apps.inventory.models import CustomerMaterial
from crm_api.test_pricing import PricingTestBase


class CustomerSuppliedMaterialTests(PricingTestBase):
    """The cloth a customer brings in, entered with the garment.

    Two records, one entry: the job line says which part of which garment it is
    for, and the customer-material ledger says how much came in and how much is
    left to give back. Neither is boutique stock.
    """

    def a_customer_line(self, field_key, name, quantity, unit='METER'):
        return {'field_key': field_key, 'free_text': name, 'quantity': quantity,
                'unit': unit, 'source': 'CUSTOMER'}

    def test_it_reaches_the_job_line_and_the_ledger(self):
        garment = self.garment(self.blouse, base=4000)
        garment['materials'] = [
            self.a_customer_line('main_fabric', 'Kanjivaram silk, maroon', '2.5')]

        response = self.confirm(self.a_draft([garment]))
        self.assertEqual(response.status_code, 201, response.data)

        line = JobMaterial.objects.get()
        self.assertEqual(line.source, JobMaterial.Source.CUSTOMER)
        self.assertEqual(line.free_text, 'Kanjivaram silk, maroon')
        # Their cloth is not stock and must never be reserved or deducted.
        self.assertIsNone(line.inventory_item)

        material = CustomerMaterial.objects.get()
        self.assertEqual(material.name, 'Kanjivaram silk, maroon')
        self.assertEqual(material.unit, 'METER')
        self.assertEqual(material.kind, CustomerMaterial.Kind.FABRIC)
        self.assertEqual(material.received_quantity, Decimal('2.500'))
        self.assertEqual(material.remaining_quantity, Decimal('2.500'))
        self.assertEqual(material.movements.count(), 1)

    def test_one_roll_across_two_parts_is_received_once(self):
        garment = self.garment(self.blouse, base=4000)
        garment['materials'] = [
            self.a_customer_line('main_fabric', 'Tissue silk', '1.5'),
            self.a_customer_line('lining', 'Tissue silk', '0.75'),
        ]

        response = self.confirm(self.a_draft([garment]))
        self.assertEqual(response.status_code, 201, response.data)

        self.assertEqual(JobMaterial.objects.count(), 2)
        # Received twice, the boutique would believe it holds 4.5m of a roll
        # the customer handed over once.
        material = CustomerMaterial.objects.get()
        self.assertEqual(material.received_quantity, Decimal('2.250'))

    def test_store_materials_stay_out_of_the_customer_ledger(self):
        garment = self.garment(self.blouse, base=4000)
        response = self.confirm(self.a_draft([garment]))
        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(CustomerMaterial.objects.exists())
