
from django.apps import apps
from django.conf import settings
from django.db.models import Q

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

EXCLUDED_MODELS = frozenset({
    'authtoken.Token',       # live credentials -- see the module docstring
    'authtoken.TokenProxy',  # the same rows under another name
    'contenttypes.ContentType',
    'auth.Permission',
    'auth.Group',
    'admin.LogEntry',
    'sessions.Session',
})

REDACTED_NAME_PARTS = ('password', 'secret', 'api_key', 'apikey', 'auth_token',
                       'access_token', 'refresh_token', 'private_key')

REDACTED = '••••••••'

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500


def _is_redacted(field, model_key=None):
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
            continue
        if key not in ALLOWED_FIELDS:
            continue
        found.append((key, model))
    found.sort(key=lambda pair: pair[0])
    return found


def get_model(key):
    for candidate, model in visible_models():
        if candidate == key:
            return model
    return None


def columns(model):
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
    if _is_redacted(field, model_key):
        return REDACTED

    internal = field.get_internal_type()

    if field.is_relation:
        related = getattr(instance, field.name, None)
        if related is None:
            return None
        if _model_key(type(related)) not in ALLOWED_FIELDS:
            return f'{type(related)._meta.verbose_name} #{related.pk}'
        return str(related)

    value = getattr(instance, field.name, None)
    if value is None:
        return None

    if internal in ('FileField', 'ImageField'):
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
    searchable = [
        f.name for f in model._meta.concrete_fields
        if f.get_internal_type() in ('CharField', 'TextField', 'EmailField', 'SlugField')
        and not _is_redacted(f, _model_key(model))
    ]
    if not searchable:
        return Q()
    query = Q()
    for name in searchable:
        query |= Q(**{f'{name}__icontains': term})
    return query


def rows(model, page=1, page_size=DEFAULT_PAGE_SIZE, search=''):
    page_size = max(1, min(int(page_size or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
    page = max(1, int(page or 1))

    queryset = model._default_manager.all()
    if search:
        queryset = queryset.filter(_search_filter(model, search))

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
    listed = []
    for key, model in visible_models():
        try:
            count = model._default_manager.count()
        except Exception:
            count = None
        listed.append({
            'key': key,
            'app': model._meta.app_label,
            'label': str(model._meta.verbose_name_plural).title(),
            'count': count,
        })
    return listed
