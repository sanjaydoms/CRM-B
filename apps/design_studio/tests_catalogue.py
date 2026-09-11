"""A design is filed at one exact place in the garment's design catalogue.

Garment -> category -> (sub-category ->) option, validated against the
catalogue on the way in, stored resolved on the asset, and filterable to the
exact position -- so Kanjeevaram lists Kanjeevaram and nothing else, while a
design uploaded before any of this still lists under its garment as before.
"""

import json

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalog.models import GarmentTemplate
from apps.design_studio.models import DesignAsset


def png(name='d.png'):
    return SimpleUploadedFile(name, b'\x89PNG\r\n\x1a\n', content_type='image/png')


class CatalogueTestBase(TenantTestCase):
    """Tenant, token and the saree template; no tests of its own."""

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "cat@test.com"
        tenant.name = "Catalogue Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = APIClient()
        user = User.objects.create_user(username="cat@test.com", email="cat@test.com", password="pw")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key,
                                HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.saree = GarmentTemplate.resolve('saree')
        self.assertIsNotNone(self.saree)

    def upload(self, title, catalogue=None, template=None):
        data = {'title': title, 'template': str((template or self.saree).id), 'images': png()}
        if catalogue is not None:
            data['catalogue'] = json.dumps(catalogue)
        return self.client.post('/api/design-studio/assets/', data, format='multipart')


class DesignCatalogueTests(CatalogueTestBase):

    # -- the tree -------------------------------------------------------------

    def test_catalogue_endpoint_serves_the_saree_tree(self):
        r = self.client.get('/api/design-studio/catalogue/?garment=saree')
        self.assertEqual(r.status_code, 200, r.content)
        labels = [c['label'] for c in r.data['categories']]
        self.assertEqual(labels[:2], ['Contemporary / Fashion Saree Designs',
                                      'Traditional Indian Saree Types'])
        self.assertEqual(labels[-2:], ['Blouse', 'Petticoat'])
        self.assertEqual(len(labels), 11)

    def test_a_garment_without_a_catalogue_is_an_empty_tree_not_an_error(self):
        r = self.client.get('/api/design-studio/catalogue/?garment=kurti')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['categories'], [])

    # -- filing ----------------------------------------------------------------

    def test_upload_stores_the_resolved_path(self):
        r = self.upload('Temple border Kanjeevaram', {
            'category': 'traditional_indian_saree_types',
            'subcategory': 'silk_pattu',
            'option': 'kanjeevaram_kanchipuram_pattu'})
        self.assertEqual(r.status_code, 201, r.content)
        cat = DesignAsset.objects.get(pk=r.data['id']).catalogue
        self.assertEqual(cat['option'], 'kanjeevaram_kanchipuram_pattu')
        self.assertEqual(cat['option_label'], 'Kanjeevaram / Kanchipuram Pattu')
        self.assertEqual(cat['path'],
                         'Traditional Indian Saree Types › Silk / Pattu › Kanjeevaram / Kanchipuram Pattu')

    def test_an_invalid_path_is_refused_not_silently_dropped(self):
        r = self.upload('Nowhere', {'category': 'traditional_indian_saree_types',
                                    'subcategory': 'silk_pattu', 'option': 'not_a_saree'})
        self.assertEqual(r.status_code, 400)
        self.assertIn('catalogue', r.data)
        # A category that needs a sub-category, given none.
        r = self.upload('Half a path', {'category': 'traditional_indian_saree_types'})
        self.assertEqual(r.status_code, 400)

    def test_upload_without_a_catalogue_still_works_as_before(self):
        r = self.upload('Old style upload')
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(DesignAsset.objects.get(pk=r.data['id']).catalogue, {})

    def test_blouse_dimension_accepts_a_design_before_its_options_exist(self):
        r = self.upload('Boat neck', {'category': 'blouse', 'subcategory': 'neck_design'})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data['catalogue']['path'], 'Blouse › Neck design')

    # -- reading back ------------------------------------------------------------

    def test_only_designs_filed_at_that_exact_option_are_listed(self):
        kanj = {'category': 'traditional_indian_saree_types', 'subcategory': 'silk_pattu',
                'option': 'kanjeevaram_kanchipuram_pattu'}
        banarasi = {**kanj, 'option': 'banarasi_silk'}
        cotton = {'category': 'traditional_indian_saree_types', 'subcategory': 'cotton',
                  'option': 'mangalagiri_cotton'}
        petticoat = {'category': 'petticoat', 'option': 'mermaid_petticoat'}
        for title, cat in [('K1', kanj), ('K2', kanj), ('B1', banarasi), ('C1', cotton), ('P1', petticoat)]:
            self.assertEqual(self.upload(title, cat).status_code, 201)
        self.assertEqual(self.upload('unfiled').status_code, 201)

        def titles(**params):
            r = self.client.get('/api/design-studio/assets/', {'template': 'saree', **params})
            self.assertEqual(r.status_code, 200)
            rows = r.data['results'] if isinstance(r.data, dict) else r.data
            return sorted(d['title'] for d in rows)

        self.assertEqual(titles(catalogue_category='traditional_indian_saree_types',
                                catalogue_subcategory='silk_pattu',
                                catalogue_option='kanjeevaram_kanchipuram_pattu'), ['K1', 'K2'])
        self.assertEqual(titles(catalogue_category='traditional_indian_saree_types',
                                catalogue_subcategory='cotton'), ['C1'])
        self.assertEqual(titles(catalogue_category='petticoat'), ['P1'])
        # No position chosen: everything under the garment, filed or not --
        # which is exactly what the Design Studio's saree step asks for.
        self.assertEqual(titles(), ['B1', 'C1', 'K1', 'K2', 'P1', 'unfiled'])

    def test_the_same_name_in_two_dimensions_is_two_positions(self):
        fashion = {'category': 'contemporary_fashion_saree_designs', 'option': 'ruffle_saree'}
        party = {'category': 'occasion_based_sarees', 'subcategory': 'party', 'option': 'ruffle_saree'}
        self.assertEqual(self.upload('Ruffle for fashion', fashion).status_code, 201)
        self.assertEqual(self.upload('Ruffle for party', party).status_code, 201)
        r = self.client.get('/api/design-studio/assets/', {
            'template': 'saree', 'catalogue_category': 'occasion_based_sarees',
            'catalogue_subcategory': 'party', 'catalogue_option': 'ruffle_saree'})
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual([d['title'] for d in rows], ['Ruffle for party'])


class HeaderFormCatalogueTests(CatalogueTestBase):
    """The page header's "Add New Design" form posts to /boutique-designs/ with
    the garment as a name. It files into the same catalogue and, having done
    so, lists under the garment like any other saree design."""

    def test_header_form_files_by_garment_name_and_links_the_template(self):
        r = self.client.post('/api/boutique-designs/', {
            'name': 'Header Banarasi', 'garment_type': 'Saree', 'is_boutique': True,
            'image_url': 'http://m/b.jpg', 'price': 0,
            'catalogue': {'category': 'traditional_indian_saree_types',
                          'subcategory': 'silk_pattu', 'option': 'banarasi_silk'},
        }, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        asset = DesignAsset.objects.get(pk=r.data['id'])
        self.assertEqual(asset.catalogue['option_label'], 'Banarasi Silk')
        self.assertEqual(asset.template.key, 'saree')
        # ...and the library finds it at that exact position.
        r = self.client.get('/api/design-studio/assets/', {
            'template': 'saree', 'catalogue_option': 'banarasi_silk'})
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual([d['title'] for d in rows], ['Header Banarasi'])

    def test_header_form_without_a_catalogue_is_unchanged(self):
        r = self.client.post('/api/boutique-designs/', {
            'name': 'Plain', 'garment_type': 'Saree', 'is_boutique': True,
            'image_url': 'http://m/p.jpg', 'price': 0}, format='json')
        self.assertEqual(r.status_code, 201, r.content)
        asset = DesignAsset.objects.get(pk=r.data['id'])
        self.assertEqual(asset.catalogue, {})
        self.assertIsNone(asset.template_id)      # exactly as before

    def test_header_form_refuses_a_bad_position(self):
        r = self.client.post('/api/boutique-designs/', {
            'name': 'Wrong', 'garment_type': 'Saree', 'is_boutique': True,
            'image_url': 'http://m/w.jpg', 'price': 0,
            'catalogue': {'category': 'petticoat', 'option': 'no_such'}}, format='json')
        self.assertEqual(r.status_code, 400)
        self.assertIn('catalogue', r.data)


class BlouseCatalogueTests(CatalogueTestBase):
    """The blouse cutting catalogue: ten headings, filed and read back at the
    exact option, and never mixed with the saree's."""

    def setUp(self):
        super().setUp()
        self.blouse = GarmentTemplate.resolve('blouse')
        self.assertIsNotNone(self.blouse)

    def test_blouse_tree_has_the_ten_headings_in_order(self):
        r = self.client.get('/api/design-studio/catalogue/?garment=blouse')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([c['label'] for c in r.data['categories']], [
            'Main Blouse Cutting / Pattern Types', 'Traditional Blouse Construction Cuts',
            'Bust-Fitting Cuts', 'Designer / Advanced Cuts', 'Katori Variations',
            'Princess-Cut Variations', 'Blouse Back Construction Cuts',
            'Sleeve Attachment / Armhole Cuts', 'Yoke Cuts', 'Blouse Cut Master'])
        katori = next(c for c in r.data['categories'] if c['key'] == 'katori_variations')
        self.assertEqual([o['label'] for o in katori['options']][:3],
                         ['Single Katori', 'Double Katori', '2-Piece Katori'])
        master = next(c for c in r.data['categories'] if c['key'] == 'blouse_cut_master')
        self.assertEqual([sc['label'] for sc in master['subcategories']],
                         ['Dart Cut', 'Katori Cut', 'Princess Cut', 'Panel Cut', 'Yoke Cut',
                          'Designer Construction'])

    def test_only_single_katori_designs_list_under_single_katori(self):
        katori = lambda o: {'category': 'katori_variations', 'option': o}
        for title, cat in [
            ('SK1', katori('single_katori')), ('SK2', katori('single_katori')),
            ('DK', katori('double_katori')),
            ('SP', {'category': 'princess_cut_variations', 'option': 'shoulder_princess'}),
            ('BD', {'category': 'blouse_back_construction_cuts', 'option': 'back_dart'}),
            ('RY', {'category': 'yoke_cuts', 'option': 'round_yoke'}),
            ('RS', {'category': 'sleeve_attachment_armhole_cuts', 'option': 'raglan_sleeve_cut'}),
        ]:
            self.assertEqual(self.upload(title, cat, template=self.blouse).status_code, 201, title)

        r = self.client.get('/api/design-studio/assets/', {
            'template': 'blouse', 'catalogue_category': 'katori_variations',
            'catalogue_option': 'single_katori'})
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual(sorted(d['title'] for d in rows), ['SK1', 'SK2'])
        stored = DesignAsset.objects.get(title='SK1').catalogue
        self.assertEqual(stored['path'], 'Katori Variations \u203a Single Katori')

    def test_master_and_detail_are_two_positions(self):
        detail = {'category': 'princess_cut_variations', 'option': 'shoulder_princess'}
        master = {'category': 'blouse_cut_master', 'subcategory': 'princess_cut',
                  'option': 'shoulder_princess'}
        self.assertEqual(self.upload('Detail', detail, template=self.blouse).status_code, 201)
        self.assertEqual(self.upload('Master', master, template=self.blouse).status_code, 201)
        r = self.client.get('/api/design-studio/assets/', {
            'template': 'blouse', 'catalogue_category': 'blouse_cut_master',
            'catalogue_subcategory': 'princess_cut', 'catalogue_option': 'shoulder_princess'})
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual([d['title'] for d in rows], ['Master'])

    def test_saree_and_blouse_designs_never_cross(self):
        self.assertEqual(self.upload('A saree', {'category': 'petticoat',
                                                 'option': 'mermaid_petticoat'}).status_code, 201)
        self.assertEqual(self.upload('A blouse', {'category': 'yoke_cuts', 'option': 'v_yoke'},
                                     template=self.blouse).status_code, 201)
        # What the Design Studio asks for: every design of the garment, no position.
        for key, expected in (('saree', ['A saree']), ('blouse', ['A blouse'])):
            r = self.client.get('/api/design-studio/assets/', {'template': key})
            rows = r.data['results'] if isinstance(r.data, dict) else r.data
            self.assertEqual([d['title'] for d in rows], expected, key)
        # A saree position is not a blouse position.
        r = self.upload('Wrong garment', {'category': 'petticoat', 'option': 'mermaid_petticoat'},
                        template=self.blouse)
        self.assertEqual(r.status_code, 400)

    def test_a_blouse_cannot_be_filed_at_a_neckline(self):
        r = self.upload('Not a cut', {'category': 'yoke_cuts', 'option': 'round_neck'},
                        template=self.blouse)
        self.assertEqual(r.status_code, 400)


class LehengaCatalogueTests(CatalogueTestBase):
    """The lehenga construction catalogue: twelve headings, kali counts kept
    apart, filed and read back at the exact option, and never mixed with the
    saree's or the blouse's."""

    def setUp(self):
        super().setUp()
        self.lehenga = GarmentTemplate.resolve('lehenga')
        self.blouse = GarmentTemplate.resolve('blouse')
        self.assertIsNotNone(self.lehenga)

    def test_lehenga_tree_has_the_twelve_headings_in_order(self):
        r = self.client.get('/api/design-studio/catalogue/?garment=lehenga')
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([c['label'] for c in r.data['categories']], [
            'Basic Lehenga Silhouettes', 'Pleated Lehenga Styles', 'Kali / Panel Construction',
            'Ruffle & Layered Styles', 'Draped Lehenga Styles', 'Modern / Designer Lehenga Cuts',
            'Traditional / Bridal Lehenga Styles', 'Fabric-Based Lehenga Styles',
            'Volume / Flare Classification', 'Waist Construction', 'Lehenga Border / Hem Styles',
            'Lehenga Design Master'])
        kali = next(c for c in r.data['categories'] if c['key'] == 'kali_panel_construction')
        self.assertEqual([o['label'] for o in kali['options']][:9], [
            '4-Kali Lehenga', '6-Kali Lehenga', '8-Kali Lehenga', '10-Kali Lehenga',
            '12-Kali Lehenga', '16-Kali Lehenga', '20-Kali Lehenga', '24-Kali Lehenga',
            '32-Kali Lehenga'])
        master = next(c for c in r.data['categories'] if c['key'] == 'lehenga_design_master')
        self.assertEqual([sc['label'] for sc in master['subcategories']], [
            'Silhouette', 'Construction', 'Kali Count', 'Pleat Type', 'Flare', 'Layer', 'Ruffle',
            'Drape', 'Waist', 'Length', 'Hem', 'Fabric'])

    def test_only_16_kali_designs_list_under_16_kali(self):
        kali = lambda o: {'category': 'kali_panel_construction', 'option': o}
        for title, cat in [
            ('K16a', kali('16_kali_lehenga')), ('K16b', kali('16_kali_lehenga')),
            ('K8', kali('8_kali_lehenga')), ('K12', kali('12_kali_lehenga')), ('K24', kali('24_kali_lehenga')),
            ('AL', {'category': 'basic_lehenga_silhouettes', 'option': 'a_line_lehenga'}),
            ('MM', {'category': 'basic_lehenga_silhouettes', 'option': 'mermaid_lehenga'}),
            ('PT', {'category': 'traditional_bridal_lehenga_styles', 'option': 'pattu_lehenga'}),
        ]:
            self.assertEqual(self.upload(title, cat, template=self.lehenga).status_code, 201, title)

        r = self.client.get('/api/design-studio/assets/', {
            'template': 'lehenga', 'catalogue_category': 'kali_panel_construction',
            'catalogue_option': '16_kali_lehenga'})
        rows = r.data['results'] if isinstance(r.data, dict) else r.data
        self.assertEqual(sorted(d['title'] for d in rows), ['K16a', 'K16b'])
        self.assertEqual(DesignAsset.objects.get(title='K16a').catalogue['path'],
                         'Kali / Panel Construction \u203a 16-Kali Lehenga')

    def test_detail_and_master_and_overlapping_categories_are_distinct_positions(self):
        for title, cat in [
            ('detail-16', {'category': 'kali_panel_construction', 'option': '16_kali_lehenga'}),
            ('master-16', {'category': 'lehenga_design_master', 'subcategory': 'kali_count',
                           'option': '16_kali'}),
            ('dhoti-draped', {'category': 'draped_lehenga_styles', 'option': 'dhoti_lehenga'}),
            ('dhoti-modern', {'category': 'modern_designer_lehenga_cuts', 'option': 'dhoti_lehenga'}),
        ]:
            self.assertEqual(self.upload(title, cat, template=self.lehenga).status_code, 201, title)

        def titles(**params):
            r = self.client.get('/api/design-studio/assets/', {'template': 'lehenga', **params})
            rows = r.data['results'] if isinstance(r.data, dict) else r.data
            return [d['title'] for d in rows]

        self.assertEqual(titles(catalogue_category='lehenga_design_master',
                                catalogue_subcategory='kali_count', catalogue_option='16_kali'),
                         ['master-16'])
        self.assertEqual(titles(catalogue_category='draped_lehenga_styles',
                                catalogue_option='dhoti_lehenga'), ['dhoti-draped'])
        self.assertEqual(titles(catalogue_category='modern_designer_lehenga_cuts',
                                catalogue_option='dhoti_lehenga'), ['dhoti-modern'])

    def test_saree_blouse_and_lehenga_designs_never_cross(self):
        self.assertEqual(self.upload('S', {'category': 'petticoat', 'option': 'mermaid_petticoat'}).status_code, 201)
        self.assertEqual(self.upload('B', {'category': 'yoke_cuts', 'option': 'v_yoke'},
                                     template=self.blouse).status_code, 201)
        self.assertEqual(self.upload('L', {'category': 'waist_construction', 'option': 'corset_waist'},
                                     template=self.lehenga).status_code, 201)
        # What the Design Studio asks for per garment: every design, no position.
        for key, expected in (('saree', ['S']), ('blouse', ['B']), ('lehenga', ['L'])):
            r = self.client.get('/api/design-studio/assets/', {'template': key})
            rows = r.data['results'] if isinstance(r.data, dict) else r.data
            self.assertEqual([d['title'] for d in rows], expected, key)
        # A blouse position is not a lehenga position, and vice versa.
        self.assertEqual(self.upload('x', {'category': 'yoke_cuts', 'option': 'v_yoke'},
                                     template=self.lehenga).status_code, 400)
        self.assertEqual(self.upload('y', {'category': 'waist_construction', 'option': 'corset_waist'},
                                     template=self.blouse).status_code, 400)
