"""Every table in a boutique, read generically -- and only what is allowed.

A boutique's schema holds 50-odd models and several hundred fields between them,
so rendering is still generic: the shape of a table comes from Django's own
introspection rather than from a serializer per model. What is no longer generic
is *which* of them an administrator may see.

Read-only, and only ever pointed at a tenant schema. There is no write path in
this module by design -- the console is for looking at what a boutique has, and
anything that should be editable is editable in the boutique's own workspace,
where the business rules that protect it live.

Three layers decide what leaves this server, in this order:

  1. **ALLOWED_FIELDS** -- an allowlist of models, and of the fields of each.
     A model that is not named is not browsable; a field that is not named is
     masked. Both directions fail closed, so a model or column added tomorrow
     is invisible until someone reviews it rather than published by default.
     This is the layer that matters and the reason for the rest of this
     docstring.
  2. **EXCLUDED_MODELS** -- Django's own plumbing and, above all,
     `authtoken.Token`, whose `key` is a *live credential*: rendering one would
     turn read access to this console into the ability to act as any user in
     any boutique. The whole model is excluded rather than the one field, so a
     future column on it cannot reopen this.
  3. **REDACTED_NAME_PARTS** -- the original denylist, kept as a second layer
     underneath the allowlist rather than as the defence. It is what stops a
     credential column being exposed by someone adding it to ALLOWED_FIELDS
     without thinking, and it costs nothing to keep.

Why the allowlist replaced the denylist as the primary control: the denylist
matched names ('password', 'secret', 'api_key', 'auth_token', ...), which is a
bet that every future credential will be spelled like a past one. Measured
against this build, it let through 'gateway_credential', 'webhook_signing',
'otp_seed', 'recovery_code', 'session_key' and 'pat'. `auth.User.password` was
caught -- but only because somebody had already been bitten by that one.

Access here is audited by the caller (superadmin/views.py, BoutiqueDataView),
not by this module. This module answers "what may be read"; the view records
"who read it".
"""

from django.apps import apps
from django.conf import settings
from django.db.models import Q

#: Every model a platform administrator may inspect, and the fields of each
#: that may be RENDERED. This is an ALLOWLIST at both levels and it fails closed
#: at both levels:
#:
#:   * a model that is not a key here is not browsable at all;
#:   * a field that is not listed against its model is MASKED, not hidden --
#:     the column still appears, so the console tells an administrator that
#:     something is there rather than quietly editing reality.
#:
#: It replaces a denylist of credential-shaped NAMES ('password', 'api_key',
#: 'auth_token', ...), which was safe only for the names someone had thought of.
#: Measured against this build: 'gateway_credential', 'webhook_signing',
#: 'otp_seed', 'recovery_code', 'session_key' and 'pat' all passed that filter
#: untouched. A denylist has to predict the future to be correct; an allowlist
#: only has to describe the present.
#:
#: THE MAINTENANCE CONTRACT, and it is deliberate rather than an oversight: a
#: field added to a model tomorrow is masked until someone adds it here. That
#: is the whole property being bought. Nothing breaks -- no test fails, no
#: request errors, the boutique's own product is untouched -- an administrator
#: simply sees a masked column and a developer decides whether it is fit to
#: show. Adding a NEW MODEL requires an entry here before the console can read
#: it, for the same reason.
#:
#: Seeded from the models present when this was written, minus the credential
#: columns REDACTED_NAME_PARTS already caught. It is a review record, not a
#: mirror of the schema; regenerating it wholesale from introspection would
#: give back exactly the property it exists to remove.
ALLOWED_FIELDS = {
    'activities.universalactivity': (
        'id', 'user', 'user_name_snapshot', 'module', 'entity_type',
        'entity_id', 'action', 'title', 'description', 'old_value',
        'new_value', 'timestamp',
    ),
    'auth.user': (
        'id', 'last_login', 'is_superuser', 'username', 'first_name',
        'last_name', 'email', 'is_staff', 'is_active', 'date_joined',
    ),
    'catalog.garmentjob': (
        'id', 'order', 'template', 'template_version', 'spec',
        'base_price', 'fabric_price', 'embroidery_price',
        'customization_price', 'tailoring_charges', 'measurements',
        'sequence', 'created_at', 'updated_at',
    ),
    'catalog.garmenttemplate': (
        'id', 'key', 'name', 'description', 'version', 'is_active',
        'sequence', 'tenant', 'created_at', 'updated_at',
    ),
    'catalog.jobmaterial': (
        'id', 'job', 'field_key', 'inventory_item', 'free_text',
        'quantity', 'unit', 'source', 'notes',
    ),
    'catalog.templatefield': (
        'id', 'section', 'key', 'label', 'field_type', 'unit',
        'is_required', 'is_repeatable', 'default', 'help_text',
        'sequence', 'visible_when', 'validation', 'inventory_category',
    ),
    'catalog.templatefieldoption': (
        'id', 'field', 'value', 'label', 'sequence', 'is_active',
    ),
    'catalog.templatesection': (
        'id', 'template', 'key', 'title', 'sequence',
    ),
    'crm_api.boutiquedesign': (
        'id', 'name', 'garment_type', 'neckline_style', 'sleeve_style',
        'image_url', 'is_boutique', 'description', 'price',
    ),
    'crm_api.boutiquefabric': (
        'id', 'name', 'material', 'color', 'price_per_meter',
        'image_url', 'is_available',
    ),
    'crm_api.boutiquesettings': (
        'id', 'name', 'address', 'phone', 'email', 'logo',
        'workflow_config', 'design_approval_required',
        'customer_messaging_enabled',
    ),
    'crm_api.customer': (
        'id', 'first_name', 'last_name', 'mobile_number',
        'email_address', 'address', 'city_region', 'source',
        'customer_type', 'garment_type', 'neckline_style',
        'sleeve_style', 'back_style', 'length_preference', 'silhouette',
        'embellishments', 'pattern_style', 'occasion',
        'custom_requirements', 'date_of_birth', 'occupation',
        'preferred_communication', 'notes', 'profile_photo',
        'created_at', 'updated_at',
    ),
    'crm_api.customermessage': (
        'id', 'order', 'channel', 'template_key', 'to_number', 'body',
        'status', 'provider_message_id', 'error', 'sent_by',
        'created_at',
    ),
    'crm_api.designpreference': (
        'id', 'customer', 'notes', 'reference_images', 'source',
        'reference_links', 'approved_image', 'is_approved',
        'approved_at',
    ),
    'crm_api.fabricselection': (
        'id', 'customer', 'is_boutique_fabric', 'fabric_name',
        'fabric_price', 'uploaded_fabric_images',
    ),
    'crm_api.garmentimage': (
        'id', 'order', 'view', 'image', 'uploaded_by', 'uploaded_at',
    ),
    'crm_api.measurement': (
        'id', 'customer', 'bust', 'waist', 'hips', 'shoulder',
        'arm_length', 'neck', 'length', 'additional_measurements',
    ),
    'crm_api.measurementhistory': (
        'id', 'customer', 'bust', 'waist', 'hips', 'shoulder',
        'arm_length', 'neck', 'length', 'additional_measurements',
        'changed_at',
    ),
    'crm_api.notification': (
        'id', 'title', 'message', 'recipient_role', 'recipient_email',
        'created_at', 'is_read',
    ),
    'crm_api.order': (
        'id', 'order_id', 'customer', 'tailor', 'master',
        'payment_status', 'order_status', 'delivery_method',
        'courier_service', 'tracking_number', 'delivery_address',
        'base_price', 'fabric_price', 'embroidery_price',
        'customization_price', 'tailoring_charges',
        'packaging_handling', 'discount', 'taxes', 'total_amount',
        'advance_paid', 'amount_paid', 'order_date',
        'estimated_delivery', 'tailor_comments',
        'completed_garment_image', 'master_verification',
        'garment_images_published', 'special_instructions',
        'current_stage_key', 'production_status',
    ),
    'crm_api.orderactivity': (
        'id', 'order', 'event_type', 'user', 'timestamp', 'metadata',
    ),
    'crm_api.orderdraft': (
        'id', 'created_by', 'customer', 'payload', 'current_step',
        'version', 'created_at', 'updated_at',
    ),
    'crm_api.orderstage': (
        'id', 'order', 'stage_key', 'stage_name', 'status',
        'started_at', 'completed_at', 'duration_seconds', 'assigned_to',
        'performed_by', 'comments', 'attachments', 'sequence',
        'sla_hours',
    ),
    'crm_api.orderstagehistory': (
        'id', 'order', 'stage', 'comments', 'image',
        'completed_by_name', 'completed_at',
    ),
    'crm_api.tailor': (
        'id', 'name', 'specialty', 'rating', 'status', 'role', 'email',
        'user',
    ),
    'design_studio.collection': (
        'id', 'designer', 'name', 'description', 'cover_image',
        'season', 'is_active', 'sequence', 'created_at', 'updated_at',
    ),
    'design_studio.designapproval': (
        'id', 'design', 'reviewer', 'decision', 'note', 'created_at',
    ),
    'design_studio.designasset': (
        'id', 'source', 'external_id', 'title', 'image_url',
        'source_url', 'designer', 'designer_ref', 'garment_type',
        'occasion', 'attributes', 'tags', 'colour_palette', 'template',
        'spec_tags', 'status', 'visibility', 'approved_by',
        'approved_at', 'collection', 'description', 'video_url',
        'gallery', 'difficulty', 'stitch_hours', 'estimated_price',
        'popularity', 'is_favourite', 'view_count', 'order_count',
        'created_by', 'created_at', 'updated_at',
    ),
    'design_studio.designassignment': (
        'id', 'garment_job', 'designer', 'status', 'brief', 'due_date',
        'design', 'submission_note', 'review_note', 'assigned_by',
        'reviewed_by', 'assigned_at', 'submitted_at', 'reviewed_at',
        'updated_at',
    ),
    'design_studio.designboard': (
        'id', 'customer', 'order', 'status', 'title', 'notes',
        'context_snapshot', 'search_queries', 'created_by',
        'approved_by', 'approved_at', 'created_at', 'updated_at',
    ),
    'design_studio.designboarditem': (
        'id', 'board', 'garment_job', 'source', 'source_ref', 'title',
        'image_url', 'source_url', 'attributes', 'tags',
        'colour_palette', 'estimated_price', 'match_score',
        'match_reasons', 'is_selected', 'customer_notes',
        'tailor_instructions', 'production_notes',
        'production_notes_by', 'position', 'created_at',
    ),
    'design_studio.designer': (
        'id', 'name', 'employee_id', 'email', 'user', 'staff',
        'profile_image', 'specialisation', 'experience_years', 'bio',
        'is_active', 'joined_at', 'last_active_at', 'created_at',
        'updated_at',
    ),
    'inventory.billofmaterials': (
        'id', 'name', 'template', 'design', 'version', 'is_active',
        'notes', 'created_by', 'created_at', 'updated_at',
    ),
    'inventory.bomline': (
        'id', 'bom', 'role', 'inventory_item', 'catalog_item',
        'description', 'quantity', 'quantity_formula', 'unit',
        'waste_percent', 'is_optional', 'is_customer_supplied',
        'sequence', 'notes',
    ),
    'inventory.catalogitem': (
        'id', 'section', 'name', 'item_type', 'default_unit',
        'legacy_category', 'is_active', 'created_at',
    ),
    'inventory.catalogsection': (
        'id', 'doc', 'sequence', 'name', 'subsection', 'created_at',
    ),
    'inventory.customermaterial': (
        'id', 'order', 'kind', 'name', 'description', 'unit',
        'received_quantity', 'used_quantity', 'returned_quantity',
        'damaged_quantity', 'received_at', 'notes',
    ),
    'inventory.customermaterialmovement': (
        'id', 'material', 'movement_type', 'quantity',
        'previous_remaining', 'new_remaining', 'user',
        'user_name_snapshot', 'remarks', 'created_at',
    ),
    'inventory.inventoryitem': (
        'id', 'item_code', 'name', 'category', 'sub_category',
        'catalog_item', 'brand', 'color', 'size', 'unit',
        'material_type', 'design_number', 'width', 'purchase_price',
        'selling_price', 'gst_percent', 'hsn_code', 'supplier',
        'current_stock', 'reserved_stock', 'minimum_stock',
        'maximum_stock', 'reorder_level', 'rack_location',
        'batch_number', 'purchase_date', 'status', 'created_at',
        'updated_at',
    ),
    'inventory.locationstock': (
        'id', 'item', 'location', 'quantity', 'updated_at',
    ),
    'inventory.ordermaterialline': (
        'id', 'plan', 'bom_line', 'garment_job', 'job_material', 'item',
        'role', 'material_name', 'unit', 'required_quantity',
        'reserved_quantity', 'consumed_quantity', 'wasted_quantity',
        'returned_quantity', 'is_customer_supplied', 'sequence',
    ),
    'inventory.ordermaterialplan': (
        'id', 'order', 'bom', 'bom_version', 'status', 'variables',
        'packaging_deducted_at', 'created_by', 'created_at',
        'updated_at',
    ),
    'inventory.purchaseorder': (
        'id', 'po_number', 'supplier', 'status', 'payment_status',
        'invoice_number', 'order_date', 'expected_date',
        'received_date', 'tax_amount', 'notes', 'created_at',
    ),
    'inventory.purchaseorderline': (
        'id', 'purchase_order', 'item', 'quantity_ordered',
        'quantity_received', 'unit_cost', 'batch_number',
    ),
    'inventory.stocklocation': (
        'id', 'name', 'kind', 'is_default', 'tailor', 'is_active',
        'sequence', 'created_at',
    ),
    'inventory.stockmovement': (
        'id', 'item', 'movement_type', 'quantity', 'previous_stock',
        'new_stock', 'previous_reserved', 'new_reserved', 'user',
        'user_name_snapshot', 'order', 'garment_job', 'stage_key',
        'from_location', 'to_location', 'performed_by', 'remarks',
        'created_at',
    ),
    'inventory.supplier': (
        'id', 'name', 'contact_person', 'phone', 'email', 'address',
        'gst_number', 'notes', 'is_active', 'created_at',
    ),
    'inventory.unitconversion': (
        'id', 'item', 'from_unit', 'to_unit', 'factor',
    ),
    'production.productiontask': (
        'id', 'order', 'title', 'description', 'stage_key',
        'assigned_to', 'status', 'priority', 'sequence',
        'estimated_hours', 'actual_hours', 'due_date', 'started_at',
        'completed_at', 'proof_images', 'notes', 'created_at',
        'updated_at',
    ),
    'production.qcrecord': (
        'id', 'order', 'task', 'inspector', 'status',
        'checklist_results', 'comments', 'proof_images', 'created_at',
    ),
    'scheduling.appointment': (
        'id', 'customer', 'order', 'appointment_type', 'status',
        'scheduled_time', 'assigned_staff', 'notes', 'reminder_sent',
        'created_at', 'updated_at',
    ),

}

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


def _is_redacted(field, model_key=None):
    """Whether this cell must be masked.

    Two independent reasons, and either is enough:

      * the field is not on its model's allowlist -- the primary rule, and the
        one that covers columns nobody has thought about yet;
      * the name looks like a credential -- the old denylist, kept underneath as
        a backstop against a careless addition to ALLOWED_FIELDS.

    `model_key` is optional so the denylist half stays callable on its own; when
    it is absent only the name rule applies, which is strictly the weaker of the
    two and is why every caller in this module passes it.
    """
    lowered = field.name.lower()
    if any(part in lowered for part in REDACTED_NAME_PARTS):
        return True
    if model_key is not None:
        return field.name not in ALLOWED_FIELDS.get(model_key, ())
    return False


def _model_key(model):
    meta = model._meta
    return f'{meta.app_label}.{meta.model_name}'


def visible_models():
    """Every model a platform administrator may inspect, in a stable order.

    The gate is ALLOWED_FIELDS, not TENANT_APPS. It used to be the other way
    round -- everything in a tenant schema, minus a short exclusion list -- which
    meant a model added to the product was published to the console the moment
    it migrated, with whatever columns it carried. That is the wrong default for
    a screen that reads every boutique's data: it publishes first and reviews
    afterwards, if anyone notices.

    TENANT_APPS is still checked, so an entry here cannot reach a SHARED_APPS
    model (the console's own audit trail among them) even by mistake.
    """
    tenant_labels = {a.rsplit('.', 1)[-1] for a in settings.TENANT_APPS}
    found = []
    for model in apps.get_models():
        meta = model._meta
        key = _model_key(model)
        if meta.app_label not in tenant_labels:
            continue
        if f'{meta.app_label}.{meta.object_name}' in EXCLUDED_MODELS:
            continue
        if meta.proxy:
            # A proxy is the same table under another name; listing both would
            # show every row twice under two headings.
            continue
        if key not in ALLOWED_FIELDS:
            # Not reviewed, so not browsable. See ALLOWED_FIELDS.
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
    key = _model_key(model)
    described = []
    for field in model._meta.concrete_fields:
        described.append({
            'name': field.name,
            'label': str(field.verbose_name) if hasattr(field, 'verbose_name') else field.name,
            'type': field.get_internal_type(),
            'redacted': _is_redacted(field, key),
        })
    return described


def _value(instance, field, model_key):
    """One cell, rendered as something JSON can carry.

    `model_key` is required rather than derived from `instance`: a masked cell
    must be decided by the same rule the header used, and a deferred or
    annotated instance is not a reliable place to ask which model it came from.
    """
    if _is_redacted(field, model_key):
        return REDACTED

    internal = field.get_internal_type()

    if field.is_relation:
        # The readable name of the related row, not its id. select_related in
        # rows() is what keeps this from being a query per cell.
        #
        # But __str__ composes whatever fields a model chose, and it answers to
        # no allowlist: crm_api.Customer.__str__ is 'Ann B (9000000999)', so the
        # ORDER table renders a customer's mobile number in its `customer`
        # column. Here that is tolerable only because mobile_number is itself
        # allowlisted on crm_api.customer -- and that is exactly the coincidence
        # not to depend on. A related model that is NOT browsable has had no
        # such review, so its __str__ is not shown at all.
        related = getattr(instance, field.name, None)
        if related is None:
            return None
        if _model_key(type(related)) not in ALLOWED_FIELDS:
            # Reachable through a relation but not approved for display. The
            # primary key still lets an administrator correlate rows without
            # putting an unreviewed string on the page.
            return f'{type(related)._meta.verbose_name} #{related.pk}'
        return str(related)

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
        # A masked column is not searchable either. Otherwise `?q=` becomes an
        # oracle: the rows come back filtered by a value the console refuses to
        # print, so an administrator could confirm a hidden field's contents one
        # guess at a time without ever being shown it.
        and not _is_redacted(f, _model_key(model))
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
    key = _model_key(model)
    page_rows = [
        {field.name: _value(instance, field, key) for field in fields}
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
