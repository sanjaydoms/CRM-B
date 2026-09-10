

import logging
import uuid

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from .context import build_context
from .intelligence.registry import get_intelligence
from .models import DesignAsset, DesignBoard, DesignBoardItem
from .providers.registry import active_providers, source_status

logger = logging.getLogger(__name__)

PER_SOURCE_LIMIT = 24


def discover(subject, order_input=None, extra_keywords=None, sources=None, limit=40):
    context = build_context(subject, order_input)
    intelligence = get_intelligence()
    queries = intelligence.generate_queries(context, extra_keywords)

    candidates = []
    seen = set()
    for provider in active_providers(sources):
        try:
            results = provider.search(queries, context, limit=PER_SOURCE_LIMIT)
        except Exception:
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
    if item.board_id != board.id:
        raise ValueError("Item does not belong to this board")
    (board.items
     .filter(is_selected=True, garment_job_id=item.garment_job_id)
     .exclude(pk=item.pk)
     .update(is_selected=False))
    item.is_selected = True
    item.save(update_fields=['is_selected'])
    if board.status == DesignBoard.STATUS_DRAFT:
        board.status = DesignBoard.STATUS_SHORTLISTED
        board.save(update_fields=['status', 'updated_at'])
    board.refresh_from_db()
    return item


@transaction.atomic
def approve_board(board, user):

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
    if board.status != DesignBoard.STATUS_APPROVED:
        raise ValueError("Approve the board before saving it to an order")
    selected = board.selected_item
    if selected is None:
        raise ValueError("Board has no selected design")
    existing = getattr(order, 'design_board', None)
    if existing is not None and existing.pk != board.pk:
        raise ValueError(f"Order {order.order_id} already has a design board attached")
    board.order = order
    board.save(update_fields=['order', 'updated_at'])
    _credit_order_to_design(selected)
    return board


def _credit_order_to_design(item):
    try:
        asset_id = uuid.UUID(item.source_ref)
    except (ValueError, TypeError, AttributeError):
        return
    DesignAsset.objects.filter(pk=asset_id).update(order_count=F('order_count') + 1)


def item_from_candidate(board, payload, position=0):

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
