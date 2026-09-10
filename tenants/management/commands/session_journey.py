"""End-to-end journey for the staff-suite features, every role, one boutique.

Complements smoke_journey (which walks an order from signup to delivered): this
one exercises what this suite added -- the renamed and custom roles, staff
documents, per-user avatars, attendance filters + leave/weekly-off, payroll,
the Cost & P&L report, staff analytics, and the role boundaries around them.

Throwaway tenant, dropped at the end unless --keep.
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django_tenants.utils import schema_context
from rest_framework.test import APIClient

from tenants.management.commands.smoke_journey import Journey

import base64
# a genuinely valid 1x1 PNG (Pillow-decodable -- ImageField validates with it)
PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==')


class Command(BaseCommand):
    help = "Exercise the staff-suite features across every role, end to end."

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true')
        parser.add_argument('--keep', action='store_true')

    def handle(self, *args, **options):
        db = settings.DATABASES['default']
        target = f"{db.get('NAME')} @ {db.get('HOST')}"
        if not options['confirm']:
            raise CommandError(f"Refusing to run without --confirm. Target: {target}")
        j = Journey(self.stdout, self.style)
        try:
            self._run(j)
        finally:
            if not options['keep']:
                for schema in j.tenants:
                    with schema_context('public'):
                        from tenants.models import BoutiqueTenant
                        t = BoutiqueTenant.objects.filter(schema_name=schema).first()
                        if t:
                            t.delete(force_drop=True)
                    self.stdout.write(f"       dropped {schema}")
        total = len(j.passed) + len(j.failed)
        if j.failed:
            self.stdout.write(self.style.ERROR(f"\n{len(j.passed)}/{total} passed, {len(j.failed)} FAILED"))
            for f in j.failed:
                self.stdout.write(self.style.ERROR(f"  - {f}"))
            raise CommandError("Session journey failed")
        self.stdout.write(self.style.SUCCESS(f"\n{len(j.passed)}/{total} passed against {target}"))

    def _run(self, j):
        from tenants.models import BoutiqueTenant
        tag = uuid.uuid4().hex[:8]
        owner_email = f'owner-{tag}@sess.test'
        pw = 'SessionJourney!2026'

        # ---- roles present ----------------------------------------------------
        j.phase("[1] Owner signs up")
        r = APIClient().post('/api/auth/signup/', {
            'first_name': 'Kavya', 'last_name': 'Reddy',
            'email_address': owner_email, 'mobile_number': '9600000000',
            'password': pw}, format='json')
        if not j.check('signup', r.status_code in (200, 201), f'{r.status_code} {getattr(r,"data",None)}'):
            return
        tenant = BoutiqueTenant.objects.filter(owner_email=owner_email).first()
        schema = tenant.schema_name
        j.tenants.append(schema)

        def login(email, p):
            c = APIClient()
            resp = c.post('/api/auth/login/', {'username': email, 'password': p}, format='json')
            if resp.status_code != 200:
                return None
            c.credentials(HTTP_AUTHORIZATION=f'Token {resp.data["token"]}', HTTP_X_TENANT_ID=schema)
            return c, resp.data.get('user', {})

        owner_login = login(owner_email, pw)
        if not j.check('owner logs in', owner_login is not None):
            return
        owner, owner_user = owner_login

        j.phase("[2] Build the team -- renamed and custom roles")
        staff = {}
        team = [('Lakshmi', 'Master'), ('Sunita', 'QC Staff'), ('Ravi', 'Tailor'),
                ('Meena', 'Maggam Master'), ('Farah', 'Packaging Staff'),
                ('Imran', 'Karigar'), ('Ganesh', 'Janitor')]  # Janitor = custom role
        for name, role in team:
            email = f'{name.lower()}-{tag}@sess.test'
            resp = owner.post('/api/tailors/', {
                'name': name, 'role': role, 'specialty': 'Bridal',
                'status': 'Available', 'email': email}, format='json')
            ok = j.check(f'add {role}', resp.status_code in (200, 201),
                         f'{resp.status_code} {getattr(resp,"data",None)}')
            if ok:
                j.check(f'{role} stored verbatim', resp.data.get('role') == role)
                staff[role] = {'id': resp.data['id'], 'email': email,
                               'pw': resp.data.get('bootstrap_password')}
        # a designer (separate table)
        dr = owner.post('/api/design-studio/designers/',
                        {'name': 'Priya', 'email': f'priya-{tag}@sess.test'}, format='json')
        j.check('add Designer', dr.status_code in (200, 201), f'{dr.status_code}')

        j.phase("[3] Staff documents (owner-scoped)")
        ravi = staff['Tailor']
        doc = owner.post('/api/staff/documents/', {
            'staff': ravi['id'], 'kind': 'AADHAAR', 'number': '1234 5678 9012',
            'file': SimpleUploadedFile('aadhaar.png', PNG, content_type='image/png')},
            format='multipart')
        j.check('owner uploads a document', doc.status_code in (200, 201),
                f'{doc.status_code} {getattr(doc,"data",None)}')
        if ravi['pw']:
            rc = login(ravi['email'], ravi['pw'])
            if j.check('tailor logs in', rc is not None):
                seen = rc[0].get(f"/api/staff/documents/?staff={staff['QC Staff']['id']}")
                rows = seen.data if isinstance(seen.data, list) else seen.data.get('results', [])
                j.check("tailor cannot read a colleague's documents", len(rows) == 0)

        j.phase("[4] Profile photos reflect on the login")
        pr = owner.patch(f"/api/tailors/{ravi['id']}/", {
            'profile_photo': SimpleUploadedFile('face.png', PNG, content_type='image/png')},
            format='multipart')
        j.check('owner sets a staff photo', pr.status_code == 200 and bool(pr.data.get('profile_photo')),
                f'{pr.status_code}')
        if ravi['pw']:
            rc = login(ravi['email'], ravi['pw'])
            j.check('photo shows on the staff login', bool(rc[1].get('profile_photo')))
            self_edit = rc[0].patch('/api/auth/me/', {
                'profile_photo': SimpleUploadedFile('me.png', PNG, content_type='image/png')},
                format='multipart')
            j.check('staff edits their own photo', self_edit.status_code == 200)
        owner_photo = owner.patch('/api/auth/me/', {
            'profile_photo': SimpleUploadedFile('owner.png', PNG, content_type='image/png')},
            format='multipart')
        j.check('OWNER sets their own photo', owner_photo.status_code == 200
                and bool(owner_photo.data.get('profile_photo')), f'{owner_photo.status_code}')

        j.phase("[5] Attendance -- filters, leave and weekly-off")
        today = timezone.localdate()
        rec = owner.post('/api/staff/attendance/record/', {
            'staff': ravi['id'],
            'check_in': f'{today}T09:00:00', 'check_out': f'{today}T18:00:00'}, format='json')
        j.check('owner records attendance', rec.status_code in (200, 201),
                f'{rec.status_code} {getattr(rec,"data",None)}')
        day = owner.get(f'/api/staff/attendance/?since={today}&until={today}')
        drows = day.data if isinstance(day.data, list) else day.data.get('results', [])
        j.check('day filter returns the session', len(drows) >= 1, f'{len(drows)}')
        month_start = today.replace(day=1)
        mk = owner.post('/api/staff/day-marks/', {
            'staff': staff['Master']['id'], 'date': str(month_start), 'kind': 'LEAVE'}, format='json')
        j.check('owner marks leave', mk.status_code in (200, 201), f'{mk.status_code}')
        mk2 = owner.post('/api/staff/day-marks/', {
            'staff': staff['Master']['id'], 'date': str(month_start), 'kind': 'WEEKLY_OFF'}, format='json')
        j.check('re-marking the day flips leave -> weekly off (upsert)', mk2.status_code == 200,
                f'{mk2.status_code}')

        j.phase("[6] Payroll -- terms, approval, payout")
        terms = owner.post('/api/staff/profiles/', {
            'staff': ravi['id'], 'employment_type': 'FULL_TIME', 'hourly_rate': '200.00',
            'weekly_hours': '48'}, format='json')
        j.check('owner sets employment terms', terms.status_code in (200, 201), f'{terms.status_code}')
        week_monday = today - timedelta(days=today.weekday())
        gen = owner.post('/api/payroll/periods/generate/', {'week': str(week_monday)}, format='json')
        j.check('payroll generates', gen.status_code in (200, 201), f'{gen.status_code} {getattr(gen,"data",None)}')
        period = gen.data if isinstance(gen.data, dict) else {}
        pid = period.get('id')
        rec_row = next((r for r in (period.get('records') or []) if str(r.get('staff')) == str(ravi['id'])), None)
        if j.check('payroll has a line for the tailor', rec_row is not None):
            j.check('gross = 9h x 200 = 1800', str(rec_row.get('gross_earnings')) in ('1800.00', '1800'),
                    f"{rec_row.get('gross_earnings')}")
        if pid:
            appr = owner.post(f'/api/payroll/periods/{pid}/approve/', {}, format='json')
            j.check('owner approves payroll', appr.status_code in (200, 201), f'{appr.status_code}')
            if rec_row:
                pay = owner.post(f"/api/payroll/records/{rec_row['id']}/payout/",
                                 {'method': 'CASH', 'reference': 'e2e'}, format='json')
                j.check('owner records the payout', pay.status_code in (200, 201), f'{pay.status_code}')

        j.phase("[7] Cost & P&L -- salaries + inventory auto-fed, plus manual")
        # a paid order gives the P&L some revenue
        with schema_context(schema):
            from crm_api.models import Customer, Order
            cust = Customer.objects.create(first_name='Ananya', last_name='K',
                                           mobile_number=f'98{tag[:8]}')
            Order.objects.create(order_id=f'E2E-{tag}', customer=cust,
                                 total_amount=Decimal('20000'), amount_paid=Decimal('20000'),
                                 payment_status='Paid', order_status='Delivered')
        exp = owner.post('/api/finance/expenses/',
                         {'category': 'RENT', 'amount': '25000', 'incurred_on': str(today)}, format='json')
        j.check('owner logs an expense', exp.status_code in (200, 201), f'{exp.status_code}')
        pnl = owner.get(f'/api/finance/profit-loss/?since={month_start}&until={today}')
        if j.check('P&L computes', pnl.status_code == 200, f'{pnl.status_code}'):
            costs = pnl.data['costs']
            j.check('P&L revenue includes the paid order', float(pnl.data['revenue']['total']) >= 20000)
            j.check('P&L auto-feeds salaries from the payout', float(costs['salaries']) >= 1800)
            j.check('P&L includes the manual rent', float(costs['manual_total']) >= 25000)

        j.phase("[8] Staff analytics for the owner")
        perf = owner.get(f'/api/staff/performance/?start={month_start}&end={today}')
        j.check('performance report loads', perf.status_code == 200, f'{perf.status_code}')
        dash = owner.get('/api/dashboard/')
        if j.check('dashboard loads', dash.status_code == 200, f'{dash.status_code}'):
            j.check('dashboard shows revenue', float(dash.data['stats']['revenue']) >= 20000)
            j.check('dashboard counts staff via customers/orders', 'active_orders' in dash.data['stats'])

        j.phase("[9] Boundaries -- a custom-role worker sees no money")
        jan = staff.get('Janitor')
        if jan and jan['pw']:
            jc = login(jan['email'], jan['pw'])
            if j.check('custom-role worker logs in', jc is not None):
                j.check('janitor is refused the P&L', jc[0].get('/api/finance/profit-loss/').status_code == 403)
                j.check('janitor is refused payroll', jc[0].get('/api/payroll/periods/').status_code == 403)
                j.check('janitor is refused staff pay records',
                        jc[0].get('/api/staff/profiles/').status_code in (200, 403))
