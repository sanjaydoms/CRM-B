from django.contrib.auth.models import User
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.models import BoutiqueFabric, FabricPlacement

FABRICS = '/api/fabrics/'
OWNER_EMAIL = 'owner@fabrics.test'


class FabricPlacementTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = OWNER_EMAIL
        tenant.name = 'Fabric Atelier'
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.owner = User.objects.create_user(
            username=OWNER_EMAIL, email=OWNER_EMAIL, password='ownerpass123')
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION='Token ' + Token.objects.create(user=self.owner).key,
            HTTP_X_TENANT_ID=self.tenant.schema_name)

    def payload(self, **kw):
        data = {'name': 'Red Silk', 'material': 'Silk', 'color': 'Red',
                'price_per_meter': '450.00'}
        data.update(kw)
        return data

    def create(self, expect=status.HTTP_201_CREATED, **kw):
        res = self.client.post(FABRICS, self.payload(**kw), format='json')
        self.assertEqual(res.status_code, expect, res.data)
        return res.data

    def paths(self, data):
        return sorted(p['path'] for p in data['placements'])

    # 1-2: nothing that worked before may stop working ---------------------

    def test_legacy_create_without_any_classification(self):
        data = self.create()
        self.assertEqual(data['kind'], '')
        self.assertEqual(data['variant'], '')
        self.assertEqual(data['placements'], [])
        self.assertEqual(data['kind_label'], '')
        self.assertFalse(data['is_accessory'])

    def test_legacy_crud_round_trip(self):
        fabric_id = self.create()['id']
        listed = self.client.get(FABRICS)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data), 1)

        patched = self.client.patch(f'{FABRICS}{fabric_id}/',
                                    {'color': 'Blue'}, format='json')
        self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)
        self.assertEqual(patched.data['color'], 'Blue')

        removed = self.client.delete(f'{FABRICS}{fabric_id}/')
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(BoutiqueFabric.objects.filter(id=fabric_id).exists())

    def test_a_row_written_before_this_feature_reads_and_edits(self):
        legacy = BoutiqueFabric.objects.create(
            name='Old Silk', material='Silk', color='Gold', price_per_meter=900)
        row = self.client.get(f'{FABRICS}{legacy.id}/').data
        self.assertEqual(row['placements'], [])

        res = self.client.patch(f'{FABRICS}{legacy.id}/',
                                {'price_per_meter': '950.00'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

    # 3: taxonomy ----------------------------------------------------------

    def test_taxonomy_endpoint(self):
        res = self.client.get(f'{FABRICS}taxonomy/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        garments = [g['key'] for g in res.data['garments']]
        self.assertEqual(garments, ['saree', 'blouse', 'lehenga', 'dupatta',
                                    'kurti', 'anarkali', 'petticoat',
                                    'bottom_wear', 'gown', 'suit', 'sherwani'])

        lehenga = next(g for g in res.data['garments'] if g['key'] == 'lehenga')
        self.assertEqual(lehenga['section_label'], 'Lehenga Section')
        self.assertEqual([s['key'] for s in lehenga['sections']],
                         ['BLOUSE', 'SKIRT', 'DUPATTA'])
        skirt = next(s for s in lehenga['sections'] if s['key'] == 'SKIRT')
        self.assertIn('CAN_CAN', [s['key'] for s in skirt['slots']])

        saree = next(g for g in res.data['garments'] if g['key'] == 'saree')
        self.assertEqual(saree['section_label'], '')
        self.assertEqual([s['key'] for s in saree['sections']], [''])

        dori = next(k for k in res.data['kinds'] if k['key'] == 'DORI')
        self.assertEqual(dori['variant_label'], 'Dori Type')
        self.assertEqual([v['key'] for v in dori['variants']],
                         ['LATKAN_DORI', 'FABRIC_FLOWER_DORI', 'POTLI_DORI',
                          'OTHER_DORI'])
        self.assertEqual(
            len([k for k in res.data['kinds'] if k['accessory']]), 16)

    # 4-7: identity and reuse ---------------------------------------------

    def test_one_placement(self):
        data = self.create(kind='FABRIC', placements=[
            {'garment': 'lehenga', 'section': 'SKIRT', 'slot': 'MAIN_FABRIC'}])
        self.assertEqual(self.paths(data), ['Lehenga / Skirt / Main Fabric'])

    def test_the_same_material_serves_many_garments(self):
        data = self.create(
            name='Gold Latkan Dori', material='Dori', color='Gold',
            kind='DORI', variant='LATKAN_DORI',
            placements=[
                {'garment': 'lehenga', 'section': 'BLOUSE', 'slot': 'DORI'},
                {'garment': 'blouse', 'section': '', 'slot': 'DORI'},
                {'garment': 'kurti', 'section': '', 'slot': 'TASSEL_LATKAN'},
                {'garment': 'suit', 'section': '', 'slot': 'DORI'},
            ])
        self.assertEqual(BoutiqueFabric.objects.count(), 1)
        self.assertEqual(len(data['placements']), 4)
        self.assertEqual(data['variant_label'], 'Latkan Dori')
        self.assertTrue(data['is_accessory'])

    def test_one_roll_in_two_different_roles(self):
        data = self.create(kind='FABRIC', placements=[
            {'garment': 'lehenga', 'section': 'SKIRT', 'slot': 'MAIN_FABRIC'},
            {'garment': 'saree', 'section': '', 'slot': 'BACKING_FABRIC'}])
        self.assertEqual(BoutiqueFabric.objects.count(), 1)
        self.assertEqual(self.paths(data),
                         ['Lehenga / Skirt / Main Fabric', 'Saree / Backing Fabric'])

    def test_every_lehenga_section(self):
        data = self.create(kind='BORDER', placements=[
            {'garment': 'lehenga', 'section': 'BLOUSE', 'slot': 'BORDER'},
            {'garment': 'lehenga', 'section': 'SKIRT', 'slot': 'BORDER'},
            {'garment': 'lehenga', 'section': 'DUPATTA', 'slot': 'BORDER'}])
        self.assertEqual(len(data['placements']), 3)

    def test_a_garment_wide_placement(self):
        data = self.create(kind='FABRIC', placements=[
            {'garment': 'saree', 'section': '', 'slot': ''}])
        self.assertEqual(self.paths(data), ['Saree'])

    # 8-9: accessories -----------------------------------------------------

    def test_an_accessory_needs_no_placement(self):
        data = self.create(name='Gold Gota', material='Gota', color='Gold',
                           kind='GOTA')
        self.assertEqual(data['placements'], [])
        self.assertTrue(data['is_accessory'])
        self.assertEqual(data['kind_label'], 'Gota')

    def test_every_dori_variant(self):
        for variant, label in (('LATKAN_DORI', 'Latkan Dori'),
                               ('FABRIC_FLOWER_DORI', 'Fabric Flower Dori'),
                               ('POTLI_DORI', 'Potli Dori'),
                               ('OTHER_DORI', 'Other Dori')):
            data = self.create(name=f'Dori {variant}', kind='DORI',
                               variant=variant)
            self.assertEqual(data['variant_label'], label)

    # 10-11: PATCH semantics ----------------------------------------------

    def test_patch_with_placements_replaces_them(self):
        fabric_id = self.create(kind='DORI', variant='POTLI_DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'}])['id']
        res = self.client.patch(f'{FABRICS}{fabric_id}/', {'placements': [
            {'garment': 'kurti', 'section': '', 'slot': 'DORI'},
            {'garment': 'suit', 'section': '', 'slot': 'DORI'}]}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(self.paths(res.data), ['Kurti / Dori', 'Suit (Kameez) / Dori'])
        self.assertEqual(FabricPlacement.objects.filter(fabric_id=fabric_id).count(), 2)

    def test_patch_without_placements_preserves_them(self):
        fabric_id = self.create(kind='DORI', variant='POTLI_DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'},
            {'garment': 'kurti', 'section': '', 'slot': 'DORI'}])['id']
        res = self.client.patch(f'{FABRICS}{fabric_id}/',
                                {'color': 'Ivory'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(len(res.data['placements']), 2)

    def test_placements_can_be_emptied_explicitly(self):
        fabric_id = self.create(kind='DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'}])['id']
        res = self.client.patch(f'{FABRICS}{fabric_id}/', {'placements': []},
                                format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data['placements'], [])

    def test_a_repeated_placement_is_collapsed(self):
        data = self.create(kind='DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'},
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'}])
        self.assertEqual(len(data['placements']), 1)

    # 12: bad input is refused, nothing is written -------------------------

    def test_unknown_garment_is_refused(self):
        self.create(expect=status.HTTP_400_BAD_REQUEST, placements=[
            {'garment': 'trousers', 'section': '', 'slot': ''}])
        self.assertEqual(BoutiqueFabric.objects.count(), 0)

    def test_section_must_belong_to_the_garment(self):
        self.create(expect=status.HTTP_400_BAD_REQUEST, placements=[
            {'garment': 'saree', 'section': 'BLOUSE', 'slot': ''}])

    def test_slot_must_belong_to_the_section(self):
        self.create(expect=status.HTTP_400_BAD_REQUEST, placements=[
            {'garment': 'lehenga', 'section': 'SKIRT', 'slot': 'DORI'}])

    def test_a_sectioned_garment_needs_its_section(self):
        self.create(expect=status.HTTP_400_BAD_REQUEST, placements=[
            {'garment': 'lehenga', 'section': '', 'slot': 'MAIN_FABRIC'}])

    def test_unknown_kind_and_variant_are_refused(self):
        self.create(expect=status.HTTP_400_BAD_REQUEST, kind='TROUSERS')
        self.create(expect=status.HTTP_400_BAD_REQUEST,
                    kind='DORI', variant='NOT_A_DORI')
        self.create(expect=status.HTTP_400_BAD_REQUEST,
                    kind='BUTTON', variant='LATKAN_DORI')

    # taxonomy guides, it does not restrict -------------------------------

    def test_a_kind_is_never_blocked_by_the_slot_it_is_put_in(self):
        """A boutique may use what it has; the taxonomy is not a rule engine."""
        data = self.create(kind='DORI', variant='LATKAN_DORI', placements=[
            {'garment': 'lehenga', 'section': 'SKIRT', 'slot': 'MAIN_FABRIC'}])
        self.assertEqual(self.paths(data), ['Lehenga / Skirt / Main Fabric'])

    # filtering ------------------------------------------------------------

    def test_filters(self):
        self.create(name='Gold Dori', kind='DORI', variant='LATKAN_DORI',
                    placements=[{'garment': 'blouse', 'section': '', 'slot': 'DORI'},
                                {'garment': 'kurti', 'section': '', 'slot': 'DORI'}])
        self.create(name='Red Silk', kind='FABRIC',
                    placements=[{'garment': 'lehenga', 'section': 'SKIRT',
                                 'slot': 'MAIN_FABRIC'}])
        self.create(name='Legacy Roll')

        def count(query=''):
            return len(self.client.get(f'{FABRICS}{query}').data)

        self.assertEqual(count(), 3)
        self.assertEqual(count('?garment=blouse'), 1)
        self.assertEqual(count('?garment=lehenga&section=SKIRT'), 1)
        self.assertEqual(count('?slot=DORI'), 1)
        self.assertEqual(count('?kind=FABRIC'), 1)
        self.assertEqual(count('?accessory=1'), 1)
        self.assertEqual(count('?uncategorised=1'), 1)
        self.assertEqual(count('?garment=sherwani'), 0)

    def test_a_reused_material_is_listed_once_per_query(self):
        self.create(name='Gold Dori', kind='DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'},
            {'garment': 'blouse', 'section': '', 'slot': 'LACE_TRIM'}])
        self.assertEqual(len(self.client.get(f'{FABRICS}?garment=blouse').data), 1)

    # cataloguing several parts of one garment in a single save -------------

    def test_a_saree_catalogued_a_part_at_a_time(self):
        rows = [
            {'name': 'Red Silk Body', 'material': 'Silk', 'color': 'Red',
             'price_per_meter': '900.00', 'kind': 'FABRIC',
             'placements': [{'garment': 'saree', 'section': '', 'slot': 'SAREE_BODY'}]},
            {'name': 'Gold Zari Border', 'material': 'Zari', 'color': 'Gold',
             'price_per_meter': '260.00', 'kind': 'BORDER',
             'placements': [{'garment': 'saree', 'section': '', 'slot': 'BORDER'}]},
            {'name': 'Gold Tassel', 'material': 'Silk thread', 'color': 'Gold',
             'price_per_meter': '40.00', 'kind': 'TASSEL',
             'placements': [{'garment': 'saree', 'section': '', 'slot': 'TASSEL_LATKAN'}]},
        ]
        res = self.client.post(FABRICS, rows, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        self.assertEqual(len(res.data), 3)
        self.assertEqual(BoutiqueFabric.objects.count(), 3)
        self.assertEqual(
            sorted(p['path'] for row in res.data for p in row['placements']),
            ['Saree / Border', 'Saree / Main Fabric / Saree Body',
             'Saree / Tassel / Latkan'])

    def test_each_row_keeps_its_own_price_and_photos(self):
        rows = [
            {'name': 'Body', 'material': 'Silk', 'color': 'Red',
             'price_per_meter': '900.00', 'image_urls': ['http://x/body.jpg']},
            {'name': 'Border', 'material': 'Zari', 'color': 'Gold',
             'price_per_meter': '260.00', 'image_urls': ['http://x/border.jpg']},
        ]
        res = self.client.post(FABRICS, rows, format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED, res.data)
        by_name = {row['name']: row for row in res.data}
        self.assertEqual(by_name['Body']['price_per_meter'], '900.00')
        self.assertEqual(by_name['Border']['price_per_meter'], '260.00')
        self.assertEqual(by_name['Body']['image_url'], 'http://x/body.jpg')
        self.assertEqual(by_name['Border']['image_url'], 'http://x/border.jpg')

    def test_one_bad_row_saves_none_of_them(self):
        rows = [
            {'name': 'Good', 'material': 'Silk', 'color': 'Red',
             'price_per_meter': '10.00'},
            {'name': 'Bad', 'material': 'Silk', 'color': 'Red',
             'price_per_meter': '10.00',
             'placements': [{'garment': 'saree', 'section': '', 'slot': 'CAN_CAN'}]},
        ]
        res = self.client.post(FABRICS, rows, format='json')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(BoutiqueFabric.objects.count(), 0)

    def test_a_single_object_post_is_unaffected(self):
        res = self.client.post(FABRICS, self.payload(), format='json')
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['name'], 'Red Silk')

    # every part of one saree, photographed separately, in one save ---------

    def test_each_part_of_a_saree_keeps_its_own_photos(self):
        data = self.create(
            name='Kanjivaram Saree', material='Silk', color='Red', kind='FABRIC',
            placements=[
                {'garment': 'saree', 'section': '', 'slot': 'SAREE_BODY',
                 'image_urls': ['http://x/body1.jpg', 'http://x/body2.jpg']},
                {'garment': 'saree', 'section': '', 'slot': 'PALLU',
                 'image_urls': ['http://x/pallu.jpg']},
                {'garment': 'saree', 'section': '', 'slot': 'BORDER',
                 'image_urls': ['http://x/border1.jpg', 'http://x/border2.jpg']},
                {'garment': 'saree', 'section': '', 'slot': 'FALL',
                 'image_urls': []},
            ])
        self.assertEqual(BoutiqueFabric.objects.count(), 1)
        by_slot = {p['slot']: p['image_urls'] for p in data['placements']}
        self.assertEqual(by_slot['SAREE_BODY'],
                         ['http://x/body1.jpg', 'http://x/body2.jpg'])
        self.assertEqual(by_slot['PALLU'], ['http://x/pallu.jpg'])
        self.assertEqual(len(by_slot['BORDER']), 2)
        self.assertEqual(by_slot['FALL'], [])

    def test_a_placement_defaults_to_no_photos(self):
        data = self.create(kind='FABRIC', placements=[
            {'garment': 'saree', 'section': '', 'slot': 'PALLU'}])
        self.assertEqual(data['placements'][0]['image_urls'], [])

    def test_patch_replaces_the_photos_of_one_part_only(self):
        fabric_id = self.create(kind='FABRIC', placements=[
            {'garment': 'saree', 'section': '', 'slot': 'PALLU',
             'image_urls': ['http://x/pallu.jpg']},
            {'garment': 'saree', 'section': '', 'slot': 'BORDER',
             'image_urls': ['http://x/border.jpg']}])['id']

        res = self.client.patch(f'{FABRICS}{fabric_id}/', {'placements': [
            {'garment': 'saree', 'section': '', 'slot': 'PALLU',
             'image_urls': ['http://x/pallu.jpg', 'http://x/pallu2.jpg']},
            {'garment': 'saree', 'section': '', 'slot': 'BORDER',
             'image_urls': ['http://x/border.jpg']}]}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        by_slot = {p['slot']: p['image_urls'] for p in res.data['placements']}
        self.assertEqual(len(by_slot['PALLU']), 2)
        self.assertEqual(by_slot['BORDER'], ['http://x/border.jpg'])
        self.assertEqual(FabricPlacement.objects.count(), 2)

    def test_editing_other_fields_keeps_the_part_photos(self):
        fabric_id = self.create(kind='FABRIC', placements=[
            {'garment': 'saree', 'section': '', 'slot': 'PALLU',
             'image_urls': ['http://x/pallu.jpg']}])['id']
        res = self.client.patch(f'{FABRICS}{fabric_id}/',
                                {'color': 'Maroon'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(res.data['placements'][0]['image_urls'],
                         ['http://x/pallu.jpg'])

    def test_bad_image_list_is_refused(self):
        self.create(expect=status.HTTP_400_BAD_REQUEST, placements=[
            {'garment': 'saree', 'section': '', 'slot': 'PALLU',
             'image_urls': 'not-a-list'}])

    # deletion --------------------------------------------------------------

    def test_deleting_a_material_takes_its_placements(self):
        fabric_id = self.create(kind='DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'}])['id']
        self.client.delete(f'{FABRICS}{fabric_id}/')
        self.assertEqual(FabricPlacement.objects.count(), 0)


class FabricTenantIsolationTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = 'iso@fabrics.test'
        tenant.name = 'Isolation Atelier'
        return tenant

    def test_placements_live_in_the_tenant_schema(self):
        from django.db import connection as conn
        conn.set_tenant(self.tenant)
        fabric = BoutiqueFabric.objects.create(
            name='Tenant Silk', material='Silk', color='Red',
            price_per_meter=100, kind='FABRIC')
        FabricPlacement.objects.create(fabric=fabric, garment='saree',
                                       section='', slot='PALLU')
        self.assertEqual(FabricPlacement.objects.count(), 1)

        conn.set_schema_to_public()
        with self.assertRaises(Exception):
            FabricPlacement.objects.count()
