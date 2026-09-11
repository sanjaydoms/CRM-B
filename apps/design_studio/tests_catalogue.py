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
