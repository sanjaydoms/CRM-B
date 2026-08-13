"""Every table in a boutique, read generically.

A boutique's schema holds 50-odd models and several hundred fields between them.
Writing a serializer and a screen per model would be that many places to update
every time a field is added, and the console would silently fall behind the
product the first time someone forgot. So nothing here knows about any specific
model: the field list comes from Django's own introspection, which means a model
added tomorrow appears in the console tomorrow with no change to this file.

Read-only, and only ever pointed at a tenant schema. There is no write path in
this module by design -- the console is for looking at what a boutique has, and
anything that should be editable is editable in the boutique's own workspace,
where the business rules that protect it live.

Two things introspection would happily expose that must never leave this server:

  * `auth.User.password` is a hash. Cheap to render, expensive to have leaked,
    and worth nothing to an administrator looking at a boutique.
  * `authtoken.Token.key` is a *live credential*. Rendering it would turn read
    access to this console into the ability to act as any user in any boutique
    -- a far larger power than the console is meant to grant. The whole model is
    excluded rather than the one field, so a future column on it cannot reopen
    this.

REDACTED_NAME_PARTS catches the same class of mistake in models that do not
exist yet.
"""

from django.apps import apps
from django.conf import settings
from django.db.models import Q

#: Models that exist in a tenant schema but are not that boutique's data.
#: Django's own plumbing, plus the credential table above.
EXCLUDED_MODELS = frozenset({
    'authtoken.Token',       # live credentials -- see the module docstring
    'authtoken.TokenProxy',  # the same rows under another name
    'contenttypes.ContentType',
    'auth.Permission',
    'auth.Group',
    'admin.LogEntry',
    'sessions.Session',
})

#: Any field whose name contains one of these is replaced with a placeholder,
#: whatever model it turns up on. A blunt rule on purpose: the cost of redacting
#: one harmless column by accident is a dash in a table, and the cost of missing
#: a real one is a credential on a web page.
REDACTED_NAME_PARTS = ('password', 'secret', 'api_key', 'apikey', 'auth_token',
                       'access_token', 'refresh_token', 'private_key')

REDACTED = '••••••••'

#: Rows per page. Generous, because an administrator scanning a boutique's
#: orders wants to see them rather than click through them, and small enough
#: that a boutique with ten thousand customers does not send all of them.
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


def _is_redacted(field):
    lowered = field.name.lower()
    return any(part in lowered for part in REDACTED_NAME_PARTS)


def visible_models():
    """Every model that is part of a boutique's own data, in a stable order.

    Derived from TENANT_APPS rather than a hand-kept list, so an app added to
    the tenant schema is browsable without touching this module.
    """
    tenant_labels = {a.rsplit('.', 1)[-1] for a in settings.TENANT_APPS}
    found = []
    for model in apps.get_models():
        meta = model._meta
        key = f'{meta.app_label}.{meta.model_name}'
        if meta.app_label not in tenant_labels:
            continue
        if f'{meta.app_label}.{meta.object_name}' in EXCLUDED_MODELS:
            continue
        if meta.proxy:
            # A proxy is the same table under another name; listing both would
            # show every row twice under two headings.
            continue
        found.append((key, model))
    found.sort(key=lambda pair: pair[0])
    return found


def get_model(key):
    """Resolve 'app_label.model_name' to a model, or None.

    Goes through visible_models() rather than apps.get_model() so that the
    exclusions above are enforced on the *fetch* path too. Resolving directly
    would let a caller name `authtoken.token` in the URL and read every token in
    the boutique, with the list endpoint none the wiser.
    """
    for candidate, model in visible_models():
        if candidate == key:
            return model
    return None


def columns(model):
    """The table header: one entry per concrete field.

    Concrete fields only -- reverse relations and many-to-many would each be a
    query per row to render, and none of them hold anything the forward side
    does not.
    """
    described = []
    for field in model._meta.concrete_fields:
        described.append({
            'name': field.name,
            'label': str(field.verbose_name) if hasattr(field, 'verbose_name') else field.name,
            'type': field.get_internal_type(),
            'redacted': _is_redacted(field),
        })
    return described


def _value(instance, field):
    """One cell, rendered as something JSON can carry."""
    if _is_redacted(field):
        return REDACTED

    internal = field.get_internal_type()

    if field.is_relation:
        # The readable name of the related row, not its id. select_related in
        # rows() is what keeps this from being a query per cell.
        related = getattr(instance, field.name, None)
        return None if related is None else str(related)

    value = getattr(instance, field.name, None)
    if value is None:
        return None

    if internal in ('FileField', 'ImageField'):
        # A missing file raises rather than returning None, and a boutique's
        # uploads live on Render's ephemeral disk, so this is a normal case.
        try:
            return value.url
        except Exception:
            return str(value)
    if internal == 'DecimalField':
        return float(value)
    if internal in ('DateTimeField', 'DateField', 'TimeField'):
        return value.isoformat()
    if internal in ('JSONField', 'BooleanField', 'IntegerField', 'BigIntegerField',
                    'PositiveIntegerField', 'SmallIntegerField', 'FloatField',
                    'AutoField', 'BigAutoField'):
        return value
    return str(value)


def _search_filter(model, term):
    """Match `term` against every text column on the model.

    ponytail: an unindexed ILIKE per text column, so it is a sequential scan on
    a large table. Acceptable for an administrator looking something up by hand;
    if a boutique's order book ever makes this slow, give the columns that are
    actually searched a trigram index rather than making this cleverer.
    """
    searchable = [
        f.name for f in model._meta.concrete_fields
        if f.get_internal_type() in ('CharField', 'TextField', 'EmailField', 'SlugField')
        and not _is_redacted(f)
    ]
    if not searchable:
        return Q()
    query = Q()
    for name in searchable:
        query |= Q(**{f'{name}__icontains': term})
    return query


def rows(model, page=1, page_size=DEFAULT_PAGE_SIZE, search=''):
    """A page of `model`, newest first.

    Ordered by `-pk` rather than the model's own Meta.ordering: several of these
    models order on a non-unique column, and paginating an unstable ordering
    silently repeats and skips rows between pages.
    """
    page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    page = max(1, int(page or 1))

    queryset = model._default_manager.all()
    if search:
        queryset = queryset.filter(_search_filter(model, search))

    # One level of FK following, so rendering the related name in _value() does
    # not cost a query per cell. Deeper than one level is not needed: str() of
    # the related object is as far as any cell goes.
    relations = [f.name for f in model._meta.concrete_fields if f.is_relation]
    if relations:
        queryset = queryset.select_related(*relations)

    total = queryset.count()
    start = (page - 1) * page_size
    fields = list(model._meta.concrete_fields)
    page_rows = [
        {field.name: _value(instance, field) for field in fields}
        for instance in queryset.order_by('-pk')[start:start + page_size]
    ]
    return {
        'columns': columns(model),
        'rows': page_rows,
        'count': total,
        'page': page,
        'page_size': page_size,
        'pages': max(1, -(-total // page_size)),
    }


def inventory():
    """Every browsable model with its row count, for the drill-down sidebar.

    One COUNT per model, so this is ~50 queries against a single schema. That is
    a page an administrator opens deliberately rather than something on a hot
    path, and it is the number that makes the sidebar useful -- a list of table
    names with no counts does not tell you where a boutique's data actually is.
    """
    listed = []
    for key, model in visible_models():
        try:
            count = model._default_manager.count()
        except Exception:
            # A table missing from this schema (a migration not yet applied
            # there) must not take the whole sidebar down with it.
            count = None
        listed.append({
            'key': key,
            'app': model._meta.app_label,
            'label': str(model._meta.verbose_name_plural).title(),
            'count': count,
        })
    return listed
