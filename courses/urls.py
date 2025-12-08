from django.urls import include, path
from rest_framework.routers import DefaultRouter

from courses.views import CourseViewSet, EnrollmentViewSet, MyCoursesView, MyEnrolledCoursesView

router = DefaultRouter()
router.register(r'', CourseViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('<int:pk>/enroll/', EnrollmentViewSet.as_view()),
    path('my-courses/', MyCoursesView.as_view(), name='my-courses'),
    path('my-enrolled-courses/', MyEnrolledCoursesView.as_view(), name='my-enrolled-courses'),
]
