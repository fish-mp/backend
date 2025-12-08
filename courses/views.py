# courses/views.py
from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404

from courses.models import Course, Enrollment
from courses.serializers import CourseSerializer, UserEnrollmentSerializer


class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    queryset = Course.objects.all()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)
    
    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my(self, request):
        """
        Получить курсы текущего пользователя
        """
        # Получаем все enrollment текущего пользователя
        enrollments = Enrollment.objects.filter(user=request.user)
        
        # Сериализуем данные
        serializer = UserEnrollmentSerializer(
            enrollments, 
            many=True,
            context={'request': request}  # Передаем request в контекст
        )
        return Response(serializer.data)
    
    # Удалите старый MyCoursesView или оставьте для других целей


class EnrollmentViewSet(APIView):
    permission_classes = [IsAuthenticated]  

    def post(self, request, *args, **kwargs):
        user = request.user
        course_id = self.kwargs['pk']
        
        if course_id is None:
            return Response("Invalid JSON", status=400)
        
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return Response("Course not Found", status=404)
        
        try:
            # Проверяем, не подписан ли уже пользователь
            existing_enrollment = Enrollment.objects.filter(user=user, course=course).first()
            if existing_enrollment:
                return Response({"result": "Already enrolled", "state": existing_enrollment.state})
            
            Enrollment.objects.create(user=user, course=course)
            return Response({"result": "Applied"})
        except Exception as e:
            return Response(f"Server Exception: {str(e)}", status=500)
