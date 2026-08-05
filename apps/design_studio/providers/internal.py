"""Sources the boutique already owns: catalogue, past orders, saved library."""

from decimal import Decimal

from django.db.models import Q

from crm_api.models import Order

from ..models import DesignAsset
from .base import DesignCandidate, DesignSourceProvider


def _tokens(queries):
    """Distinct lowercase words across all search queries."""
    seen = []
    for query in queries:
        for token in str(query).replace(',', ' ').split():
            token = token.strip().lower()
            if len(token) > 2 and token not in seen:
                seen.append(token)
    return seen


class CatalogueProvider(DesignSourceProvider):
    key = 'catalogue'
    label = 'Boutique Catalogue'

    def search(self, queries, context, limit=20):
        # The catalogue moved into the library; these are the same rows.
        from ..models import DesignAsset
        designs = DesignAsset.objects.filter(
            source__in=[DesignAsset.SOURCE_CATALOGUE, DesignAsset.SOURCE_SUGGESTION])
        if context.garment_type:
            # Narrow to the garment being ordered, but fall back to the full
            # catalogue rather than showing an empty gallery when nothing in
            # the catalogue is tagged with that garment yet.
            narrowed = designs.filter(garment_type__iexact=context.garment_type)
            designs = narrowed if narrowed.exists() else designs

        tokens = _tokens(queries)
        if tokens:
            matches = Q()
            for token in tokens:
                matches |= Q(title__icontains=token) | Q(description__icontains=token)
            keyword_hits = designs.filter(matches)
            if keyword_hits.exists():
                designs = keyword_hits

        candidates = []
        for design in designs[:limit]:
            candidates.append(DesignCandidate(
                source=self.key,
                source_ref=str(design.id),
                title=design.title,
                image_url=design.image_url or '',
                garment_type=design.garment_type or '',
                attributes={
                    'neck_type': (design.attributes or {}).get('neckline_style', ''),
                    'sleeve': (design.attributes or {}).get('sleeve_style', ''),
                },
                tags=[t for t in [design.garment_type,
                                  (design.attributes or {}).get('neckline_style'),
                                  (design.attributes or {}).get('sleeve_style')] if t],
                estimated_price=Decimal(design.estimated_price or 0),
                popularity=80 if design.source == design.SOURCE_CATALOGUE else 50,
            ))
        return candidates


class PastOrderProvider(DesignSourceProvider):
    key = 'past_order'
    label = 'Previously Completed Orders'

    def search(self, queries, context, limit=20):
        orders = (Order.objects
                  .select_related('customer')
                  .exclude(completed_garment_image='')
                  .exclude(completed_garment_image=None)
                  .order_by('-order_date'))

        candidates = []
        for order in orders[:limit]:
            customer = order.customer
            if context.garment_type and customer.garment_type:
                if customer.garment_type.lower() != context.garment_type.lower():
                    continue
            candidates.append(DesignCandidate(
                source=self.key,
                source_ref=str(order.id),
                title=f"{customer.garment_type or 'Garment'} for {customer.first_name}",
                image_url=order.completed_garment_image.url if order.completed_garment_image else '',
                garment_type=customer.garment_type or '',
                occasion=customer.occasion or '',
                attributes={
                    'neck_type': customer.neckline_style or '',
                    'sleeve': customer.sleeve_style or '',
                    'back': customer.back_style or '',
                    'pattern': customer.pattern_style or '',
                    'embroidery': customer.embellishments or '',
                    'fit': customer.silhouette or '',
                },
                tags=[t for t in [customer.occasion, customer.pattern_style, customer.embellishments] if t],
                estimated_price=Decimal(order.total_amount or 0),
                popularity=70,
            ))
        return candidates


class LibraryProvider(DesignSourceProvider):
    """Team uploads, saved favourites and anything imported from a platform."""

    key = 'library'
    label = 'Saved & Uploaded Designs'

    def search(self, queries, context, limit=20):
        assets = DesignAsset.objects.all()
        if context.garment_type:
            narrowed = assets.filter(garment_type__iexact=context.garment_type)
            assets = narrowed if narrowed.exists() else assets

        candidates = []
        for asset in assets[:limit]:
            candidates.append(DesignCandidate(
                source=asset.source,
                source_ref=str(asset.id),
                title=asset.title,
                image_url=asset.image_url,
                source_url=asset.source_url,
                designer=asset.designer,
                garment_type=asset.garment_type,
                occasion=asset.occasion,
                attributes=dict(asset.attributes or {}),
                tags=list(asset.tags or []),
                colour_palette=list(asset.colour_palette or []),
                estimated_price=Decimal(asset.estimated_price or 0),
                popularity=asset.popularity + (20 if asset.is_favourite else 0),
            ))
        return candidates
