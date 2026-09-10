from rest_framework import viewsets, views
from rest_framework.response import Response
from django.utils.dateparse import parse_date

from core.permissions import OwnerOnly

from . import services
from .models import Expense
from .serializers import ExpenseSerializer


class ExpenseViewSet(viewsets.ModelViewSet):
    """Manual business costs. Owner-only, every method.

    Costs are the owner's private view of the business -- what rent runs to,
    what was paid a supplier off the books of a PO -- and no staff role has a
    reason to read or write them, so this uses OwnerOnly rather than the
    looser RolePermission that governs the order book.
    """

    serializer_class = ExpenseSerializer
    permission_classes = [OwnerOnly]

    def get_queryset(self):
        qs = Expense.objects.all()
        since = parse_date(self.request.query_params.get('since') or '')
        until = parse_date(self.request.query_params.get('until') or '')
        if since:
            qs = qs.filter(incurred_on__gte=since)
        if until:
            qs = qs.filter(incurred_on__lte=until)
        if category := self.request.query_params.get('category'):
            qs = qs.filter(category=category)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProfitLossView(views.APIView):
    """Revenue minus every cost, for a window. Owner-only.

    A computed report, not a resource -- its own path rather than a router
    action, the same shape apps.staff uses for the timesheet and performance
    reports.
    """

    permission_classes = [OwnerOnly]

    def get(self, request):
        since = parse_date(request.query_params.get('since') or '')
        until = parse_date(request.query_params.get('until') or '')
        return Response(services.profit_and_loss(since=since, until=until))
