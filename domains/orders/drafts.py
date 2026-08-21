"""Order drafts: work in progress, kept out of production.

KNOWN UX LIMITATION -- browser Back/Forward is not wizard-step aware.
The app is a single-page application with no URL routing, so the wizard's step
is component state and the browser's history has no entry for it. Pressing Back
leaves the application rather than stepping back through the order form.

That is a navigation gap, not a data one, and the distinction matters: the
draft is on the server, so the work is safe and is re-offered on the order
screen whenever the owner returns. Recorded here so nobody later reads the
behaviour as a defect that slipped through -- restoring the exact in-progress
step needs URL routing, which is its own change.

One rule runs through this module, and it is the reason the draft is its own
model rather than a flag: **a draft is not an order.** It has no stages, no
material plan, no invoice and no tracking link. It cannot be assigned, reserved
against, delivered, counted in revenue or seen by a tailor. It becomes an order
once, at confirm(), and that is the only door.
"""

from django.db import transaction

from crm_api.models import Customer, OrderDraft


class DraftConflict(ValueError):
    """Someone else's copy of this draft is newer than the one being saved."""


@transaction.atomic
def save_draft(user, payload, *, draft_id=None, customer=None, current_step=1,
               version=None):
    """Create or update the caller's draft.

    `version` is what the client last read. Supplying a stale one is refused
    rather than merged: two tabs open on the same draft is an ordinary thing to
    do -- one gets opened to check a measurement and left there -- and the
    older tab must not be able to quietly write its idea of the order over the
    newer one. Refusing loudly is what lets the interface say so.
    """
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
    """What this user can pick back up."""
    return OrderDraft.objects.filter(created_by=user).select_related('customer')


@transaction.atomic
def abandon(user, draft_id):
    """Throw a draft away, explicitly.

    Deleted rather than flagged: an abandoned draft is not a record of
    anything, and keeping it would only give the resume prompt something stale
    to offer. The customer, if there is one, is left alone -- they may have
    been on file long before this draft existed.
    """
    return OrderDraft.objects.filter(pk=draft_id, created_by=user).delete()[0]


@transaction.atomic
def confirm(user, draft_id, *, create_order):
    """Turn a draft into a real order, once.

    `create_order` does the actual work and is passed in rather than imported,
    so this module never reaches into the order-creation path and the two can
    be tested apart. The draft is deleted in the same transaction: if order
    creation raises, the draft is still there and the boutique has lost
    nothing.
    """
    draft = (OrderDraft.objects.select_for_update()
             .filter(pk=draft_id, created_by=user).first())
    if draft is None:
        return None
    order = create_order(draft)
    draft.delete()
    return order


def customer_for(draft, payload):
    """The client this draft is for, created only now if they are new.

    Held back until confirmation on purpose. The wizard used to POST the
    customer at step one, so abandoning at step four left a customer nobody
    asked for, with no order attached and no way to reach the work again.
    """
    if draft.customer_id:
        return draft.customer
    fields = {k: payload.get(k, '') for k in (
        'first_name', 'last_name', 'mobile_number', 'email_address', 'address',
        'city_region', 'source', 'customer_type', 'garment_type', 'occasion',
        'pattern_style', 'custom_requirements', 'occupation',
        'preferred_communication', 'notes',
    ) if payload.get(k) not in (None, '')}
    return Customer.objects.create(**fields)
