"""One page shape for every list in the product.

Nothing was paginated. `GET /api/orders/` returned every order a boutique had
ever taken, `GET /api/inventory/items/` every item, and the browser then filtered
the lot in JavaScript. That is survivable on a shop desktop on the shop's wifi.
It is not survivable on a phone on mobile data, which is the client this exists
for.

The shape is DRF's own -- {count, next, previous, results} -- deliberately, so
that a mobile list can page by following `next` and needs no arithmetic, and so
that nothing here has to be explained to anyone who has used DRF.

Two decisions worth stating:

**A page size cap.** `page_size` is a query parameter because a phone wants 20
rows and a report wants as many as it can get, but it is capped, or the
parameter is just a way to ask the server to build the unbounded response this
class exists to prevent.

**A fallback ordering.** Paginating an unordered queryset is not slow, it is
WRONG: without ORDER BY, PostgreSQL may return rows in any order it likes, and
it need not pick the same order twice -- so a row can appear on page 1 and again
on page 3 while another is never seen at all. Most models here declare
Meta.ordering, but "most" is not a guarantee an unbounded list ever had to make.
Rather than audit thirty querysets and hope the thirty-first remembers, an
unordered queryset is ordered by primary key here. That order is arbitrary but
STABLE, which is the property paging actually requires.
"""

from django.db.models import QuerySet
from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def paginate_queryset(self, queryset, request, view=None):
        if isinstance(queryset, QuerySet) and not queryset.ordered:
            queryset = queryset.order_by('pk')
        return super().paginate_queryset(queryset, request, view)
