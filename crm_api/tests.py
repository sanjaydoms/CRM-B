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
from .models import Customer, Measurement, DesignPreference, FabricSelection, Tailor, Order, BoutiqueFabric, BoutiqueDesign, OrderStage, Notification

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


class PasswordResetTests(TenantTestCase):
    """A locked-out owner's only route back in.

    Before this there was none: no view, no url, and a login screen that said
    "Password help? Ask your admin" because saying anything else would have
    been a lie. Everything worth asserting here is a security property rather
    than a happy path, so that is what these test.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "reset@test.com"
        tenant.name = "Reset Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        from django.db import connection
        connection.set_tenant(self.tenant)
        # The reset endpoint is throttled per address, and the whole suite runs
        # in one process against one LocMemCache -- so without this the fourth
        # test in the class starts getting 429s from the third one's requests.
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="reset@test.com", email="reset@test.com",
            password="original-password-1", first_name="Ria", last_name="Nair",
        )
        self.token = Token.objects.create(user=self.user)

    def _request_reset(self, email="reset@test.com"):
        return self.client.post(reverse('auth-password-reset'),
                                {"email": email}, format='json')

    def _payload_from_outbox(self):
        from django.core import mail
        body = mail.outbox[-1].body
        marker = '?reset='
        start = body.index(marker) + len(marker)
        return body[start:].split()[0]

    def _reload_user(self):
        """Re-read the user from the boutique's own schema.

        The request cycle leaves the connection wherever the middleware put it
        -- public, for a call that carries no X-Tenant-ID -- so a bare
        refresh_from_db() here looks for the user in the wrong schema and
        raises DoesNotExist. The view itself is unaffected: it does its work
        inside an explicit schema_context.
        """
        from django_tenants.utils import schema_context
        with schema_context(self.tenant.schema_name):
            return User.objects.get(pk=self.user.pk)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_reset_link_lets_the_owner_choose_a_new_password(self):
        from django.core import mail
        mail.outbox = []
        self.assertEqual(self._request_reset().status_code, 200)
        self.assertEqual(len(mail.outbox), 1)

        response = self.client.post(
            reverse('auth-password-reset-confirm'),
            {"token": self._payload_from_outbox(),
             "password": "a-brand-new-password-2"},
            format='json')
        self.assertEqual(response.status_code, 200)

        self.assertTrue(self._reload_user().check_password("a-brand-new-password-2"))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_completing_a_reset_signs_every_device_out(self):
        # The whole point when the reason for the reset is a stolen token.
        from django.core import mail
        mail.outbox = []
        self._request_reset()
        self.client.post(
            reverse('auth-password-reset-confirm'),
            {"token": self._payload_from_outbox(),
             "password": "a-brand-new-password-2"},
            format='json')
        from django_tenants.utils import schema_context
        with schema_context(self.tenant.schema_name):
            self.assertFalse(Token.objects.filter(user=self.user).exists())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_a_link_cannot_be_used_twice(self):
        from django.core import mail
        mail.outbox = []
        self._request_reset()
        payload = self._payload_from_outbox()
        self.client.post(reverse('auth-password-reset-confirm'),
                         {"token": payload, "password": "first-new-password-2"},
                         format='json')
        second = self.client.post(
            reverse('auth-password-reset-confirm'),
            {"token": payload, "password": "second-new-password-3"},
            format='json')
        self.assertEqual(second.status_code, 400)
        self.assertTrue(self._reload_user().check_password("first-new-password-2"))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_an_unknown_address_is_answered_exactly_like_a_known_one(self):
        # Otherwise this endpoint is a directory of every account on the
        # platform, readable by anyone.
        from django.core import mail
        mail.outbox = []
        known = self._request_reset()
        unknown = self._request_reset("nobody@nowhere.test")
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.data, unknown.data)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_a_tampered_token_is_refused(self):
        from django.core import mail
        mail.outbox = []
        self._request_reset()
        schema, uid, token = self._payload_from_outbox().split('.')
        forged = '.'.join([schema, uid, token[:-1] + ('a' if token[-1] != 'a' else 'b')])
        response = self.client.post(
            reverse('auth-password-reset-confirm'),
            {"token": forged, "password": "attackers-password-9"},
            format='json')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self._reload_user().check_password("original-password-1"))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_a_weak_new_password_is_refused(self):
        from django.core import mail
        mail.outbox = []
        self._request_reset()
        response = self.client.post(
            reverse('auth-password-reset-confirm'),
            {"token": self._payload_from_outbox(), "password": "123"},
            format='json')
        self.assertEqual(response.status_code, 400)
        self.assertTrue(self._reload_user().check_password("original-password-1"))

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_a_suspended_boutique_cannot_reset_its_way_back_in(self):
        from django.core import mail
        from django_tenants.utils import schema_context
        mail.outbox = []
        self._request_reset()
        payload = self._payload_from_outbox()
        with schema_context('public'):
            self.tenant.is_active = False
            self.tenant.save(update_fields=['is_active'])
        try:
            response = self.client.post(
                reverse('auth-password-reset-confirm'),
                {"token": payload, "password": "a-brand-new-password-2"},
                format='json')
            self.assertEqual(response.status_code, 403)
        finally:
            with schema_context('public'):
                self.tenant.is_active = True
                self.tenant.save(update_fields=['is_active'])


class BootstrapCredentialTests(TenantTestCase):
    """Staff and designer logins must not share one published password.

    The literals these replace -- 'TailorSecure2026!' and 'DesignerSecure2026!'
    -- were in this repository and in the shipped JavaScript bundle, usernames
    are the email's local part, and find_tenant_for_account searches every
    boutique's schema for a matching username. So one unauthenticated POST to
    /api/auth/login/ was a working credential against any boutique that had
    such an account, not merely the guesser's own.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "creds@test.com"
        tenant.name = "Credential Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        from django.db import connection
        connection.set_tenant(self.tenant)
        cache.clear()   # LoginThrottle counts in the cache; see LoginThrottle
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="creds@test.com", email="creds@test.com",
            password="owner-password-1", first_name="Owner", last_name="One",
        )
        self.token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + self.token.key,
                                HTTP_X_TENANT_ID=self.tenant.schema_name)

    def _create_tailor(self, name, email):
        return self.client.post(reverse('tailor-list'), {
            "name": name, "email": email, "specialty": "Blouses",
            "rating": 4.5, "status": "Available", "role": "Tailor",
        }, format='json')

    def test_the_published_literal_is_not_a_working_password(self):
        response = self._create_tailor("Anya Sharma", "anya@test.com")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(email="anya@test.com")
        self.assertFalse(user.check_password('TailorSecure2026!'))

    def test_each_staff_account_gets_its_own_password(self):
        first = self._create_tailor("Anya Sharma", "anya@test.com")
        second = self._create_tailor("Rahul Verma", "rahul@test.com")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.data['bootstrap_password'],
                            second.data['bootstrap_password'])

    def test_the_password_is_returned_once_and_never_again(self):
        created = self._create_tailor("Anya Sharma", "anya@test.com")
        secret = created.data['bootstrap_password']
        # It really is the account's password...
        self.assertTrue(User.objects.get(email="anya@test.com").check_password(secret))
        # ...and it is gone from every later read, so the roster is not a
        # password list for anyone who reaches it.
        listing = self.client.get(reverse('tailor-list'))
        self.assertEqual(listing.status_code, 200)
        rows = listing.data['results'] if isinstance(listing.data, dict) else listing.data
        for row in rows:
            self.assertNotIn('bootstrap_password', row)
        detail = self.client.get(reverse('tailor-detail',
                                         kwargs={'pk': created.data['id']}))
        self.assertNotIn('bootstrap_password', detail.data)

    def test_editing_a_staff_member_does_not_mint_a_new_password(self):
        # perform_update also calls _ensure_user_account. Re-issuing there
        # would silently invalidate the password the owner already handed over.
        created = self._create_tailor("Anya Sharma", "anya@test.com")
        secret = created.data['bootstrap_password']
        edited = self.client.patch(
            reverse('tailor-detail', kwargs={'pk': created.data['id']}),
            {"specialty": "Lehengas"}, format='json')
        self.assertEqual(edited.status_code, 200)
        self.assertNotIn('bootstrap_password', edited.data)
        self.assertTrue(User.objects.get(email="anya@test.com").check_password(secret))


class LoginThrottleTests(TenantTestCase):
    """Password guessing has a ceiling on the door that searches every schema."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "throttle@test.com"
        tenant.name = "Throttle Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.core.cache import cache
        from django.db import connection
        connection.set_tenant(self.tenant)
        cache.clear()
        self.client = APIClient()
        User.objects.create_user(username="throttle@test.com",
                                 email="throttle@test.com",
                                 password="a-real-password-1")

    def tearDown(self):
        # Put the budget back. This class deliberately spends the entire
        # per-IP login allowance, the whole suite runs in one process against
        # one LocMemCache, and every test client reports the same address --
        # so without this, the tests that merely happen to run afterwards get
        # 429 from requests they never made. That is exactly what happened:
        # SuspensionTests and ModuleGateTests both failed on a correct password
        # because this class had already used the hour up.
        #
        # Cleared here rather than in each victim's setUp: the mess is made
        # here, so it is cleaned up here, and a login test written next year
        # does not have to know this class exists.
        from django.core.cache import cache
        cache.clear()
        super().tearDown()

    def test_repeated_wrong_passwords_are_eventually_refused(self):
        # Drives the rate that is actually configured rather than overriding it.
        # DRF resolves DEFAULT_THROTTLE_RATES through its own cached settings
        # object, so override_settings(REST_FRAMEWORK=...) does not reach the
        # throttle here -- the test passed against a limit that was never
        # applied. Reading the real rate also means this keeps testing the
        # deployed behaviour if LOGIN_RATE is ever retuned.
        from rest_framework.settings import api_settings
        from django.core.cache import cache
        cache.clear()
        limit = int(api_settings.DEFAULT_THROTTLE_RATES['login'].split('/')[0])
        url = reverse('auth-login')
        codes = [
            self.client.post(url, {"username": "throttle@test.com",
                                   "password": f"wrong-{i}"},
                             format='json').status_code
            for i in range(limit + 2)
        ]
        self.assertIn(429, codes, f"no throttling after {limit + 2} attempts: {codes}")
        # The wall must not have gone up early enough to lock out a real person
        # mistyping their password two or three times.
        self.assertEqual(codes[:3], [400, 400, 400])

    def test_successful_logins_do_not_spend_the_budget(self):
        # The lockout case this exists to prevent: a boutique is one shop on one
        # IP, so a morning of staff signing in must not look like an attack. Far
        # more successful logins than the limit, then a wrong one, which must
        # still be answered 400 rather than 429.
        from rest_framework.settings import api_settings
        from django.core.cache import cache
        cache.clear()
        limit = int(api_settings.DEFAULT_THROTTLE_RATES['login'].split('/')[0])
        url = reverse('auth-login')
        for _ in range(limit + 5):
            good = self.client.post(url, {"username": "throttle@test.com",
                                          "password": "a-real-password-1"},
                                    format='json')
            self.assertEqual(good.status_code, 200, good.data)
        wrong = self.client.post(url, {"username": "throttle@test.com",
                                       "password": "still-wrong"},
                                 format='json')
        self.assertEqual(wrong.status_code, 400, wrong.data)

    def test_an_unknown_username_is_charged_too(self):
        # The cheapest branch to hammer: it answers without ever reaching a
        # password check, so it must cost the guesser something.
        from rest_framework.settings import api_settings
        from django.core.cache import cache
        cache.clear()
        limit = int(api_settings.DEFAULT_THROTTLE_RATES['login'].split('/')[0])
        url = reverse('auth-login')
        codes = [
            self.client.post(url, {"username": f"nobody-{i}@nowhere.test",
                                   "password": "guess"},
                             format='json').status_code
            for i in range(limit + 2)
        ]
        self.assertIn(429, codes, f"unknown usernames were never charged: {codes}")

    def test_a_correct_password_still_works_below_the_limit(self):
        from django.core.cache import cache
        cache.clear()
        url = reverse('auth-login')
        self.client.post(url, {"username": "throttle@test.com",
                               "password": "wrong-once"}, format='json')
        good = self.client.post(url, {"username": "throttle@test.com",
                                      "password": "a-real-password-1"},
                                format='json')
        self.assertEqual(good.status_code, 200, good.data)


class MobileNumberNormalisationTests(TenantTestCase):
    """The same person, typed two ways, must be the same customer.

    mobile_number is unique=True on the raw column and both search paths do a
    literal substring match, while validate_mobile_number used whatsapp_number
    only as a yes/no check and stored whatever was typed. So a returning client
    whose number was entered differently the second time missed the search,
    missed the unique index, and got a second profile -- splitting their
    measurements, order history and preferences with no signal to anyone.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "mobile@test.com"
        tenant.name = "Mobile Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username="mobile@test.com", email="mobile@test.com",
            password="owner-password-1")
        token = Token.objects.create(user=self.owner)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key,
                                HTTP_X_TENANT_ID=self.tenant.schema_name)

    def _create(self, mobile, first_name="Meera"):
        return self.client.post(reverse('customer-list'), {
            "first_name": first_name, "last_name": "Nair",
            "mobile_number": mobile,
        }, format='json')

    def test_the_stored_number_is_canonical(self):
        response = self._create("098765 43211")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Customer.objects.get(pk=response.data['id']).mobile_number,
                         "919876543211")

    def test_the_same_person_typed_differently_is_refused_as_a_duplicate(self):
        first = self._create("9876543211")
        self.assertEqual(first.status_code, 201, first.data)
        # Same person: +91 with a trunk zero and spaces.
        second = self._create("+91 (0) 98765 43211", first_name="Meera")
        self.assertEqual(second.status_code, 400,
                         f"a duplicate profile was created: {second.data}")
        self.assertEqual(Customer.objects.count(), 1)

    def test_the_international_access_code_reaches_the_same_record(self):
        self._create("9876543211")
        second = self._create("0091 9876543211")
        self.assertEqual(second.status_code, 400, second.data)
        self.assertEqual(Customer.objects.count(), 1)

    def test_an_unreachable_number_is_still_refused(self):
        response = self._create("12345")
        self.assertEqual(response.status_code, 400)


class RoleBoundaryTests(TenantTestCase):
    """What one role may read of another's work, inside one boutique.

    None of these is a cross-tenant leak -- django-tenants schema isolation
    holds. They are boundaries within a single shop, which is where the audit
    found every confirmed disclosure in the application layer.
    """

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "boundary@test.com"
        tenant.name = "Boundary Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        from django.db import connection
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username="boundary@test.com", email="boundary@test.com",
            password="owner-password-1")
        self.tailor_user = User.objects.create_user(
            username="stitcher@test.com", email="stitcher@test.com",
            password="tailor-password-1")
        self.tailor = Tailor.objects.create(
            name="Anya", specialty="Lehenga", role="Tailor",
            status="Available", user=self.tailor_user)

        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=self.tailor_user).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name)

    def test_a_tailor_cannot_read_garment_jobs_for_orders_that_are_not_theirs(self):
        """/api/catalog/jobs/ carried every client's measurements and the notes
        marked "Staff only -- never shown on the customer copy", narrowed only
        by an optional ?order= filter."""
        from apps.catalog.models import GarmentJob, GarmentTemplate
        from domains.orders.services import OrderService
        other_tailor = Tailor.objects.create(
            name="Ira", specialty="Gowns", role="Tailor", status="Available")
        stranger = Customer.objects.create(
            first_name="Not", last_name="Mine", mobile_number="919800000201")
        order = OrderService.create_order_for_customer(
            stranger, {"base_price": 10000, "tailor_id": other_tailor.id,
                       "master_id": other_tailor.id}, user=self.owner)
        template = GarmentTemplate.objects.first()
        GarmentJob.objects.create(
            order=order, template=template,
            measurements={'bust': 36, 'waist': 30})

        response = self.client.get('/api/catalog/jobs/')
        self.assertEqual(response.status_code, 200, response.data)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(list(rows), [], f"another tailor's garments leaked: {rows}")

    def test_a_tailor_cannot_read_stock_valuation(self):
        response = self.client.get('/api/inventory/items/')
        self.assertEqual(response.status_code, 403, response.data)

    def test_a_tailor_cannot_forge_a_notification_into_the_owners_feed(self):
        response = self.client.post(reverse('notification-list'), {
            'title': 'Payment received',
            'message': 'Please release the garment.',
            'recipient_role': 'Owner',
            'recipient_email': 'boundary@test.com',
        }, format='json')
        self.assertEqual(response.status_code, 403, response.data)
        self.assertFalse(Notification.objects.filter(title='Payment received').exists())

    def test_a_tailor_can_still_read_and_clear_their_own_notifications(self):
        # The bell is on every screen; breaking it drops the whole app for a
        # tailor, which is the outage OwnNotifications was written to fix.
        listing = self.client.get(reverse('notification-list'))
        self.assertEqual(listing.status_code, 200)
        cleared = self.client.post(reverse('notification-mark-all-read'), {}, format='json')
        self.assertEqual(cleared.status_code, 200, cleared.data)
