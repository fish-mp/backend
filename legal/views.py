from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from .catalog import catalog


class LegalDocumentsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        preview = settings.DEBUG and request.query_params.get('preview') == '1'
        try:
            data = catalog(preview=preview)
        except ImproperlyConfigured:
            return Response({'detail': 'Документы временно недоступны.'}, status=503)
        response = Response(data)
        response['Cache-Control'] = 'no-store'
        return response
