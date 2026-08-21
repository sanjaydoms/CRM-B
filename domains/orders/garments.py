"""What the boutique is actually making for an order.

One answer, in one place, because there used to be several that disagreed.

The wizard writes a GarmentJob per dress and always has. Every screen except
the stage-detail panel read `Customer.garment_type` instead -- a single field
on the *person*, overwritten by whichever dress was picked last. So an order
for a blouse and a lehenga showed one garment on the order summary, the
invoice, the Master, Tailor and QC dashboards, the customer's WhatsApp
confirmation, the tracking page and the analytics. The customer was billed for
one of the two garments she had ordered.

Read the jobs. Never the customer.
"""


def garment_names(order):
    """Every garment on this order, in the sequence the wizard collected them.

    The fallback to Customer.garment_type fires only for an order that carries
    no garment jobs at all, which means it predates them -- nine of the ten
    orders already in the database are in that state. This is the one place in
    the codebase allowed to read that field for display, and keeping it here is
    what lets every caller stop choosing for itself.
    """
    names = []
    for job in order.garment_jobs.all():
        # template is nullable on the model; a job that lost its template still
        # describes a real garment somebody has to make, so it stays in the list.
        name = (job.template.name if job.template_id else '') or 'Custom garment'
        names.append(name)
    if names:
        return names

    legacy = (order.customer.garment_type or '').strip()
    return [legacy] if legacy else []


def garment_label(order):
    """The garments as one line of prose: 'Blouse and Lehenga'.

    For invoice headers, WhatsApp messages and anywhere a sentence needs to
    name the work. Screens that show per-garment detail iterate the jobs
    themselves rather than calling this.
    """
    names = garment_names(order)
    if not names:
        return 'Custom garment'
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
