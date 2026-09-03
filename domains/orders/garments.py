

def garment_names(order):
    names = []
    for job in order.garment_jobs.all():
        name = (job.template.name if job.template_id else '') or 'Custom garment'
        names.append(name)
    if names:
        return names

    legacy = (order.customer.garment_type or '').strip()
    return [legacy] if legacy else []


def garment_label(order):
    names = garment_names(order)
    if not names:
        return 'Custom garment'
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
