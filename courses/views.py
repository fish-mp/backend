from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated


from courses.models import Course, Enrollment
from courses.serializers import CourseSerializer, UserEnrollmentSerializer, EnrollmentCourseSerializer
from rest_framework import generics


# Create your views here.
class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    queryset = Course.objects.all()

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True, context={'request': request})

        return Response(serializer.data)    


class EnrollmentViewSet(APIView):

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
            Enrollment.objects.create(user=user, course=course)
            return Response({"result": "Applied"})
        except Exception:
            return Response("Server Exception")

class MyCoursesView(APIView):
    """View для получения курсов, на которые подписан пользователь"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, *args, **kwargs):
        # Получаем все enrollment текущего пользователя
        enrollments = Enrollment.objects.filter(user=request.user)
        
        # Можно вернуть два варианта:
        # Вариант 1: Вернуть список enrollment с деталями курсов
        serializer = UserEnrollmentSerializer(enrollments, many=True)
        return Response(serializer.data)
        
        # Или Вариант 2: Вернуть просто список курсов
        # courses = [enrollment.course for enrollment in enrollments]
        # serializer = CourseSerializer(courses, many=True, context={'request': request})
        # return Response(serializer.data)


class MyEnrolledCoursesView(generics.ListAPIView):
    """View для получения курсов пользователя с использованием generics"""
    serializer_class = CourseSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Получаем курсы, на которые подписан пользователь
        user_enrollments = Enrollment.objects.filter(user=self.request.user)
        course_ids = user_enrollments.values_list('course_id', flat=True)
        return Course.objects.filter(id__in=course_ids)
    
    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        
        # Добавляем информацию о состоянии enrollment
        data = serializer.data
        for course_data in data:
            enrollment = Enrollment.objects.filter(
                user=request.user, 
                course_id=course_data['id']
            ).first()
            if enrollment:
                course_data['enrollment_state'] = enrollment.state
            else:
                course_data['enrollment_state'] = None
        
        return Response(data)
