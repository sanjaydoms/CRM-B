from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from core.permissions import OwnerOnly
from .models import BoutiqueSettings


ALLOWED_INVOICE_TEMPLATES = {'classic', 'modern', 'elegant'}

TEMPLATE_OPTIONS = [
    {'code': 'classic', 'name': 'Classic'},
    {'code': 'modern', 'name': 'Modern'},
    {'code': 'elegant', 'name': 'Elegant'},
]


class InvoiceTemplateView(APIView):
    """
    API endpoint to retrieve and update the active boutique invoice template.
    Restricted to the Boutique Owner.
    """
    permission_classes = [OwnerOnly]

    def get(self, request):
        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        current_template = getattr(config, 'invoice_template', 'classic') or 'classic'
        if current_template not in ALLOWED_INVOICE_TEMPLATES:
            current_template = 'classic'

        return Response({
            'template': current_template,
            'templates': TEMPLATE_OPTIONS
        }, status=status.HTTP_200_OK)

    def patch(self, request):
        template_code = request.data.get('template')
        if not template_code or template_code not in ALLOWED_INVOICE_TEMPLATES:
            return Response(
                {'detail': 'Invalid invoice template.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        config, _ = BoutiqueSettings.objects.get_or_create(id=1)
        config.invoice_template = template_code
        config.save()

        return Response({
            'success': True,
            'template': template_code
        }, status=status.HTTP_200_OK)
