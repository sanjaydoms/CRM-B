"""Placements, taxonomy kinds and photographs on stocked materials.

Ported from crm_api/test_fabric_placements.py when the fabric catalogue was
merged into inventory: the same behaviour, now on /api/inventory/items/.
"""
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.inventory.models import InventoryItem, ItemPlacement

ITEMS = '/api/inventory/items/'
OWNER_EMAIL = 'owner@fabrics.test'


class ItemPlacementTests(TenantTestCase):

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
        self.codes = 0

    def payload(self, **kw):
        self.codes += 1
        data = {'item_code': f'FAB-{self.codes:04d}', 'name': 'Red Silk',
                'category': 'FABRIC', 'material_type': 'Silk', 'color': 'Red',
                'selling_price': '450.00'}
        data.update(kw)
        return data

    def create(self, expect=status.HTTP_201_CREATED, **kw):
        res = self.client.post(ITEMS, self.payload(**kw), format='json')
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
        self.assertEqual(data['unit'], 'METER', 'fabric is counted in metres')

    def test_legacy_crud_round_trip(self):
        item_id = self.create()['id']
        listed = self.client.get(ITEMS)
        self.assertEqual(listed.status_code, status.HTTP_200_OK)
        self.assertEqual(len(listed.data), 1)

        patched = self.client.patch(f'{ITEMS}{item_id}/',
                                    {'color': 'Blue'}, format='json')
        self.assertEqual(patched.status_code, status.HTTP_200_OK, patched.data)
        self.assertEqual(patched.data['color'], 'Blue')

        removed = self.client.delete(f'{ITEMS}{item_id}/')
        self.assertEqual(removed.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(InventoryItem.objects.filter(id=item_id).exists())

    def test_a_row_written_before_this_feature_reads_and_edits(self):
        legacy = InventoryItem.objects.create(
            item_code='OLD-0001', name='Old Silk', category='FABRIC', unit='METER',
            material_type='Silk', color='Gold', selling_price=900)
        row = self.client.get(f'{ITEMS}{legacy.id}/').data
        self.assertEqual(row['placements'], [])

        res = self.client.patch(f'{ITEMS}{legacy.id}/',
                                {'selling_price': '950.00'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)

    # 3: taxonomy ----------------------------------------------------------

    def test_taxonomy_endpoint(self):
        res = self.client.get(f'{ITEMS}taxonomy/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

        garments = [g['key'] for g in res.data['garments']]
        self.assertEqual(garments[:3], ['saree', 'blouse', 'lehenga'])
        for key in ('dupatta', 'kurti', 'anarkali', 'petticoat', 'bottom_wear',
                    'gown', 'suit', 'sherwani'):
            self.assertIn(key, garments)

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
        self.assertEqual(self.paths(data), ['Lehenga / Skirt / Main Fabric / Body'])

    def test_the_same_material_serves_many_garments(self):
        data = self.create(
            name='Gold Latkan Dori', material_type='Dori', color='Gold',
            category='EMBELLISHMENT', kind='DORI', variant='LATKAN_DORI',
            placements=[
                {'garment': 'lehenga', 'section': 'BLOUSE', 'slot': 'DORI'},
                {'garment': 'blouse', 'section': '', 'slot': 'DORI'},
                {'garment': 'dupatta', 'section': '', 'slot': 'TASSEL_LATKAN'},
                {'garment': 'lehenga_blouse', 'section': '', 'slot': 'DORI'},
            ])
        self.assertEqual(InventoryItem.objects.count(), 1)
        self.assertEqual(len(data['placements']), 4)
        self.assertEqual(data['variant_label'], 'Latkan Dori')
        self.assertTrue(data['is_accessory'])

    def test_one_roll_in_two_different_roles(self):
        data = self.create(kind='FABRIC', placements=[
            {'garment': 'lehenga', 'section': 'SKIRT', 'slot': 'MAIN_FABRIC'},
            {'garment': 'saree', 'section': '', 'slot': 'BACKING_FABRIC'}])
        self.assertEqual(InventoryItem.objects.count(), 1)
        self.assertEqual(self.paths(data),
                         ['Lehenga / Skirt / Main Fabric / Body', 'Saree / Backing'])

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
        data = self.create(name='Gold Gota', material_type='Gota', color='Gold',
                           category='BORDER', kind='GOTA')
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
        item_id = self.create(kind='DORI', variant='POTLI_DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'}])['id']
        res = self.client.patch(f'{ITEMS}{item_id}/', {'placements': [
            {'garment': 'lehenga', 'section': 'BLOUSE', 'slot': 'DORI'},
            {'garment': 'lehenga_blouse', 'section': '', 'slot': 'DORI'}]}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(self.paths(res.data), ['Lehenga / Blouse / Dori', 'Lehenga Blouse / Dori'])
        self.assertEqual(ItemPlacement.objects.filter(item_id=item_id).count(), 2)

    def test_patch_without_placements_preserves_them(self):
        item_id = self.create(kind='DORI', variant='POTLI_DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'},
            {'garment': 'lehenga_blouse', 'section': '', 'slot': 'DORI'}])['id']
        res = self.client.patch(f'{ITEMS}{item_id}/',
                                {'color': 'Ivory'}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        self.assertEqual(len(res.data['placements']), 2)

    def test_placements_can_be_emptied_explicitly(self):
        item_id = self.create(kind='DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'}])['id']
        res = self.client.patch(f'{ITEMS}{item_id}/', {'placements': []},
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
        self.assertEqual(InventoryItem.objects.count(), 0)

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
        self.assertEqual(self.paths(data), ['Lehenga / Skirt / Main Fabric / Body'])

    # filtering ------------------------------------------------------------

    def test_filters(self):
        self.create(name='Gold Dori', category='EMBELLISHMENT', kind='DORI',
                    variant='LATKAN_DORI',
                    placements=[{'garment': 'blouse', 'section': '', 'slot': 'DORI'},
                                {'garment': 'lehenga_blouse', 'section': '', 'slot': 'DORI'}])
        self.create(name='Red Silk', kind='FABRIC',
                    placements=[{'garment': 'lehenga', 'section': 'SKIRT',
                                 'slot': 'MAIN_FABRIC'}])
        self.create(name='Legacy Roll')
        # Stock the wizard never lays on a garment part: no kind, no
        # placement, and not a cloth category.
        self.create(name='Polyester Thread', category='STITCHING', material_type='')

        def count(query=''):
            return len(self.client.get(f'{ITEMS}{query}').data)

        self.assertEqual(count(), 4)
        self.assertEqual(count('?garment=blouse'), 1)
        self.assertEqual(count('?garment=lehenga&section=SKIRT'), 1)
        self.assertEqual(count('?slot=DORI'), 1)
        self.assertEqual(count('?kind=FABRIC'), 1)
        self.assertEqual(count('?accessory=1'), 1)
        self.assertEqual(count('?uncategorised=1'), 2)
        self.assertEqual(count('?garment=sherwani'), 0)
        self.assertEqual(count('?picker=1'), 3, 'the thread stays off the fabric step')

    def test_a_reused_material_is_listed_once_per_query(self):
        self.create(name='Gold Dori', kind='DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'},
            {'garment': 'blouse', 'section': '', 'slot': 'LACE_TRIM'}])
        self.assertEqual(len(self.client.get(f'{ITEMS}?garment=blouse').data), 1)

    # photographs ----------------------------------------------------------

    def test_the_swatch_is_validated_and_the_first_photo_becomes_the_card_image(self):
        bad = self.create(expect=status.HTTP_400_BAD_REQUEST, color_hex='aqua-blue')
        self.assertIn('color_hex', bad)

        good = self.create(name='Chanderi Silk', color_hex='#1A2B3C',
                           image_urls=['https://example.test/a.jpg',
                                       'https://example.test/b.jpg'])
        self.assertEqual(good['color_hex'], '#1a2b3c')
        # Every card and the wizard's picker read image_url; it must not stay
        # empty when the owner only ever photographed the roll.
        self.assertEqual(good['image_url'], 'https://example.test/a.jpg')
        self.assertEqual(len(good['image_urls']), 2)

    def test_uploads_take_images_only(self):
        upload = f'{ITEMS}upload-images/'
        junk = SimpleUploadedFile('notes.txt', b'not an image', content_type='text/plain')
        self.assertEqual(
            self.client.post(upload, {'images': junk}, format='multipart').status_code,
            status.HTTP_400_BAD_REQUEST)

        shot = SimpleUploadedFile('roll.png', b'\x89PNG\r\n\x1a\n fake', content_type='image/png')
        stored = self.client.post(upload, {'images': shot}, format='multipart')
        self.assertEqual(stored.status_code, status.HTTP_201_CREATED, stored.data)
        self.assertEqual(len(stored.data['image_urls']), 1)

    def test_each_part_of_a_saree_keeps_its_own_photos(self):
        data = self.create(
            name='Kanjivaram Saree', material_type='Silk', color='Red', kind='FABRIC',
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
        self.assertEqual(InventoryItem.objects.count(), 1)
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
        item_id = self.create(kind='FABRIC', placements=[
            {'garment': 'saree', 'section': '', 'slot': 'PALLU',
             'image_urls': ['http://x/pallu.jpg']},
            {'garment': 'saree', 'section': '', 'slot': 'BORDER',
             'image_urls': ['http://x/border.jpg']}])['id']

        res = self.client.patch(f'{ITEMS}{item_id}/', {'placements': [
            {'garment': 'saree', 'section': '', 'slot': 'PALLU',
             'image_urls': ['http://x/pallu.jpg', 'http://x/pallu2.jpg']},
            {'garment': 'saree', 'section': '', 'slot': 'BORDER',
             'image_urls': ['http://x/border.jpg']}]}, format='json')
        self.assertEqual(res.status_code, status.HTTP_200_OK, res.data)
        by_slot = {p['slot']: p['image_urls'] for p in res.data['placements']}
        self.assertEqual(len(by_slot['PALLU']), 2)
        self.assertEqual(by_slot['BORDER'], ['http://x/border.jpg'])
        self.assertEqual(ItemPlacement.objects.count(), 2)

    def test_editing_other_fields_keeps_the_part_photos(self):
        item_id = self.create(kind='FABRIC', placements=[
            {'garment': 'saree', 'section': '', 'slot': 'PALLU',
             'image_urls': ['http://x/pallu.jpg']}])['id']
        res = self.client.patch(f'{ITEMS}{item_id}/',
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
        item_id = self.create(kind='DORI', placements=[
            {'garment': 'blouse', 'section': '', 'slot': 'DORI'}])['id']
        self.client.delete(f'{ITEMS}{item_id}/')
        self.assertEqual(ItemPlacement.objects.count(), 0)


class ItemPlacementTenantIsolationTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = 'iso@fabrics.test'
        tenant.name = 'Isolation Atelier'
        return tenant

    def test_placements_live_in_the_tenant_schema(self):
        from django.db import connection as conn
        conn.set_tenant(self.tenant)
        item = InventoryItem.objects.create(
            item_code='ISO-0001', name='Tenant Silk', category='FABRIC', unit='METER',
            material_type='Silk', color='Red', selling_price=100, kind='FABRIC')
        ItemPlacement.objects.create(item=item, garment='saree', section='', slot='PALLU')
        self.assertEqual(ItemPlacement.objects.count(), 1)

        conn.set_schema_to_public()
        with self.assertRaises(Exception):
            ItemPlacement.objects.count()
