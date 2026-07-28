"""Studio orchestration: context -> queries -> multi-source search -> ranking."""

import logging

from django.db import transaction
from django.utils import timezone

from .context import build_context
from .intelligence.registry import get_intelligence
from .models import DesignBoard, DesignBoardItem
from .providers.registry import active_providers, source_status

logger = logging.getLogger(__name__)

# Per-source cap. Without it a large catalogue would crowd every other source
# out of the gallery.
PER_SOURCE_LIMIT = 24


def discover(customer, order_input=None, extra_keywords=None, sources=None, limit=40):
    """Run a full studio search and return ranked designs with their context."""
    context = build_context(customer, order_input)
    intelligence = get_intelligence()
    queries = intelligence.generate_queries(context, extra_keywords)

    candidates = []
    seen = set()
    for provider in active_providers(sources):
        try:
            results = provider.search(queries, context, limit=PER_SOURCE_LIMIT)
        except Exception:
            # One misbehaving source must not empty the gallery. Log it and
            # carry on with whatever the others returned.
            logger.exception("Design source %s failed", provider.key)
            continue
        for candidate in results:
            key = (candidate.source, candidate.source_ref)
            if key in seen:
                continue
            seen.add(key)
            candidate.attributes = intelligence.analyse(candidate, context)
            candidates.append(candidate)

    ranked = intelligence.rank(candidates, context)[:limit]

    return {
        'context': context,
        'queries': queries,
        'sources': source_status(),
        'results': ranked,
    }


@transaction.atomic
def select_item(board, item):
    """Make ``item`` the board's single selected design."""
    if item.board_id != board.id:
        raise ValueError("Item does not belong to this board")
    # The DB enforces one selection per board, so the old one has to be cleared
    # before the new one is written.
    board.items.filter(is_selected=True).exclude(pk=item.pk).update(is_selected=False)
    item.is_selected = True
    item.save(update_fields=['is_selected'])
    if board.status == DesignBoard.STATUS_DRAFT:
        board.status = DesignBoard.STATUS_SHORTLISTED
        board.save(update_fields=['status', 'updated_at'])
    # The board was loaded with its items prefetched, so that cached list still
    # shows the old selection. Serialising it as-is sent the client a board
    # whose items all read is_selected=false straight after a successful
    # select, and the UI had no way to know which design had been chosen.
    board.refresh_from_db()
    return item


@transaction.atomic
def approve_board(board, user):
    """Lock in the selected design as the reference production will follow."""
    selected = board.selected_item
    if selected is None:
        raise ValueError("Select a design before approving the board")
    board.status = DesignBoard.STATUS_APPROVED
    board.approved_by = user if getattr(user, 'is_authenticated', False) else None
    board.approved_at = timezone.now()
    board.save(update_fields=['status', 'approved_by', 'approved_at', 'updated_at'])
    board.refresh_from_db()
    return board


@transaction.atomic
def save_to_order(board, order):
    """Attach an approved board to an order.

    Everything production needs -- reference image, source and original URL,
    attributes, palette, customer notes and tailor instructions -- travels with
    the board, so the order carries the full design specification from here on.
    """
    if board.status != DesignBoard.STATUS_APPROVED:
        raise ValueError("Approve the board before saving it to an order")
    if board.selected_item is None:
        raise ValueError("Board has no selected design")
    existing = getattr(order, 'design_board', None)
    if existing is not None and existing.pk != board.pk:
        raise ValueError(f"Order {order.order_id} already has a design board attached")
    board.order = order
    board.save(update_fields=['order', 'updated_at'])
    return board


def item_from_candidate(board, payload, position=0):
    """Create a board item from a gallery result payload."""
    return DesignBoardItem(
        board=board,
        source=payload.get('source', ''),
        source_ref=str(payload.get('source_ref', '')),
        title=payload.get('title', ''),
        image_url=payload.get('image_url', ''),
        source_url=payload.get('source_url', ''),
        attributes=payload.get('attributes') or {},
        tags=payload.get('tags') or [],
        colour_palette=payload.get('colour_palette') or [],
        estimated_price=payload.get('estimated_price') or 0,
        match_score=payload.get('match_score') or 0,
        match_reasons=payload.get('match_reasons') or [],
        customer_notes=payload.get('customer_notes', '') or '',
        tailor_instructions=payload.get('tailor_instructions', '') or '',
        position=position,
    )
