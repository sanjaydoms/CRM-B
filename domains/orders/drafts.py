
from django.db import transaction

from crm_api.models import Customer, OrderDraft


class DraftConflict(ValueError):
    pass



@transaction.atomic
def save_draft(user, payload, *, draft_id=None, customer=None, current_step=1,
               version=None):
    if draft_id is None:
        return OrderDraft.objects.create(
            created_by=user, customer=customer, payload=payload or {},
            current_step=current_step)

    draft = (OrderDraft.objects.select_for_update()
             .filter(pk=draft_id, created_by=user).first())
    if draft is None:
        return None

    if version is not None and int(version) != draft.version:
        raise DraftConflict(
            f'This order was changed somewhere else after you opened it '
            f'(you have version {version}, the saved one is {draft.version}). '
            f'Reload it to carry on from the newer copy.')

    draft.payload = payload if payload is not None else draft.payload
    draft.current_step = current_step or draft.current_step
    if customer is not None:
        draft.customer = customer
    draft.version += 1
    draft.save(update_fields=['payload', 'current_step', 'customer', 'version',
                              'updated_at'])
    return draft


def open_drafts(user):

    return OrderDraft.objects.filter(created_by=user).select_related('customer')


@transaction.atomic
def abandon(user, draft_id):
    return OrderDraft.objects.filter(pk=draft_id, created_by=user).delete()[0]


@transaction.atomic
def confirm(user, draft_id, *, create_order):
    draft = (OrderDraft.objects.select_for_update()
             .filter(pk=draft_id, created_by=user).first())
    if draft is None:
        return None
    order = create_order(draft)
    draft.delete()
    return order


def customer_for(draft, payload):
    if draft.customer_id:
        return draft.customer
    fields = {k: payload.get(k, '') for k in (
        'first_name', 'last_name', 'mobile_number', 'email_address', 'address',
        'city_region', 'source', 'customer_type', 'garment_type', 'occasion',
        'pattern_style', 'custom_requirements', 'occupation',
        'preferred_communication', 'notes',
    ) if payload.get(k) not in (None, '')}
    return Customer.objects.create(**fields)
