from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django_tenants.test.cases import TenantTestCase
import datetime

from .models import Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign

class BoutiqueCRMTests(TenantTestCase):
    @classmethod
    def setup_tenant(cls, tenant):
        # Configure required tenant fields for test execution
        tenant.owner_email = "amara@test.com"
        tenant.name = "Amara's Boutique"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        self.client = APIClient()

        # Seed test data inside the tenant schema
        self.tailor = Tailor.objects.create(
            name="Test Tailor", specialty="Suits", rating=4.8, status="Available"
        )
        self.fabric = BoutiqueFabric.objects.create(
            name="Silk Dupion", material="Pure Silk", color="Dusty Rose", price_per_meter=1800.00
        )
        
        # Test User for Authentication inside the tenant schema
        self.user_password = "securepassword123"
        self.user = User.objects.create_user(
            username="amara@test.com",
            email="amara@test.com",
            password=self.user_password,
            first_name="Amara",
            last_name="Singh"
        )
        self.token = Token.objects.create(user=self.user)

    def authenticate_client(self):
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + self.token.key,
            HTTP_X_TENANT_ID=self.tenant.schema_name
        )

    # --- Authentication Tests ---
    def test_signup_success(self):
        url = reverse('auth-signup')
        data = {
            "first_name": "Rohan",
            "last_name": "Verma",
            "email_address": "rohan@test.com",
            "mobile_number": "9876500000",
            "password": "rohanpassword123"
        }
        self.client.credentials()  # clear default tenant header to hit public schema
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["user"]["email"], "rohan@test.com")

    def test_signup_already_exists(self):
        url = reverse('auth-signup')
        data = {
            "first_name": "Duplicate",
            "last_name": "User",
            "email_address": "amara@test.com",
            "mobile_number": "9876500001",
            "password": "anotherpassword123"
        }
        self.client.credentials()
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("error", response.data)

    def test_login_success(self):
        url = reverse('auth-login')
        data = {
            "username": "amara@test.com",
            "password": self.user_password
        }
        self.client.credentials()
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("token", response.data)
        self.assertEqual(response.data["token"], self.token.key)

    def test_login_invalid(self):
        url = reverse('auth-login')
        data = {
            "username": "amara@test.com",
            "password": "wrongpassword"
        }
        self.client.credentials()
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertNotIn("token", response.data)

    def test_logout(self):
        url = reverse('auth-logout')
        self.authenticate_client()
        response = self.client.post(url, {}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Token should be deleted from tenant DB
        self.assertFalse(Token.objects.filter(key=self.token.key).exists())

    def test_me_authenticated(self):
        url = reverse('auth-me')
        self.authenticate_client()
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "amara@test.com")

    # --- CRM Business Flow Tests (Authenticated) ---
    def test_create_customer_with_measurements(self):
        url = reverse('customer-list')
        self.authenticate_client()
        
        customer_data = {
            "first_name": "Jane",
            "last_name": "Doe",
            "mobile_number": "9876543210",
            "email_address": "jane@example.com",
            "address": "123 Test St",
            "city_region": "New Delhi",
            "source": "Walk In",
            "customer_type": "Women",
            "garment_type": "Lehenga",
            "measurements": {
                "bust": 34.00,
                "waist": 28.00,
                "hips": 36.00,
                "shoulder": 15.00,
                "arm_length": 22.00,
                "neck": 13.50,
                "length": 42.00
            }
        }
        response = self.client.post(url, customer_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Measurement.objects.count(), 1)
        
        customer = Customer.objects.first()
        self.assertEqual(customer.first_name, "Jane")
        self.assertEqual(customer.measurements.bust, 34.00)

    def test_update_customer_measurements(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Jane", last_name="Doe", mobile_number="9876543210"
        )
        Measurement.objects.create(customer=customer, bust=32.00)

        url = reverse('customer-detail', kwargs={'pk': customer.id})
        update_data = {
            "measurements": {
                "bust": 35.50,
                "waist": 29.00
            }
        }
        response = self.client.patch(url, update_data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        measurement = Measurement.objects.get(customer=customer)
        self.assertEqual(measurement.bust, 35.50)

    def test_save_design_preferences(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Jane", last_name="Doe", mobile_number="9876543210"
        )
        url = reverse('customer-save-design-preferences', kwargs={'pk': customer.id})
        data = {
            "notes": "Love deep necklines and zari embroidery",
        }
        response = self.client.post(url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(DesignPreference.objects.count(), 1)
        self.assertEqual(DesignPreference.objects.first().notes, "Love deep necklines and zari embroidery")

    def test_save_fabric_selection(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Jane", last_name="Doe", mobile_number="9876543210"
        )
        url = reverse('customer-save-fabric-selection', kwargs={'pk': customer.id})
        data = {
            "is_boutique_fabric": "true",
            "fabric_name": "Silk Dupion",
            "fabric_price": 5400.00
        }
        response = self.client.post(url, data, format='multipart')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FabricSelection.objects.count(), 1)
        selection = FabricSelection.objects.first()
        self.assertEqual(selection.fabric_name, "Silk Dupion")

    def test_create_order_pricing_math(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Jane", last_name="Doe", mobile_number="9876543210"
        )
        url = reverse('customer-create-order', kwargs={'pk': customer.id})
        
        data = {
            "tailor_id": self.tailor.id,
            "base_price": 1000.00,
            "fabric_price": 500.00,
            "embroidery_price": 200.00,
            "customization_price": 100.00,
            "tailoring_charges": 0.00,
            "packaging_handling": 0.00
        }
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        order = Order.objects.first()
        self.assertEqual(order.taxes, 90.00)
        self.assertEqual(order.total_amount, 1890.00)

    def test_dashboard_stats(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Jane", last_name="Doe", mobile_number="9876543210"
        )
        Order.objects.create(
            order_id="T2B-TEST-01",
            customer=customer,
            tailor=self.tailor,
            payment_status="Paid",
            base_price=1000.00,
            total_amount=1050.00
        )
        
        url = reverse('dashboard')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['stats']['total_customers'], 1)

    def test_get_ai_suggestions(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Alice", last_name="Smith", mobile_number="9998887776", garment_type="Lehenga"
        )
        BoutiqueDesign.objects.create(
            name="AI Lehenga suggestion", garment_type="Lehenga", is_boutique=False, image_url="http://example.com/ai_lehenga.jpg"
        )
        BoutiqueDesign.objects.create(
            name="AI Gown suggestion", garment_type="Gown", is_boutique=False, image_url="http://example.com/ai_gown.jpg"
        )
        
        url = reverse('customer-ai-suggestions', kwargs={'pk': customer.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "AI Lehenga suggestion")

    def test_get_boutique_designs(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Alice", last_name="Smith", mobile_number="9998887776", garment_type="Lehenga"
        )
        BoutiqueDesign.objects.create(
            name="Boutique Lehenga 1", garment_type="Lehenga", is_boutique=True, image_url="http://example.com/bot_lehenga.jpg", price=12000.00
        )
        BoutiqueDesign.objects.create(
            name="Boutique Sherwani 1", garment_type="Sherwani", is_boutique=True, image_url="http://example.com/bot_sherwani.jpg", price=15000.00
        )
        
        url = reverse('customer-boutique-designs', kwargs={'pk': customer.id})
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], "Boutique Lehenga 1")

    def test_fabric_crud(self):
        self.authenticate_client()
        
        # Test Create (POST)
        url = reverse('fabric-list')
        data = {
            "name": "Chanderi Silk",
            "material": "Silk Blend",
            "color": "Aqua Blue",
            "price_per_meter": 1250.00
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], "Chanderi Silk")
        fabric_id = response.data['id']

        # Test Update (PATCH)
        detail_url = reverse('fabric-detail', kwargs={'pk': fabric_id})
        patch_data = {"price_per_meter": 1400.00}
        response = self.client.patch(detail_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['price_per_meter']), 1400.00)

        # Test Delete (DELETE)
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BoutiqueFabric.objects.filter(id=fabric_id).exists())

    def test_tailor_crud(self):
        self.authenticate_client()

        # Test Create (POST)
        url = reverse('tailor-list')
        data = {
            "name": "Master Shabbir",
            "specialty": "Lehengas & Blouses",
            "rating": 4.90,
            "status": "Available"
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], "Master Shabbir")
        tailor_id = response.data['id']

        # Test Update (PATCH)
        detail_url = reverse('tailor-detail', kwargs={'pk': tailor_id})
        patch_data = {"status": "Busy"}
        response = self.client.patch(detail_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], "Busy")

        # Test Delete (DELETE)
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Tailor.objects.filter(id=tailor_id).exists())

    def test_boutique_design_crud(self):
        self.authenticate_client()

        # Test Create (POST)
        url = reverse('boutique-design-list')
        data = {
            "name": "Royal Brocade Kurta",
            "garment_type": "Kurta",
            "image_url": "http://example.com/kurta.jpg",
            "is_boutique": True,
            "price": 8500.00
        }
        response = self.client.post(url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], "Royal Brocade Kurta")
        design_id = response.data['id']

        # Test Update (PATCH)
        detail_url = reverse('boutique-design-detail', kwargs={'pk': design_id})
        patch_data = {"price": 9200.00}
        response = self.client.patch(detail_url, patch_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(float(response.data['price']), 9200.00)

        # Test Delete (DELETE)
        response = self.client.delete(detail_url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BoutiqueDesign.objects.filter(id=design_id).exists())
