"""A customer's own reference, for one part of one garment.

Covers the two things the part flow gained: a picture the customer brought is
stored and handed back as a URL, and a part slot carrying one survives the trip
from draft to DesignBoardItem with its part, its source and its link intact --
while a slot filled from the boutique's catalogue keeps reading exactly as it
did before any of this existed.
"""

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django_tenants.test.cases import TenantTestCase
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from crm_api.views import _part_items_from_draft


class ReferenceUploadTests(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "refs@test.com"
        tenant.name = "Reference Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="refs@test.com", email="refs@test.com", password="pw")
        token = Token.objects.create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION='Token ' + token.key,
                                HTTP_X_TENANT_ID=self.tenant.schema_name)

    def test_upload_returns_a_url(self):
        image = SimpleUploadedFile('pallu.png', b'\x89PNG\r\n\x1a\n', content_type='image/png')
        response = self.client.post('/api/design-studio/reference-upload/',
                                    {'image': image}, format='multipart')
        self.assertEqual(response.status_code, 201, response.content)
        self.assertIn('design_references/', response.data['image_url'])

    def test_upload_without_a_file_is_a_clean_400(self):
        response = self.client.post('/api/design-studio/reference-upload/',
                                    {}, format='multipart')
        self.assertEqual(response.status_code, 400, response.content)

    def test_draft_parts_keep_garment_part_and_source(self):
        items = _part_items_from_draft({'parts': {
            'overall_saree_design': {'design_id': 'abc', 'image_url': 'http://m/o.jpg',
                                     'part_label': 'Overall Saree Design'},
            'pallu_design': {'image_url': 'http://m/p.jpg', 'part_label': 'Pallu Design',
                             'source': 'customer_upload'},
            'border_design': {'image_url': 'http://pin/x', 'source_url': 'http://pin/x',
                              'part_label': 'Border Design', 'source': 'customer_link'},
            # A part the customer never filled in must not become a selection.
            'body_design': None,
        }})
        by_part = {item['part']: item for item in items}

        self.assertEqual(set(by_part), {'overall_saree_design', 'pallu_design', 'border_design'})
        # A catalogue photograph reads exactly as it did before customers could
        # bring their own.
        self.assertEqual(by_part['overall_saree_design']['source'], 'library')
        self.assertEqual(by_part['overall_saree_design']['source_ref'], 'abc')
        self.assertEqual(by_part['pallu_design']['source'], 'customer_upload')
        self.assertEqual(by_part['border_design']['source'], 'customer_link')
        self.assertEqual(by_part['border_design']['source_url'], 'http://pin/x')
        self.assertTrue(all(item['is_selected'] for item in items))

    def test_many_references_per_part_all_reach_the_order(self):
        """Several photographs and links for one part, and one for another."""
        items = _part_items_from_draft({'part_refs': {
            'pallu_design': [
                {'image_url': 'http://m/p1.jpg', 'source': 'customer_upload',
                 'design_title': 'p1.jpg', 'part_label': 'Pallu Design'},
                {'image_url': 'http://m/p2.jpg', 'source': 'customer_upload',
                 'design_title': 'p2.jpg', 'part_label': 'Pallu Design'},
                {'image_url': 'http://pin/a', 'source_url': 'http://pin/a',
                 'source': 'customer_link', 'design_title': 'pin/a'},
            ],
            'border_design': [
                {'image_url': 'http://m/b1.jpg', 'source': 'customer_upload',
                 'design_title': 'b1.jpg'},
            ],
        }})

        pallu = [i for i in items if i['part'] == 'pallu_design']
        self.assertEqual(len(pallu), 3)
        self.assertEqual([i['image_url'] for i in pallu],
                         ['http://m/p1.jpg', 'http://m/p2.jpg', 'http://pin/a'])
        self.assertEqual(pallu[2]['source_url'], 'http://pin/a')
        # One selected per part, so the 0017 uniqueness constraint holds.
        self.assertEqual([i['is_selected'] for i in pallu], [True, False, False])
        self.assertEqual([i['is_selected'] for i in items if i['part'] == 'border_design'],
                         [True])

    def test_a_catalogue_pick_keeps_the_selection_for_its_part(self):
        """The customer's own references must not fight the chosen photograph.

        Two selected rows for one (board, garment_job, part) is an
        IntegrityError at Confirm, which would fail the whole order.
        """
        items = _part_items_from_draft({
            'parts': {'pallu_design': {'design_id': 'd1', 'image_url': 'http://m/lib.jpg'}},
            'part_refs': {'pallu_design': [
                {'image_url': 'http://m/mine1.jpg', 'source': 'customer_upload'},
                {'image_url': 'http://m/mine2.jpg', 'source': 'customer_upload'},
            ]},
        })
        selected = [i for i in items if i['is_selected']]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]['source'], 'library')
        self.assertEqual(len(items), 3)

    def test_a_draft_written_before_parts_had_a_source_still_confirms(self):
        items = _part_items_from_draft({'parts': {
            'overall': {'design_id': 'z', 'image_url': 'http://m/z.jpg'}}})
        self.assertEqual(items[0]['source'], 'library')
        self.assertEqual(items[0]['source_url'], '')
        self.assertEqual(items[0]['part'], 'overall')

    def test_a_draft_with_no_references_at_all_is_unchanged(self):
        self.assertEqual(_part_items_from_draft({}), [])
        self.assertEqual(_part_items_from_draft({'part_refs': {'pallu_design': []}}), [])
