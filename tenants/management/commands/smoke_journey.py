
import os
import uuid
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.test import Client
from django_tenants.utils import schema_context
from rest_framework.test import APIClient


class Journey:

    def __init__(self, stdout, style):
        self.stdout, self.style = stdout, style
        self.passed, self.failed = [], []
        self.tenants = []

    def phase(self, title):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n{title}"))

    def check(self, label, ok, detail=''):
        if ok:
            self.passed.append(label)
            self.stdout.write(self.style.SUCCESS(f"  OK   {label}"))
        else:
            self.failed.append(label)
            self.stdout.write(self.style.ERROR(
                f"  FAIL {label}" + (f"  -- {detail}" if detail else '')))
        return ok

    def note(self, text):
        self.stdout.write(f"       {text}")


class Command(BaseCommand):
    help = "Provision a throwaway boutique and take one order from signup to delivered."

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm', action='store_true',
            help='Required. This command writes to the database it is pointed at.')
        parser.add_argument(
            '--keep', action='store_true',
            help='Leave the throwaway tenants behind for inspection.')

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        target = f"{db.get('NAME')} @ {db.get('HOST')}"
        self.stdout.write(self.style.WARNING(f"Target database: {target}"))
        if not options['confirm']:
            raise CommandError(
                "Refusing to run without --confirm. This creates a boutique, a "
                "customer and an order in the database named above. Check that "
                "it is the one you meant -- staging, not production."
            )

        j = Journey(self.stdout, self.style)
        try:
            self._environment(j, db)
            self._run(j)
        finally:
            if options['keep']:
                self.stdout.write(f"\nLeaving behind: {', '.join(j.tenants) or 'nothing'}")
            else:
                self._cleanup(j)

        self.stdout.write("")
        total = len(j.passed) + len(j.failed)
        if j.failed:
            self.stdout.write(self.style.ERROR(
                f"{len(j.passed)}/{total} passed, {len(j.failed)} FAILED"))
            for f in j.failed:
                self.stdout.write(self.style.ERROR(f"  - {f}"))
            raise CommandError("Smoke journey failed against " + target)
        self.stdout.write(self.style.SUCCESS(f"{len(j.passed)}/{total} passed against {target}"))

    def _environment(self, j, db):
        j.phase("[0] Environment")
        with connection.cursor() as cursor:
            cursor.execute("SELECT version()")
            version = cursor.fetchone()[0]
            cursor.execute(
                "SELECT reset_val FROM pg_settings WHERE name = 'TimeZone'")
            row = cursor.fetchone()
            server_tz = row[0] if row else 'unknown'
            try:
                cursor.execute(
                    "SELECT ssl, version FROM pg_stat_ssl WHERE pid = pg_backend_pid()")
                row = cursor.fetchone()
                ssl_on, ssl_version = (bool(row[0]), row[1]) if row else (False, None)
            except Exception:
                ssl_on, ssl_version = False, None
            cursor.execute("SELECT current_setting('TimeZone')")
            session_tz = cursor.fetchone()[0]

        j.note(version)
        j.note(f"server default timezone {server_tz}; this session {session_tz}")

        host = (db.get('HOST') or '').strip()
        local = host in ('', 'localhost', '127.0.0.1', '::1')
        requested = os.environ.get('DB_SSLMODE', '(unset -- libpq default `prefer`)')
        j.note(f"DB_SSLMODE={requested}")
        if ssl_on:
            j.check(f'connection is encrypted ({ssl_version})', True)
        else:
            j.check('connection is encrypted', local,
                    f'host={host} is remote and TLS was not negotiated -- '
                    f'set DB_SSLMODE=require')
            if local:
                j.note('TLS not negotiated, and not required over loopback')

        j.check('session runs in UTC regardless of the server clock',
                session_tz.upper() == 'UTC', session_tz)



    def _run(self, j):
        from tenants.models import BoutiqueTenant

        tag = uuid.uuid4().hex[:8]
        owner_email = f'smoke-{tag}@smoke.test'
        password = 'SmokeJourney!2026'

        j.phase("[1] Signup provisions a boutique")
        r = APIClient().post('/api/auth/signup/', {
            'first_name': 'Smoke', 'last_name': 'Test',
            'email_address': owner_email, 'mobile_number': '9600000000',
            'password': password}, format='json')
        if not j.check('signup succeeds', r.status_code in (200, 201),
                       f'{r.status_code} {getattr(r, "data", None)}'):
            return
        tenant = BoutiqueTenant.objects.filter(owner_email=owner_email).first()
        if not j.check('tenant row created', tenant is not None):
            return
        schema = tenant.schema_name
        j.tenants.append(schema)
        j.check('tenant carries a timezone', bool(tenant.timezone), '')
        j.note(f"schema={schema} tz={tenant.timezone}")

        def login(email, pw):
            c = APIClient()
            resp = c.post('/api/auth/login/',
                          {'username': email, 'password': pw}, format='json')
            if resp.status_code != 200:
                return None
            c.credentials(HTTP_AUTHORIZATION=f'Token {resp.data.get("token")}',
                          HTTP_X_TENANT_ID=schema)
            return c

        owner = login(owner_email, password)
        if not j.check('owner can log in', owner is not None):
            return

        j.phase("[2] The new boutique is usable")
        with schema_context(schema):
            from apps.catalog.models import GarmentTemplate
            from crm_api.models import Customer, Order
            j.check('garment templates provisioned',
                    GarmentTemplate.objects.count() >= 10)
            j.check('no business data yet',
                    Customer.objects.count() == 0 and Order.objects.count() == 0)
            blouse = str(GarmentTemplate.objects.get(key='blouse').id)
            lehenga = str(GarmentTemplate.objects.get(key='lehenga').id)

        j.phase("[3] Staff and stock")
        staff = {}
        for name, role in (('Master Ravi', 'Master'), ('Tailor Sunita', 'Tailor'),
                           ('QC Anand', 'QC Master')):
            email = f'{role.split()[0].lower()}-{tag}@smoke.test'
            resp = owner.post('/api/tailors/', {
                'name': name, 'role': role, 'specialty': 'Bridal',
                'status': 'Available', 'email': email}, format='json')
            if j.check(f'onboard {role}', resp.status_code in (200, 201),
                       f'{resp.status_code}'):
                staff[role] = {'id': resp.data['id'], 'email': email,
                               'pw': resp.data.get('bootstrap_password')}

        resp = owner.post('/api/design-studio/designers/',
                          {'name': 'Designer Priya',
                           'email': f'designer-{tag}@smoke.test'}, format='json')
        designer_id = resp.data['id'] if resp.status_code in (200, 201) else None
        j.check('create designer', designer_id is not None, f'{resp.status_code}')
        designer_pw = None
        if designer_id:
            resp = owner.post(
                f'/api/design-studio/designers/{designer_id}/create-login/',
                {'email': f'designer-{tag}@smoke.test'}, format='json')
            if j.check('designer gets a login', resp.status_code in (200, 201)):
                designer_pw = resp.data.get('bootstrap_password')

        resp = owner.post('/api/inventory/items/', {
            'item_code': f'SMOKE-{tag}', 'name': 'Smoke Brocade',
            'category': 'FABRIC', 'unit': 'METER',
            'purchase_price': '450', 'reorder_level': '5'}, format='json')
        item = resp.data['id'] if resp.status_code in (200, 201) else None
        j.check('create inventory item', item is not None, f'{resp.status_code}')
        if item:
            resp = owner.post(f'/api/inventory/items/{item}/stock-in/',
                              {'quantity': '30', 'remarks': 'smoke'}, format='json')
            j.check('stock in', resp.status_code in (200, 201), f'{resp.status_code}')

        j.phase("[4] Two-garment draft, personalised before any customer exists")
        payload = self._draft_payload(blouse, lehenga, item, staff)
        r = owner.post('/api/order-drafts/',
                       {'payload': payload, 'current_step': 6}, format='json')
        if not j.check('draft saved', r.status_code == 201,
                       f'{r.status_code} {getattr(r, "data", None)}'):
            return
        draft_id = r.data['id']
        with schema_context(schema):
            from crm_api.models import Customer, Order
            j.check('draft created no customer and no order',
                    Customer.objects.count() == 0 and Order.objects.count() == 0)
        for key in ('blouse', 'lehenga'):
            resp = owner.get('/api/design-studio/context/',
                             {'draft_id': draft_id, 'garment_key': key})
            ok = resp.status_code == 200
            j.check(f'{key} personalises from the draft', ok, f'{resp.status_code}')
            if ok:
                j.check(f'{key} needs no customer row',
                        resp.data['context']['customer_id'] == '')

        j.phase("[5] Atomic confirm")
        r = owner.post(f'/api/order-drafts/{draft_id}/confirm/')
        if not j.check('confirm succeeds', r.status_code == 201,
                       f'{r.status_code} {getattr(r, "data", None)}'):
            return
        order_id = r.data['order_id']
        j.note(f"order={order_id}")
        j.check('confirm retry refused',
                owner.post(f'/api/order-drafts/{draft_id}/confirm/').status_code == 409)

        with schema_context(schema):
            from crm_api.models import Customer, Order, OrderDraft
            from apps.design_studio.models import DesignBoard, DesignBoardItem
            j.check('exactly one customer', Customer.objects.count() == 1)
            j.check('draft consumed', OrderDraft.objects.count() == 0)
            order = Order.objects.get(order_id=order_id)
            jobs = {job.template.key: job for job in order.garment_jobs.all()}
            j.check('two garment jobs', len(jobs) == 2)
            j.check('each garment priced on its own job',
                    jobs['blouse'].base_price == Decimal('15000')
                    and jobs['lehenga'].base_price == Decimal('132000'))
            j.check('order total is the rollup plus tax',
                    order.base_price == Decimal('147000') and order.total_amount > 0,
                    str(order.total_amount))
            j.check('one design board', DesignBoard.objects.count() == 1)
            by_garment = {i.garment_job.template.key: i.title for i
                          in DesignBoardItem.objects.select_related('garment_job__template')}
            j.check('each design on its own garment',
                    by_garment.get('blouse') == 'Blouse Reference'
                    and by_garment.get('lehenga') == 'Lehenga Reference', str(by_garment))
            order_pk = order.pk
            blouse_job_id = str(jobs['blouse'].id)

        j.phase("[6] Designer receives, submits; owner approves")
        if designer_id and designer_pw:
            designer = login(f'designer-{tag}@smoke.test', designer_pw)
            if j.check('designer can log in', designer is not None):
                r = owner.post('/api/design-studio/assignments/',
                               {'garment_job': blouse_job_id, 'designer': designer_id,
                                'brief': 'Smoke brief.'}, format='json')
                if j.check('owner assigns the blouse', r.status_code == 201,
                           f'{r.status_code} {getattr(r, "data", None)}'):
                    assignment = r.data['id']
                    rows = designer.get('/api/design-studio/assignments/',
                                        {'open': '1'}).data
                    rows = rows['results'] if isinstance(rows, dict) else rows
                    j.check('designer sees only their own work', len(rows) == 1)
                    j.check('designer payload withholds the customer',
                            rows and 'customer_name' not in rows[0])
                    r = designer.post('/api/design-studio/assets/', {
                        'title': 'Smoke Design', 'image_url': 'https://smoke.test/d.jpg',
                        'source': 'upload'}, format='json')
                    if j.check('designer uploads', r.status_code in (200, 201)):
                        design = r.data['id']
                        j.check('designer submits', designer.post(
                            f'/api/design-studio/assignments/{assignment}/submit/',
                            {'design': design}, format='json').status_code == 200)
                        j.check('owner approves', owner.post(
                            f'/api/design-studio/assignments/{assignment}/review/',
                            {'decision': 'approve'}, format='json').status_code == 200)

        j.phase("[7] Production floor, inventory and quality check")
        with schema_context(schema):
            from crm_api.models import BoutiqueSettings
            config = BoutiqueSettings.objects.get_or_create(id=1)[0].workflow_config
        keys = [s['key'] for s in config]

        def step(client, key, status='COMPLETED'):
            return client.post(f'/api/orders/{order_pk}/transition/',
                               {'stage_key': key, 'status': status}, format='json')

        broke = None
        for key in keys[:keys.index('master_quality_check')]:
            with schema_context(schema):
                from crm_api.models import Order
                stage = Order.objects.get(pk=order_pk).stages.filter(stage_key=key).first()
            if stage is None or stage.status in ('COMPLETED', 'SKIPPED'):
                continue
            optional = next((s.get('optional') for s in config if s['key'] == key), False)
            resp = step(owner, key, 'SKIPPED' if optional else 'COMPLETED')
            if resp.status_code != 200:
                broke = f'{key}: {resp.status_code} {getattr(resp, "data", None)}'
                break
        j.check('order walks to quality check', broke is None, broke or '')

        with schema_context(schema):
            from apps.inventory.models import OrderMaterialPlan, OrderMaterialLine, StockMovement
            plan = OrderMaterialPlan.objects.filter(order_id=order_pk).first()
            j.check('material plan built once production started', plan is not None)
            if plan:
                lines = OrderMaterialLine.objects.filter(plan=plan)
                j.check('materials attributed per garment',
                        lines.count() >= 2 and all(l.garment_job_id for l in lines))
            j.check('stock reserved and consumed',
                    StockMovement.objects.filter(
                        movement_type__in=['RESERVATION', 'CONSUMPTION']).exists())

        if 'QC Master' in staff and staff['QC Master']['pw']:
            qc = login(staff['QC Master']['email'], staff['QC Master']['pw'])
            if j.check('QC Master can log in', qc is not None):
                rows = qc.get('/api/orders/').data
                rows = rows['results'] if isinstance(rows, dict) else rows
                j.check('QC Master discovers the order unassigned',
                        any(o['order_id'] == order_id for o in rows),
                        f'{len(rows)} visible')
                with schema_context(schema):
                    from crm_api.models import Order
                    stage = Order.objects.get(pk=order_pk).stages.get(
                        stage_key='master_quality_check')
                    j.check('nobody assigned the QC stage', stage.assigned_to_id is None)
                j.check('QC Master completes the inspection',
                        step(qc, 'master_quality_check').status_code == 200)

        for key in keys[keys.index('master_quality_check') + 1:]:
            resp = step(owner, key)
            if resp.status_code != 200:
                j.check(f'stage {key}', False,
                        f'{resp.status_code} {getattr(resp, "data", None)}')
                break
        with schema_context(schema):
            from crm_api.models import Order
            order = Order.objects.get(pk=order_pk)
            j.check('order reaches Delivered', order.order_status == 'Delivered',
                    order.order_status)

        j.phase("[8] What the customer sees")
        from core.formatting import format_money, format_datetime
        with schema_context(schema):
            from crm_api.models import Order, Notification
            from domains.orders.tracking import build_token
            order = Order.objects.get(pk=order_pk)
            token = build_token(order)
            total, paid = order.total_amount, order.amount_paid
            stage = order.stages.filter(completed_at__isnull=False).first()
            stamp = stage.completed_at if stage else None
            balance_msgs = [n.message for n in
                            Notification.objects.filter(recipient_role='Customer')
                            if 'balance' in n.message.lower()]

        page = Client().get(f'/track/{token}/').content.decode()
        j.check('tracking page renders', order_id in page)
        j.check('total matches the ledger', format_money(total) in page,
                format_money(total))
        j.check('balance matches the ledger',
                format_money(total - paid) in page, format_money(total - paid))
        if stamp is not None:
            local = format_datetime(stamp, tenant)
            j.check(f'timestamp in the boutique clock ({local})', local in page)
        if balance_msgs:
            j.check('customer message quotes the same balance',
                    format_money(total - paid) in balance_msgs[0])

        j.phase("[9] Boundaries")
        if designer_pw:
            d = login(f'designer-{tag}@smoke.test', designer_pw)
            if d:
                resp = d.get('/api/orders/')
                body = resp.data
                if isinstance(body, dict):
                    body = body.get('results')
                j.check('designer sees no orders',
                        resp.status_code in (401, 403)
                        or (isinstance(body, list) and len(body) == 0),
                        f'{resp.status_code} {str(resp.data)[:60]}')
        anon = APIClient()
        anon.credentials(HTTP_X_TENANT_ID=schema)
        j.check('anonymous refused the order book',
                anon.get('/api/orders/').status_code in (401, 403))

        second = APIClient().post('/api/auth/signup/', {
            'first_name': 'Second', 'last_name': 'House',
            'email_address': f'second-{tag}@smoke.test', 'mobile_number': '9600000001',
            'password': password}, format='json')
        if j.check('a second boutique provisions', second.status_code in (200, 201)):
            other = BoutiqueTenant.objects.filter(
                owner_email=f'second-{tag}@smoke.test').first()
            if other:
                j.tenants.append(other.schema_name)
                cross = APIClient()
                lr = cross.post('/api/auth/login/',
                                {'username': owner_email, 'password': password},
                                format='json')
                cross.credentials(HTTP_AUTHORIZATION=f'Token {lr.data.get("token")}',
                                  HTTP_X_TENANT_ID=other.schema_name)
                body = str(getattr(cross.get('/api/customers/'), 'data', ''))
                j.check("one boutique's token cannot read another's customers",
                        'Smoke Client' not in body, body[:80])

    def _draft_payload(self, blouse, lehenga, item, staff):
        materials = ([{'field_key': 'main_fabric', 'inventory_item': item,
                       'quantity': '2', 'source': 'STORE'}] if item else [])
        materials2 = ([{'field_key': 'fabric', 'inventory_item': item,
                        'quantity': '4.5', 'source': 'STORE'}] if item else [])
        return {
            'first_name': 'Smoke', 'last_name': 'Client',
            'mobile_number': '919600000009', 'email_address': 'client@smoke.test',
            'address': '1 Smoke Street', 'customer_type': 'Women',
            'occasion': 'Wedding', 'neckline_style': 'Sweetheart',
            'measurements': {'bust': '38', 'waist': '28', 'hips': '40'},
            'prices': {'packaging': 500, 'discount': 2000},
            'payment': {'option': 'partial', 'advance': 20000},
            'staff': {'tailor_id': staff.get('Tailor', {}).get('id'),
                      'master_id': staff.get('Master', {}).get('id')},
            'garments': [
                {'key': 'blouse', 'template_key': 'blouse', 'template': blouse,
                 'spec': {'blouse_type': 'princess', 'sleeve_length': 'elbow',
                          'front_neck': 'Deep V'},
                 'measurements': {'chest': '36', 'waist': '28'},
                 'pricing': {'base': 15000, 'fabric': 0, 'embroidery': 2500,
                             'customization': 0, 'tailoring': 1500},
                 'design': {'items': [{'source': 'catalogue', 'source_ref': 'b1',
                                       'title': 'Blouse Reference',
                                       'image_url': 'https://smoke.test/b.jpg',
                                       'is_selected': True}]},
                 'materials': materials},
                {'key': 'lehenga', 'template_key': 'lehenga', 'template': lehenga,
                 'spec': {'lehenga_type': 'a_line'},
                 'measurements': {'waist': '32', 'floor_length': '41'},
                 'pricing': {'base': 132000, 'fabric': 0, 'embroidery': 0,
                             'customization': 0, 'tailoring': 0},
                 'design': {'items': [{'source': 'catalogue', 'source_ref': 'l1',
                                       'title': 'Lehenga Reference',
                                       'image_url': 'https://smoke.test/l.jpg',
                                       'is_selected': True}]},
                 'materials': materials2},
            ],
        }

    def _cleanup(self, j):
        from tenants.models import BoutiqueTenant
        connection.set_schema_to_public()
        for schema in j.tenants:
            try:
                BoutiqueTenant.objects.get(schema_name=schema).delete(force_drop=True)
                self.stdout.write(f"       dropped {schema}")
            except Exception as exc:
                self.stdout.write(self.style.WARNING(
                    f"       could not drop {schema}: {exc}"))
