
from datetime import date, timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.urls import reverse
from django_tenants.test.cases import TenantTestCase
from rest_framework.test import APIClient

from apps.activities.models import UniversalActivity
from apps.catalog.models import GarmentJob, GarmentTemplate
from apps.catalog.services import sync_global_templates
from crm_api.models import Customer, Order, Tailor

from .models import Designer, DesignAsset, DesignAssignment


class AssignmentTestCase(TenantTestCase):

    @classmethod
    def setup_tenant(cls, tenant):
        tenant.owner_email = "owner@assign.test"
        tenant.name = "Assignment Atelier"
        return tenant

    def setUp(self):
        super().setUp()
        connection.set_tenant(self.tenant)
        sync_global_templates()

        self.owner = User.objects.create_user(
            username="owner@assign.test", email="owner@assign.test", password="pass12345")

        self.customer = Customer.objects.create(
            first_name="Ananya", last_name="Rao", mobile_number="9600002222",
            customer_type="Women", garment_type="Lehenga", occasion="Bridal")
        self.order = Order.objects.create(order_id="T2B-ASN-0001", customer=self.customer)

        self.lehenga_template = GarmentTemplate.objects.filter(key='lehenga').first()
        self.blouse_template = GarmentTemplate.objects.filter(key='blouse').first()
        self.assertIsNotNone(self.lehenga_template, "lehenga template must be seeded")
        self.assertIsNotNone(self.blouse_template, "blouse template must be seeded")

        self.lehenga_job = GarmentJob.objects.create(
            order=self.order, template=self.lehenga_template, sequence=0,
            spec={'occasion': 'wedding'}, measurements={'waist': '28'})
        self.blouse_job = GarmentJob.objects.create(
            order=self.order, template=self.blouse_template, sequence=1,
            spec={'sleeve_length': 'elbow'}, measurements={'bust': '38'})

        self.meera, self.meera_client = self._designer("Meera", "meera@assign.test")
        self.kavya, self.kavya_client = self._designer("Kavya", "kavya@assign.test")

        self.client = self._client_for(self.owner)


    def _client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        client.force_authenticate(user=user)
        return client

    def _designer(self, name, email):
        user = User.objects.create_user(username=email, email=email, password="pass12345")
        designer = Designer.objects.create(name=name, email=email, user=user)
        return designer, self._client_for(user)

    def _staff_client(self, role, username):
        user = User.objects.create_user(username=username, email=username, password="pass12345")
        Tailor.objects.create(name=username, specialty="Bridal", role=role, user=user)
        return self._client_for(user)

    def _design_by(self, designer, title, user=None):
        return DesignAsset.objects.create(
            title=title, image_url="https://example.test/d.jpg",
            source=DesignAsset.SOURCE_UPLOAD, designer_ref=designer, created_by=user)

    def _assign(self, job, designer, client=None, **extra):
        payload = {'garment_job': str(job.id), 'designer': str(designer.id)}
        payload.update(extra)
        return (client or self.client).post(
            reverse('design-assignment-list'), payload, format='json')

    def _submit(self, assignment_id, design, client, note=''):
        return client.post(
            reverse('design-assignment-submit', args=[assignment_id]),
            {'design': str(design.id), 'note': note}, format='json')

    def _review(self, assignment_id, decision, client=None, note=''):
        return (client or self.client).post(
            reverse('design-assignment-review', args=[assignment_id]),
            {'decision': decision, 'note': note}, format='json')


class AssignmentTests(AssignmentTestCase):
    def test_owner_assigns_design_work_to_a_designer(self):
        response = self._assign(self.lehenga_job, self.meera,
                                brief="Heavy zari on the border.")
        self.assertEqual(response.status_code, 201, response.data)

        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        self.assertEqual(assignment.designer_id, self.meera.id)
        self.assertEqual(assignment.status, DesignAssignment.Status.ASSIGNED)
        self.assertEqual(assignment.brief, "Heavy zari on the border.")
        self.assertEqual(assignment.assigned_by_id, self.owner.id)

    def test_master_may_also_assign(self):
        master = self._staff_client("Master", "master@assign.test")
        response = self._assign(self.lehenga_job, self.meera, client=master)
        self.assertEqual(response.status_code, 201, response.data)

    def test_a_due_date_survives_the_round_trip(self):
        due = date.today() + timedelta(days=5)
        response = self._assign(self.lehenga_job, self.meera, due_date=due.isoformat())
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(
            DesignAssignment.objects.get(garment_job=self.lehenga_job).due_date, due)


class GarmentAttributionTests(AssignmentTestCase):

    def test_two_garments_carry_two_designers_independently(self):
        self.assertEqual(self._assign(self.lehenga_job, self.meera).status_code, 201)
        self.assertEqual(self._assign(self.blouse_job, self.kavya).status_code, 201)

        lehenga = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        blouse = DesignAssignment.objects.get(garment_job=self.blouse_job)
        self.assertEqual(lehenga.designer_id, self.meera.id)
        self.assertEqual(blouse.designer_id, self.kavya.id)
        self.assertNotEqual(lehenga.id, blouse.id)

    def test_a_submitted_design_lands_on_its_own_garment_and_not_the_other(self):
        self._assign(self.lehenga_job, self.meera)
        self._assign(self.blouse_job, self.kavya)
        lehenga_assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        blouse_assignment = DesignAssignment.objects.get(garment_job=self.blouse_job)

        lehenga_design = self._design_by(self.meera, "Zari Lehenga")
        blouse_design = self._design_by(self.kavya, "Sweetheart Blouse")

        self.assertEqual(
            self._submit(lehenga_assignment.id, lehenga_design, self.meera_client).status_code, 200)
        self.assertEqual(
            self._submit(blouse_assignment.id, blouse_design, self.kavya_client).status_code, 200)

        lehenga_assignment.refresh_from_db()
        blouse_assignment.refresh_from_db()
        self.assertEqual(lehenga_assignment.design_id, lehenga_design.id)
        self.assertEqual(blouse_assignment.design_id, blouse_design.id)
        self.assertEqual(self.lehenga_job.design_assignment.design_id, lehenga_design.id)
        self.assertEqual(self.blouse_job.design_assignment.design_id, blouse_design.id)

    def test_a_garment_holds_one_assignment_and_reassignment_moves_it(self):
        self.assertEqual(self._assign(self.lehenga_job, self.meera).status_code, 201)
        again = self._assign(self.lehenga_job, self.kavya)
        self.assertEqual(again.status_code, 200, again.data)
        self.assertEqual(DesignAssignment.objects.filter(garment_job=self.lehenga_job).count(), 1)
        self.assertEqual(
            DesignAssignment.objects.get(garment_job=self.lehenga_job).designer_id,
            self.kavya.id)

    def test_reassigning_clears_the_previous_designers_submission(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "Meera's draft")
        self._submit(assignment.id, design, self.meera_client)

        self._assign(self.lehenga_job, self.kavya)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.design_id)
        self.assertEqual(assignment.status, DesignAssignment.Status.ASSIGNED)

    def test_an_approved_garment_is_not_silently_reassigned(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "Final")
        self._submit(assignment.id, design, self.meera_client)
        self._review(assignment.id, 'approve')

        response = self._assign(self.lehenga_job, self.kavya)
        self.assertEqual(response.status_code, 409)
        assignment.refresh_from_db()
        self.assertEqual(assignment.design_id, design.id)
        self.assertEqual(assignment.designer_id, self.meera.id)


class DesignerWorkQueueTests(AssignmentTestCase):
    def test_a_designer_sees_the_work_assigned_to_them(self):
        self._assign(self.lehenga_job, self.meera)
        response = self.meera_client.get(reverse('design-assignment-list'))
        self.assertEqual(response.status_code, 200)
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['garment_name'], self.lehenga_template.name)

    def test_a_designer_sees_the_specification_they_need_to_do_the_work(self):
        self._assign(self.lehenga_job, self.meera, brief="Heavy zari.")
        response = self.meera_client.get(reverse('design-assignment-list'))
        row = (response.data['results'] if isinstance(response.data, dict) else response.data)[0]
        self.assertEqual(row['spec'], {'occasion': 'wedding'})
        self.assertEqual(row['measurements'], {'waist': '28'})
        self.assertEqual(row['brief'], "Heavy zari.")
        self.assertEqual(row['order_ref'], "T2B-ASN-0001")

    def test_a_designers_queue_does_not_carry_the_customer(self):
        self._assign(self.lehenga_job, self.meera)
        response = self.meera_client.get(reverse('design-assignment-list'))
        row = (response.data['results'] if isinstance(response.data, dict) else response.data)[0]
        self.assertNotIn('customer_name', row)
        self.assertNotIn('Ananya', str(row))
        self.assertNotIn('9600002222', str(row))

    def test_one_designer_cannot_see_anothers_queue(self):
        self._assign(self.lehenga_job, self.meera)
        self._assign(self.blouse_job, self.kavya)

        response = self.kavya_client.get(reverse('design-assignment-list'))
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['garment_name'], self.blouse_template.name)

    def test_one_designer_cannot_fetch_anothers_assignment_by_id(self):
        self._assign(self.lehenga_job, self.meera)
        meera_assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        response = self.kavya_client.get(
            reverse('design-assignment-detail', args=[meera_assignment.id]))
        self.assertEqual(response.status_code, 404)

    def test_the_open_filter_is_everything_short_of_approved(self):
        self._assign(self.lehenga_job, self.meera)
        self._assign(self.blouse_job, self.meera)
        finished = DesignAssignment.objects.get(garment_job=self.blouse_job)
        design = self._design_by(self.meera, "Done")
        self._submit(finished.id, design, self.meera_client)
        self._review(finished.id, 'approve')
        pending = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        self._submit(pending.id, self._design_by(self.meera, "Pending"), self.meera_client)

        response = self.meera_client.get(reverse('design-assignment-list'), {'open': '1'})
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['garment_name'], self.lehenga_template.name)
        self.assertEqual(rows[0]['status'], DesignAssignment.Status.SUBMITTED)

    def test_changes_requested_returns_to_the_open_queue(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "First pass")
        self._submit(assignment.id, design, self.meera_client)
        self._review(assignment.id, 'changes', note="Border too thin.")

        response = self.meera_client.get(reverse('design-assignment-list'), {'open': '1'})
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['review_note'], "Border too thin.")


class SubmissionTests(AssignmentTestCase):
    def test_a_designer_submits_their_design_and_the_owner_sees_it(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "Zari Lehenga")

        response = self._submit(assignment.id, design, self.meera_client, note="Two colourways.")
        self.assertEqual(response.status_code, 200, response.data)

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DesignAssignment.Status.SUBMITTED)
        self.assertEqual(assignment.design_id, design.id)
        self.assertEqual(assignment.submission_note, "Two colourways.")
        self.assertIsNotNone(assignment.submitted_at)

        owner_view = self.client.get(reverse('design-assignment-detail', args=[assignment.id]))
        self.assertEqual(owner_view.status_code, 200)
        self.assertEqual(owner_view.data['design_detail']['title'], "Zari Lehenga")
        self.assertEqual(owner_view.data['customer_name'], "Ananya Rao")

    def test_submitting_without_a_design_is_refused(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        response = self.meera_client.post(
            reverse('design-assignment-submit', args=[assignment.id]), {}, format='json')
        self.assertEqual(response.status_code, 400)

    def test_a_designer_cannot_submit_a_colleagues_design(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        kavyas_work = self._design_by(self.kavya, "Kavya's upload")

        response = self._submit(assignment.id, kavyas_work, self.meera_client)
        self.assertEqual(response.status_code, 403)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.design_id)

    def test_a_designer_cannot_submit_against_someone_elses_assignment(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.kavya, "Kavya's")
        response = self._submit(assignment.id, design, self.kavya_client)
        self.assertEqual(response.status_code, 404)

    def test_submitting_credits_an_uncredited_upload_to_the_commissioned_designer(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = DesignAsset.objects.create(
            title="Untitled sketch", image_url="https://example.test/s.jpg",
            source=DesignAsset.SOURCE_UPLOAD,
            created_by=self.meera.user)

        self._submit(assignment.id, design, self.meera_client)
        design.refresh_from_db()
        self.assertEqual(design.designer_ref_id, self.meera.id)


class ReviewTests(AssignmentTestCase):
    def _submitted(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "Zari Lehenga")
        self._submit(assignment.id, design, self.meera_client)
        return assignment, design

    def test_owner_approves_and_the_design_stays_on_the_garment(self):
        assignment, design = self._submitted()
        response = self._review(assignment.id, 'approve', note="Lovely.")
        self.assertEqual(response.status_code, 200, response.data)

        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DesignAssignment.Status.APPROVED)
        self.assertEqual(assignment.reviewed_by_id, self.owner.id)
        self.assertIsNotNone(assignment.reviewed_at)
        self.assertEqual(self.lehenga_job.design_assignment.design_id, design.id)

    def test_requesting_changes_keeps_the_design_but_reopens_the_work(self):
        assignment, design = self._submitted()
        self._review(assignment.id, 'changes', note="Border too thin.")
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DesignAssignment.Status.CHANGES_REQUESTED)
        self.assertEqual(assignment.design_id, design.id)
        self.assertEqual(assignment.review_note, "Border too thin.")

    def test_a_resubmission_after_changes_is_accepted(self):
        assignment, _ = self._submitted()
        self._review(assignment.id, 'changes')
        second = self._design_by(self.meera, "Second pass")
        response = self._submit(assignment.id, second, self.meera_client)
        self.assertEqual(response.status_code, 200, response.data)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DesignAssignment.Status.SUBMITTED)
        self.assertEqual(assignment.design_id, second.id)

    def test_reviewing_nothing_is_refused(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        self.assertEqual(self._review(assignment.id, 'approve').status_code, 400)

    def test_a_junk_decision_is_refused(self):
        assignment, _ = self._submitted()
        self.assertEqual(self._review(assignment.id, 'maybe').status_code, 400)

    def test_an_approved_design_is_not_resubmitted_over(self):
        assignment, design = self._submitted()
        self._review(assignment.id, 'approve')
        other = self._design_by(self.meera, "Sneaky replacement")
        response = self._submit(assignment.id, other, self.meera_client)
        self.assertEqual(response.status_code, 409)
        assignment.refresh_from_db()
        self.assertEqual(assignment.design_id, design.id)


class AssignmentRoleBoundaryTests(AssignmentTestCase):
    def test_a_designer_cannot_assign_work(self):
        response = self._assign(self.lehenga_job, self.meera, client=self.meera_client)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(DesignAssignment.objects.exists())

    def test_a_designer_cannot_approve_their_own_design(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "Self-approved")
        self._submit(assignment.id, design, self.meera_client)

        response = self._review(assignment.id, 'approve', client=self.meera_client)
        self.assertEqual(response.status_code, 403)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DesignAssignment.Status.SUBMITTED)

    def test_a_tailor_sees_no_assignments_at_all(self):
        self._assign(self.lehenga_job, self.meera)
        tailor = self._staff_client("Tailor", "stitcher@assign.test")
        response = tailor.get(reverse('design-assignment-list'))
        self.assertEqual(response.status_code, 403)

    def test_a_tailor_cannot_assign_work(self):
        tailor = self._staff_client("Tailor", "cutter@assign.test")
        self.assertEqual(self._assign(self.lehenga_job, self.meera, client=tailor).status_code, 403)

    def test_a_qc_master_is_not_a_design_supervisor(self):
        qc = self._staff_client("QC Master", "qc@assign.test")
        self.assertEqual(qc.get(reverse('design-assignment-list')).status_code, 403)

    def test_a_supervisor_submitting_on_behalf_is_recorded_as_themselves(self):
        credit_only = Designer.objects.create(name="Nadia (credit only)")
        self._assign(self.lehenga_job, credit_only)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(credit_only, "Handed-over sketch")

        response = self._submit(assignment.id, design, self.client)
        self.assertEqual(response.status_code, 200, response.data)
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, DesignAssignment.Status.SUBMITTED)

        activity = UniversalActivity.objects.filter(
            entity_id=str(assignment.id), action="DESIGN_SUBMITTED").get()
        self.assertEqual(activity.user_id, self.owner.id)

    def test_an_anonymous_caller_is_refused(self):
        anonymous = APIClient()
        anonymous.credentials(HTTP_X_TENANT_ID=self.tenant.schema_name)
        self.assertEqual(anonymous.get(reverse('design-assignment-list')).status_code, 401)


class AssignmentVisibilityTests(AssignmentTestCase):

    def test_assigning_writes_an_activity_the_owner_can_read_back(self):
        self._assign(self.lehenga_job, self.meera)
        activity = UniversalActivity.objects.filter(
            module="design_studio", action="DESIGN_ASSIGNED").first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.entity_type, "DesignAssignment")
        self.assertIn("Meera", activity.description)
        self.assertIn(self.lehenga_template.name, activity.description)

    def test_submitting_and_approving_are_both_recorded(self):
        self._assign(self.lehenga_job, self.meera)
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "Zari Lehenga")
        self._submit(assignment.id, design, self.meera_client)
        self._review(assignment.id, 'approve')

        actions = set(UniversalActivity.objects
                      .filter(entity_id=str(assignment.id))
                      .values_list('action', flat=True))
        self.assertEqual(actions, {"DESIGN_ASSIGNED", "DESIGN_SUBMITTED", "DESIGN_APPROVED"})

    def test_the_owner_can_list_everything_still_owed_across_designers(self):
        self._assign(self.lehenga_job, self.meera)
        self._assign(self.blouse_job, self.kavya)
        response = self.client.get(reverse('design-assignment-list'), {'open': '1'})
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['designer_name'] for r in rows}, {"Meera", "Kavya"})

    def test_the_owner_can_filter_the_board_by_order(self):
        self._assign(self.lehenga_job, self.meera)
        response = self.client.get(
            reverse('design-assignment-list'), {'order_id': "T2B-ASN-0001"})
        rows = response.data['results'] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1)

    def test_state_survives_a_fresh_client_the_way_a_refresh_would(self):
        self._assign(self.lehenga_job, self.meera, brief="Heavy zari.")
        assignment = DesignAssignment.objects.get(garment_job=self.lehenga_job)
        design = self._design_by(self.meera, "Zari Lehenga")
        self._submit(assignment.id, design, self.meera_client, note="Two colourways.")

        reopened = self._client_for(self.meera.user)
        response = reopened.get(reverse('design-assignment-detail', args=[assignment.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], DesignAssignment.Status.SUBMITTED)
        self.assertEqual(response.data['brief'], "Heavy zari.")
        self.assertEqual(response.data['submission_note'], "Two colourways.")
        self.assertEqual(response.data['design_detail']['title'], "Zari Lehenga")
