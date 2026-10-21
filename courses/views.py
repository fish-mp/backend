from rest_framework.views import APIView
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django_filters.rest_framework import DjangoFilterBackend
from courses.models import Course, Enrollment, School, Teacher
from courses.serializers import (
    CourseSerializer, UserEnrollmentSerializer, SchoolSerializer,
    SchoolWithPopularCoursesSerializer, TeacherSerializer
)

class SchoolViewSet(viewsets.ReadOnlyModelViewSet):
    """Список всех активных разделов (Планет)"""
    queryset = School.objects.filter(is_active=True)
    serializer_class = SchoolSerializer
    permission_classes = [AllowAny]
    lookup_field = 'slug'

class TeacherViewSet(viewsets.ReadOnlyModelViewSet):
    """Список преподавателей"""
    queryset = Teacher.objects.select_related('school').all()
    serializer_class = TeacherSerializer
    permission_classes = [AllowAny]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['school', 'school__slug']

class LandingPageAPIView(APIView):
    """Единый эндпоинт для главной страницы (Космос)"""
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs):
        schools = School.objects.filter(is_active=True).prefetch_related('courses')
        teachers = Teacher.objects.select_related('school').all()

        return Response({
            "planets": SchoolWithPopularCoursesSerializer(
                schools, many=True, context={'request': request}
            ).data,
            "teachers": TeacherSerializer(
                teachers, many=True, context={'request': request}
            ).data,
        })

class CourseViewSet(viewsets.ModelViewSet):
    serializer_class = CourseSerializer
    queryset = Course.objects.select_related('school', 'tag').prefetch_related('modules').all()
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['school', 'school__slug', 'tag', 'is_popular', 'course_type']

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def my(self, request):
        enrollments = Enrollment.objects.filter(user=request.user).select_related('course')
        serializer = UserEnrollmentSerializer(
            enrollments, many=True, context={'request': request}
        )
        return Response(serializer.data)

class EnrollmentViewSet(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        user = request.user
        course_id = self.kwargs.get('pk')
        if course_id is None:
            return Response("Invalid JSON", status=400)
        try:
            course = Course.objects.get(pk=course_id)
        except Course.DoesNotExist:
            return Response("Course not Found", status=404)
        try:
            existing_enrollment = Enrollment.objects.filter(user=user, course=course).first()
            if existing_enrollment:
                return Response({"result": "Already enrolled", "state": existing_enrollment.state})
            Enrollment.objects.create(user=user, course=course)
            return Response({"result": "Enrolled"})
        except Exception as e:
            return Response(f"Server Exception: {str(e)}", status=500)