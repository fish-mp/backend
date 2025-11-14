from django.http import HttpResponse
from django.shortcuts import render
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView


from courses.models import Course, Enrollment
from courses.serializers import CourseSerializer
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
