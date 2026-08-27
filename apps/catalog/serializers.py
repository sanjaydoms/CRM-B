from rest_framework import serializers

from core.templates import SpecValidationError, validate_spec

from .models import (
    GarmentJob, GarmentTemplate, JobMaterial, TemplateField, TemplateFieldOption,
    TemplateSection,
)


class TemplateFieldOptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = TemplateFieldOption
        fields = ['value', 'label', 'sequence']


class TemplateFieldSerializer(serializers.ModelSerializer):
    options = serializers.SerializerMethodField()

    class Meta:
        model = TemplateField
        fields = [
            'key', 'label', 'field_type', 'unit', 'is_required', 'is_repeatable',
            'default', 'help_text', 'sequence', 'visible_when', 'validation',
            'inventory_category', 'options',
        ]

    def get_options(self, field):
        active = [o for o in field.options.all() if o.is_active]
        return TemplateFieldOptionSerializer(active, many=True).data


class TemplateSectionSerializer(serializers.ModelSerializer):
    fields = TemplateFieldSerializer(many=True, read_only=True)

    class Meta:
        model = TemplateSection
        fields = ['key', 'title', 'sequence', 'fields']


class GarmentTemplateSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = GarmentTemplate
        fields = ['id', 'key', 'name', 'version', 'sequence', 'description']


class GarmentTemplateSerializer(serializers.ModelSerializer):
    sections = TemplateSectionSerializer(many=True, read_only=True)

    class Meta:
        model = GarmentTemplate
        fields = ['id', 'key', 'name', 'version', 'sequence', 'description', 'sections']


class JobMaterialSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source='inventory_item.name', read_only=True)

    class Meta:
        model = JobMaterial
        fields = [
            'id', 'field_key', 'inventory_item', 'item_name', 'free_text',
            'quantity', 'unit', 'source', 'notes',
        ]

    def validate(self, attrs):
        source = attrs.get('source', JobMaterial.Source.STORE)
        item = attrs.get('inventory_item')
        if source == JobMaterial.Source.STORE and not item:
            raise serializers.ValidationError(
                {'inventory_item': 'Store material must reference an inventory item.'}
            )
        if source == JobMaterial.Source.CUSTOMER and item:
            raise serializers.ValidationError(
                {'inventory_item': 'Customer-supplied material does not come from stock.'}
            )
        return attrs


class GarmentJobSerializer(serializers.ModelSerializer):
    materials = JobMaterialSerializer(many=True, required=False)
    template_key = serializers.CharField(source='template.key', read_only=True)
    template_name = serializers.CharField(source='template.name', read_only=True)

    class Meta:
        model = GarmentJob
        fields = [
            'id', 'order', 'template', 'template_key', 'template_name',
            'template_version', 'spec', 'measurements', 'sequence', 'materials',
            'base_price', 'fabric_price', 'embroidery_price',
            'customization_price', 'tailoring_charges',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['template_version', 'created_at', 'updated_at']

    def validate(self, attrs):
        from domains.orders.pricing import JOB_COMPONENTS
        for field in JOB_COMPONENTS:
            value = attrs.get(field)
            if value is not None and value < 0:
                raise serializers.ValidationError({field: 'cannot be negative.'})

        template = attrs.get('template') or getattr(self.instance, 'template', None)
        if template is None:
            return attrs

        spec = attrs.get('spec', getattr(self.instance, 'spec', {}) or {})
        measurements = attrs.get(
            'measurements', getattr(self.instance, 'measurements', {}) or {}
        )
        combined = {**spec, **measurements}
        partial = bool(self.context.get('draft'))
        try:
            cleaned = validate_spec(template, combined, partial=partial)
        except SpecValidationError as exc:
            raise serializers.ValidationError(exc.errors)

        measurement_keys = {
            f.key
            for section in template.sections.all() if section.key == 'measurements'
            for f in section.fields.all()
        }
        attrs['measurements'] = {
            k: v for k, v in cleaned.items() if k in measurement_keys
        }
        attrs['spec'] = {k: v for k, v in cleaned.items() if k not in measurement_keys}
        return attrs

    def create(self, validated_data):
        materials = validated_data.pop('materials', [])
        job = super().create(validated_data)
        for line in materials:
            item = line.get('inventory_item')
            JobMaterial.objects.create(
                job=job,
                **{**line, 'unit': (item.unit if item else line.get('unit')) or ''},
            )
        return job
