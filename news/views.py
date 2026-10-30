from rest_framework import viewsets
from rest_framework.parsers import MultiPartParser, FormParser
from .models import News, NewsPhoto
from .serializers import NewsSerializer, NewsPhotoSerializer

class NewsViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint для просмотра новостей.
    ReadOnlyModelViewSet предоставляет только операции 'list' и 'retrieve'.
    """
    queryset = News.objects.prefetch_related('photos').all()
    serializer_class = NewsSerializer
    parser_classes = (MultiPartParser, FormParser)
