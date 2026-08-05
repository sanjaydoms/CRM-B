from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from django_tenants.test.cases import TenantTestCase
from django.conf import settings
from django.test import override_settings
import datetime

from apps.design_studio.models import DesignAsset
from .models import Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign, OrderStage

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

    def _customer_with_order(self, amount=30000.00, mobile="9876543210"):
        customer = Customer.objects.create(
            first_name="Jane", last_name="Doe", mobile_number=mobile, garment_type="Lehenga"
        )
        Measurement.objects.create(customer=customer, bust=36.00, waist=28.00)
        Order.objects.create(
            order_id=f"T2B-LIST-{mobile[-4:]}",
            customer=customer,
            tailor=self.tailor,
            payment_status="Paid",
            base_price=amount,
            total_amount=amount,
        )
        return customer

    def test_customer_list_omits_nested_orders(self):
        """The directory list must stay flat -- see CustomerSummarySerializer."""
        self.authenticate_client()
        self._customer_with_order()

        response = self.client.get(reverse('customer-list'))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        row = response.json()[0]
        for heavy in ('orders', 'measurement_history', 'design_preferences', 'fabric_selections'):
            self.assertNotIn(heavy, row, f"{heavy} must not be nested in the list payload")

    def test_customer_list_keeps_fields_the_directory_card_renders(self):
        self.authenticate_client()
        self._customer_with_order(amount=30000.00)

        row = self.client.get(reverse('customer-list')).json()[0]

        self.assertEqual(row['order_count'], 1)
        self.assertEqual(row['total_spend'], 30000.00)
        self.assertEqual(row['segment'], 'HVC')
        self.assertEqual(row['measurements']['bust'], '36.00')
        # Style DNA is derived from annotations, not from loaded order rows.
        self.assertIn('30,000', row['style_dna']['budget'])
        self.assertIn('risk_level', row['style_dna'])

    def test_customer_detail_still_returns_full_orders(self):
        self.authenticate_client()
        customer = self._customer_with_order()

        response = self.client.get(reverse('customer-detail', args=[customer.id]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        body = response.json()
        self.assertEqual(len(body['orders']), 1)
        self.assertEqual(body['orders'][0]['order_id'], 'T2B-LIST-3210')
        self.assertIn('stages', body['orders'][0])
        self.assertIn('measurement_history', body)

    def test_customer_list_query_count_does_not_grow_with_customers(self):
        """Guards against the N+1 that made this endpoint take 14s.

        Asserts the invariant rather than a fixed number: tripling the number of
        clients must not add a single query.
        """
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.authenticate_client()

        def list_query_count():
            with CaptureQueriesContext(connection) as ctx:
                response = self.client.get(reverse('customer-list'))
                self.assertEqual(response.status_code, status.HTTP_200_OK)
            return len(ctx.captured_queries)

        for i in range(3):
            self._customer_with_order(mobile=f"90000000{i:02d}")
        baseline = list_query_count()

        for i in range(3, 9):
            self._customer_with_order(mobile=f"90000000{i:02d}")
        self.assertEqual(
            list_query_count(), baseline,
            "customer list query count grew with the number of customers (N+1)",
        )

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

    def test_dashboard_recent_orders_keep_stages_but_drop_unused_relations(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        OrderStage.objects.create(
            order=order, stage_key='created', stage_name='Created',
            status='COMPLETED', sequence=0,
        )

        body = self.client.get(reverse('dashboard')).json()

        recent = body['recent_orders'][0]
        # The Order Progress tracker renders these.
        self.assertEqual(len(recent['stages']), 1)
        self.assertEqual(recent['stages'][0]['stage_name'], 'Created')
        self.assertIn('customer_name', recent)
        self.assertIn('estimated_delivery', recent)
        # Nothing on the dashboard renders these.
        for unused in ('activities', 'stage_histories', 'customer_measurements'):
            self.assertNotIn(unused, recent, f"{unused} is not rendered by the dashboard")

    def test_dashboard_query_count_does_not_grow_with_orders(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.authenticate_client()

        def dashboard_query_count():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(
                    self.client.get(reverse('dashboard')).status_code, status.HTTP_200_OK
                )
            return len(ctx.captured_queries)

        for i in range(2):
            self._customer_with_order(mobile=f"91000000{i:02d}")
        baseline = dashboard_query_count()

        for i in range(2, 8):
            self._customer_with_order(mobile=f"91000000{i:02d}")
        self.assertEqual(
            dashboard_query_count(), baseline,
            "dashboard query count grew with the number of orders (N+1)",
        )

    # --- Specialist roles, design approval, stage assignment ---

    def test_specialist_role_may_advance_its_own_stage(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        stage = OrderStage.objects.create(
            order=order, stage_key='master_quality_check',
            stage_name='Master Quality Check', status='NOT_STARTED', sequence=7,
        )
        qc = Tailor.objects.create(name="QC Lead", specialty="Inspection", role="QC Master",
                                   email="qc@test.com")
        qc_user = User.objects.create_user(username="qc", email="qc@test.com", password="x")
        qc.user = qc_user
        qc.save()

        from domains.orders.services import OrderService
        OrderService.transition_order_stage(
            order=order, stage_key='master_quality_check', new_status='COMPLETED', user=qc_user,
        )
        stage.refresh_from_db()
        self.assertEqual(stage.status, 'COMPLETED')

    def test_wrong_specialist_is_refused(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        OrderStage.objects.create(
            order=order, stage_key='master_quality_check',
            stage_name='Master Quality Check', status='NOT_STARTED', sequence=7,
        )
        presser = Tailor.objects.create(name="Presser", specialty="Pressing",
                                        role="Pressing Staff", email="press@test.com")
        presser_user = User.objects.create_user(username="press", email="press@test.com", password="x")
        presser.user = presser_user
        presser.save()

        from domains.orders.services import OrderService
        with self.assertRaises(ValueError) as ctx:
            OrderService.transition_order_stage(
                order=order, stage_key='master_quality_check', new_status='COMPLETED',
                user=presser_user,
            )
        self.assertIn('not authorized', str(ctx.exception))

    def test_generalist_master_still_works_after_role_split(self):
        """A boutique with one Master must be unaffected by the specialist roles."""
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        stage = OrderStage.objects.create(
            order=order, stage_key='master_quality_check',
            stage_name='Master Quality Check', status='NOT_STARTED', sequence=7,
        )
        master = Tailor.objects.create(name="Generalist", specialty="All", role="Master",
                                       email="gen@test.com")
        master_user = User.objects.create_user(username="gen", email="gen@test.com", password="x")
        master.user = master_user
        master.save()

        from domains.orders.services import OrderService
        OrderService.transition_order_stage(
            order=order, stage_key='master_quality_check', new_status='COMPLETED', user=master_user,
        )
        stage.refresh_from_db()
        self.assertEqual(stage.status, 'COMPLETED')

    def test_every_staff_role_has_a_stage_it_can_work_on(self):
        """A role nobody can be assigned to is a role that does not exist."""
        from crm_api.models import get_default_workflow
        workflow = get_default_workflow()
        homeless = [
            role for role, _ in Tailor.ROLE_CHOICES
            if not any(role in stage.get('roles', []) for stage in workflow)
        ]
        self.assertEqual(homeless, [], f"roles with no stage to act on: {homeless}")

    def test_maggam_stage_can_be_skipped_for_a_garment_that_needs_no_embroidery(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        stage = OrderStage.objects.create(order=order, stage_key='maggam_work',
                                          stage_name='Maggam Work', sequence=4)

        from domains.orders.services import OrderService
        OrderService.transition_order_stage(
            order=order, stage_key='maggam_work', new_status='SKIPPED', user=self.user,
        )

        stage.refresh_from_db()
        self.assertEqual(stage.status, 'SKIPPED')

    def test_finishing_and_pressing_specialists_can_advance_their_stages(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        from domains.orders.services import OrderService

        for key, name, role, username in [
            ('finishing', 'Hemming & Finishing', 'Finishing Master', 'fin'),
            ('pressing', 'Pressing', 'Pressing Staff', 'press'),
        ]:
            OrderStage.objects.create(order=order, stage_key=key, stage_name=name, sequence=9)
            staff = Tailor.objects.create(name=f"{role} person", specialty=name,
                                          role=role, email=f"{username}@test.com")
            user = User.objects.create_user(username=username, email=f"{username}@test.com",
                                            password="x")
            staff.user = user
            staff.save()

            OrderService.transition_order_stage(
                order=order, stage_key=key, new_status='COMPLETED', user=user,
            )
            self.assertEqual(order.stages.get(stage_key=key).status, 'COMPLETED')

    def test_new_orders_get_the_full_fifteen_stage_workflow(self):
        self.authenticate_client()
        customer = Customer.objects.create(first_name="Nita", last_name="R", mobile_number="9600000001")
        from domains.orders.services import OrderService
        order = OrderService.create_order_for_customer(customer, {'base_price': 1000}, user=self.user)

        keys = list(order.stages.order_by('sequence').values_list('stage_key', flat=True))
        for expected in ('maggam_work', 'finishing', 'pressing'):
            self.assertIn(expected, keys)
        self.assertLess(keys.index('maggam_work'), keys.index('stitching_in_progress'))
        self.assertLess(keys.index('finishing'), keys.index('pressing'))
        self.assertLess(keys.index('pressing'), keys.index('master_quality_check'))

    def test_design_preference_records_source_and_links(self):
        self.authenticate_client()
        customer = Customer.objects.create(first_name="Ria", last_name="S", mobile_number="9700000001")

        response = self.client.post(
            reverse('customer-save-design-preferences', args=[customer.id]),
            {'notes': 'Sweetheart neckline', 'source': 'PINTEREST',
             'reference_links': '["https://pin.it/abc"]',
             'selected_urls': '["https://img.test/a.jpg"]'},
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()['source'], 'PINTEREST')
        self.assertEqual(response.json()['source_display'], 'Pinterest Inspiration')
        self.assertEqual(response.json()['reference_links'], ['https://pin.it/abc'])
        self.assertFalse(response.json()['is_approved'])

    def test_unknown_design_source_is_rejected(self):
        self.authenticate_client()
        customer = Customer.objects.create(first_name="Ria", last_name="S", mobile_number="9700000002")
        response = self.client.post(
            reverse('customer-save-design-preferences', args=[customer.id]),
            {'notes': 'x', 'source': 'TIKTOK'},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_approving_a_design_supersedes_the_previous_one(self):
        self.authenticate_client()
        customer = Customer.objects.create(first_name="Ria", last_name="S", mobile_number="9700000003")
        first = DesignPreference.objects.create(
            customer=customer, notes='v1', reference_images=['https://img.test/1.jpg'])
        second = DesignPreference.objects.create(
            customer=customer, notes='v2', reference_images=['https://img.test/2.jpg'])

        url = reverse('customer-approve-design', args=[customer.id, first.id])
        self.assertEqual(self.client.post(url).status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        self.assertTrue(first.is_approved)
        self.assertEqual(first.approved_image, 'https://img.test/1.jpg')

        url2 = reverse('customer-approve-design', args=[customer.id, second.id])
        self.assertEqual(self.client.post(url2).status_code, status.HTTP_200_OK)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.is_approved, "approving a design must supersede the previous one")
        self.assertTrue(second.is_approved)
        self.assertIsNone(first.approved_at)

    def test_stage_assignment_accepts_permitted_role(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        OrderStage.objects.create(order=order, stage_key='measurements_completed',
                                  stage_name='Measurements Completed', sequence=1)
        mm = Tailor.objects.create(name="Meena", specialty="Measuring", role="Measurement Master")

        response = self.client.post(
            reverse('order-assign-stage', args=[order.id]),
            {'stage_key': 'measurements_completed', 'tailor_id': mm.id}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()['assigned_to_name'], 'Meena')
        self.assertEqual(response.json()['assigned_to_role'], 'Measurement Master')

    def test_stage_assignment_refuses_a_role_the_stage_does_not_permit(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        OrderStage.objects.create(order=order, stage_key='measurements_completed',
                                  stage_name='Measurements Completed', sequence=1)
        presser = Tailor.objects.create(name="Presser", specialty="Pressing", role="Pressing Staff")

        response = self.client.post(
            reverse('order-assign-stage', args=[order.id]),
            {'stage_key': 'measurements_completed', 'tailor_id': presser.id}, format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('cannot be assigned', response.json()['error'])

    def test_stage_assignment_is_distinct_from_who_performed_it(self):
        self.authenticate_client()
        customer = self._customer_with_order()
        order = Order.objects.get(customer=customer)
        stage = OrderStage.objects.create(order=order, stage_key='measurements_completed',
                                          stage_name='Measurements Completed', sequence=1)
        planned = Tailor.objects.create(name="Meena", specialty="Measuring", role="Measurement Master")
        actual = Tailor.objects.create(name="Stand-in", specialty="Measuring", role="Master")

        self.client.post(reverse('order-assign-stage', args=[order.id]),
                         {'stage_key': 'measurements_completed', 'tailor_id': planned.id}, format='json')
        from domains.orders.services import OrderService
        OrderService.transition_order_stage(
            order=order, stage_key='measurements_completed', new_status='COMPLETED',
            performer_id=actual.id, user=self.user,
        )

        stage.refresh_from_db()
        self.assertEqual(stage.assigned_to, planned, "assignment must survive the transition")
        self.assertEqual(stage.performed_by, actual)

    def test_get_ai_suggestions(self):
        self.authenticate_client()
        customer = Customer.objects.create(
            first_name="Alice", last_name="Smith", mobile_number="9998887776", garment_type="Lehenga"
        )
        DesignAsset.objects.create(
            title="AI Lehenga suggestion", garment_type="Lehenga",
            source=DesignAsset.SOURCE_SUGGESTION, image_url="http://example.com/ai_lehenga.jpg"
        )
        DesignAsset.objects.create(
            title="AI Gown suggestion", garment_type="Gown",
            source=DesignAsset.SOURCE_SUGGESTION, image_url="http://example.com/ai_gown.jpg"
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
        DesignAsset.objects.create(
            title="Boutique Lehenga 1", garment_type="Lehenga",
            source=DesignAsset.SOURCE_CATALOGUE,
            image_url="http://example.com/bot_lehenga.jpg", estimated_price=12000.00
        )
        DesignAsset.objects.create(
            title="Boutique Sherwani 1", garment_type="Sherwani",
            source=DesignAsset.SOURCE_CATALOGUE,
            image_url="http://example.com/bot_sherwani.jpg", estimated_price=15000.00
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
        self.assertFalse(DesignAsset.objects.filter(id=design_id).exists())


class MediaServingTests(TenantTestCase):
    """Catalogue imagery has to load in production, not just in DEBUG.

    Uploads use FileSystemStorage and the seeded fabric and design images are
    committed to the repo, but the media route used to be registered only when
    DEBUG was True. On Render, where DEBUG is False, that left every fabric and
    design image returning 404 with nothing to serve them.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "media@test.com"
        tenant.name = "Media Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        self.media_file = settings.MEDIA_ROOT / "fabric_02.jpg"

    @override_settings(DEBUG=False)
    def test_media_is_served_with_debug_off(self):
        if not self.media_file.exists():
            self.skipTest("seeded media is not present in this checkout")
        response = self.client.get("/media/fabric_02.jpg")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "image/jpeg")

    @override_settings(DEBUG=False)
    def test_media_route_rejects_traversal_outside_the_media_root(self):
        response = self.client.get("/media/../boutique_crm/settings.py")
        self.assertNotEqual(response.status_code, 200)
