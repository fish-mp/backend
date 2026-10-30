
from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from django.utils import timezone
from .models import Event, EventPhoto, Certificate
from .serializers import EventSerializer, EventPhotoSerializer, CertificateSerializer

class EventViewSet(viewsets.ModelViewSet):
    queryset = Event.objects.all()
    serializer_class = EventSerializer
    parser_classes = (MultiPartParser, FormParser)

    def get_permissions(self):
        """
        Переопределяем permissions в зависимости от действия:
        - GET запросы доступны всем
        - POST, PUT, DELETE только для админов
        """
        if self.action in ['create', 'update', 'partial_update', 'destroy', 'upload_photos', 'upload_certificate']:
            permission_classes = [IsAdminUser]
        else:
            permission_classes = []
        return [permission() for permission in permission_classes]

    def get_queryset(self):
        queryset = Event.objects.prefetch_related('photos', 'certificates').all()
        status = self.request.query_params.get('status', None)
        
        if status == 'upcoming':
            return queryset.filter(date__gt=timezone.now())
        elif status == 'finished':
            return queryset.filter(date__lte=timezone.now())
        
        return queryset

    @action(detail=True, methods=['post'])
    def upload_photos(self, request, pk=None):
        event = self.get_object()
        
        # Проверяем, завершилось ли мероприятие
        if event.date > timezone.now():
            return Response(
                {"error": "Нельзя загружать фотографии для предстоящего мероприятия"},
                status=status.HTTP_400_BAD_REQUEST
            )

        files = request.FILES.getlist('photos')
        if not files:
            return Response(
                {"error": "Не выбраны файлы для загрузки"},
                status=status.HTTP_400_BAD_REQUEST
            )

        photos = []
        for file in files:
            photo = EventPhoto.objects.create(
                event=event,
                image=file,
                description=request.data.get('description', '')
            )
            photos.append(photo)
        
        serializer = EventPhotoSerializer(photos, many=True)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def upload_certificate(self, request, pk=None):
        event = self.get_object()

        # Проверяем, завершилось ли мероприятие
        if event.date > timezone.now():
            return Response(
                {"error": "Нельзя загружать сертификаты для предстоящего мероприятия"},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CertificateSerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(event=event)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def calendar(self, request):
        """
        Возвращает список мероприятий для календаря
        """
        events = self.get_queryset()
        serializer = EventSerializer(events, many=True)
        return Response(serializer.data)
