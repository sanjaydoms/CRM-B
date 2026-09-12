"""A customer's captured design: uploaded as a photograph of a paper sketch or
drawn in the studio, stored the same way, listed and shown the same way.
"""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalog.models import GarmentTemplate
from apps.design_studio.models import CustomerDesign, DesignAsset
from crm_api.models import Customer, Order


def png(name='sketch.png'):
    return SimpleUploadedFile(name, b'\x89PNG\r\n\x1a\n', content_type='image/png')


class CustomerDesignTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "cd@test.com"
        tenant.name = "Customer Design Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = APIClient()
        self.user = User.objects.create_user(username="cd@test.com", email="cd@test.com", password="pw")
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key,
                                HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.priya = Customer.objects.create(first_name='Priya', last_name='S', mobile_number='9000000001')
        self.asha = Customer.objects.create(first_name='Asha', last_name='K', mobile_number='9000000002')
        self.blouse = GarmentTemplate.resolve('blouse')
        self.saree = GarmentTemplate.resolve('saree')
        self.lehenga = GarmentTemplate.resolve('lehenga')

    def create(self, **over):
        data = {'title': 'Bridal Blouse', 'customer': str(self.priya.id), 'template': str(self.blouse.id),
                'notes': 'Deep back neck.', 'image': png()}
        data.update(over)
        return self.client.post('/api/design-studio/customer-designs/', data, format='multipart')

    def test_uploaded_sketch_is_stored_and_listed(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['source'], 'uploaded')
        self.assertEqual(r.data['source_display'], 'Uploaded')
        self.assertEqual(r.data['customer_name'], 'Priya S')
        self.assertEqual(r.data['garment_type'], 'Blouse')
        self.assertIn('customer_designs/', r.data['image_url'])
        self.assertTrue(r.data['image_url'].endswith('sketch.png'))
        r = self.client.get('/api/design-studio/customer-designs/')
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual([d['title'] for d in rows], ['Bridal Blouse'])

    def test_drawn_design_is_the_same_thing_with_its_source_recorded(self):
        r = self.create(title='Neck sketch', source='drawn', image=png('drawing.png'))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual((r.data['source'], r.data['source_display']), ('drawn', 'Drawn'))
        self.assertTrue(r.data['image_url'].endswith('drawing.png'))
        r = self.client.get(f"/api/design-studio/customer-designs/{r.data['id']}/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['notes'], 'Deep back neck.')

    def test_many_designs_and_garments_stay_apart(self):
        for title, tpl in (('Bridal Blouse', self.blouse), ('Floral Saree', self.saree),
                           ('Party Lehenga', self.lehenga)):
            self.assertEqual(self.create(title=title, template=str(tpl.id)).status_code, 201, title)
        self.assertEqual(self.create(title='Asha blouse', customer=str(self.asha.id)).status_code, 201)
        r = self.client.get('/api/design-studio/customer-designs/')
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual(sorted((d['title'], d['garment_type']) for d in rows), [
            ('Asha blouse', 'Blouse'), ('Bridal Blouse', 'Blouse'),
            ('Floral Saree', 'Saree'), ('Party Lehenga', 'Lehenga')])
        r = self.client.get('/api/design-studio/customer-designs/', {'customer': str(self.priya.id)})
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual(len(rows), 3)
        self.assertEqual(CustomerDesign.objects.count(), 4)
        # The boutique's own library is untouched by any of it.
        self.assertEqual(DesignAsset.objects.count(), 0)

    def test_refusals(self):
        self.assertEqual(self.create(image='').status_code, 400)          # no picture
        self.assertEqual(self.create(title='').status_code, 400)          # no name
        self.assertEqual(self.create(customer='').status_code, 400)       # no customer
        self.assertEqual(self.create(source='scanned').status_code, 400)  # unknown source
        other = Order.objects.create(order_id='T2B-1', customer=self.asha)
        r = self.create(order=str(other.id))
        self.assertEqual(r.status_code, 400)
        self.assertIn('order', r.data)

    def test_order_of_the_same_customer_is_attached(self):
        order = Order.objects.create(order_id='T2B-2', customer=self.priya)
        r = self.create(order=str(order.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['order_reference'], order.reference)
