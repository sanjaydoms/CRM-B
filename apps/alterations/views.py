"""The alteration API.

Same shape as the rest of the product: a viewset whose write paths are
`@action` endpoints delegating to domain services, translating the services'
exceptions into the status codes this API already uses --

    ValueError / TransitionError -> 400 with {'detail': ...}
    PermissionError              -> 403 with {'detail': ...}
    DoesNotExist                 -> 404

Tenant isolation is the schema: this app is in TENANT_APPS, so every query
below runs inside the caller's own boutique schema. There is no cross-tenant
row to filter out, because there is no cross-tenant row in the table.
"""

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.alterations.models import AlterationRequest, AlterationStatus, AlterationType
from apps.alterations.serializers import (
    AlterationMaterialLineSerializer,
    AlterationPaymentSerializer,
    AlterationRequestCreateSerializer,
    AlterationRequestDetailSerializer,
    AlterationRequestListSerializer,
    AssignSerializer,
    InspectionSerializer,
    NotesSerializer,
    ReasonSerializer,
    RecordMaterialSerializer,
    RecordPaymentSerializer,
    SubmitForApprovalSerializer,
)
from core.permissions import AlterationPermission
from core.roles import OWNER, resolve_user_role
from domains.alterations import services
from domains.alterations.workflow import SUPERVISOR_ROLES, TransitionError


def _tailor_id(user):
    profile = getattr(user, 'tailor_profile', None)
    return profile.id if profile else None


def visible_alterations(queryset, user):
    """Which alterations this staff member may see.

    Mirrors core.permissions.visible_orders: the owner and the floor
    supervisor see the whole board, and everyone else sees what is in their
    own hands. A bench worker has no business reading another customer's
    charge or another tailor's queue.
    """
    role = resolve_user_role(user)
    if role is None:
        return queryset.none()
    if role == OWNER or role in SUPERVISOR_ROLES:
        return queryset

    profile_id = _tailor_id(user)
    if profile_id is None:
        return queryset.none()
    return queryset.filter(tasks__assigned_to_id=profile_id).distinct()


class AlterationRequestViewSet(mixins.CreateModelMixin,
                               viewsets.ReadOnlyModelViewSet):
    """List, retrieve, create -- and then named business actions.

    Create + read only, rather than a full ModelViewSet, on purpose: there is
    no generic PUT/PATCH/DELETE on an alteration. Every change after intake is
    a named action that has to pass the state machine, so a blanket update
    endpoint would simply be a way around it.
    """

    permission_classes = [AlterationPermission]
    serializer_class = AlterationRequestDetailSerializer

    def get_queryset(self):
        queryset = (
            AlterationRequest.objects
            .select_related('customer', 'original_order', 'garment_job',
                            'garment_job__template')
            .prefetch_related('tasks', 'tasks__assigned_to', 'activities',
                              'activities__performed_by', 'payments', 'material_lines')
        )
        queryset = visible_alterations(queryset, self.request.user)

        params = self.request.query_params

        if value := params.get('customer'):
            queryset = queryset.filter(customer_id=value)

        if value := params.get('order'):
            if str(value).isdigit():
                queryset = queryset.filter(original_order_id=int(value))
            else:
                queryset = queryset.filter(original_order__order_id=value)

        if value := params.get('garment_job'):
            queryset = queryset.filter(garment_job_id=value)

        if value := params.get('status'):
            queryset = queryset.filter(status__in=[s for s in value.split(',') if s])

        if value := params.get('alteration_type'):
            queryset = queryset.filter(alteration_type=value)

        if params.get('assigned_to_me') in ('1', 'true', 'True'):
            profile_id = _tailor_id(self.request.user)
            queryset = (queryset.filter(tasks__assigned_to_id=profile_id).distinct()
                        if profile_id else queryset.none())

        if params.get('open') in ('1', 'true', 'True'):
            queryset = queryset.exclude(
                status__in=[AlterationStatus.COMPLETED, AlterationStatus.CANCELLED])

        if search := (params.get('search') or '').strip():
            from django.db.models import Q
            queryset = queryset.filter(
                Q(alteration_number__icontains=search)
                | Q(customer__first_name__icontains=search)
                | Q(customer__last_name__icontains=search)
                | Q(customer__mobile_number__icontains=search)
                | Q(original_order__order_id__icontains=search)
                | Q(issue_description__icontains=search)
            )

        return queryset

    def get_serializer_class(self):
        if self.action == 'list':
            return AlterationRequestListSerializer
        return AlterationRequestDetailSerializer

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['role'] = resolve_user_role(self.request.user)
        context['tailor_id'] = _tailor_id(self.request.user)
        return context

    # -- helpers ----------------------------------------------------------

    def _detail(self, alteration, code=status.HTTP_200_OK):
        serializer = AlterationRequestDetailSerializer(
            alteration, context=self.get_serializer_context())
        return Response(serializer.data, status=code)

    def _run(self, service, **kwargs):
        """Call a domain service and map its refusals onto the API's codes.

        `self.get_object()` first, always. It applies get_queryset -- which is
        both the tenant's own schema and this person's visibility -- and raises
        Http404 for anything outside it. Handing the raw pk straight to a
        service instead would turn another boutique's id into a 500 rather than
        a 404, and would let a bench worker drive an alteration they cannot
        even see.
        """
        alteration = self.get_object()
        kwargs['alteration_request_id'] = alteration.id
        try:
            return self._detail(service(**kwargs))
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except (TransitionError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    def _payload(self, serializer_class, request):
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _actor(self, request):
        return {
            'performed_by': request.user,
            'role': resolve_user_role(request.user),
        }

    # -- intake -----------------------------------------------------------

    def create(self, request, *args, **kwargs):
        data = self._payload(AlterationRequestCreateSerializer, request)
        try:
            alteration = services.create_alteration_request(
                customer_id=data['customer_id'],
                order_id=data['order_id'],
                garment_job_id=data['garment_job_id'],
                alteration_type=data.get('alteration_type', AlterationType.PAID_CLIENT_REQUEST),
                issue_description=data.get('issue_description', ''),
                requested_adjustments=data.get('requested_adjustments') or {},
                charge_amount=data.get('charge_amount'),
                notes=data.get('notes', ''),
                **self._actor(request),
            )
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except (TransitionError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return self._detail(alteration, status.HTTP_201_CREATED)

    # -- workflow ---------------------------------------------------------

    @action(detail=True, methods=['POST'], url_path='start-inspection')
    def start_inspection(self, request, pk=None):
        data = self._payload(NotesSerializer, request)
        return self._run(services.start_inspection,
                         notes=data.get('notes', ''), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='record-inspection')
    def record_inspection(self, request, pk=None):
        data = self._payload(InspectionSerializer, request)
        return self._run(services.record_inspection,
                         inspection_notes=data.get('inspection_notes', ''),
                         adjustments=data.get('adjustments') or {},
                         **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='submit-for-approval')
    def submit_for_approval(self, request, pk=None):
        data = self._payload(SubmitForApprovalSerializer, request)
        return self._run(services.submit_for_approval,
                         charge_amount=data.get('charge_amount'),
                         notes=data.get('notes', ''), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='approve')
    def approve(self, request, pk=None):
        data = self._payload(NotesSerializer, request)
        return self._run(services.approve_alteration,
                         notes=data.get('notes', ''), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='assign')
    def assign(self, request, pk=None):
        data = self._payload(AssignSerializer, request)
        return self._run(services.assign_alteration,
                         tailor_id=data['tailor_id'],
                         title=data.get('title') or None,
                         stage_key=data.get('stage_key') or None,
                         notes=data.get('notes', ''), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='start-work')
    def start_work(self, request, pk=None):
        data = self._payload(NotesSerializer, request)
        return self._run(services.start_alteration_work,
                         task_id=data.get('task_id'), notes=data.get('notes', ''),
                         tailor_id=_tailor_id(request.user), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='send-to-qc')
    def send_to_qc(self, request, pk=None):
        data = self._payload(NotesSerializer, request)
        return self._run(services.send_to_qc,
                         task_id=data.get('task_id'), notes=data.get('notes', ''),
                         tailor_id=_tailor_id(request.user), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='pass-qc')
    def pass_qc(self, request, pk=None):
        data = self._payload(NotesSerializer, request)
        return self._run(services.pass_quality_check,
                         notes=data.get('notes', ''), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='fail-qc')
    def fail_qc(self, request, pk=None):
        data = self._payload(ReasonSerializer, request)
        return self._run(services.fail_quality_check,
                         reason=data['reason'], **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='complete')
    def complete(self, request, pk=None):
        data = self._payload(NotesSerializer, request)
        return self._run(services.complete_alteration,
                         notes=data.get('notes', ''), **self._actor(request))

    @action(detail=True, methods=['POST'], url_path='cancel')
    def cancel(self, request, pk=None):
        data = self._payload(ReasonSerializer, request)
        return self._run(services.cancel_alteration,
                         reason=data['reason'], **self._actor(request))

    # -- money ------------------------------------------------------------

    @action(detail=True, methods=['GET', 'POST'], url_path='payments')
    def payments(self, request, pk=None):
        alteration = self.get_object()

        if request.method == 'GET':
            return Response(
                AlterationPaymentSerializer(alteration.payments.all(), many=True).data)

        data = self._payload(RecordPaymentSerializer, request)
        try:
            payment = services.record_alteration_payment(
                alteration.id,
                amount=data['amount'],
                payment_method=data.get('payment_method'),
                transaction_reference=data.get('transaction_reference', ''),
                notes=data.get('notes', ''),
                received_by=request.user,
                role=resolve_user_role(request.user),
            )
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AlterationPaymentSerializer(payment).data,
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['GET'], url_path='outstanding-balance')
    def outstanding_balance(self, request, pk=None):
        alteration = self.get_object()
        return Response({
            'alteration_id': str(alteration.id),
            'alteration_number': alteration.alteration_number,
            'alteration_type': alteration.alteration_type,
            'charge_amount': str(alteration.charge_amount),
            'amount_paid': str(alteration.amount_paid),
            'outstanding_balance': str(
                services.calculate_outstanding_balance(alteration)),
        })

    # -- materials --------------------------------------------------------

    @action(detail=True, methods=['GET', 'POST'], url_path='materials')
    def materials(self, request, pk=None):
        alteration = self.get_object()

        if request.method == 'GET':
            return Response(
                AlterationMaterialLineSerializer(
                    alteration.material_lines.all(), many=True).data)

        data = self._payload(RecordMaterialSerializer, request)
        try:
            line = services.record_alteration_material_usage(
                alteration.id,
                item_id=data['item_id'],
                quantity=data['quantity'],
                unit=data.get('unit') or None,
                remarks=data.get('remarks', ''),
                recorded_by=request.user,
                role=resolve_user_role(request.user),
            )
        except PermissionError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(AlterationMaterialLineSerializer(line).data,
                        status=status.HTTP_201_CREATED)
